"""Persist group notices encrypted; read explicitly dated dashboard tasks."""
import base64
import hashlib
import json
import time
from datetime import datetime

import requests
from kpi import SupabaseKpiSource, KpiSourceError
from tracker import VIETNAM


class DeadlineSource:
    def __init__(self, config, ledger_key, group_id):
        SupabaseKpiSource(config)
        self.config = config
        self.key = base64.b64decode(ledger_key, validate=True)
        if len(self.key) != 32: raise KpiSourceError('invalid_notice_key')
        self.aad = ('ollie-notices:v1:' + group_id).encode()
        self.url = f"{config['url']}/rest/v1/{config['table']}"
        self.headers = {'apikey': config['anon_key'], 'Authorization': 'Bearer ' + config['anon_key']}

    @staticmethod
    def event_key(event):
        return 'ollieNotice:' + hashlib.sha256(event['event_id'].encode()).hexdigest()

    def seal(self, event):
        import os
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        data = json.dumps(event, ensure_ascii=False, sort_keys=True).encode()
        return {'version': 1, 'sealed': base64.b64encode(nonce + AESGCM(self.key).encrypt(nonce, data, self.aad)).decode()}

    def open(self, value):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            data = base64.b64decode(value['sealed'], validate=True)
            if value['version'] != 1 or len(data) > 80000: raise ValueError()
            event = json.loads(AESGCM(self.key).decrypt(data[:12], data[12:], self.aad))
            if not isinstance(event, dict): raise ValueError()
            return event
        except Exception:
            raise KpiSourceError('notice_integrity_failed') from None

    def write_event(self, event):
        key = self.event_key(event); value = self.seal(event)
        try:
            result = requests.post(self.url, headers={**self.headers, 'Prefer': 'resolution=merge-duplicates,return=representation'},
                                   json=[{'key': key, 'value': value, 'updated_at': datetime.now(VIETNAM).isoformat()}], timeout=20)
            if not result.ok: raise KpiSourceError(f'notice_write_http_{result.status_code}')
            rows = result.json()
            if not isinstance(rows, list) or len(rows) != 1 or rows[0].get('key') != key or rows[0].get('value') != value:
                raise KpiSourceError('notice_write_unconfirmed')
        except requests.RequestException:
            raise KpiSourceError('notice_write_connection_failed') from None

    def rows(self, prefix):
        out = []
        for offset in range(0, 10000, 500):
            try:
                result = requests.get(self.url, headers=self.headers,
                                      params={'select': 'key,value', 'key': 'like.' + prefix + '*',
                                              'order': 'key.asc', 'limit': 500, 'offset': offset}, timeout=20)
                if not result.ok: raise KpiSourceError(f'notice_read_http_{result.status_code}')
                rows = result.json()
                if not isinstance(rows, list): raise KpiSourceError('invalid_notice_source')
            except requests.RequestException:
                raise KpiSourceError('notice_read_connection_failed') from None
            out.extend(rows)
            if len(rows) < 500: return out
        raise KpiSourceError('notice_source_too_large')

    def sync_local_events(self, database):
        rows = database.execute('SELECT event_id,payload FROM task_events WHERE synced_at IS NULL ORDER BY recorded_at,event_id LIMIT 100').fetchall()
        for event_id, payload in rows:
            self.write_event(json.loads(payload))
            database.execute('UPDATE task_events SET synced_at=? WHERE event_id=?', (time.time(), event_id))
            database.commit()
        return len(rows)

    def events(self):
        events = []
        for row in self.rows('ollieNotice:'):
            event = self.open(row['value'])
            if self.event_key(event) != row['key']: raise KpiSourceError('notice_identity_mismatch')
            events.append(event)
        return sorted(events, key=lambda e: (e['recorded_at'], e['event_id']))

    def dashboard_tasks(self):
        return self.rows('ollieTask:'), {r['key']: r['value'] for r in self.rows('ollieDone:')}


def import_sources(tracker, source, recipients, trainer_names, now):
    """Map source identities once; retain completion state separately per Trainer."""
    db = tracker.db
    known = {v['target'] for v in recipients.values()} | {tracker.owner}
    events = source.events()
    tasks, dones = source.dashboard_tasks()
    with db:
        for tid, name in trainer_names.items():
            if tid in recipients:
                db.execute('INSERT INTO people VALUES (?,?) ON CONFLICT(staff_id) DO UPDATE SET name=excluded.name',
                           (recipients[tid]['target'], name))
        for event in events:
            if event.get('operation') == 'settings':
                if event.get('author') != tracker.owner or not isinstance(event.get('enabled'), bool):
                    raise KpiSourceError('notice_author_unverified')
                if not db.execute('SELECT 1 FROM task_imports WHERE event_id=?', (event['event_id'],)).fetchone():
                    settings = tracker.settings(); settings['enabled'] = event['enabled']
                    db.execute("UPDATE settings SET value=? WHERE key='reminders'", (json.dumps(settings),))
                    db.execute('INSERT INTO task_imports VALUES (?)', (event['event_id'],))
                continue
            if event.get('author') not in known or any(sid not in known for sid in event['assignees']):
                raise KpiSourceError('notice_recipient_unverified')
            if event['operation'] != 'complete' and event['author'] != tracker.owner:
                raise KpiSourceError('notice_author_unverified')
            if db.execute('SELECT 1 FROM task_imports WHERE event_id=?', (event['event_id'],)).fetchone(): continue
            reference = event['task_source_event']
            row = db.execute('SELECT id FROM tasks WHERE source_event=?', (reference,)).fetchone()
            if row:
                task_id = row[0]
                db.execute('UPDATE tasks SET content=?,deadline=?,cancelled=MAX(cancelled,?) WHERE id=?',
                           (event['content'], event['deadline'], int(event['cancelled']), task_id))
            else:
                cursor = db.execute('''INSERT INTO tasks (source_event,created_by,content,deadline,created_at,first_reminder_at,cancelled)
                                       VALUES (?,?,?,?,?,?,?)''', (reference, tracker.owner, event['content'], event['deadline'],
                                       event['created_at'], tracker.first_reminder(event['deadline'], event['created_at']), int(event['cancelled'])))
                task_id = cursor.lastrowid
            for sid in event['assignees']:
                done = event.get('done', {}).get(sid)
                db.execute('INSERT OR IGNORE INTO assignments VALUES (?,?,NULL)', (task_id, sid))
                if done is not None:
                    # Completion is monotonic; a delayed older snapshot cannot undo it.
                    db.execute('UPDATE assignments SET done_at=COALESCE(done_at,?) WHERE task_id=? AND staff_id=?', (done, task_id, sid))
            db.execute('INSERT INTO task_imports VALUES (?)', (event['event_id'],))
        for row in tasks:
            value = row['value']
            if not isinstance(value, dict) or row['key'] != 'ollieTask:' + str(value.get('id')):
                raise KpiSourceError('invalid_dashboard_task')
            tids = value.get('trainer_ids', [])
            if not tids or any(tid not in recipients for tid in tids): raise KpiSourceError('dashboard_task_recipient_unverified')
            try:
                due = datetime.fromisoformat(value['deadline'].replace('Z', '+00:00'))
                created = datetime.fromisoformat(value['created_at'].replace('Z', '+00:00'))
                if due.tzinfo is None or created.tzinfo is None: raise ValueError()
                content = str(value['content']).strip()
                if not content or len(content) > 12000: raise ValueError()
                if value.get('link'):
                    if not str(value['link']).startswith(('https://', 'http://')): raise ValueError()
                    content += '\n🔗 Link: ' + str(value['link'])
            except (KeyError, ValueError): raise KpiSourceError('dashboard_task_missing_deadline') from None
            reference = 'dashboard:' + value['id']
            result = db.execute('SELECT id FROM tasks WHERE source_event=?', (reference,)).fetchone()
            cancelled = int(bool(value.get('cancelled')))
            if result:
                task_id = result[0]
                db.execute('UPDATE tasks SET content=?,deadline=?,cancelled=? WHERE id=?', (content, due.timestamp(), cancelled, task_id))
            else:
                cursor = db.execute('''INSERT INTO tasks (source_event,created_by,content,deadline,created_at,first_reminder_at,cancelled)
                                       VALUES (?,?,?,?,?,?,?)''', (reference, tracker.owner, content, due.timestamp(), created.timestamp(),
                                       tracker.first_reminder(due.timestamp(), created.timestamp()), cancelled))
                task_id = cursor.lastrowid
            wanted = {recipients[tid]['target'] for tid in tids} | {tracker.owner}
            for old_sid, in db.execute('SELECT staff_id FROM assignments WHERE task_id=?', (task_id,)).fetchall():
                if old_sid not in wanted: db.execute('DELETE FROM assignments WHERE task_id=? AND staff_id=?', (task_id, old_sid))
            for sid in wanted: db.execute('INSERT OR IGNORE INTO assignments VALUES (?,?,NULL)', (task_id, sid))
            for tid in tids:
                done = dones.get('ollieDone:' + value['id'] + ':' + tid, {})
                db.execute('UPDATE assignments SET done_at=? WHERE task_id=? AND staff_id=?',
                           (now if done.get('done') is True else None, task_id, recipients[tid]['target']))
            everyone_done = all(dones.get('ollieDone:' + value['id'] + ':' + tid, {}).get('done') is True for tid in tids)
            db.execute('UPDATE assignments SET done_at=? WHERE task_id=? AND staff_id=?', (now if everyone_done else None, task_id, tracker.owner))
    return {'group_events': len(events), 'dashboard_tasks': len(tasks)}
