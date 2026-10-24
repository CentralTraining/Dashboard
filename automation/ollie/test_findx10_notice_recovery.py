from copy import deepcopy
from datetime import datetime
import hashlib
import sqlite3
import unittest

from deadline_scheduler import configure_deadline_policy
from findx10_notice_recovery import choose_notice, restore_selected, EXPECTED_DUE
from github_daily import StateError
from tracker import Tracker, VIETNAM

FORM = 'SYNTHETIC_FORM_ONLY'
FORM_HASH = hashlib.sha256(FORM.encode()).hexdigest()
FORM_URL = f'https://docs.google.com/spreadsheets/d/{FORM}/edit?gid=0#gid=0'
BODY = f'CHƯƠNG TRÌNH - LĂNG KÍNH FINDX10 SERIES\nAnh em điền link đăng kí page đăng bài trước 22h ngày 25/10 {FORM_URL}'


class FakeSource:
    def __init__(self): self.events = []
    def write_event(self, event): self.events.append(deepcopy(event))


class ApprovedNoticeRecoveryChecks(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, 9, tzinfo=VIETNAM).timestamp()
        self.state = {'leader_staff_id': 'owner', 'leader_name': 'Leader thử nghiệm',
                      'conversation_id': 'group'}
        self.recipients = {'t1': {'target': 'trainer-1'}, 't2': {'target': 'trainer-2'}}
        self.db = sqlite3.connect(':memory:')
        self.tracker = Tracker(self.db, self.state)
        configure_deadline_policy(self.tracker)
        self.db.execute("INSERT INTO outbox VALUES ('existing','daily','2026-10-24','dm','trainer-1',0,'accepted',1,'synthetic-receipt','',0)")
        self.db.commit()
        self.message = {'text': BODY.replace(' ', '\u00a0'), 'createTime': '2026-10-23T05:00:00Z'}
        self.notice = choose_notice([self.message], 'group', 'owner', self.now, FORM_HASH)
        self.source = FakeSource()

    def tearDown(self): self.db.close()

    def restore(self):
        return restore_selected(self.db, self.state, self.recipients, self.notice, self.source, self.now,
                                readback=lambda source, event: deepcopy(source.events[-1]))

    def test_expected_notice_is_distinct_from_past_meeting_and_other_forms(self):
        meeting = {'text': f'MEETING LĂNG KÍNH FINDX10\nThời gian: 14h00 - 14h30 ngày 23/10/2026\n{FORM_URL}', 'createTime': '2026-10-23T01:00:00Z'}
        selected = choose_notice([meeting, self.message], 'group', 'owner', self.now, FORM_HASH)
        self.assertEqual(selected['due'], EXPECTED_DUE)
        self.assertIn('điền link đăng kí page', selected['content'])
        with self.assertRaisesRegex(StateError, 'not_found'):
            choose_notice([self.message], 'group', 'owner', self.now, hashlib.sha256(b'wrong-form').hexdigest())

    def test_wrong_deadline_and_ambiguous_versions_are_not_restored(self):
        wrong = {**self.message, 'text': BODY.replace('25/10', '26/10')}
        with self.assertRaisesRegex(StateError, 'not_found'):
            choose_notice([wrong], 'group', 'owner', self.now, FORM_HASH)
        changed = {**self.message, 'text': BODY + '\nPhải nộp thêm 2 ảnh.'}
        with self.assertRaisesRegex(StateError, 'ambiguous'):
            choose_notice([self.message, changed], 'group', 'owner', self.now, FORM_HASH)
        with self.assertRaisesRegex(StateError, 'already_passed'):
            choose_notice([self.message], 'group', 'owner', EXPECTED_DUE + 1, FORM_HASH)

    def test_duplicate_forwards_choose_one_original_notice(self):
        repeat = {**self.message, 'createTime': '2026-10-23T06:00:00Z'}
        chosen = choose_notice([repeat, self.message], 'group', 'owner', self.now, FORM_HASH)
        self.assertEqual(chosen['source'], self.notice['source'])

    def test_only_target_is_restored_once_without_changing_existing_outbox(self):
        protected = self.db.execute('SELECT * FROM outbox').fetchall()
        result = self.restore()
        self.assertTrue(result['created'])
        self.assertEqual(result['pending_private_recipients'], 3)
        self.assertEqual(result['deadline'], '2026-10-25T22:00:00+07:00')
        self.assertEqual(result['next_reminder'], '2026-10-25T08:00:00+07:00')
        self.assertEqual(result['messages_sent'], 0)
        self.assertEqual(self.db.execute('SELECT * FROM outbox').fetchall(), protected)
        self.restore()
        self.assertEqual(self.db.execute('SELECT count(*) FROM tasks').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM assignments').fetchone()[0], 3)
        self.assertEqual(self.source.events[-1]['original'], self.notice['text'])

    def test_cancellation_and_completed_assignments_are_not_reset(self):
        self.restore()
        task_id = self.db.execute('SELECT id FROM tasks').fetchone()[0]
        self.db.execute('UPDATE assignments SET done_at=? WHERE task_id=? AND staff_id=?', (self.now, task_id, 'trainer-1'))
        self.db.commit()
        result = self.restore()
        self.assertEqual(result['pending_private_recipients'], 2)
        self.assertEqual(self.source.events[-1]['done']['trainer-1'], self.now)
        self.db.execute('UPDATE tasks SET cancelled=1 WHERE id=?', (task_id,)); self.db.commit()
        count = len(self.source.events)
        with self.assertRaisesRegex(StateError, 'cancelled'):
            self.restore()
        self.assertEqual(len(self.source.events), count)

    def test_unconfirmed_private_write_does_not_modify_the_local_schedule(self):
        with self.assertRaisesRegex(StateError, 'readback_mismatch'):
            restore_selected(self.db, self.state, self.recipients, self.notice, self.source, self.now,
                             readback=lambda source, event: {})
        self.assertEqual(self.db.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT status FROM outbox').fetchone()[0], 'accepted')


if __name__ == '__main__': unittest.main()
