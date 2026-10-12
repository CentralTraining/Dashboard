"""Read-only KPI reporting for the user's existing Supabase dashboard."""

import json
import math
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from tracker import VIETNAM


class KpiSourceError(Exception):
    pass


def number(value):
    try:
        n = float(value or 0)
        return max(0, n) if math.isfinite(n) else 0
    except (ValueError, TypeError):
        return 0


def jsround(value):
    return math.floor(value + .5)


def normalize(value):
    text = unicodedata.normalize('NFD', str(value or '').replace('đ', 'd').replace('Đ', 'D'))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', ' ', text.upper()).strip()


def name_key(value):
    # Match the dashboard's normTrName_: preserve accents, normalize Unicode.
    return unicodedata.normalize('NFC', str(value or '').strip().upper())


def date_vietnam(value):
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return d.replace(tzinfo=VIETNAM) if d.tzinfo is None else d.astimezone(VIETNAM)
    except (ValueError, TypeError):
        return None


def metric(key, label, actual, target, **extra):
    a, t = number(actual), number(target)
    return {'key': key, 'label': label, 'actual': a, 'target': t,
            'pct': jsround(a / t * 1000) / 10 if t > 0 else None,
            'remaining': max(0, t - a) if t > 0 else None, **extra}


def average(metrics):
    values = [min(100, m['pct']) for m in metrics if m['pct'] is not None]
    return jsround(sum(values) / len(values)) if values else None


def campaign_subtype(c):
    return c.get('subtype') or {'noibo': 'pgsdev', 'doitac': 'ftf', 'truyenthong': 'noibo'}.get(c.get('group'))


def channel_group(value):
    k = normalize(value).replace(' ', '')
    if k in ('TGDD', 'DMX', 'MWG', 'TGDDDMX', 'DMXTGDD') or 'THEGIOIDIDONG' in k or 'DIENMAYXANH' in k:
        return 'MWG'
    if k in ('FPT', 'VIETTEL', 'CELLPHONE', 'CELLPHONES', 'CPS') or any(s in k for s in ('CHOLON', 'HOANGHA', 'CELLPHONE')):
        return 'K.A'
    return 'IND'


def required_keys(month, campaigns):
    keys = ['config', 'campaigns', f'records:{month}', f'pgs:{month}',
            f'surveyResponses:{month}', f'surveyResponsesNew:{month}', f'ftfShopList:{month}',
            'onoffRoster', 'pendingTargetAdjustments', 'shopTrainerMap', 'partnerList']
    for c in campaigns:
        if c.get('month') != month:
            continue
        cid = c['id']
        if c.get('group') == 'truyenthong':
            prefix = 'mediaDoitacEmps:' if campaign_subtype(c) == 'doitac' else 'mediaResponses:'
            keys.extend([f'mediaTargets:{cid}', prefix + cid])
        if c.get('group') == 'doitac' and campaign_subtype(c) == 'workshop':
            keys.extend([f'partnerTrainingTargets:{cid}', f'partnerTrainingActuals:{cid}', f'wsDoitacParticipants:{cid}'])
    return list(dict.fromkeys(keys))


class SupabaseKpiSource:
    def __init__(self, config):
        self.config = config
        parsed = urlparse(config['url'])
        if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.supabase.co'):
            raise KpiSourceError('invalid_source_host')
        if not re.fullmatch(r'[A-Za-z0-9_]+', config['table']):
            raise KpiSourceError('invalid_source_table')

    def read(self, keys):
        if any(k.startswith('auth_') for k in keys):
            raise KpiSourceError('account_data_excluded')
        try:
            response = requests.get(f"{self.config['url']}/rest/v1/{self.config['table']}",
                params={'select': 'key,value,updated_at',
                        'key': 'in.(' + ','.join(json.dumps(k) for k in keys) + ')'},
                headers={'apikey': self.config['anon_key'], 'Authorization': 'Bearer ' + self.config['anon_key']},
                timeout=30, allow_redirects=False)
            if not response.ok:
                raise KpiSourceError(f'source_http_{response.status_code}')
            rows = response.json()
            if not isinstance(rows, list):
                raise KpiSourceError('invalid_source_response')
            return rows
        except requests.RequestException:
            raise KpiSourceError('source_connection_failed') from None
        except ValueError:
            raise KpiSourceError('invalid_source_json') from None

    def snapshot(self, month):
        base = self.read(['config', 'campaigns'])
        data = {r['key']: r['value'] for r in base}
        if not isinstance(data.get('config'), dict) or not isinstance(data.get('campaigns'), list):
            raise KpiSourceError('missing_dashboard_configuration')
        rows = self.read(required_keys(month, data['campaigns']))
        return KpiSnapshot(rows, month)


class KpiSnapshot:
    def __init__(self, rows, month):
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
            raise KpiSourceError('invalid_report_month')
        self.month = month
        self.data = {r['key']: r['value'] for r in rows}
        self.updated = {r['key']: r.get('updated_at') for r in rows}
        if not isinstance(self.data.get('config'), dict) or f'records:{month}' not in self.data:
            raise KpiSourceError('missing_month_data')
        self.trainers = self.data['config'].get('trainers', [])
        self.campaigns = [c for c in self.data.get('campaigns', []) if c.get('month') == month]
        self.records = self.data.get(f'records:{month}') or {}

    def list_value(self, key):
        value = self.data.get(key)
        return value if isinstance(value, list) else []

    def dict_value(self, key):
        value = self.data.get(key)
        return value if isinstance(value, dict) else {}

    def coaching(self, trainer):
        tid = trainer['id']; rec = self.records.get(tid, {})
        month = self.month
        if not any(c.get('group') == 'noibo' and campaign_subtype(c) == 'pgsdev' for c in self.campaigns):
            return []
        necessary = ['onoffRoster', f'pgs:{month}', f'surveyResponses:{month}', f'surveyResponsesNew:{month}']
        if any(k not in self.data for k in necessary):
            raise KpiSourceError('missing_coaching_source')
        roster = self.list_value('onoffRoster'); pgs = self.list_value(f'pgs:{month}')
        pgs_by_code = {str(p.get('code')): p for p in reversed(pgs) if p.get('code')}
        def in_month(r):
            d = date_vietnam(r.get('joinedAt'))
            return r.get('trainerId') == tid and d is not None and d.strftime('%Y-%m') == month and d.day < 25
        valid = [r for r in roster if in_month(r) and r.get('status') == 'On']
        codes = {str(r['code']).strip() for r in valid if r.get('code')}
        names = {name_key(r.get('name')) for r in valid if r.get('name')}
        actual_new = sum(1 for r in self.list_value(f'surveyResponsesNew:{month}') if r.get('trainerId') == tid
                         and (str(r.get('code') or '').strip() in codes if str(r.get('code') or '').strip()
                              else name_key(r.get('pgName')) in names))
        pending = any(p.get('trainerId') == tid and p.get('month') == month for p in self.list_value('pendingTargetAdjustments'))
        def status(r):
            if str(r.get('devStatusNote') or '').strip(): return r['devStatusNote']
            p = pgs_by_code.get(str(r.get('code'))) if r.get('code') else None
            return p.get('status') if p else 'Đang làm'
        target_new = rec.get('pgMoiTarget', 0) if pending else sum(1 for r in roster if in_month(r) and status(r) == 'Đang làm') * 2
        actual_01 = sum(1 for r in self.list_value(f'surveyResponses:{month}') if r.get('trainerId') == tid)
        return [metric('pgMoi', 'PGs mới', actual_new, target_new, unit='lượt coaching'),
                metric('pg01', 'PGs 0★/1★', actual_01, rec.get('pg01Target', 0), unit='lượt coaching')]

    def ftf(self, trainer):
        if not any(c.get('group') == 'doitac' and campaign_subtype(c) == 'ftf' for c in self.campaigns): return []
        tid = trainer['id']; rec = self.records.get(tid, {})
        key = f'ftfShopList:{self.month}'
        if key not in self.data: raise KpiSourceError('missing_ftf_source')
        shops = [s for s in self.list_value(key) if s.get('trainerId') == tid]
        definitions = [('ftfShop', 'Shop', None), ('ftfHr', 'Học viên', 'hrActual'),
                       ('ftfBaiTest', 'Pass test', 'testPass'), ('ftfTuVanAI', 'Tư vấn AI', 'aiDone'),
                       ('ftfKhaoSat', 'Khảo sát', 'surveyDone')]
        result = []
        for channel, suffix in [('MWG', 'MWG'), ('K.A', 'KA')]:
            subset = [s for s in shops if channel_group(s.get('channel')) == channel]
            actual_hr = sum(number(s.get('hrActual')) for s in subset)
            for mk, label, afield in definitions:
                a = sum(s.get('status') == 'DONE' for s in subset) if afield is None else sum(number(s.get(afield)) for s in subset)
                if mk == 'ftfKhaoSat': t = actual_hr
                elif mk + 'Target_' + suffix in rec: t = rec[mk + 'Target_' + suffix]
                elif mk == 'ftfShop': t = len(subset)
                elif mk == 'ftfHr': t = sum(number(s.get('hrTarget')) for s in subset)
                elif mk == 'ftfBaiTest': t = sum(number(s.get('testTotal')) for s in subset)
                else: t = 0
                result.append(metric(mk + ':' + channel, f'FTF {channel} — {label}', a, t, channel=channel))
        return result

    def workshop(self, trainer):
        result = []
        def find_region(mapping):
            return next((v for k, v in mapping.items() if normalize(k) == normalize(trainer.get('region'))), {})
        for c in self.campaigns:
            if c.get('group') != 'doitac' or campaign_subtype(c) != 'workshop': continue
            cid = c['id']; tk = 'partnerTrainingTargets:' + cid; ak = 'partnerTrainingActuals:' + cid
            if tk not in self.data or ak not in self.data: raise KpiSourceError('missing_workshop_source')
            t = find_region(self.dict_value(tk)); a = find_region(self.dict_value(ak))
            base = {'shared_region': trainer.get('region'), 'campaign_id': cid, 'campaign_name': c['name']}
            result.extend([metric('ws:buoi:' + cid, 'WS đối tác — Số buổi', a.get('sessions'), t.get('sessions'), **base),
                           metric('ws:hv:' + cid, 'WS đối tác — Học viên', a.get('students'), t.get('students'), **base)])
            pk = 'wsDoitacParticipants:' + cid
            if pk in self.data:
                done = sum(1 for p in self.list_value(pk)
                    if normalize(p.get('Khu vực') or p.get('Khu Vực')) == normalize(trainer.get('region'))
                    and str(p.get('Khảo sát') or p.get('Khao sat') or '').strip().lower() in ('đã làm', 'da lam', 'done', 'hoàn thành'))
                result.append(metric('ws:ks:' + cid, 'WS đối tác — Khảo sát', done, jsround(number(a.get('students')) * .8), **base))
        return result

    def media(self, trainer):
        tid = trainer['id']; rec = self.records.get(tid, {}); result = []
        shopkey = lambda s: normalize(s).replace(' ', '')
        shops = {shopkey(s.get('shopName') or s.get('shopId')) for s in self.list_value('shopTrainerMap') if s.get('trainerId') == tid}
        partners = {str(p.get('code')).strip(): p for p in self.list_value('partnerList') if p.get('code')}
        for c in self.campaigns:
            if c.get('group') != 'truyenthong': continue
            cid = c['id']; subtype = campaign_subtype(c); targets = self.dict_value('mediaTargets:' + cid)
            if subtype == 'doitac':
                necessary = ['shopTrainerMap', 'partnerList', 'mediaDoitacEmps:' + cid, 'mediaTargets:' + cid]
                if any(k not in self.data for k in necessary): raise KpiSourceError('missing_partner_media_source')
                actual = 0
                for e in self.list_value('mediaDoitacEmps:' + cid):
                    if number(e.get('approved')) < 1: continue
                    p = partners.get(str(e.get('code') or '').strip())
                    if p and shopkey(p.get('shop')) in shops: actual += number(e.get('approved'))
                target = targets.get(tid, 0)
                label = 'Đối tác'
            else:
                if 'mediaResponses:' + cid not in self.data: raise KpiSourceError('missing_internal_media_source')
                actual = sum(1 for r in self.list_value('mediaResponses:' + cid) if r.get('trainerId') == tid)
                target = targets[tid] if tid in targets else rec.get('ttTarget', 0)
                label = 'Nội bộ'
            result.append(metric('tt:' + cid, f'{label} — {c["name"]}', actual, target, subtype=subtype, campaign_id=cid))
        return result

    def trainer_report(self, trainer):
        ftf = self.ftf(trainer)
        workshop = self.workshop(trainer)
        groups = {'noibo': self.coaching(trainer), 'doitac': ftf + workshop, 'truyenthong': self.media(trainer)}
        return {'trainer_id': trainer['id'], 'name': trainer['name'], 'region': trainer.get('region'),
                'month': self.month, 'groups': groups,
                'percentages': {'noibo': average(groups['noibo']), 'doitac': average(ftf), 'truyenthong': average(groups['truyenthong'])},
                'workshop_percentage': average(workshop)}

    def reports(self):
        return [self.trainer_report(t) for t in self.trainers]


def shown(value):
    return f'{value:g}' if isinstance(value, (float, int)) else str(value)


def format_trainer_report(report, dashboard_url):
    month = report['month'].split('-')
    lines = [f"📊 KPI tháng {int(month[1])}/{month[0]} — {report['name']}"]
    labels = [('noibo', 'Nội bộ — Coaching PGs Dev'), ('doitac', 'Đối tác'), ('truyenthong', 'Truyền thông')]
    for i, (key, label) in enumerate(labels, 1):
        p = report['percentages'][key]
        lines.append(f"\n{i}. {label}" + (f' ({p}%)' if p is not None and key != 'doitac' else ''))
        if key == 'doitac' and p is not None:
            lines.append(f'FTF: {p}%')
        metrics = report['groups'][key]
        if not metrics: lines.append('Chưa có chiến dịch trong tháng.'); continue
        region_noted = False
        for m in metrics:
            if m.get('shared_region') and not region_noted:
                ws = report.get('workshop_percentage')
                lines.append(f"WS dùng chung theo khu vực {m['shared_region']}" + (f' ({ws}%)' if ws is not None else '') + ':'); region_noted = True
            text = f"• {m['label']}: {shown(m['actual'])}/{shown(m['target'])}"
            if m['pct'] is None: text += ' — chưa có target'
            else:
                text += f" ({shown(m['pct'])}%)"
                text += f" — còn {shown(m['remaining'])}" if m['remaining'] > 0 else ' — đã đạt'
            lines.append(text)
    lines.extend(['', 'Xem chi tiết: ' + dashboard_url])
    return '\n'.join(lines)


def format_team_report(reports, dashboard_url):
    month = reports[0]['month'] if reports else ''
    lines = [f'📊 Tiến độ KPI Team — {month}', 'Coaching | FTF / WS khu vực | Truyền thông']
    def priority(r):
        values = [p for p in r['percentages'].values() if p is not None]
        return sum(values) / len(values) if values else 101
    for i, r in enumerate(sorted(reports, key=priority), 1):
        values = [str(r['percentages'][k]) + '%' if r['percentages'][k] is not None else 'chưa có target'
                  for k in ('noibo', 'doitac', 'truyenthong')]
        ws = r.get('workshop_percentage')
        values[1] += ' / ' + (str(ws) + '%' if ws is not None else 'chưa có target')
        lines.append(f"{i}. {r['name']}: {' | '.join(values)}")
    lines.extend(['WS đối tác tính theo khu vực, dùng chung cho Trainer cùng khu vực.', 'Xem chi tiết: ' + dashboard_url])
    return '\n'.join(lines)
