import base64
import copy
from datetime import datetime
import json
import os
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from daily_digest import compact_links, format_deadline_digest, MarkdownMessage
from deadline_scheduler import configure_deadline_policy
from deadline_source import DeadlineSource, import_sources
from kpi import KpiSourceError
from tracker import Tracker, VIETNAM, DingTalkSender
from github_daily import deliver_jobs


def stamp(day, hour=12):
    return datetime(2026, 10, day, hour, tzinfo=VIETNAM).timestamp()


class DeadlineChecks(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.state = {'leader_staff_id': 'leader', 'leader_name': 'CENTRAL - T. Nghĩa',
                      'conversation_id': 'group', 'robot_code': 'bot', 'audience_staff_ids': ['do', 'cam']}
        self.tracker = Tracker(self.db, self.state)
        configure_deadline_policy(self.tracker)

    def tearDown(self): self.db.close()

    def test_next_morning_does_not_wait_for_four_day_window_or_send_same_morning(self):
        for hour in (7, 12):
            self.assertEqual(self.tracker.first_reminder(stamp(30), stamp(12, hour)), stamp(13, 8))

    def test_rotating_wish_is_stable_today_and_different_tomorrow(self):
        tasks = [(1, 'Nộp báo cáo', stamp(20), ['do'])]
        first = format_deadline_digest('ĐẶNG ANH ĐÔ', tasks, stamp(12))
        self.assertIsInstance(first, MarkdownMessage)
        self.assertIn('Xin chào Đô!', first)
        self.assertEqual(first, format_deadline_digest('ĐẶNG ANH ĐÔ', tasks, stamp(12, 8)))
        self.assertNotEqual(first.splitlines()[1], format_deadline_digest('Đô', tasks, stamp(13)).splitlines()[1])

    def test_complete_zoom_destination_id_and_passcode_survive_short_link(self):
        url = 'https://zoom.us/j/123?pwd=secret%2Btoken.1&source=team'
        text = compact_links(f'Họp Trainer\nLink Zoom: [{url}]({url})\nID cuộc họp: 123 456\nMật mã: 001901')
        self.assertEqual(text.count(url), 1)
        self.assertIn(f'**[Link]({url})**', text)
        self.assertIn('ID cuộc họp: 123 456', text)
        self.assertIn('Mật mã: 001901', text)

    def test_notice_has_original_and_durable_completion_event(self):
        incoming = SimpleNamespace(sender_staff_id='leader', sender_nick='Nghĩa', create_at=None,
                                   original_text='Original notice', at_users=[], chatbot_user_id='bot')
        self.tracker.handle('THÔNG BÁO TRIỂN KHAI\n- Mỗi Trainer nộp 2 video\nDeadline: 20/10/2026', incoming, 'create', now=stamp(12))
        self.assertEqual(self.db.execute('SELECT first_reminder_at FROM tasks').fetchone()[0], stamp(13,8))
        event=json.loads(self.db.execute('SELECT payload FROM task_events').fetchone()[0])
        self.assertEqual(event['original'], 'Original notice')
        self.tracker.complete_task(1, 'do', 'complete-do', stamp(13))
        event=json.loads(self.db.execute("SELECT payload FROM task_events WHERE event_id='complete-do'").fetchone()[0])
        self.assertIn('do',event['done'])
        self.assertNotIn('cam',event['done'])

    def test_dashboard_assignment_completion_and_edit_are_idempotent(self):
        task={'id':'abc','content':'Nộp 2 video','created_at':'2026-10-12T07:00:00+07:00',
              'deadline':'2026-10-20T17:00:00+07:00','trainer_ids':['a','b']}
        records=[{'key':'ollieTask:abc','value':task}]
        done={'ollieDone:abc:a':{'done':True}}
        source=SimpleNamespace(events=lambda:[],dashboard_tasks=lambda:(records,done))
        mapping={'a':{'target':'do'},'b':{'target':'cam'}}
        for _ in range(2): import_sources(self.tracker,source,mapping,{'a':'Đô','b':'Cảm'},stamp(13))
        self.assertEqual(self.db.execute('SELECT count(*) FROM tasks').fetchone()[0],1)
        self.assertEqual(self.tracker.pending_tasks('do'),[])
        self.assertEqual(len(self.tracker.pending_tasks('cam')),1)
        task['cancelled']=True
        import_sources(self.tracker,source,mapping,{},stamp(14))
        self.assertEqual(self.tracker.pending_tasks(),[])

    def test_missing_dashboard_deadline_is_not_invented(self):
        value={'id':'abc','content':'Nộp báo cáo','trainer_ids':['a'],'created_at':'2026-10-12T07:00:00+07:00'}
        source=SimpleNamespace(events=lambda:[],dashboard_tasks=lambda:([{'key':'ollieTask:abc','value':value}],{}))
        with self.assertRaisesRegex(KpiSourceError,'missing_deadline'):
            import_sources(self.tracker,source,{'a':{'target':'do'}},{},stamp(13))
        self.assertEqual(self.db.execute('SELECT count(*) FROM tasks').fetchone()[0],0)

    def test_leader_pause_is_persisted_without_changing_assignments(self):
        event={'event_id':'pause','operation':'settings','author':'leader','recorded_at':stamp(12),'enabled':False}
        source=SimpleNamespace(events=lambda:[event],dashboard_tasks=lambda:([],{}))
        import_sources(self.tracker,source,{}, {},stamp(13))
        self.assertFalse(self.tracker.settings()['enabled'])
        event={**event,'event_id':'resume','enabled':True}
        import_sources(self.tracker,source,{}, {},stamp(14))
        self.assertTrue(self.tracker.settings()['enabled'])

    def test_delivery_drains_more_than_twenty_destinations_once(self):
        for i in range(30):
            self.db.execute('INSERT INTO alerts (source_event,content,staff_id,due_at) VALUES (?,?,?,?)',
                            (str(i),'Content','do',1))
            self.tracker.add_job(str(i),'alert',str(i+1),'dm','do',1)
        self.db.commit()
        sender=Mock();sender.send.return_value='receipt';store=Mock()
        self.assertEqual(deliver_jobs(self.tracker,sender,store,stamp(13))['accepted'],30)
        self.assertEqual(deliver_jobs(self.tracker,sender,store,stamp(13))['accepted'],0)
        self.assertEqual(sender.send.call_count,30)


class NoticeCryptoChecks(unittest.TestCase):
    def test_private_original_round_trip_and_tampering_or_wrong_group_rejected(self):
        key=base64.b64encode(os.urandom(32)).decode()
        config={'url':'https://example.supabase.co','table':'kv_store','anon_key':'public'}
        source=DeadlineSource(config,key,'group')
        event={'event_id':'one','original':'Private Zoom password 000001'}
        sealed=source.seal(event)
        self.assertNotIn('000001',json.dumps(sealed))
        self.assertEqual(source.open(sealed),event)
        with self.assertRaisesRegex(KpiSourceError,'integrity'):
            DeadlineSource(config,key,'other-group').open(sealed)
        bad=copy.deepcopy(sealed);bad['sealed']=bad['sealed'][:-10]+'AAAAAAAAAA'
        with self.assertRaisesRegex(KpiSourceError,'integrity'): source.open(bad)


if __name__ == '__main__': unittest.main()
