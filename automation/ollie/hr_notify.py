"""Only notify the configured leader privately after verified HR commits.

The server queues success transactionally, releases it at 08:00 Vietnam the
following day, and keeps a provider receipt. Unknown sends are not retried.
"""
import argparse
import base64
from datetime import datetime
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from tracker import DingTalkSender, DeliveryError

BASE = 'https://qruxqlsbhyhwiqjdkyyc.supabase.co'
ENDPOINT = BASE + '/functions/v1/ollie-hr-notify'
VN = ZoneInfo('Asia/Ho_Chi_Minh')
UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

class NoticeError(Exception):
    pass


def configuration(raw):
    try:
        config = json.loads(raw)
        c, s, source = config['credentials'], config['state'], config['source']
        if (source['url'].rstrip('/') != BASE or not c['appKey'] or not c['appSecret']
                or c['appKey'] != s['robot_code'] or not isinstance(s['leader_staff_id'], str)
                or not s['leader_staff_id'].strip()):
            raise ValueError()
        return config
    except (ValueError, TypeError, KeyError):
        raise NoticeError('notice_configuration_invalid') from None


def gateway_key(config):
    values = [config['source'].get('anon_key', '')]
    path = Path(__file__).resolve().parents[2] / 'index.html'
    if path.is_file():
        values += re.findall(r"const OTRAINING_ANON_KEY_\s*=\s*'([^']+)'", path.read_text())
    for token in values:
        try:
            part = token.split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
            if claims.get('role') == 'anon' and claims.get('ref') == 'qruxqlsbhyhwiqjdkyyc':
                return token
        except (ValueError, TypeError, IndexError):
            pass
    raise NoticeError('notice_public_gateway_key_missing')


def oidc_token():
    address = os.environ.get('ACTIONS_ID_TOKEN_REQUEST_URL', '')
    secret = os.environ.get('ACTIONS_ID_TOKEN_REQUEST_TOKEN', '')
    u = urlparse(address)
    if (u.scheme != 'https' or not (u.hostname or '').endswith('.actions.githubusercontent.com')
            or u.username or u.password or u.port or not secret):
        raise NoticeError('notice_oidc_required')
    try:
        r = requests.get(address, params={'audience': ENDPOINT},
                         headers={'Authorization': 'Bearer ' + secret}, timeout=20, allow_redirects=False)
        value = r.json()
        if not r.ok or not isinstance(value.get('value'), str):
            raise ValueError()
        return value['value']
    except (ValueError, requests.RequestException):
        raise NoticeError('notice_oidc_unavailable') from None


class NoticeApi:
    def __init__(self, config):
        self.key = gateway_key(config)
        self.token = oidc_token()

    def call(self, action, **extra):
        try:
            r = requests.post(ENDPOINT, json={'action': action, 'reportToken': self.token, **extra},
                              headers={'apikey': self.key, 'Authorization': 'Bearer ' + self.key},
                              timeout=25, allow_redirects=False)
            data = r.json()
            if not r.ok or data.get('ok') is not True or data.get('environment') != 'main':
                raise ValueError()
            return data
        except (ValueError, requests.RequestException):
            raise NoticeError('notice_state_unconfirmed') from None


def sync_result(notice):
    """Only render status facts supplied by the server's verified run proof."""
    if notice['kind'] == 'hr_data_updated' and notice['version'] == 1:
        return ('Đã cập nhật Data HR mới thành công!',
                'Đã đồng bộ Gán shop PGs, Sao PGs, ON và OFF vào Dashboard chính.')
    if notice['kind'] != 'hr_data_sync_report' or notice['version'] != 2:
        raise ValueError()
    status, core, history = notice['runStatus'], notice['coreVerified'], notice['historyVerified']
    if type(core) is not bool or type(history) is not bool:
        raise ValueError()
    expected = ['assign', 'stars', 'on', 'off'] if core else []
    if history:
        expected += ['promotions']
    if notice['verifiedSources'] != expected:
        raise ValueError()
    count = notice['historyRecords']
    if history and (not core or type(count) is not int or not 1 <= count <= 60000):
        raise ValueError()
    if not history and count is not None:
        raise ValueError()
    if status == 'succeeded' and core:
        if history:
            return ('Đã cập nhật Data HR mới thành công!',
                    'Đã đồng bộ đủ 5 tab: DS GÁN SHOP PGS, SAO PGS, ON, OFF và LÊN SAO.\n'
                    'Data nhân sự và nguồn lộ trình lên sao đã được xác nhận cập nhật.')
        return ('Data HR đã cập nhật 4 nguồn; LÊN SAO chưa được xác nhận.',
                'Gán shop PGs, Sao PGs, ON và OFF đã nhập vào Dashboard.\n'
                'Chưa có xác nhận đồng bộ LÊN SAO. Vui lòng kiểm tra tại Data → Nhân sự → Nội bộ.')
    if status not in ('failed', 'uncertain') or core or history:
        raise ValueError()
    title = ('Cập nhật Data HR chưa hoàn tất.' if status == 'failed'
             else 'Lượt cập nhật Data HR cần đối soát kết quả.')
    return (title, 'Chưa có đủ xác nhận đồng bộ 5 tab và nhập Data nhân sự.\n'
            'Vui lòng kiểm tra lượt gần nhất tại Data → Nhân sự → Nội bộ; không tự chạy lại lượt chưa rõ kết quả.')


def message(notice):
    try:
        title, detail = sync_result(notice)
        if not UUID.fullmatch(notice['runId']) or not UUID.fullmatch(notice['claimId']):
            raise ValueError()
        if not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', notice['month']):
            raise ValueError()
        date = datetime.fromisoformat(notice['completedAt'].replace('Z', '+00:00'))
        if date.tzinfo is None:
            raise ValueError()
        shown = date.astimezone(VN).strftime('%H:%M ngày %d/%m/%Y')
        period = '/'.join(reversed(notice['month'].split('-')))
        return (title + '\n'
                f'Kỳ dữ liệu: {period}. Ghi nhận kết quả lúc {shown}.\n' + detail)
    except (ValueError, KeyError, TypeError):
        raise NoticeError('notice_proof_invalid') from None


def acknowledge(api, notice, **result):
    # Retry only the receipt write, never the message send.
    for attempt in range(2):
        try:
            return api.call('ack', runId=notice['runId'], claimId=notice['claimId'], **result)
        except NoticeError:
            if attempt:
                raise


def run(config, send=False, api=None, sender=None):
    api = api or NoticeApi(config)
    sender = sender or DingTalkSender(config['credentials'], {'robot_code': config['state']['robot_code']})
    if not send:
        state = api.call('status')
        sender.access_token()  # Verify existing bot credentials without any message.
        return {'mode': 'verify', 'ready': True, 'pending': state['pending'], 'due': state['due'], 'sent': 0}
    accepted = rejected = unknown = 0
    for _ in range(5):
        notice = api.call('claim').get('notice')
        if notice is None:
            break
        text = message(notice)
        try:
            sender.access_token()  # Do not start a send if bot authorization fails.
        except (DeliveryError, ValueError):
            api.call('release', runId=notice['runId'], claimId=notice['claimId'])
            raise NoticeError('notice_bot_authorization_unavailable') from None
        # A timeout here must stop: the durable sending state may already exist.
        api.call('sending', runId=notice['runId'], claimId=notice['claimId'])
        try:
            receipt = sender.send('dm', config['state']['leader_staff_id'], text)
            if not isinstance(receipt, str) or not receipt:
                raise DeliveryError('missing_send_receipt', ambiguous=True)
        except DeliveryError as e:
            outcome = 'unknown' if e.ambiguous else 'rejected'
            acknowledge(api, notice, outcome=outcome)
            unknown += int(e.ambiguous)
            rejected += int(not e.ambiguous)
        except Exception:
            acknowledge(api, notice, outcome='unknown')
            unknown += 1
        else:
            result = acknowledge(api, notice, outcome='accepted', receipt=receipt)
            if result.get('accepted') is not True:
                raise NoticeError('notice_receipt_unconfirmed')
            accepted += 1
    state = api.call('status')
    return {'mode': 'send', 'accepted': accepted, 'rejected': rejected, 'unknown': unknown,
            'due': state['due'], 'unresolved': state.get('unresolved', state['unknown'] + state['rejected']), 'group': 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', action='store_true')
    args = parser.parse_args()
    try:
        result = run(configuration(os.environ.get('OLLIE_KPI_CONFIG_JSON', '')), send=args.send)
        print(json.dumps({'hr_notice': result}))
        return int(bool(result.get('rejected') or result.get('unknown') or result.get('unresolved') or result.get('due')))
    except Exception as e:
        # No exception bodies, credentials, destination IDs, content or receipts in logs.
        print(json.dumps({'hr_notice': {'ok': False, 'error_type': type(e).__name__}}))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())

