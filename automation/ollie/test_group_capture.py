from datetime import datetime
import sqlite3
import unittest
from types import SimpleNamespace
from announcements import notice_source_id, parse_announcement
from deadline_scheduler import configure_deadline_policy
from github_daily import StateError
from group_capture import message_time, validate_history
from tracker import Tracker, VIETNAM


class GroupCaptureTests(unittest.TestCase):
    def test_relative_day_in_heading_and_clock_on_separate_line(self):
        posted = message_time("2026-10-12 00:30:00")
        _, due = parse_announcement("Mẫu nhắc việc ngày mai!\nNộp báo cáo tuần.\nThời gian : 20:25", posted)
        self.assertEqual(datetime.fromtimestamp(due, VIETNAM).isoformat(), "2026-10-12T20:25:00+07:00")
        with self.assertRaisesRegex(ValueError, "nhiều ngày"):
            parse_announcement("Hôm nay hoặc ngày mai\nNộp báo cáo.\nThời gian: 20:25", posted)

    def fixture(self):
        return {"complete": True, "partial": False, "hasMore": False, "failedCount": 0,
                "senderFilter": {"status": "applied", "applied": True},
                "resolvedFilters": {"senders": [{"status": "resolved", "selected": {"userId": "owner", "openDingTalkId": "opaque-owner"}}]},
                "messages": [{"senderId": "opaque-owner", "conversationId": "group", "text": "Nộp báo cáo"}]}

    def test_verified_sender_alias_and_group_are_required(self):
        data = self.fixture()
        self.assertEqual(len(validate_history(data, "owner", "group")), 1)
        data["messages"][0]["senderId"] = "another-trainer"
        with self.assertRaisesRegex(StateError, "scope_mismatch"):
            validate_history(data, "owner", "group")

    def test_partial_history_cannot_advance_capture(self):
        data = self.fixture()
        data["complete"] = False
        with self.assertRaisesRegex(StateError, "incomplete"):
            validate_history(data, "owner", "group")

    def test_cli_cst_message_timestamp_uses_original_vietnam_day(self):
        stamp = message_time("2026-10-13 00:30:00")
        self.assertEqual(datetime.fromtimestamp(stamp, VIETNAM).isoformat(), "2026-10-12T23:30:00+07:00")
        self.assertEqual(stamp, message_time("2026-10-12T16:30:00+00:00"))

    def test_plain_group_notice_captured_later_starts_next_original_morning_once(self):
        database = sqlite3.connect(":memory:")
        state = {"leader_staff_id": "owner", "leader_name": "Nghĩa",
                 "conversation_id": "group", "audience_staff_ids": ["trainer"]}
        tracker = Tracker(database, state)
        configure_deadline_policy(tracker)
        posted = message_time("2026-10-13 00:30:00")
        text = "Mỗi Trainer nộp báo cáo tuần.\nDeadline : 20/10/2026 17:00"
        incoming = SimpleNamespace(sender_staff_id="owner", create_at=posted * 1000,
                    conversation_type="2", conversation_id="group", original_text=text)
        for msg_id in ["stream-id", "history-id"]:
            tracker.handle(text, incoming, msg_id, now=posted + 3600)
        self.assertEqual(database.execute("SELECT count(*) FROM tasks").fetchone()[0], 1)
        first = database.execute("SELECT first_reminder_at FROM tasks").fetchone()[0]
        self.assertEqual(datetime.fromtimestamp(first, VIETNAM).isoformat(), "2026-10-13T08:00:00+07:00")
        self.assertEqual(database.execute("SELECT count(*) FROM assignments").fetchone()[0], 2)
        self.assertEqual(notice_source_id("group", "owner", posted, text),
                         notice_source_id("group", "owner", posted + .7, "@Ollie_MT " + text))
        database.close()

    def test_plain_giao_viec_heading_does_not_require_trainer_form(self):
        database = sqlite3.connect(":memory:")
        state = {"leader_staff_id": "owner", "leader_name": "Nghĩa",
                 "conversation_id": "group", "audience_staff_ids": ["trainer"]}
        tracker = Tracker(database, state)
        configure_deadline_policy(tracker)
        posted = message_time("2026-10-12 10:00:00")
        incoming = SimpleNamespace(sender_staff_id="owner", create_at=posted * 1000,
                                  conversation_type="2", conversation_id="group")
        tracker.handle("Giao việc cho Team\nMọi người nộp báo cáo.\nDeadline: 20/10/2026 17:00",
                       incoming, "plain", now=posted)
        self.assertEqual(database.execute("SELECT count(*) FROM tasks").fetchone()[0], 1)
        self.assertEqual(database.execute("SELECT count(*) FROM assignments").fetchone()[0], 2)
        database.close()
