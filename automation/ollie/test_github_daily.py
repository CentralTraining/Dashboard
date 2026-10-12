import sqlite3
import unittest
import base64
import os
import tempfile
from pathlib import Path
import contextlib
import io
from unittest.mock import Mock, patch

from github_daily import deliver_jobs, StateError, GitHubState, run
from tracker import Tracker, DeliveryError
from kpi import KpiSnapshot
from test_kpi import fixture, rows


class DeliveryLedgerChecks(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.state = {'leader_staff_id': 'leader', 'leader_name': 'Leader',
                      'conversation_id': 'group', 'robot_code': 'bot'}
        self.tracker = Tracker(self.db, self.state)
        self.db.execute("INSERT INTO alerts (id,source_event,content,staff_id,due_at) VALUES (1,'event','Private content','trainer',1)")
        self.tracker.add_job('one', 'alert', '1', 'dm', 'trainer', 1)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_state_save_must_succeed_before_any_send(self):
        store = Mock(); store.save.side_effect = StateError('github_state_http_403')
        sender = Mock()
        with self.assertRaises(StateError):
            deliver_jobs(self.tracker, sender, store, 10)
        sender.send.assert_not_called()
        self.assertEqual(self.db.execute("SELECT status FROM outbox WHERE job_key='one'").fetchone()[0], 'sending')

    def test_success_is_not_sent_again_and_sending_is_saved_first(self):
        saved = []
        store = Mock(); store.save.side_effect = lambda db: saved.append(db.execute("SELECT status FROM outbox WHERE job_key='one'").fetchone()[0])
        sender = Mock(); sender.send.return_value = 'receipt'
        self.assertEqual(deliver_jobs(self.tracker, sender, store, 10)['accepted'], 1)
        self.assertEqual(saved, ['sending', 'accepted'])
        self.assertEqual(deliver_jobs(self.tracker, sender, store, 11)['accepted'], 0)
        sender.send.assert_called_once_with('dm', 'trainer', 'Private content')

    def test_ambiguous_send_is_not_retried_after_restart(self):
        store = Mock(); sender = Mock()
        sender.send.side_effect = DeliveryError('timeout', ambiguous=True)
        self.assertEqual(deliver_jobs(self.tracker, sender, store, 10)['uncertain'], 1)
        reloaded = Tracker(self.db, self.state)
        deliver_jobs(reloaded, sender, store, 11)
        self.assertEqual(sender.send.call_count, 1)
        self.assertEqual(self.db.execute("SELECT status FROM outbox WHERE job_key='one'").fetchone()[0], 'unknown')

    def test_explicit_rejection_can_retry_without_duplicating_success(self):
        store = Mock(); sender = Mock()
        sender.send.side_effect = [DeliveryError('recipient_rejected'), 'receipt']
        with patch('github_daily.time.time', return_value=10):
            self.assertEqual(deliver_jobs(self.tracker, sender, store, 10)['failed'], 1)
            self.assertEqual(deliver_jobs(self.tracker, sender, store, 11)['accepted'], 0)
            self.assertEqual(deliver_jobs(self.tracker, sender, store, 71)['accepted'], 1)
            self.assertEqual(deliver_jobs(self.tracker, sender, store, 72)['accepted'], 0)
        self.assertEqual(sender.send.call_count, 2)


class VerifyModeChecks(unittest.IsolatedAsyncioTestCase):
    async def test_verify_checks_live_source_and_auth_without_sending_or_creating_state(self):
        config = {
            'source': {'url': 'https://example.supabase.co', 'table': 'kv_store',
                       'anon_key': 'fake', 'dashboard_url': 'https://example.invalid/'},
            'settings': {'hour': 8, 'minute': 0, 'timezone': 'Asia/Ho_Chi_Minh',
                         'trainer_recipients': {'a': {'channel': 'dm', 'target': 'staff-a'},
                                                'b': {'channel': 'dm', 'target': 'staff-b'}}},
            'state': {'leader_staff_id': 'leader', 'leader_name': 'Leader', 'conversation_id': 'group', 'robot_code': 'bot'},
            'credentials': {'appKey': 'bot', 'appSecret': 'fake'},
        }
        async def direct(fn, *args):
            return fn(*args)
        with patch('github_daily.asyncio.to_thread', side_effect=direct), \
             patch('github_daily.SupabaseKpiSource.snapshot', return_value=KpiSnapshot(rows(fixture()), '2026-10')) as source, \
             patch('github_daily.sync_deadlines', return_value={'group_events': 0, 'dashboard_tasks': 0}), \
             patch('github_daily.DingTalkSender') as sender, \
             patch('github_daily.GitHubState') as state, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            sender.return_value.access_token.return_value = 'private-token'
            await run(config, send=False)
        source.assert_called_once()
        sender.return_value.access_token.assert_called_once()
        sender.return_value.send.assert_not_called()
        state.assert_not_called()
        self.assertIn('"messages_sent": 0', output.getvalue())
        self.assertNotIn('private-token', output.getvalue())


class EncryptedStateChecks(unittest.TestCase):
    def setUp(self):
        self.key = base64.b64encode(os.urandom(32)).decode()
        self.store = GitHubState('CentralTraining/Dashboard', 'fake-token', self.key, 'a' * 40)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'db.sqlite'
            db = sqlite3.connect(path)
            db.execute('CREATE TABLE messages (body TEXT)')
            db.execute('INSERT INTO messages VALUES (?)', ('Private Trainer report',))
            db.commit(); db.close()
            self.plain = path.read_bytes()

    def test_encrypted_state_round_trip_keeps_private_body_out_of_git(self):
        encrypted = self.store.encrypt(self.plain)
        self.assertNotIn(b'Private Trainer report', encrypted)
        self.assertNotIn(b'SQLite format 3', encrypted)
        self.assertEqual(self.store.decrypt(encrypted), self.plain)

    def test_tampered_bytes_wrong_key_or_other_repository_are_rejected(self):
        encrypted = self.store.encrypt(self.plain)
        tampered = bytearray(encrypted); tampered[-1] ^= 1
        with self.assertRaisesRegex(StateError, 'ledger_integrity_failed'):
            self.store.decrypt(bytes(tampered))
        other = GitHubState('Other/Repository', 'fake-token', self.key, 'a' * 40)
        with self.assertRaisesRegex(StateError, 'ledger_integrity_failed'):
            other.decrypt(encrypted)
        other = GitHubState('CentralTraining/Dashboard', 'fake-token', base64.b64encode(os.urandom(32)).decode(), 'a' * 40)
        with self.assertRaisesRegex(StateError, 'ledger_integrity_failed'):
            other.decrypt(encrypted)

    def test_missing_existing_ledger_does_not_reset_duplicate_protection(self):
        self.store.request = Mock(side_effect=[None, {'ref': 'existing-state-branch'}])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(StateError, 'existing_ledger_missing'):
                self.store.restore(Path(directory) / 'db.sqlite')


if __name__ == '__main__':
    unittest.main()
