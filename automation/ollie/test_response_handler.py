import sqlite3
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app import ResponseHandler
from tracker import Tracker


class ResponseHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root_patch=patch('app.ROOT',Path(self.temp.name));self.root_patch.start()
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE replies (event_id TEXT PRIMARY KEY, received_at REAL, sender_id TEXT, conversation_id TEXT, response TEXT, delivered_at REAL)")
        self.state = {"leader_staff_id": "owner", "leader_name": "Leader", "robot_code": "bot", "profile": "corp:user", "conversation_id": "group"}
        self.tracker = Tracker(self.db, self.state)
        self.handler = ResponseHandler(self.state, self.db, self.tracker)
        self.health = patch("app.write_health").start()
        self.send = patch.object(self.handler, "send_response").start()

    def tearDown(self):
        self.handler.conversation.knowledge.db.close()
        patch.stopall()
        self.db.close()
        self.temp.cleanup()

    def callback(self, text, event="event-1", sender="owner"):
        return SimpleNamespace(headers=SimpleNamespace(message_id=event), data={
            "msgId": event, "robotCode": "bot", "chatbotCorpId": "corp",
            "senderStaffId": sender, "senderNick": "Test", "conversationId": "dm",
            "conversationType": "1", "msgtype": "text", "text": {"content": text}})

    async def test_duplicate_callback_reuses_accepted_reply_without_model_or_send(self):
        self.handler.conversation.answer = AsyncMock(return_value="Chào bạn")
        callback = self.callback("Xin chào")
        await self.handler.process(callback)
        await self.handler.process(callback)
        self.handler.conversation.answer.assert_awaited_once()
        self.send.assert_called_once()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()[0], 1)

    async def test_failed_delivery_does_not_become_conversation_memory(self):
        self.handler.conversation.answer = AsyncMock(return_value="Chào bạn")
        self.send.side_effect = RuntimeError("rejected")
        status, _ = await self.handler.process(self.callback("Xin chào"))
        self.assertEqual(status, 500)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()[0], 0)
        self.assertIsNone(self.db.execute("SELECT delivered_at FROM replies").fetchone()[0])

    async def test_task_command_uses_existing_permissions_not_model(self):
        self.handler.conversation.answer = AsyncMock()
        callback = self.callback("giao việc\nNgười phụ trách: tôi\nNội dung: Nộp báo cáo\nDeadline: 20/10/2099 17:00", sender="trainer")
        await self.handler.process(callback)
        self.handler.conversation.answer.assert_not_awaited()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)
        self.assertIn("Chỉ leader", self.send.call_args.args[1])

    async def test_drafting_announcement_does_not_create_or_schedule_tasks(self):
        self.handler.conversation.answer = AsyncMock(return_value="Bản nháp thông báo họp")
        await self.handler.process(self.callback("Soạn thông báo họp 14:00 ngày 20/10/2099 giúp mình"))
        self.handler.conversation.answer.assert_awaited_once()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 0)

    async def test_file_upload_is_queued_once_and_is_not_a_chat_prompt_or_task(self):
        (self.handler.conversation.knowledge.folder/'settings.json').write_text('{"enabled":true}')
        callback=self.callback('')
        callback.data.update(msgtype='file',content={'downloadCode':'synthetic-ticket','fileName':'manual.docx'})
        self.handler.conversation.answer=AsyncMock()
        await self.handler.process(callback);await self.handler.process(callback)
        self.handler.conversation.answer.assert_not_awaited()
        self.assertEqual(self.handler.conversation.knowledge.db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tasks').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM conversation_turns').fetchone()[0],0)


if __name__ == "__main__": unittest.main()
