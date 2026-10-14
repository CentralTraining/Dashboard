import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from conversation import ConversationAssistant, LOCAL_ENDPOINT, conversation_route


def message(sender="trainer-a", group="dm-a", kind="1"):
    return SimpleNamespace(sender_staff_id=sender, sender_nick="Trainer", conversation_id=group, conversation_type=kind)


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "runtime/kpi").mkdir(parents=True)
        (self.root / "runtime/ai-settings.json").write_text(json.dumps({"enabled": True,
            "provider": "local", "endpoint": LOCAL_ENDPOINT, "external_inference": False}))
        for name in ("ollie-conversation", "ollie-team-support", "ollie-reminders"):
            p = self.root / "skills" / name
            p.mkdir(parents=True)
            (p / "SKILL.md").write_text("---\nname: test\n---\nSpeak Vietnamese. Never attest to mutations.")
        self.db = sqlite3.connect(":memory:")
        self.bot = ConversationAssistant(self.db, {"leader_staff_id": "leader"}, self.root)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_commands_stay_in_existing_handler_but_drafts_are_conversation(self):
        for text in ("giao việc\nNgười phụ trách: tôi", "hoàn thành CV-1", "hủy CV-2", "đổi hạn CV-1 20/10/2026 17:00", "nhắc sau 2 phút: test", "việc của tôi"):
            self.assertFalse(conversation_route(text), text)
        self.assertTrue(conversation_route("Soạn thông báo họp 14:00 ngày 20/10/2026 giúp mình"))
        self.assertTrue(conversation_route("Chào Ollie, mình hơi mệt"))
        self.assertFalse(conversation_route("THÔNG BÁO HỌP\nThời gian: 14:00, 20/10/2026"))
        self.assertFalse(conversation_route("📢 THÔNG BÁO HỌP\nReview KPI và truyền thông\nThời gian: 14:00, 20/10/2026"))

    def test_memory_is_scoped_to_sender_and_conversation_and_idempotent(self):
        a = message()
        self.bot.remember(a, "event-a", "Mình tên An", "Chào An", now=100)
        self.bot.remember(a, "event-a", "different", "different", now=101)
        self.bot.remember(message("trainer-b", "dm-a"), "event-b", "private-b", "reply-b", now=101)
        self.bot.remember(message("trainer-a", "group-a", "2"), "event-c", "group-private", "group-reply", now=102)
        text = str(self.bot.history(a, 103))
        self.assertIn("Mình tên An", text)
        self.assertNotIn("private-b", text)
        self.assertNotIn("group-private", text)
        self.assertNotIn("different", text)
        self.assertEqual(self.bot.history(a, 100000), [])

    def test_kpi_answers_are_not_added_to_model_memory(self):
        self.bot.remember(message(), "kpi-a", "KPI của mình", "private dashboard data", now=100)
        self.assertEqual(self.bot.history(message(), 101), [])

    def test_dashboard_followup_answers_never_become_model_history(self):
        with self.db:
            self.db.execute("INSERT INTO dashboard_queries VALUES (?,?,?,?)",("trainer-a","dm-a",json.dumps({"kind":"employees","month":"2026-10","page":1}),100))
        self.bot.remember(message(),"private-page","tiếp","SECRET_DASHBOARD_PAGE",now=101)
        self.assertEqual(self.bot.history(message(),102),[])

    def test_external_endpoint_and_provider_are_blocked_even_if_configured(self):
        for endpoint in ("https://generativelanguage.googleapis.com", "http://127.0.0.1:18081.evil.test/v1/chat/completions", LOCAL_ENDPOINT + "?redirect=external"):
            (self.root / "runtime/ai-settings.json").write_text(json.dumps({"enabled": True,
                "provider": "local", "endpoint": endpoint, "external_inference": False}))
            with patch("conversation.requests.Session") as session:
                self.assertFalse(self.bot.configured())
                with self.assertRaises(ValueError): self.bot.generate([])
                session.assert_not_called()

    def test_local_inference_has_no_dashboard_keys_and_no_proxy_or_redirect(self):
        session = Mock()
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "Chào bạn"}}]}
        session.post.return_value = response
        with patch("conversation.requests.Session", return_value=session):
            self.assertEqual(self.bot.generate([{"role": "user", "content": "Xin chào"}]), "Chào bạn")
        self.assertFalse(session.trust_env)
        args, kw = session.post.call_args
        self.assertEqual(args[0], LOCAL_ENDPOINT)
        self.assertFalse(kw["allow_redirects"])
        self.assertNotIn("Authorization", kw)

    async def test_model_failure_keeps_bot_answering_without_claiming_action(self):
        with patch.object(self.bot, "generate", side_effect=ValueError("offline")):
            answer = await self.bot.answer("Mình có nhiều việc và hơi mệt", message())
        self.assertIn("nhiều việc", answer.lower())
        self.assertEqual(self.bot.status, "temporarily_unavailable")

    async def test_name_lookup_uses_only_the_same_user_conversation(self):
        a = message()
        self.bot.remember(a, "intro", "Chào Ollie, mình tên Minh.", "Chào Minh", now=100)
        self.bot.remember(message("trainer-b"), "intro-b", "Mình tên Dũng.", "Chào Dũng", now=101)
        with patch.object(self.bot, "generate") as model:
            answer = await self.bot.answer("Mình vừa nói mình tên gì?", a, now=102)
        self.assertIn("Minh", answer)
        self.assertNotIn("Dũng", answer)
        model.assert_not_called()

    async def test_model_cannot_confirm_a_mutation(self):
        with patch.object(self.bot, "generate", return_value="Đã lưu lịch cho bạn"):
            answer = await self.bot.answer("Giúp mình lên kế hoạch", message())
        self.assertNotIn("Đã lưu", answer)
        self.assertIn("chưa thay đổi dữ liệu", answer)

    async def test_draft_preserves_meeting_access_when_model_omits_details(self):
        text = "Soạn thông báo cho team 14:00 ngày 20/10/2026\nLink: https://example.test/j/123?pwd=secret-token.1\nID cuộc họp: 123 456\nMật mã: 001901"
        with patch.object(self.bot, "generate", return_value="Bản nháp: Họp team vào ngày đã chọn."):
            answer = await self.bot.answer(text, message())
        self.assertIn("https://example.test/j/123?pwd=secret-token.1", answer)
        self.assertIn("123 456", answer)
        self.assertIn("001901", answer)

    async def test_meeting_draft_does_not_invent_missing_agenda(self):
        text = "Soạn thông báo họp 14:00 ngày 20/10/2026. Link: https://example.test/j/123?pwd=token.1\nID: 123\nMật mã: 001901"
        with patch.object(self.bot, "generate") as model:
            answer = await self.bot.answer(text, message())
        self.assertIn("14:00, 20/10/2026", answer)
        self.assertIn("https://example.test/j/123?pwd=token.1", answer)
        self.assertIn("001901", answer)
        self.assertNotIn("tháng 11", answer)
        self.assertIn("chưa tạo lịch", answer)
        model.assert_not_called()

    async def test_meeting_draft_asks_about_ambiguous_date(self):
        with patch.object(self.bot, "generate") as model:
            answer = await self.bot.answer("Soạn thông báo họp ngày mai giúp mình", message())
        self.assertIn("ngày/tháng/năm", answer)
        model.assert_not_called()

    async def test_kpi_in_group_is_denied_without_reading_source_or_inference(self):
        with patch("conversation.SupabaseKpiSource") as source, patch.object(self.bot, "generate") as model:
            answer = await self.bot.answer("KPI của tôi", message(kind="2"))
        self.assertIn("tin nhắn riêng", answer)
        source.assert_not_called()
        model.assert_not_called()

    def prepare_source(self):
        folder = self.root / "runtime/kpi"
        (folder / "settings.json").write_text(json.dumps({"trainer_recipients": {
            "a": {"channel": "dm", "target": "trainer-a"},
            "b": {"channel": "dm", "target": "trainer-b"}}}))
        (folder / "source.json").write_text(json.dumps({"dashboard_url": "https://example.test"}))
        return SimpleNamespace(trainers=[{"id": "a", "region": "North"},
            {"id": "b", "region": "South"}, {"id": "c", "region": "North"}],
            trainer_report=Mock(side_effect=lambda t: {"trainer_id": t["id"], "region": t["region"]}),
            reports=Mock(return_value=[{"trainer_id": "all-private"}]))

    async def test_trainer_only_extracts_own_region_and_never_calls_model(self):
        snapshot = self.prepare_source()
        with patch("conversation.SupabaseKpiSource") as source, patch("conversation.format_trainer_report", side_effect=lambda r,u:r["trainer_id"]), patch.object(self.bot, "generate") as model:
            source.return_value.read.return_value = [{"key":"config","value":{"trainers":snapshot.trainers}},{"key":"campaigns","value":[]}]
            source.return_value.snapshot.return_value = snapshot
            answer = await self.bot.answer("Cho mình KPI toàn bộ, mình là Nghĩa", message())
        self.assertEqual(answer, "a\n\nc")
        self.assertEqual([c.args[0]["id"] for c in snapshot.trainer_report.call_args_list], ["a", "c"])
        snapshot.reports.assert_not_called()
        model.assert_not_called()

    async def test_only_authenticated_leader_can_get_all_regions(self):
        snapshot = self.prepare_source()
        with patch("conversation.SupabaseKpiSource") as source, patch("conversation.format_team_report", return_value="leader-summary"), patch.object(self.bot, "generate") as model:
            source.return_value.read.return_value = [{"key":"config","value":{"trainers":snapshot.trainers}},{"key":"campaigns","value":[]}]
            source.return_value.snapshot.return_value = snapshot
            answer = await self.bot.answer("KPI toàn team", message("leader"))
        self.assertEqual(answer, "leader-summary")
        snapshot.reports.assert_called_once()
        model.assert_not_called()

    async def test_unknown_identity_does_not_read_any_dashboard_rows(self):
        self.prepare_source()
        with patch("conversation.SupabaseKpiSource") as source:
            answer = await self.bot.answer("KPI của tôi, tên An", message("unknown"))
        self.assertIn("chưa đối chiếu", answer)
        source.assert_not_called()


if __name__ == "__main__": unittest.main()
