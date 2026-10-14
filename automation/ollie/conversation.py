"""Local conversation skills and read-only, account-scoped KPI answers.

Inference accepts only the fixed loopback service. No dashboard records are
included in model prompts; KPI replies use the existing deterministic formatter.
"""
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests

from announcements import has_deadline
from kpi import KpiSourceError, SupabaseKpiSource, format_team_report, format_trainer_report
from tracker import VIETNAM, folded

LOCAL_ENDPOINT = "http://127.0.0.1:18081/v1/chat/completions"
DASHBOARD = "https://centraltraining.github.io/Dashboard/"
SKILLS = ("ollie-conversation", "ollie-team-support", "ollie-reminders")


def clean_text(text):
    return re.sub(r"@Ollie_MT\b", "", text or "", flags=re.I).strip()


def is_kpi_question(text):
    command = folded(text)
    return any(re.search(r"\b" + word + r"\b", command) for word in
               ("kpi", "target", "dashboard", "tien do", "chi so", "doanh so"))


def conversation_route(text):
    """Keep existing mutations in the audited task handler, not in the LLM."""
    command = folded(clean_text(text))
    if re.match(r"^(?:giao viec|hoan thanh cv|doi han cv|huy (?:cv|nr)|nhac sau)\b", command):
        return False
    if command in ("dang ky trainer", "dang ky", "trang thai", "cai dat",
                   "danh sach", "viec cua toi", "bat nhac viec", "tat nhac viec"):
        return False
    draft = bool(re.search(r"\b(?:soan|viet|ban nhap)\b", command))
    question = draft or "?" in text or bool(re.match(
        r"^(?:giup|hay giup|lam sao|tai sao|sao |toi muon|minh muon|ban co|co the|cho toi|cho minh)", command))
    if not question and ("thong bao" in command or has_deadline(text)):
        return False
    return True


def meeting_draft(text):
    """Render supplied meeting facts without inventing an agenda or saving it."""
    command = folded(text)
    if not re.search(r"\b(?:soan|viet)\b", command) or not re.search(r"\bhop\b", command):
        return None
    day = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text)
    hour = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
    if not day or not hour:
        return "Buổi họp diễn ra ngày nào (ngày/tháng/năm) và lúc mấy giờ? Bạn gửi thêm để mình soạn đúng thời gian nhé."
    try:
        date = datetime.strptime(day[1], "%d/%m/%Y").strftime("%d/%m/%Y")
    except ValueError:
        return "Ngày họp chưa hợp lệ. Bạn kiểm tra lại ngày/tháng/năm nhé."
    lines = ["📢 THÔNG BÁO HỌP", "", "Dear anh em Trainer,",
             "Anh em sắp xếp tham gia buổi họp theo thông tin dưới đây nhé.",
             "", "⏰ Thời gian: " + f"{int(hour[1]):02}:{hour[2]}, {date}"]
    topics = re.findall(r"(?im)^\s*(?:[-+•]\s+|(?:Nội dung|Chủ đề)\s*:\s*)(.+)$", text)
    if topics:
        lines.extend(["", "Nội dung:", *["- " + topic.strip() for topic in topics]])
    urls = list(dict.fromkeys(url.rstrip(".,") for url in re.findall(r"https?://[^\s<>]+", text)))
    if urls:
        lines.extend(["💻 Hình thức: Online", *["🔗 Link: " + url for url in urls]])
    for label, value in re.findall(r"(?i)(ID(?: cuộc họp)?|Mật mã|passcode)\s*:\s*([^\n.;]+)", text):
        lines.append(label + ": " + value.strip())
    lines.extend(["", "Anh em tham gia đầy đủ và đúng giờ nhé!", "", "(Bản nháp; chưa tạo lịch nhắc.)"])
    return "\n".join(lines)


class ConversationAssistant:
    def __init__(self, database, state, root):
        self.db = database
        self.state = state
        self.root = Path(root)
        self.lock = asyncio.Lock()
        self.status = "not_configured"
        self.db.execute("""CREATE TABLE IF NOT EXISTS conversation_turns (
            event_id TEXT PRIMARY KEY, sender_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL, created_at REAL NOT NULL,
            question TEXT NOT NULL, answer TEXT NOT NULL)""")
        self.db.commit()

    def config(self):
        path = self.root / "runtime/ai-settings.json"
        if not path.exists():
            return {"enabled": False}
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            return {"enabled": False}

    def configured(self):
        c = self.config()
        return bool(c.get("enabled") and c.get("provider") == "local"
                    and c.get("endpoint") == LOCAL_ENDPOINT
                    and c.get("external_inference") is False)

    def scope(self, incoming):
        return (str(incoming.sender_staff_id or ""),
                str(getattr(incoming, "conversation_id", "") or "private"))

    def history(self, incoming, now):
        sender, conversation = self.scope(incoming)
        rows = self.db.execute("""SELECT question,answer FROM conversation_turns
            WHERE sender_id=? AND conversation_id=? AND created_at>?
            ORDER BY created_at DESC,event_id DESC LIMIT 3""",
            (sender, conversation, now - 86400)).fetchall()
        result = []
        for question, answer in reversed(rows):
            result.extend(({"role": "user", "content": question},
                           {"role": "assistant", "content": answer}))
        return result

    def remember(self, incoming, event_id, question, answer, now=None):
        if is_kpi_question(question) or not conversation_route(question):
            return
        now = time.time() if now is None else now
        sender, conversation = self.scope(incoming)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO conversation_turns VALUES (?,?,?,?,?,?)",
                (event_id, sender, conversation, now, clean_text(question)[:2000], answer[:2000]))
            self.db.execute("DELETE FROM conversation_turns WHERE created_at<?", (now - 7 * 86400,))

    def instructions(self, question=""):
        # The team adaptations are the active skills. Upstream examples remain
        # installed as attributed references, not instructions to read Slack.
        parts = []
        command = folded(question)
        active = ["ollie-conversation"]
        if any(word in command for word in ("soan", "viet", "thong bao", "san pham", "coaching")):
            active.append("ollie-team-support")
        if any(word in command for word in ("nhac", "deadline", "cong viec", "hoan thanh", "giao viec")):
            active.append("ollie-reminders")
        for name in active:
            text = (self.root / "skills" / name / "SKILL.md").read_text()
            text = text.split("\nVí dụ:", 1)[0]
            parts.append(re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S).strip())
        return "\n\n".join(parts) + ("\nAnswer the user's latest message directly in Vietnamese. "
            "Do not repeat a previous reply. When asked to draft, write the requested draft "
            "using the supplied facts. Do not claim an action has been performed. "
            "Use a neutral, helpful tone. Do not assume anyone is tired unless the user says so. "
            "Avoid gendered or romantic forms of address. Usually answer in 1 to 3 sentences.")

    async def answer(self, text, incoming, now=None):
        now = time.time() if now is None else now
        text = clean_text(text)
        if not incoming.sender_staff_id:
            return "Mình chưa xác định được tài khoản của bạn. Bạn gửi từ tài khoản DingTalk nội bộ nhé."
        draft = meeting_draft(text)
        if draft is not None:
            return draft
        if is_kpi_question(text):
            return await self.kpi_answer(incoming, now)
        if not self.configured():
            self.status = "not_configured"
            return self.fallback(text)
        async with self.lock:
            current = datetime.fromtimestamp(now, VIETNAM).strftime("%H:%M %d/%m/%Y")
            messages = [{"role": "system", "content": self.instructions(text)
                         + "\nThời điểm hiện tại theo giờ Việt Nam: " + current + "."}]
            messages.extend(self.history(incoming, now))
            messages.append({"role": "user", "content": text[:3000]})
            try:
                answer = await asyncio.to_thread(self.generate, messages)
            except (requests.RequestException, ValueError, KeyError, TypeError):
                self.status = "temporarily_unavailable"
                return self.fallback(text)
            # A conversation reply cannot attest to a task mutation or delivery.
            if re.search(r"\bda (?:luu|gui|dat lich|doi (?:han|deadline)|huy|cap nhat)\b", folded(answer)):
                answer = ("Mình có thể giúp chuẩn bị nội dung. Để thực hiện và nhận xác nhận, "
                          "hãy dùng lệnh giao việc hoặc đặt nhắc; phần trò chuyện chưa thay đổi dữ liệu.")
            else:
                # Keep original meeting access details even if a small local
                # model omits them while shortening a draft.
                details = []
                for url in re.findall(r"https?://[^\s<>]+", text):
                    url = url.rstrip(".,")
                    if url not in answer:
                        details.append("Link: " + url)
                for label, value in re.findall(r"(?i)(ID(?: cuộc họp)?|Mật mã|passcode)\s*:\s*([^\n.;]+)", text):
                    value = value.strip()
                    if value and value not in answer:
                        details.append(label + ": " + value)
                if details:
                    answer += "\n" + "\n".join(dict.fromkeys(details))
            self.status = "local_ready"
            return answer

    def generate(self, messages):
        c = self.config()
        if (not self.configured() or c.get("endpoint") != LOCAL_ENDPOINT):
            raise ValueError("External inference is disabled")
        session = requests.Session()
        # Loopback traffic stays on this machine instead of going to an HTTP proxy.
        session.trust_env = False
        try:
            headers = {}
            key_path = self.root / "runtime/local-ai/api-key.txt"
            if key_path.exists():
                headers["Authorization"] = "Bearer " + key_path.read_text().strip()
            response = session.post(LOCAL_ENDPOINT, headers=headers, json={
                "model": c.get("model", "ollie-local"), "messages": messages,
                "max_tokens": min(256, max(32, int(c.get("max_output_tokens", 128)))),
                "temperature": 0.6, "top_p": 0.9,
                "presence_penalty": 0.5,
                "chat_template_kwargs": {"enable_thinking": False},
            }, timeout=(3, 40), allow_redirects=False)
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("No local answer")
            answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip()
            if not answer or "<think>" in answer:
                raise ValueError("Incomplete local answer")
            return answer[:2000]
        finally:
            session.close()

    @staticmethod
    def fallback(text):
        command = folded(text)
        if re.search(r"\b(?:cam on|thanks|thank you)\b", command):
            return "Rất vui được hỗ trợ bạn! Cần thêm gì cứ nhắn mình nhé."
        if re.search(r"\b(?:chao|hello|hi)\b", command):
            return "Chào bạn! Mình là Ollie_MT, trợ lý của team Trainer. Hôm nay bạn muốn mình hỗ trợ việc gì trước?"
        if re.search(r"\b(?:met|ap luc|nhieu viec|qua tai|roi)\b", command):
            return "Nhiều việc cùng lúc dễ khiến mình bị rối. Bạn gửi những việc đang cần xử lý nhé; mình giúp bạn xếp việc gần deadline trước."
        if command in ("huong dan", "help", "/start", "ban la ai"):
            return ("Mình là Ollie_MT, trợ lý của team Trainer. Bạn có thể hỏi về KPI khu vực, "
                    "nhắn ‘việc của tôi’ để xem việc hoặc nhờ mình soạn nội dung. Trong nhóm, nhớ chọn @Ollie_MT nhé.")
        return ("Mình đã nhận câu hỏi. Phần trò chuyện AI tại chỗ hiện chưa sẵn sàng. "
                "Bạn vẫn có thể nhắn ‘việc của tôi’, ‘hướng dẫn’ hoặc hỏi KPI trong tin nhắn riêng.")

    def authorized_trainer(self, incoming, recipients):
        sender = str(incoming.sender_staff_id)
        aliases = {sender}
        for person in self.state.get("verified_recipients", {}).values():
            if isinstance(person, dict) and str(person.get("staff_id")) == sender:
                aliases.add(str(person.get("open_dingtalk_id", "")))
        matches = [tid for tid, route in recipients.items() if str(route.get("target", "")) in aliases]
        if len(matches) != 1:
            return None
        return matches[0]

    async def kpi_answer(self, incoming, now):
        if str(getattr(incoming, "conversation_type", "1")) != "1":
            return "KPI được trả qua tin nhắn riêng. Bạn mở cuộc trò chuyện riêng với Ollie_MT và hỏi lại nhé."
        leader = str(incoming.sender_staff_id) == str(self.state["leader_staff_id"])
        try:
            directory = self.root / "runtime/kpi"
            settings = json.loads((directory / "settings.json").read_text())
            tid = None if leader else self.authorized_trainer(incoming, settings.get("trainer_recipients", {}))
            if not leader and tid is None:
                return "Mình chưa đối chiếu được tài khoản với khu vực của bạn. Nghĩa cần xác nhận đối chiếu trước khi mình trả dữ liệu KPI."
            config = json.loads((directory / "source.json").read_text())
            month = datetime.fromtimestamp(now, VIETNAM).strftime("%Y-%m")
            snapshot = await asyncio.to_thread(SupabaseKpiSource(config).snapshot, month)
            if leader:
                reports = await asyncio.to_thread(snapshot.reports)
                return format_team_report(reports, config["dashboard_url"])
            trainer = next((t for t in snapshot.trainers if str(t["id"]) == str(tid)), None)
            if not trainer or not trainer.get("region"):
                raise KpiSourceError("account_region_missing")
            region = str(trainer["region"]).strip()
            scoped = [t for t in snapshot.trainers if str(t.get("region", "")).strip() == region]
            reports = await asyncio.to_thread(lambda: [snapshot.trainer_report(t) for t in scoped])
            return "\n\n".join(format_trainer_report(r, config["dashboard_url"]) for r in reports)
        except (OSError, ValueError, KeyError, KpiSourceError):
            return "Mình chưa đọc được KPI khu vực từ nguồn dữ liệu. Mình sẽ không suy đoán số liệu; bạn có thể kiểm tra trực tiếp trên dashboard."
