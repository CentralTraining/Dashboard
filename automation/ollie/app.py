"""Ollie_MT: Vietnamese task commands and persistent scheduled reminders."""

import asyncio
import json
import logging
import os
import signal
import socket
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from zoneinfo import ZoneInfo

import dingtalk_stream
import requests
import websockets
from tracker import Tracker, DingTalkSender, DeliveryError
from kpi import KpiSourceError
from kpi_scheduler import KpiBridge
from deadline_scheduler import configure_deadline_policy, sync_deadlines
from deadline_source import DeadlineSource
from conversation import ConversationAssistant, conversation_route
from local_chat_service import supervise as supervise_local_chat
from knowledge import attachments

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")
STATE_PATH = Path("/workspace/dingtalk-tools/connection-state.json")
CREDENTIALS_PATH = Path("/workspace/dingtalk-tools/config/ollie-app-credentials.json")


def write_health(connected, **extra):
    target = RUNTIME / "health.json"
    previous = {}
    if target.exists():
        previous = json.loads(target.read_text())
        if previous.get("pid") != os.getpid():
            previous = {}
    value = {**previous, "connected": connected, "pid": os.getpid(),
             "updated_at": datetime.now(VIETNAM).isoformat(), **extra}
    if connected:
        value.pop("error_type", None)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False))
    temp.chmod(0o600)
    os.replace(temp, target)


class ResponseHandler(dingtalk_stream.ChatbotHandler):
    def __init__(self, state, database, tracker):
        super().__init__()
        self.state = state
        self.database = database
        self.tracker = tracker
        self.conversation = ConversationAssistant(database, state, ROOT)
        self.logger = logging.getLogger("ollie.sdk")

    async def process(self, callback):
        incoming = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        if incoming.robot_code and incoming.robot_code != self.state["robot_code"]:
            return dingtalk_stream.AckMessage.STATUS_OK, "ignored"
        if incoming.chatbot_corp_id and incoming.chatbot_corp_id != self.state["profile"].split(":")[0]:
            return dingtalk_stream.AckMessage.STATUS_OK, "ignored"
        allowed_groups = self.state.get("source_conversation_ids", [self.state["conversation_id"]])
        if str(incoming.conversation_type) == "2" and incoming.conversation_id not in allowed_groups:
            return dingtalk_stream.AckMessage.STATUS_OK, "ignored"
        event_id = incoming.message_id or callback.headers.message_id
        if not event_id:
            return 500, "missing message identity"
        existing = self.database.execute(
            "SELECT response, delivered_at FROM replies WHERE event_id = ?", (event_id,)
        ).fetchone()
        if existing and existing[1] is not None:
            return dingtalk_stream.AckMessage.STATUS_OK, "already delivered"
        text = incoming.text.content if incoming.text else ""
        if not text and incoming.rich_text_content:
            text = "".join(item.get("text", "") for item in
                           (incoming.rich_text_content.rich_text_list or []) if isinstance(item, dict))
        incoming.original_text = text
        files=attachments(callback.data)
        if existing:
            answer = existing[0]
        elif files and (not text.strip() or conversation_route(text)):
            incoming.knowledge_answer=True
            answer=self.conversation.knowledge.queue(files,incoming,event_id)
        elif conversation_route(text):
            answer = await self.conversation.answer(text, incoming)
        else:
            answer = self.tracker.handle(text, incoming, event_id)
        if not existing:
            self.database.execute(
                "INSERT INTO replies VALUES (?, ?, ?, ?, ?, NULL)",
                (event_id, time.time(), incoming.sender_staff_id, incoming.conversation_id, answer),
            )
            self.database.commit()
        try:
            await asyncio.to_thread(self.send_response, incoming, answer)
        except Exception as exc:
            logging.getLogger("ollie").error("Reply failed: %s", type(exc).__name__)
            return 500, "reply failed"
        self.database.execute("UPDATE replies SET delivered_at = ? WHERE event_id = ?",
                              (time.time(), event_id))
        self.database.commit()
        self.conversation.remember(incoming, event_id, text, answer)
        logging.getLogger("ollie").info("A new message received a Vietnamese reply")
        write_health(True, last_reply_at=datetime.now(VIETNAM).isoformat(),
                     conversation_status=self.conversation.status,
                     external_inference=False, conversation_skills=4)
        return dingtalk_stream.AckMessage.STATUS_OK, "OK"

    @staticmethod
    def send_response(incoming, answer):
        parsed = urlparse(incoming.session_webhook or "")
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".dingtalk.com"):
            raise ValueError("Unexpected session reply destination")
        payload = {"msgtype": "text", "text": {"content": answer}}
        if incoming.sender_staff_id:
            payload["at"] = {"atUserIds": [incoming.sender_staff_id], "isAtAll": False}
        response = requests.post(incoming.session_webhook, json=payload,
                                 timeout=20, allow_redirects=False)
        if not response.ok:
            raise RuntimeError("Reply HTTP request rejected")
        if response.json().get("errcode") != 0:
            raise RuntimeError("DingTalk rejected the reply")


class ResponseClient(dingtalk_stream.DingTalkStreamClient):
    async def start_service(self):
        self.pre_start()
        while True:
            try:
                connection = await asyncio.to_thread(self.open_stream)
                uri = connection["endpoint"] + "?ticket=" + quote_plus(connection["ticket"])
                async with websockets.connect(uri, open_timeout=20,
                                              ping_interval=20, ping_timeout=20) as websocket:
                    self.websocket = websocket
                    self.stream_connected = True
                    write_health(True, response_service="running", task_scheduler="running", version="private-deadlines-v13", external_inference=False,
                                 dashboard_qa="read_only", dashboard_delivery="private", dashboard_scope="verified_account_region",knowledge_files="offline_curated")
                    logging.getLogger("ollie").info("Ollie_MT Stream connected")
                    async for raw in websocket:
                        result = await self.route_message(json.loads(raw))
                        if result == self.TAG_DISCONNECT:
                            break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                write_health(False, error_type=type(exc).__name__)
                logging.getLogger("ollie").warning("Stream reconnecting: %s", type(exc).__name__)
                await asyncio.sleep(5)
            finally:
                self.stream_connected = False
                self.websocket = None

    def open_stream(self):
        response = requests.post(self.OPEN_CONNECTION_API, json={
            "clientId": self.credential.client_id,
            "clientSecret": self.credential.client_secret,
            "subscriptions": [{"type": "CALLBACK", "topic": topic}
                              for topic in self.callback_handler_map],
            "ua": "ollie-trainer-bot/0.1",
            "localIp": socket.gethostbyname(socket.gethostname()),
        }, timeout=25)
        if not response.ok:
            raise RuntimeError("Gateway rejected connection")
        result = response.json()
        if not result.get("ticket") or not result.get("endpoint", "").startswith("wss://"):
            raise RuntimeError("Gateway connection was not established")
        return result


async def scheduled_reminders(tracker, sender, kpi_bridge=None):
    logger = logging.getLogger("ollie")
    while True:
        try:
            now = time.time()
            if kpi_bridge is not None:
                try:
                    await kpi_bridge.prepare(now)
                except KpiSourceError as exc:
                    logger.warning("KPI waiting: %s", str(exc))
                except Exception as exc:
                    logger.warning("KPI cycle failed: %s", type(exc).__name__)
            tracker.prepare_jobs(now, include_daily=tracker.state.get('daily_provider') != 'GitHub Actions')
            for job in tracker.next_jobs(now):
                content = tracker.job_content(job, time.time())
                if not content:
                    if tracker.settings()["enabled"]:
                        tracker.finish_job(job[0], "skipped", time.time())
                    continue
                if not tracker.begin_job(job[0], time.time()):
                    continue
                try:
                    receipt = await asyncio.to_thread(sender.send, job[3], job[4], content)
                except DeliveryError as exc:
                    status = "unknown" if exc.ambiguous else "retry"
                    tracker.finish_job(job[0], status, time.time(), error=exc.code)
                    logger.warning("Reminder %s: %s", status, exc.code)
                except Exception as exc:
                    tracker.finish_job(job[0], "unknown", time.time(), error=type(exc).__name__)
                    logger.warning("Reminder result uncertain: %s", type(exc).__name__)
                else:
                    tracker.finish_job(job[0], "accepted", time.time(), receipt=receipt)
                    logger.info("DingTalk accepted a scheduled %s reminder", job[3])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Reminder cycle failed: %s", type(exc).__name__)
        await asyncio.sleep(10)


async def daily_greetings():
    from greetings import GreetingRunner
    runner = None
    while True:
        try:
            if runner is None:
                runner = GreetingRunner()
            await asyncio.to_thread(runner.step)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.getLogger("ollie").warning("Greeting cycle failed: %s", type(exc).__name__)
        await asyncio.sleep(2)


async def refresh_configuration(state):
    mutable = ("conversation_id", "source_conversation_ids", "audience_staff_ids",
               "notification_group_name", "allowed_open_dingtalk_ids", 'daily_provider')
    while True:
        fresh = json.loads(STATE_PATH.read_text())
        for key in mutable:
            if key in fresh:
                state[key] = fresh[key]
        await asyncio.sleep(2)


async def synchronize_notices(tracker, config, client):
    logger = logging.getLogger('ollie')
    source = DeadlineSource(config['source'], config['ledger_key'], config['state']['conversation_id'])
    while True:
        try:
            rows = tracker.db.execute('SELECT event_id,payload FROM task_events WHERE synced_at IS NULL ORDER BY recorded_at,event_id LIMIT 100').fetchall()
            for event_id, payload in rows:
                await asyncio.to_thread(source.write_event, json.loads(payload))
                tracker.db.execute('UPDATE task_events SET synced_at=? WHERE event_id=?', (time.time(), event_id))
                tracker.db.commit()
            await sync_deadlines(tracker, config, time.time())
            write_health(bool(getattr(client, 'stream_connected', False)), notice_sync_ok=True, notice_sync_at=datetime.now(VIETNAM).isoformat())
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning('Notice sync waiting: %s', str(error) if isinstance(error, KpiSourceError) else type(error).__name__)
            write_health(bool(getattr(client, 'stream_connected', False)), notice_sync_ok=False)
        await asyncio.sleep(30)


async def main():
    os.umask(0o077)
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    RUNTIME.chmod(0o700)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # SDK logging can include temporary connection tickets or session webhook URLs.
    sdk_logger = logging.getLogger("ollie.sdk")
    sdk_logger.addHandler(logging.NullHandler())
    sdk_logger.propagate = False
    sdk_logger.disabled = True
    state = json.loads(STATE_PATH.read_text())
    credentials = json.loads(CREDENTIALS_PATH.read_text())["data"]
    if credentials["appKey"] != state["robot_code"]:
        raise RuntimeError("Credentials do not match Ollie_MT")
    database = sqlite3.connect(RUNTIME / "responses.sqlite3")
    database.execute("""CREATE TABLE IF NOT EXISTS replies (
        event_id TEXT PRIMARY KEY, received_at REAL NOT NULL, sender_id TEXT,
        conversation_id TEXT, response TEXT NOT NULL, delivered_at REAL)""")
    database.commit()
    tracker = Tracker(database, state)
    configure_deadline_policy(tracker)
    kpi_bridge = KpiBridge(database, state, RUNTIME / "kpi") if (RUNTIME / "kpi/source.json").exists() else None
    client = ResponseClient(dingtalk_stream.Credential(
        credentials["appKey"], credentials["appSecret"]), logger=sdk_logger)
    handler=ResponseHandler(state, database, tracker)
    client.register_callback_handler(dingtalk_stream.ChatbotMessage.TOPIC,handler)
    client.system_handler.logger = sdk_logger
    client.event_handler.logger = sdk_logger
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    tasks = [asyncio.create_task(client.start_service()),
             asyncio.create_task(scheduled_reminders(tracker, DingTalkSender(credentials, state), kpi_bridge)),
             asyncio.create_task(refresh_configuration(state)),
             asyncio.create_task(handler.conversation.knowledge.run(DingTalkSender(credentials,state))),
             asyncio.create_task(supervise_local_chat(ROOT))]
    config_path = Path(os.environ.get('OLLIE_CONFIG_FILE', str(ROOT / 'runtime/github/OLLIE_KPI_CONFIG_JSON.txt')))
    if config_path.exists():
        task_config = json.loads(config_path.read_text())
        tasks.append(asyncio.create_task(synchronize_notices(tracker, task_config, client)))
    if (RUNTIME / "greeting-schedule.json").exists():
        tasks.append(asyncio.create_task(daily_greetings()))
    await stop.wait()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    write_health(False, response_service="stopped", task_scheduler="stopped")
    database.close()


if __name__ == "__main__":
    asyncio.run(main())
