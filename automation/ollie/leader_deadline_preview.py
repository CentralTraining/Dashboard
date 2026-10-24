"""One-off, read-only preview: one private message to the configured leader."""
import asyncio
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from daily_digest import MarkdownMessage, format_deadline_digest, given_name
from deadline_scheduler import sync_deadlines
from github_daily import GitHubState, StateError, validate_configuration
from tracker import DeliveryError, DingTalkSender, Tracker


def validate_oneoff_event(event, attempt):
    if str(attempt) != '1' or not isinstance(event, dict) or event.get('created') is not True or event.get('deleted'):
        raise StateError('oneoff_preview_not_first_branch_creation')


def preview_content(tracker, now):
    rows = [row for row in tracker.pending_tasks() if row[2] > now]
    tasks = tracker.group_tasks(rows)
    if tasks:
        content = format_deadline_digest(tracker.name(tracker.owner), tasks, now)
    else:
        content = MarkdownMessage(f'Xin chào {given_name(tracker.name(tracker.owner))}!\n\n📌 Hiện không có công việc còn hạn cần nhắc.')
    if len(content.encode('utf-8')) > 18000: raise StateError('preview_message_too_large')
    return content, len(tasks)


def send_preview_once(tracker, sender, content, task_count):
    try:
        receipt = sender.send('dm', tracker.owner, content)
        if not receipt: raise DeliveryError('missing_send_receipt', ambiguous=True)
    except DeliveryError as error:
        return {'mode': 'oneoff_leader_deadline_preview', 'accepted': 0, 'failed': int(not error.ambiguous),
                'uncertain': int(error.ambiguous), 'task_count': task_count, 'group_accepted': 0, 'trainer_accepted': 0}
    return {'mode': 'oneoff_leader_deadline_preview', 'accepted': 1, 'receipt_confirmed': True,
            'failed': 0, 'uncertain': 0, 'task_count': task_count, 'group_accepted': 0, 'trainer_accepted': 0}


async def run(config):
    validate_oneoff_event(json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text()), os.environ.get('GITHUB_RUN_ATTEMPT'))
    validate_configuration(config)
    store = GitHubState(os.environ.get('GITHUB_REPOSITORY', ''), os.environ.get('GITHUB_TOKEN', ''),
                        config.get('ledger_key', ''), os.environ.get('GITHUB_SHA', ''))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'preview.sqlite3'
        store.restore(path)  # Read and decrypt locally; never save or reset the shared ledger.
        database = sqlite3.connect(path)
        try:
            tracker = Tracker(database, config['state'])
            now = time.time()
            await sync_deadlines(tracker, config, now)  # Source reads and local SQLite only.
            content, count = preview_content(tracker, now)
            result = send_preview_once(tracker, DingTalkSender(config['credentials'], config['state']), content, count)
            print(json.dumps(result))  # No bodies, identities, credentials or receipt values.
            return int(result['accepted'] != 1 or result['failed'] or result['uncertain'])
        finally:
            database.close()


if __name__ == '__main__':
    os.umask(0o077)
    try:
        code = asyncio.run(run(json.loads(os.environ.get('OLLIE_KPI_CONFIG_JSON', ''))))
    except Exception as error:
        print(json.dumps({'mode': 'oneoff_leader_deadline_preview', 'confirmed': False, 'error_type': type(error).__name__}))
        code = 1
    raise SystemExit(code)
