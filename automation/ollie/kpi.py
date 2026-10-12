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
    raw = c.get('subtype') or {'noibo': 'pgsdev', 'doitac': 'ftf', 'truyenthong': 'noibo'}.get(c.get('group'))
    return 'tuvanai_checkshop' if c.get('group') == 'noibo' and raw in ('tuvanai', 'checkshop') else raw


def campaign_fields(c):
    return {'campaign_id': c['id'], 'campaign_name': c['name'], 'subtype': campaign_subtype(c)}


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
        if c.get('group') == 'noibo' and campaign_subtype(c) == 'workshop':
            keys.extend([f'workshopTargetRows:{cid}', f'workshopActualRows:{cid}'])
        if c.get('group') == 'noibo' and campaign_subtype(c) in ('testonline', 'tuvanai_checkshop'):
            keys.append(('frequencyProgress:' if campaign_subtype(c) == 'testonline' else 'aiCheckProgress:') + cid)
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
        campaigns = [c for c in self.campaigns if c.get('group') == 'noibo' and campaign_subtype(c) == 'pgsdev']
        if not campaigns:
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
        base = campaign_fields(campaigns[0])
        return [metric('pgMoi', 'PGs mới', actual_new, target_new, unit='lượt', **base),
                metric('pg01', 'PGs 0★/1★', actual_01, rec.get('pg01Target', 0), unit='lượt', **base)]

    def internal_other(self, trainer):
        """Include assigned internal campaigns outside Coaching, using their scope."""
        result = []; tid = trainer['id']; rec = self.records.get(tid, {})
        for c in self.campaigns:
            if c.get('group') != 'noibo': continue
            subtype = campaign_subtype(c); cid = c['id']; base = campaign_fields(c)
            if subtype == 'workshop':
                tk, ak = 'workshopTargetRows:' + cid, 'workshopActualRows:' + cid
                targets = [r for r in self.list_value(tk) if r.get('trainerId') == tid]
                actuals = [r for r in self.list_value(ak) if r.get('trainerId') == tid
                           and (r.get('done') is True or normalize(r.get('status')) in ('DONE', 'HOAN THANH', 'COMPLETED', 'COMPLETE'))]
                scoped = tk in self.data
                target_sessions = len(targets) if scoped else rec.get('wsNbBuoiTarget', 0)
                target_students = sum(number(r.get('expectedStudents')) for r in targets) if scoped else rec.get('wsNbHocVienTarget', 0)
                actual_sessions = len(actuals) if ak in self.data else rec.get('wsNbBuoiActual', 0)
                actual_students = sum(number(r.get('actualStudents')) for r in actuals) if ak in self.data else rec.get('wsNbHocVienActual', 0)
                result.extend([metric('wsnb:buoi:' + cid, 'WS nội bộ — Số buổi', actual_sessions, target_sessions, unit='buổi', **base),
                               metric('wsnb:hv:' + cid, 'WS nội bộ — Học viên', actual_students, target_students, unit='HV', **base)])
            elif subtype in ('testonline', 'tuvanai_checkshop'):
                active = [p for p in self.list_value('pgs:' + self.month)
                          if p.get('trainerId') == tid and p.get('brand') == 'OPPO' and p.get('status') == 'Đang làm']
                x = max(1, jsround(number(c.get('frequencyX')) or 1))
                pg_key = lambda p: str(p.get('code') or p.get('id') or '').strip().upper()
                if subtype == 'testonline':
                    values = self.dict_value('frequencyProgress:' + cid)
                    actual = sum(number(values.get(pg_key(p))) >= x for p in active)
                    result.append(metric('test:' + cid, 'Test Online', actual, len(active), unit='PG', **base))
                else:
                    values = self.dict_value('aiCheckProgress:' + cid)
                    ai = sum(number((values.get(pg_key(p)) or {}).get('aiCount')) >= x for p in active)
                    check = sum(bool((values.get(pg_key(p)) or {}).get('checkPass')) for p in active)
                    result.extend([metric('ai:' + cid, 'Tư vấn AI', ai, len(active), unit='PG', **base),
                                   metric('check:' + cid, 'Check shop', check, len(active), unit='PG', **base)])
        return result

    def ftf(self, trainer):
        campaigns = [c for c in self.campaigns if c.get('group') == 'doitac' and campaign_subtype(c) == 'ftf']
        if not campaigns: return []
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
                result.append(metric(mk + ':' + channel, f'FTF {channel} — {label}', a, t, channel=channel,
                                     unit='shop' if mk == 'ftfShop' else 'HV' if mk == 'ftfHr' else 'lượt', **campaign_fields(campaigns[0])))
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
            base = {'shared_region': trainer.get('region'), **campaign_fields(c)}
            result.extend([metric('ws:buoi:' + cid, 'WS đối tác — Số buổi', a.get('sessions'), t.get('sessions'), unit='buổi', **base),
                           metric('ws:hv:' + cid, 'WS đối tác — Học viên', a.get('students'), t.get('students'), unit='HV', **base)])
            pk = 'wsDoitacParticipants:' + cid
            if pk in self.data:
                done = sum(1 for p in self.list_value(pk)
                    if normalize(p.get('Khu vực') or p.get('Khu Vực')) == normalize(trainer.get('region'))
                    and str(p.get('Khảo sát') or p.get('Khao sat') or '').strip().lower() in ('đã làm', 'da lam', 'done', 'hoàn thành'))
                result.append(metric('ws:ks:' + cid, 'WS đối tác — Khảo sát', done, jsround(number(a.get('students')) * .8), unit='lượt', **base))
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
            result.append(metric('tt:' + cid, f'{label} — {c["name"]}', actual, target, unit='bài', **campaign_fields(c)))
        return result

    def trainer_report(self, trainer):
        ftf = self.ftf(trainer)
        workshop = self.workshop(trainer)
        groups = {'noibo': self.coaching(trainer) + self.internal_other(trainer), 'doitac': ftf + workshop, 'truyenthong': self.media(trainer)}
        return {'trainer_id': trainer['id'], 'name': trainer['name'], 'region': trainer.get('region'),
                'month': self.month, 'groups': groups,
                'percentages': {key: average(metrics) for key, metrics in groups.items()},
                'ftf_percentage': average(ftf),
                'workshop_percentage': average(workshop)}

    def reports(self):
        return [self.trainer_report(t) for t in self.trainers]


def shown(value):
    if isinstance(value, (float, int)):
        return str(int(value)) if float(value).is_integer() else f'{value:.1f}'
    return str(value)


def short_name(name):
    words = unicodedata.normalize('NFC', str(name)).strip().split()
    return words[-1].title() if words else 'Trainer'


def fit_label(value, limit=18):
    text = re.sub(r'\s+', ' ', str(value)).strip()
    if len(text) <= limit: return text
    prefix = text[:limit - 1]
    if ' ' in prefix: prefix = prefix.rsplit(' ', 1)[0]
    return prefix.rstrip() + '…'


def campaign_label(m):
    name = m.get('campaign_name') or m['label']
    simple = normalize(name)
    model = re.search(r'(?i)(?:Find\s*)?X\s*\d+|A\s*\d+\s*(?:Pro|s)?', name)
    model = re.sub(r'\s+', '', model.group(0)) if model else ''
    model = re.sub(r'(?i)^Find', '', model)
    model = re.sub(r'(?i)(A\d+)pro', r'\1 Pro', model)
    model = model[:1].upper() + model[1:] if model else ''
    if 'UNBOX' in simple: return ('Unbox ' + model).strip()
    if 'TIKTOK' in simple: return ('TikTok ' + model).strip()
    if m.get('subtype') == 'workshop': return ('WS ' + model).strip()
    if m.get('subtype') == 'ftf': return ('FTF ' + model).strip()
    if m.get('subtype') == 'testonline': return ('Test ' + model).strip()
    name = re.sub(r'\([^)]*\)', '', name)
    name = re.sub(r'(?i)\b(?:video|challenge|truyền thông)\b', '', name)
    return fit_label(name)


def metric_label(m):
    key = m['key']
    if key == 'pgMoi': return 'PG mới'
    if key == 'pg01': return 'PG 0★/1★'
    if key.startswith('ftf'):
        labels = {'ftfShop': 'shop', 'ftfHr': 'HV', 'ftfBaiTest': 'test', 'ftfTuVanAI': 'AI', 'ftfKhaoSat': 'KS'}
        return fit_label(f"{campaign_label(m)} {m['channel']} {labels[key.split(':')[0]]}")
    if key.startswith(('ws:', 'wsnb:')):
        kind = key.split(':')[1]; unit = {'buoi': 'buổi', 'hv': 'HV', 'ks': 'KS'}[kind]
        return fit_label(f'{campaign_label(m)} {unit}') + ('*' if m.get('shared_region') else '')
    if key.startswith('tt:'):
        suffix = 'ĐT' if m.get('subtype') == 'doitac' else 'NB'
        base = re.sub(r'(?i)\s+(NB|ĐT)$', '', campaign_label(m))
        return fit_label(base, 15) + ' ' + suffix
    if key.startswith('ai:'): return 'Tư vấn AI'
    if key.startswith('check:'): return 'Check shop'
    return fit_label(campaign_label(m))


def numeric_cluster(m):
    # Nonbreaking spaces bind the count and percentage together. Word joiners
    # protect slash/percent boundaries in mobile clients without manual wraps.
    return f"{shown(m['actual'])}\u2060/\u2060{shown(m['target'])}\u00a0·\u00a0{shown(m['pct'])}\u2060%"


def percent_cluster(value):
    return '—' if value is None else shown(value) + '\u2060%'


def assigned_metrics(report, group):
    return [m for m in report['groups'][group] if m['target'] > 0 and m['pct'] is not None]


def focus_metrics(report):
    # Select one unfinished metric in each category. Lowest progress first;
    # remaining work breaks ties without changing the KPI percentage itself.
    result = []
    for group in ('noibo', 'doitac', 'truyenthong'):
        pending = [m for m in assigned_metrics(report, group) if m['pct'] < 100]
        if pending: result.append(min(pending, key=lambda m: (m['pct'], -m['remaining'])))
    return result


def focus_label(m):
    if m['key'].startswith('ftf'):
        unit = {'ftfShop': 'shop', 'ftfHr': 'HV', 'ftfBaiTest': 'test', 'ftfTuVanAI': 'AI', 'ftfKhaoSat': 'KS'}[m['key'].split(':')[0]]
        return f'{campaign_label(m)} {unit}'
    if m['key'].startswith(('ws:', 'wsnb:')):
        unit = {'buoi': 'buổi', 'hv': 'HV', 'ks': 'KS'}[m['key'].split(':')[1]]
        scope = 'ĐT vùng' if m.get('shared_region') else 'NB'
        return f'WS {scope} {unit}'
    return metric_label(m)


def format_trainer_report(report, dashboard_url):
    month = report['month'].split('-')
    lines = [f"📊 KPI {int(month[1])}/{month[0]} · {short_name(report['name'])}"]
    labels = [('noibo', '🏫 Nội bộ'), ('doitac', '🤝 Đối tác'), ('truyenthong', '📣 Truyền thông')]
    for key, label in labels:
        lines.extend(['', label])
        metrics = assigned_metrics(report, key)
        lines.extend(f'• {metric_label(m)}: {numeric_cluster(m)}' for m in metrics)
        if not metrics: lines.append('• Chưa có target')
    focus = focus_metrics(report)
    lines.extend(['', '🎯 Cần tập trung'])
    if focus:
        for m in focus:
            remaining = shown(m['remaining']) + '\u00a0' + m.get('unit', 'lượt')
            lines.append(f'• {focus_label(m)}: còn {remaining}')
    else: lines.append('Đã đạt các target được giao.' if any(assigned_metrics(report, k) for k, _ in labels) else 'Chưa có target được giao.')
    if any(m.get('shared_region') for k, _ in labels for m in assigned_metrics(report, k)):
        lines.append('* WS đối tác dùng số liệu khu vực.')
    lines.extend(['', '🔗 Chi tiết dashboard', dashboard_url])
    return '\n'.join(lines)


def format_team_report(reports, dashboard_url):
    month = reports[0]['month'].split('-') if reports else ['', '']
    lines = [f'📊 KPI Team · {int(month[1])}/{month[0]}' if reports else '📊 KPI Team',
             '🏫 NB: Nội bộ · 🤝 ĐT: Đối tác', '📣 TT: Truyền thông', '']
    def priority(r):
        values = [p for p in r['percentages'].values() if p is not None]
        return sum(values) / len(values) if values else 101
    for i, r in enumerate(sorted(reports, key=priority), 1):
        values = [alias + '\u00a0' + percent_cluster(r['percentages'][key])
                  for alias, key in [('NB', 'noibo'), ('ĐT', 'doitac'), ('TT', 'truyenthong')]]
        lines.append(f"{short_name(r['name'])}: {' | '.join(values)}")
    focus_groups = {}
    for r in reports:
        labels = tuple(focus_label(m) for m in focus_metrics(r))
        if labels: focus_groups.setdefault(labels, []).append(short_name(r['name']))
    lines.extend(['', '🎯 Cần tập trung'])
    if not focus_groups:
        has_targets = any(assigned_metrics(r, k) for r in reports for k in ('noibo', 'doitac', 'truyenthong'))
        lines.append('Các target được giao đã đạt.' if has_targets else 'Chưa có target được giao.')
    for labels, names in focus_groups.items():
        audience = f'Cả {len(reports)} Trainer' if len(names) == len(reports) else ', '.join(names)
        lines.append(f"• {audience}: {'; '.join(labels)}")
    if any(m.get('shared_region') for r in reports for m in assigned_metrics(r, 'doitac')):
        lines.append('ĐT gồm FTF cá nhân và WS khu vực.')
    lines.extend(['', '🔗 Chi tiết dashboard', dashboard_url])
    return '\n'.join(lines)
