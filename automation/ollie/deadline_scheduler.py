"""Shared source sync for the persistent receiver and the daily GitHub runner."""
import asyncio
import json
from types import SimpleNamespace

from deadline_source import DeadlineSource, import_sources
from kpi import SupabaseKpiSource, KpiSourceError


def fetch_deadline_sources(config):
    source = DeadlineSource(config['source'], config['ledger_key'], config['state']['conversation_id'])
    records = SupabaseKpiSource(config['source']).read(['config'])
    trainers = next((r['value'].get('trainers', []) for r in records if r['key'] == 'config'), [])
    if not trainers: raise KpiSourceError('missing_deadline_trainer_configuration')
    events = source.events(); tasks, dones = source.dashboard_tasks()
    return events, tasks, dones, {t['id']: t['name'] for t in trainers}


async def sync_deadlines(tracker, config, now):
    events, tasks, dones, names = await asyncio.to_thread(fetch_deadline_sources, config)
    cached = SimpleNamespace(events=lambda: events, dashboard_tasks=lambda: (tasks, dones))
    return import_sources(tracker, cached, config['settings']['trainer_recipients'], names, now)


def configure_deadline_policy(tracker):
    settings = tracker.settings()
    settings.update({'start_policy': 'next_morning', 'hour': 8, 'minute': 0})
    tracker.db.execute("UPDATE settings SET value=? WHERE key='reminders'", (json.dumps(settings),))
    tracker.db.commit()
