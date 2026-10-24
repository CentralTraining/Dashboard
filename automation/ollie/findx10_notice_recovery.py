"""One-off user-approved restoration of the Find X10 page-registration notice."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
from types import SimpleNamespace
from urllib.parse import urlparse

import requests

from announcements import notice_source_id, parse_announcement, notice_spacing
from daily_digest import split_links
from deadline_source import DeadlineSource, import_sources
from github_daily import GitHubState, StateError, validate_configuration
from group_capture import command, message_time, validate_history
from kpi import KpiSourceError
from tracker import Tracker, VIETNAM, folded

EXPECTED_DUE = datetime(2026, 10, 25, 22, tzinfo=VIETNAM).timestamp()
EXPECTED_FORM_HASH = 'e8f11c99a915cac9f2ee66807adf6384aa237ceed03dc66b12a4aa125d3a069c'


def is_target(text):
    key = re.sub(r'[^a-z0-9]', '', folded(text))
    return 'langkinh' in key and 'findx10' in key


def has_form(text, expected_hash=EXPECTED_FORM_HASH):
    for url in split_links(text)[1]:
        parsed = urlparse(url)
        match = re.match(r'^/spreadsheets/d/([^/]+)', parsed.path)
        if parsed.hostname == 'docs.google.com' and match:
            if hashlib.sha256(match[1].encode()).hexdigest() == expected_hash: return True
    return False


def choose_notice(messages, group, owner, now, form_hash=EXPECTED_FORM_HASH):
    if now >= EXPECTED_DUE: raise StateError('approved_deadline_already_passed')
    candidates = []
    for message in messages:
        text = re.sub(r'@Ollie_MT\b', '', message.get('text', ''), flags=re.I).strip()
        if not is_target(text) or not has_form(text, form_hash): continue
        clean = folded(notice_spacing(text))
        if not ('dien' in clean and 'page' in clean and ('dang ki' in clean or 'dang ky' in clean)): continue
        posted = message_time(message['createTime'])
        if not now - 7 * 86400 <= posted <= now: continue
        try: content, due = parse_announcement(text, posted)
        except ValueError: continue
        if due != EXPECTED_DUE: continue
        candidates.append({'text': text, 'content': content, 'due': due, 'posted': posted,
            'source': notice_source_id(group, owner, posted, text)})
    if not candidates: raise StateError('approved_notice_not_found_in_leader_history')
    variants = {notice_spacing(c['text']).strip() for c in candidates}
    if len(variants) != 1: raise StateError('approved_notice_is_ambiguous')
    return min(candidates, key=lambda c: c['posted'])


def existing_tracker(database, state):
    tables = {r[0] for r in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'tasks', 'assignments', 'settings', 'task_imports', 'task_originals', 'outbox'} <= tables:
        raise StateError('existing_tracker_schema_required')
    # Open the existing schema without Tracker.__init__ changing unrelated outbox states.
    tracker = Tracker.__new__(Tracker)
    tracker.db, tracker.state, tracker.owner = database, state, state['leader_staff_id']
    settings = tracker.settings()
    if settings.get('start_policy') != 'next_morning' or settings.get('daily_channels') != ['dm'] or (settings.get('hour'), settings.get('minute')) != (8, 0):
        raise StateError('existing_deadline_policy_mismatch')
    return tracker


def read_one_event(source, event):
    key = source.event_key(event)
    response = requests.get(source.url, headers=source.headers,
                            params={'select': 'key,value', 'key': 'eq.' + key}, timeout=20)
    if not response.ok: raise StateError('approved_notice_readback_failed')
    rows = response.json()
    if not isinstance(rows, list) or len(rows) != 1 or rows[0].get('key') != key:
        raise StateError('approved_notice_readback_unconfirmed')
    return source.open(rows[0]['value'])


def restore_selected(database, state, recipients, notice, source, now, readback=read_one_event):
    tracker = existing_tracker(database, state)
    targets = {value['target'] for value in recipients.values()} | {tracker.owner}
    protected = database.execute('SELECT * FROM outbox ORDER BY job_key').fetchall()
    others = database.execute('SELECT * FROM tasks WHERE source_event<>? ORDER BY id', (notice['source'],)).fetchall()
    row = database.execute('SELECT id,deadline,cancelled,created_at FROM tasks WHERE source_event=?', (notice['source'],)).fetchone()
    if not row:
        for content, due in database.execute('SELECT content,deadline FROM tasks'):
            if due == EXPECTED_DUE and is_target(content): raise StateError('equivalent_notice_requires_review')
    else:
        if row[1] != EXPECTED_DUE: raise StateError('existing_notice_deadline_conflict')
        if row[2]: raise StateError('existing_notice_cancelled_not_reopened')
        current = database.execute('SELECT staff_id,done_at FROM assignments WHERE task_id=?', (row[0],)).fetchall()
        if {sid for sid, _ in current} != targets: raise StateError('existing_notice_assignment_scope_mismatch')
    done = {sid: at for sid, at in database.execute('SELECT staff_id,done_at FROM assignments WHERE task_id=?', (row[0],)).fetchall() if at is not None} if row else {}
    event = {'event_id': notice['source'], 'task_source_event': notice['source'],
        'content': notice['content'], 'deadline': EXPECTED_DUE,
        'created_at': row[3] if row else notice['posted'], 'cancelled': False,
        'assignees': sorted(targets), 'done': done, 'operation': 'create', 'author': tracker.owner,
        'recorded_at': notice['posted'], 'original': notice['text']}
    source.write_event(event)  # Existing AES-GCM notice storage; only this event key is written.
    if readback(source, event) != event: raise StateError('approved_notice_readback_mismatch')
    scoped_source = SimpleNamespace(events=lambda: [event], dashboard_tasks=lambda: ([], {}))
    import_sources(tracker, scoped_source, recipients, {}, now)
    selected = database.execute('SELECT id,deadline,cancelled,first_reminder_at FROM tasks WHERE source_event=?', (notice['source'],)).fetchone()
    database.execute('INSERT OR IGNORE INTO task_originals VALUES (?,?)', (selected[0], notice['text']))
    database.commit()
    if database.execute('SELECT * FROM outbox ORDER BY job_key').fetchall() != protected:
        raise StateError('outbox_changed_unexpectedly')
    if database.execute('SELECT * FROM tasks WHERE source_event<>? ORDER BY id', (notice['source'],)).fetchall() != others:
        raise StateError('other_tasks_changed_unexpectedly')
    local = datetime.fromtimestamp(now, VIETNAM)
    next_run = local.replace(hour=8, minute=0, second=0, microsecond=0)
    if next_run.timestamp() <= now: next_run += timedelta(days=1)
    due_rows = tracker.due_tasks(next_run.date(), now=next_run.timestamp())
    pending = {r[3] for r in due_rows if r[0] == selected[0]}
    return {'mode': 'approved_findx10_notice_recovery', 'saved': True, 'created': row is None,
        'deadline': datetime.fromtimestamp(selected[1], VIETNAM).isoformat(),
        'source_readback_confirmed': True, 'outbox_unchanged': True,
        'next_reminder': next_run.isoformat(), 'pending_private_recipients': len(pending),
        'reminders_enabled': tracker.settings()['enabled'], 'messages_sent': 0}


def main():
    os.umask(0o077)
    config = json.loads(os.environ['OLLIE_KPI_CONFIG_JSON'])
    validate_configuration(config)
    if len(config['settings']['trainer_recipients']) != 13: raise StateError('expected_thirteen_trainers')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if not event.get('created') or os.environ.get('GITHUB_RUN_ATTEMPT') != '1': raise StateError('oneoff_only')
    now = time.time()
    if now >= EXPECTED_DUE: raise StateError('approved_deadline_already_passed')
    store = GitHubState(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN'], config['ledger_key'], os.environ['GITHUB_SHA'])
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder); path = root / 'ledger.sqlite3'
        if not store.restore(path): raise StateError('existing_ledger_required')
        db = sqlite3.connect(path)
        result = None
        try:
            owner, group = config['state']['leader_staff_id'], config['state']['conversation_id']
            rows = db.execute('SELECT profile,bundle,cursor FROM group_auth').fetchall()
            if len(rows) != 1 or not rows[0][0].endswith(':' + owner): raise StateError('group_login_owner_mismatch')
            profile, bundle, cursor = rows[0]
            auth = root / 'auth-private.tar.gz'; auth.write_bytes(bundle); auth.chmod(0o600)
            env = {**os.environ, 'DWS_CONFIG_DIR': str(root / 'dws-config'), 'DWS_KEYCHAIN_DIR': str(root / 'dws-keychain'), 'DWS_LANG': 'en'}
            cli = Path(__file__).resolve().parent / 'dws'
            command(cli, profile, env, ['auth', 'import', '-i', str(auth)])
            try:
                start = datetime.fromtimestamp(now - 7 * 86400, timezone.utc).isoformat()
                end = datetime.fromtimestamp(now, timezone.utc).isoformat()
                raw = command(cli, profile, env, ['chat', '+chat-messages', '--group', group, '--sender', owner,
                    '--start', start, '--end', end, '--order', 'asc', '--page-all', '--page-limit', '20', '--max-items', '1000', '--no-reactions', '-f', 'json'])
                messages = validate_history(json.loads(raw), owner, group)
                notice = choose_notice(messages, group, owner, now)
                source = DeadlineSource(config['source'], config['ledger_key'], group)
                result = restore_selected(db, config['state'], config['settings']['trainer_recipients'], notice, source, now)
            finally:
                refreshed = root / 'auth-refreshed-private.tar.gz'
                command(cli, profile, env, ['auth', 'export', '-o', str(refreshed)])
                db.execute('UPDATE group_auth SET bundle=? WHERE profile=?', (refreshed.read_bytes(), profile))
                db.commit(); store.save(db)
            check_path = root / 'confirmed.sqlite3'
            if not store.restore(check_path): raise StateError('ledger_readback_failed')
            verify = sqlite3.connect(check_path)
            try:
                task = verify.execute('SELECT deadline,cancelled FROM tasks WHERE source_event=?', (notice['source'],)).fetchone()
                if task != (EXPECTED_DUE, 0): raise StateError('saved_notice_unconfirmed')
                saved_cursor = verify.execute('SELECT cursor FROM group_auth WHERE profile=?', (profile,)).fetchone()
                if saved_cursor != (cursor,): raise StateError('scan_cursor_changed_unexpectedly')
            finally: verify.close()
            result['ledger_readback_confirmed'] = True
            result['scan_cursor_unchanged'] = True
            print(json.dumps(result))  # Only this approved deadline and aggregate counters.
        finally: db.close()


if __name__ == '__main__':
    try: main()
    except Exception as error:
        detail = str(error) if isinstance(error, (StateError, KpiSourceError)) and re.fullmatch(r'[a-z0-9_]{1,100}', str(error)) else type(error).__name__
        print(json.dumps({'mode': 'approved_findx10_notice_recovery', 'confirmed': False, 'error_code': detail, 'messages_sent': 0}))
        raise SystemExit(1)
