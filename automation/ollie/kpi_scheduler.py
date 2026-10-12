"""Queue the authorized daily KPI reports once per Vietnam calendar day."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from kpi import SupabaseKpiSource, KpiSourceError, format_trainer_report, format_team_report
from tracker import VIETNAM


class KpiBridge:
    def __init__(self, database, state, directory):
        self.db = database
        self.state = state
        self.directory = Path(directory)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS kpi_runs (
                day TEXT PRIMARY KEY, month TEXT NOT NULL, queued_at REAL NOT NULL,
                report_count INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS kpi_messages (
                reference TEXT PRIMARY KEY, day TEXT NOT NULL, content TEXT NOT NULL);
        ''')
        self.db.commit()
        self.next_attempt = 0

    def health(self, **values):
        path = self.directory / 'health.json'
        value = {'pid': os.getpid(), 'updated_at': datetime.now(VIETNAM).isoformat(), **values}
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False)); temp.chmod(0o600)
        os.replace(temp, path)

    async def prepare(self, now):
        path = self.directory / 'settings.json'
        if not path.exists(): return
        settings = json.loads(path.read_text())
        self.state['kpi_enabled'] = bool(settings.get('enabled'))
        if not settings.get('enabled'):
            return
        local = datetime.fromtimestamp(now, VIETNAM)
        day = local.date().isoformat()
        if day < settings['start_date']: return
        due = local.replace(hour=settings['hour'], minute=settings['minute'], second=0, microsecond=0).timestamp()
        if now < due or now < self.next_attempt: return
        if self.db.execute('SELECT 1 FROM kpi_runs WHERE day=?', (day,)).fetchone(): return
        self.next_attempt = now + 60
        month = local.strftime('%Y-%m')
        try:
            config = json.loads((self.directory / 'source.json').read_text())
            source = SupabaseKpiSource(config)
            snapshot = await asyncio.to_thread(source.snapshot, month)
            reports = await asyncio.to_thread(snapshot.reports)
            mapping = settings.get('trainer_recipients', {})
            if not reports: raise KpiSourceError('no_trainers')
            if any(r['trainer_id'] not in mapping for r in reports):
                raise KpiSourceError('trainer_mapping_incomplete')
            targets = [(mapping[r['trainer_id']]['channel'], mapping[r['trainer_id']]['target']) for r in reports]
            if len(set(targets)) != len(targets): raise KpiSourceError('duplicate_trainer_account')
            if any(channel not in ('dm', 'dm_open') or not target for channel, target in targets):
                raise KpiSourceError('invalid_trainer_account')
            dashboard_url = config['dashboard_url']
            team_text = format_team_report(reports, dashboard_url)
            # One group summary and one private team summary for the leader.
            deliveries = [('group', self.state['conversation_id'], team_text)]
            leader = ('dm', self.state['leader_staff_id'])
            if leader not in targets:
                deliveries.append((*leader, team_text))
            for report, (channel, target) in zip(reports, targets):
                deliveries.append((channel, target, format_trainer_report(report, dashboard_url)))
            with self.db:
                for channel, target, content in deliveries:
                    reference = f'kpi:{day}:{channel}:{target}'
                    self.db.execute('INSERT OR IGNORE INTO kpi_messages VALUES (?,?,?)', (reference, day, content))
                    self.db.execute('''INSERT OR IGNORE INTO outbox
                        (job_key,kind,reference,channel,target,due_at) VALUES (?,?,?,?,?,?)''',
                        (reference, 'kpi', reference, channel, target, due))
                self.db.execute('INSERT INTO kpi_runs VALUES (?,?,?,?)', (day, month, now, len(reports)))
            self.health(enabled=True, status='queued', day=day, trainer_count=len(reports), delivery_count=len(deliveries))
        except KpiSourceError as exc:
            self.health(enabled=True, status='waiting', error_code=str(exc), day=day)
            raise
