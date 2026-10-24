from datetime import datetime
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from daily_digest import MarkdownMessage
from github_daily import StateError
from leader_deadline_preview import preview_content, send_preview_once, validate_oneoff_event
from tracker import DeliveryError, Tracker, VIETNAM


class LeaderPreviewChecks(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, 10, tzinfo=VIETNAM).timestamp()
        self.db = sqlite3.connect(':memory:')
        self.tracker = Tracker(self.db, {'leader_staff_id': 'synthetic-leader', 'leader_name': 'Leader thử nghiệm',
                                        'conversation_id': 'synthetic-group', 'robot_code': 'synthetic-bot'})

    def tearDown(self): self.db.close()

    def test_only_the_first_branch_creation_can_send(self):
        validate_oneoff_event({'created': True, 'deleted': False}, '1')
        for event, attempt in [({'created': True}, '2'), ({'created': False}, '1'), ({'created': True, 'deleted': True}, '1')]:
            with self.assertRaises(StateError): validate_oneoff_event(event, attempt)

    def test_actual_pending_tasks_are_combined_without_creating_send_jobs(self):
        incoming = SimpleNamespace(sender_staff_id='synthetic-leader')
        for i, name in enumerate(('Nộp 2 video', 'Điền báo cáo')):
            self.tracker.save_task(name, self.now + 86400 + i * 3600, incoming, str(i), self.now - 100,
                                   ['synthetic-trainer', 'synthetic-leader'])
        content, count = preview_content(self.tracker, self.now)
        self.assertEqual(count, 2)
        self.assertIsInstance(content, MarkdownMessage)
        self.assertIn('1. Nộp 2 video', content)
        self.assertIn('2. Điền báo cáo', content)
        self.assertEqual(self.tracker.next_jobs(self.now), [])

    def test_no_active_deadline_is_stated_without_inventing_tasks(self):
        content, count = preview_content(self.tracker, self.now)
        self.assertEqual(count, 0)
        self.assertIn('không có công việc còn hạn', content)
        self.assertEqual(self.tracker.pending_tasks(), [])

    def test_only_one_dm_to_the_configured_leader(self):
        sender = Mock(); sender.send.return_value = 'synthetic-receipt'
        content = MarkdownMessage('Synthetic preview')
        result = send_preview_once(self.tracker, sender, content, 2)
        sender.send.assert_called_once_with('dm', 'synthetic-leader', content)
        self.assertEqual(result['accepted'], 1)
        self.assertTrue(result['receipt_confirmed'])
        self.assertEqual(result['group_accepted'], 0)
        self.assertEqual(result['trainer_accepted'], 0)
        self.assertNotIn('synthetic-receipt', str(result))

    def test_unknown_send_is_not_retried(self):
        sender = Mock(); sender.send.side_effect = DeliveryError('timeout', ambiguous=True)
        result = send_preview_once(self.tracker, sender, 'Preview', 2)
        self.assertEqual(result['uncertain'], 1)
        self.assertEqual(result['accepted'], 0)
        sender.send.assert_called_once()

    def test_definite_rejection_is_not_reported_as_accepted(self):
        sender = Mock(); sender.send.side_effect = DeliveryError('recipient_rejected')
        result = send_preview_once(self.tracker, sender, 'Preview', 2)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['accepted'], 0)
        sender.send.assert_called_once()


if __name__ == '__main__': unittest.main()
