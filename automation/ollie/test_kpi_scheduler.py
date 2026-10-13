import json
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from kpi import KpiSnapshot, KpiSourceError
from kpi_scheduler import KpiBridge
from tracker import Tracker, DingTalkSender, DeliveryError, VIETNAM
from test_kpi import fixture, rows


def stamp(day=12, hour=8, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=VIETNAM).timestamp()


class BridgeChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.state = {'leader_staff_id': 'leader', 'leader_name': 'Leader', 'conversation_id': 'group', 'robot_code': 'bot'}
        self.db = sqlite3.connect(':memory:'); self.tracker = Tracker(self.db, self.state)
        self.bridge = KpiBridge(self.db, self.state, self.root)
        self.settings = {'enabled': True, 'start_date': '2026-10-12', 'hour': 8, 'minute': 0,
                         'trainer_recipients': {'a': {'channel': 'dm', 'target': 'staff-a'},
                                                'b': {'channel': 'dm_open', 'target': 'open-b'}}}
        (self.root / 'settings.json').write_text(json.dumps(self.settings))
        (self.root / 'source.json').write_text(json.dumps({'url': 'https://example.supabase.co', 'table': 'kv_store',
                                                        'anon_key': 'fake', 'dashboard_url': 'https://example.invalid/dashboard/'}))
        async def direct(fn, *args, **kwargs):
            return fn(*args, **kwargs)
        # Sources are mocked in these unit checks; avoid starting network threads.
        self.thread_patch = patch('kpi_scheduler.asyncio.to_thread', side_effect=direct)
        self.thread_patch.start()

    def tearDown(self):
        self.thread_patch.stop()
        self.db.close(); self.temp.cleanup()

    async def test_daily_eight_vietnam_once_and_each_trainer_plus_leader_privately(self):
        snapshot = KpiSnapshot(rows(fixture()), '2026-10')
        with patch('kpi_scheduler.SupabaseKpiSource.snapshot', return_value=snapshot) as source:
            await self.bridge.prepare(stamp(hour=7, minute=59)); source.assert_not_called()
            await self.bridge.prepare(stamp())
            jobs = self.tracker.next_jobs(stamp())
            self.assertEqual({(j[3], j[4]) for j in jobs}, {('dm', 'leader'), ('dm', 'staff-a'), ('dm_open', 'open-b')})
            a = next(j for j in jobs if j[4] == 'staff-a')
            self.assertIn('KPI 10/2026 · A', self.tracker.job_content(a, stamp()))
            self.assertNotIn('KPI 10/2026 · B', self.tracker.job_content(a, stamp()))
            await self.bridge.prepare(stamp(hour=9)); self.assertEqual(source.call_count, 1)
            await self.bridge.prepare(stamp(day=13)); self.assertEqual(source.call_count, 2)
            self.assertIsNone(self.tracker.job_content(a, stamp(day=13)))

    async def test_unmapped_or_duplicate_accounts_block_every_outbound_message(self):
        del self.settings['trainer_recipients']['b']
        (self.root / 'settings.json').write_text(json.dumps(self.settings))
        with patch('kpi_scheduler.SupabaseKpiSource.snapshot', return_value=KpiSnapshot(rows(fixture()), '2026-10')):
            with self.assertRaisesRegex(KpiSourceError, 'trainer_mapping_incomplete'):
                await self.bridge.prepare(stamp())
        self.assertEqual(self.tracker.next_jobs(stamp()), [])

    async def test_source_failure_never_creates_zero_progress_messages(self):
        with patch('kpi_scheduler.SupabaseKpiSource.snapshot', side_effect=KpiSourceError('source_connection_failed')):
            with self.assertRaises(KpiSourceError): await self.bridge.prepare(stamp())
        self.assertEqual(self.tracker.next_jobs(stamp()), [])

    async def test_disabling_kpi_stops_queued_reports(self):
        with patch('kpi_scheduler.SupabaseKpiSource.snapshot', return_value=KpiSnapshot(rows(fixture()), '2026-10')):
            await self.bridge.prepare(stamp())
        jobs = self.tracker.next_jobs(stamp())
        self.settings['enabled'] = False
        (self.root / 'settings.json').write_text(json.dumps(self.settings))
        await self.bridge.prepare(stamp(hour=9))
        self.assertTrue(all(self.tracker.job_content(j, stamp(hour=9)) is None for j in jobs))

    async def test_old_queued_group_report_is_not_delivered_after_private_only_change(self):
        with patch('kpi_scheduler.SupabaseKpiSource.snapshot', return_value=KpiSnapshot(rows(fixture()), '2026-10')):
            await self.bridge.prepare(stamp())
        reference = 'legacy-group-kpi'
        self.db.execute('INSERT INTO kpi_messages VALUES (?,?,?)',
                        (reference, '2026-10-12', 'Old group report'))
        self.tracker.add_job(reference, 'kpi', reference, 'group', 'group', stamp())
        self.db.commit()
        jobs = self.tracker.next_jobs(stamp())
        group_job = next(job for job in jobs if job[3] == 'group')
        self.assertIsNone(self.tracker.job_content(group_job, stamp()))
        self.assertTrue(all(self.tracker.job_content(job, stamp()) for job in jobs if job[3] != 'group'))


class RecipientChecks(unittest.TestCase):
    def setUp(self):
        self.sender = DingTalkSender({'appKey': 'bot', 'appSecret': 'fake'},
            {'robot_code': 'bot', 'profile': 'corp:leader', 'allowed_open_dingtalk_ids': ['open-b']})

    def test_verified_open_id_uses_scoped_profile_and_requires_receipt(self):
        response = SimpleNamespace(returncode=0, stdout=json.dumps({'success': True, 'result': {'processQueryKey': 'receipt'}}))
        with patch('tracker.subprocess.run', return_value=response) as command:
            self.assertEqual(self.sender.send('dm_open', 'open-b', 'Tiến độ\nXem dashboard'), 'receipt')
            args = command.call_args.args[0]
            self.assertEqual(args[args.index('--profile') + 1], 'corp:leader')
            self.assertEqual(args[args.index('--open-dingtalk-ids') + 1], 'open-b')
        with patch('tracker.subprocess.run') as command:
            with self.assertRaisesRegex(DeliveryError, 'recipient_not_configured'):
                self.sender.send('dm_open', 'unverified-person', 'body')
            command.assert_not_called()

    def test_uncertain_cli_result_is_not_accepted_or_retried(self):
        with patch('tracker.subprocess.run', side_effect=subprocess.TimeoutExpired(['dws'], 35)) as command:
            with self.assertRaises(DeliveryError) as result: self.sender.send('dm_open', 'open-b', 'body')
            self.assertTrue(result.exception.ambiguous)
            self.assertEqual(command.call_count, 1)


if __name__ == '__main__':
    unittest.main()
