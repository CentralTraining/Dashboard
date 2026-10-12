import json
import sqlite3
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tracker import Tracker, DingTalkSender, DeliveryError, VIETNAM


def stamp(day, hour=12, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=VIETNAM).timestamp()


def incoming(sender="owner", mentions=()):
    return SimpleNamespace(sender_staff_id=sender, sender_nick=sender,
        chatbot_user_id="bot-id", at_users=[SimpleNamespace(staff_id=sid, dingtalk_id=did) for sid,did in mentions])


class TaskChecks(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.state = {"leader_staff_id":"owner", "leader_name":"Leader",
                      "conversation_id":"configured-group", "robot_code":"configured-bot"}
        self.tracker = Tracker(self.db, self.state)

    def tearDown(self):
        self.db.close()

    def create(self, assignee="tôi", sender=None, event="task-1", deadline="20/10/2026 17:00", now=None):
        return self.tracker.handle(f"giao việc\nNgười phụ trách: {assignee}\nNội dung: Nộp báo cáo\nDeadline: {deadline}",
                                   sender or incoming(), event, now=now or stamp(11))

    def test_invalid_date_and_unauthorized_sender_do_not_save(self):
        self.assertIn("cả ngày và giờ", self.create(deadline="20/10/2026"))
        self.assertIn("Chỉ leader", self.create(sender=incoming("trainer")))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)

    def test_duplicate_creation_and_restart_preserve_one_task(self):
        self.assertIn("Đã lưu CV-1", self.create())
        self.create()
        restarted = Tracker(self.db, self.state)
        self.assertEqual(len(restarted.pending_tasks()), 1)
        self.assertIn("CV-1", restarted.task_list("owner", stamp(11)))

    def test_calendar_days_vietnam_hour_and_both_destinations(self):
        self.create()
        self.tracker.prepare_jobs(stamp(15, 23))
        self.assertEqual(self.tracker.next_jobs(stamp(15, 23)), [])
        self.tracker.prepare_jobs(stamp(16, 7, 59))
        self.assertEqual(self.tracker.next_jobs(stamp(16, 7, 59)), [])
        self.tracker.prepare_jobs(stamp(16, 8))
        jobs = self.tracker.next_jobs(stamp(16, 8))
        self.assertEqual({(j[3],j[4]) for j in jobs}, {("group","configured-group"),("dm","owner")})
        for j in jobs:
            self.tracker.begin_job(j[0], stamp(16,8))
            self.tracker.finish_job(j[0], "accepted", stamp(16,8), receipt="receipt")
        self.tracker.prepare_jobs(stamp(16, 9))
        self.assertEqual(self.tracker.next_jobs(stamp(16, 9)), [])
        self.tracker.prepare_jobs(stamp(17, 8))
        self.assertEqual(len(self.tracker.next_jobs(stamp(17, 8))), 2)

    def test_task_created_after_eight_waits_until_next_morning(self):
        result = self.create(deadline="13/10/2026 17:00")
        self.assertIn("08:00 ngày 12/10/2026", result)
        self.tracker.prepare_jobs(stamp(11,13))
        self.assertEqual(self.tracker.next_jobs(stamp(11,13)), [])
        self.tracker.prepare_jobs(stamp(12,8))
        self.assertEqual(len(self.tracker.next_jobs(stamp(12,8))), 2)

    def test_each_trainer_has_independent_completion(self):
        sender = incoming(mentions=(("amy","amy-id"),("binh","binh-id"),("bot","bot-id")))
        self.create("@Amy, @Bình", sender=sender)
        self.tracker.handle("hoàn thành CV-1", incoming("amy"), "complete", now=stamp(15))
        self.assertEqual([r[3] for r in self.tracker.pending_tasks()], ["binh"])
        self.assertIn("chưa được phân công", self.tracker.handle("hoàn thành CV-1", incoming("outsider"), "other"))
        self.tracker.prepare_jobs(stamp(16,8))
        self.assertEqual({j[4] for j in self.tracker.next_jobs(stamp(16,8))}, {"configured-group","binh","owner"})

    def test_reminders_stop_at_deadline_even_if_queued_earlier(self):
        self.create()
        self.tracker.prepare_jobs(stamp(20,8))
        jobs=self.tracker.next_jobs(stamp(20,8))
        self.assertEqual(len(jobs),2)
        self.assertTrue(all(self.tracker.job_content(j,stamp(20,17)) is None for j in jobs))
        self.tracker.prepare_jobs(stamp(21,8))
        self.assertEqual(self.tracker.due_tasks(datetime(2026,10,21).date(),now=stamp(21,8)),[])

    def test_group_digest_numbers_tasks_once_and_leader_receives_all(self):
        self.create('@Bình',sender=incoming(mentions=(("binh","binh-id"),)),event='later',deadline='20/10/2026 17:00')
        self.create('@Amy',sender=incoming(mentions=(("amy","amy-id"),)),event='earlier',deadline='18/10/2026 17:00')
        self.tracker.prepare_jobs(stamp(16,8))
        jobs=self.tracker.next_jobs(stamp(16,8))
        leader_job=next(j for j in jobs if j[3]=='dm' and j[4]=='owner')
        content=self.tracker.job_content(leader_job,stamp(16,8))
        self.assertIn('1. Nộp báo cáo',content)
        self.assertIn('2. Nộp báo cáo',content)
        self.assertLess(content.index('18/10/2026'), content.index('20/10/2026'))

    def test_announcements_assign_everyone_and_leader(self):
        self.state['audience_staff_ids']=['amy','binh']
        url='https://example.zoom.us/j/12345678901?pwd=test%2Btoken.1'
        text='THÔNG BÁO HỌP TRAINER TOÀN QUỐC\n+ Truyền thông OPPO A7 Pro\n+ Kế hoạch content Buds3s\nThời gian: 14:00, 20/10/2026\nHình thức: Online qua Zoom'+f'\nLink Zoom: {url}\nID cuộc họp: 123 4567 8901\nMật mã: 001901'
        result=self.tracker.handle(text,incoming(),'meeting',now=stamp(11))
        self.assertIn('Đã lưu CV-1',result)
        self.assertEqual({r[3] for r in self.tracker.pending_tasks()},{'amy','binh','owner'})
        self.assertEqual(len(self.tracker.group_tasks(self.tracker.pending_tasks())),1)
        self.tracker.prepare_jobs(stamp(16,8))
        for job in self.tracker.next_jobs(stamp(16,8)):
            content=self.tracker.job_content(job,stamp(16,8))
            self.assertIn(url,content)
            self.assertIn('ID cuộc họp: 123 4567 8901',content)
            self.assertIn('Mật mã: 001901',content)

    def test_announcement_without_roster_does_not_claim_scheduled(self):
        text='THÔNG BÁO HỌP TRAINER\nThời gian: 14:00, 20/10/2026'
        result=self.tracker.handle(text,incoming(),'meeting',now=stamp(11))
        self.assertIn('Chưa tạo lịch nhắc',result)
        self.assertEqual(self.tracker.pending_tasks(),[])

    def test_completion_or_deadline_change_removes_queued_reminder_content(self):
        self.create()
        self.tracker.prepare_jobs(stamp(16,8))
        jobs = self.tracker.next_jobs(stamp(16,8))
        self.tracker.handle("đổi hạn CV-1 30/10/2026 17:00", incoming(), "change", now=stamp(16,8))
        self.assertTrue(all(self.tracker.job_content(j,stamp(16,8)) is None for j in jobs))
        self.tracker.handle("hoàn thành CV-1", incoming(), "done")
        self.assertEqual(self.tracker.pending_tasks(), [])

    def test_one_off_reminder_cancel_pause_and_uncertain_send(self):
        answer = self.tracker.handle("nhắc sau 2 phút: Kiểm tra Ollie_MT", incoming(), "alert", now=stamp(11))
        self.assertIn("12:02 ngày 11/10/2026", answer)
        self.tracker.prepare_jobs(stamp(11,12,1))
        self.assertEqual(self.tracker.next_jobs(stamp(11,12,1)), [])
        self.tracker.prepare_jobs(stamp(11,12,2))
        jobs = self.tracker.next_jobs(stamp(11,12,2))
        self.assertEqual(len(jobs), 2)
        self.assertTrue(all(self.tracker.job_content(j,stamp(11,12,2)) == "Kiểm tra Ollie_MT"
                            for j in jobs))
        self.assertEqual(self.db.execute("SELECT staff_id,due_at FROM alerts WHERE id=1").fetchone(),
                         ("owner",stamp(11,12,2)))
        self.tracker.set_enabled(False)
        self.assertIsNone(self.tracker.job_content(jobs[0],stamp(11,12,2)))
        self.tracker.set_enabled(True)
        self.tracker.begin_job(jobs[0][0],stamp(11,12,2))
        restarted = Tracker(self.db,self.state)
        self.assertEqual(self.db.execute("SELECT status FROM outbox WHERE job_key=?",(jobs[0][0],)).fetchone()[0], "unknown")
        restarted.handle("hủy NR-1", incoming(), "cancel")
        self.assertIsNone(restarted.job_content(jobs[1],stamp(11,12,2)))


class SenderChecks(unittest.TestCase):
    def setUp(self):
        self.sender = DingTalkSender({"appKey":"key","appSecret":"secret"},
                                     {"conversation_id":"group","robot_code":"key"})

    @staticmethod
    def response(data, status=200):
        return SimpleNamespace(ok=status < 400, status_code=status, json=lambda: data)

    def test_api_routes_group_and_staff_id_and_requires_receipt(self):
        responses = [self.response({"accessToken":"token","expireIn":7200}),
                     self.response({"processQueryKey":"group-receipt"}),
                     self.response({"processQueryKey":"dm-receipt"})]
        with patch("tracker.requests.post", side_effect=responses) as post:
            self.assertEqual(self.sender.send("group","group","nhắc việc"),"group-receipt")
            self.assertEqual(self.sender.send("dm","trainer-staff-id","nhắc việc"),"dm-receipt")
            self.assertIn("groupMessages/send",post.call_args_list[1].args[0])
            self.assertEqual(post.call_args_list[2].kwargs["json"]["userIds"],["trainer-staff-id"])
            self.assertEqual(json.loads(post.call_args_list[2].kwargs["json"]["msgParam"])["content"],"nhắc việc")

    def test_rejected_recipient_is_not_accepted(self):
        self.sender.token="token"
        self.sender.token_until=10**12
        with patch("tracker.requests.post",return_value=self.response({"processQueryKey":"r","invalidStaffIdList":["bad"]})):
            with self.assertRaises(DeliveryError) as caught:
                self.sender.send("dm","bad","nhắc việc")
            self.assertFalse(caught.exception.ambiguous)

    def test_timeout_is_uncertain_without_automatic_resend(self):
        import requests
        self.sender.token="token"
        self.sender.token_until=10**12
        with patch("tracker.requests.post",side_effect=requests.Timeout) as post:
            with self.assertRaises(DeliveryError) as caught:
                self.sender.send("group","group","nhắc việc")
            self.assertTrue(caught.exception.ambiguous)
            self.assertEqual(post.call_count,1)


if __name__ == "__main__":
    unittest.main()
