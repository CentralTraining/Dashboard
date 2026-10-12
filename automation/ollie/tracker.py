"""Persistent tasks and reminders for the configured DingTalk organization."""

import json
import re
import time
import unicodedata
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")


def folded(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.lower())
                   if not unicodedata.combining(c)).replace("đ", "d").strip()


def local_time(timestamp):
    return datetime.fromtimestamp(timestamp, VIETNAM)


def display_time(timestamp):
    return local_time(timestamp).strftime("%H:%M ngày %d/%m/%Y")


def parse_deadline(value):
    for pattern in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value.strip(), pattern).replace(tzinfo=VIETNAM).timestamp()
        except ValueError:
            pass
    raise ValueError("Deadline cần cả ngày và giờ, ví dụ: 20/10/2026 17:00.")


class Tracker:
    def __init__(self, database, state):
        self.db = database
        self.state = state
        self.owner = state["leader_staff_id"]
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS people (
                staff_id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_event TEXT UNIQUE NOT NULL,
                created_by TEXT NOT NULL, content TEXT NOT NULL,
                deadline REAL NOT NULL, created_at REAL NOT NULL,
                first_reminder_at REAL NOT NULL,
                cancelled INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS assignments (
                task_id INTEGER NOT NULL, staff_id TEXT NOT NULL,
                done_at REAL, PRIMARY KEY(task_id, staff_id));
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_event TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL, staff_id TEXT NOT NULL,
                due_at REAL NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS outbox (
                job_key TEXT PRIMARY KEY, kind TEXT NOT NULL,
                reference TEXT NOT NULL, channel TEXT NOT NULL,
                target TEXT NOT NULL, due_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                receipt TEXT, error_code TEXT, updated_at REAL);
            CREATE TABLE IF NOT EXISTS task_events (
                event_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                recorded_at REAL NOT NULL, synced_at REAL);
            CREATE TABLE IF NOT EXISTS task_imports (event_id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS task_originals (task_id INTEGER PRIMARY KEY, content TEXT NOT NULL);
        """)
        self.db.execute("INSERT OR IGNORE INTO people VALUES (?, ?)",
                        (self.owner, state["leader_name"]))
        initial = {"enabled": True, "hour": 8, "minute": 0,
                   "days_before": 4, "channels": ["group", "dm"]}
        self.db.execute("INSERT OR IGNORE INTO settings VALUES ('reminders', ?)",
                        (json.dumps(initial),))
        # A process interrupted during an outbound request must not blindly resend it.
        self.db.execute("UPDATE outbox SET status='unknown', error_code='interrupted' "
                        "WHERE status='sending'")
        self.db.commit()

    def settings(self):
        return json.loads(self.db.execute(
            "SELECT value FROM settings WHERE key='reminders'").fetchone()[0])

    def record_task_event(self, event_id, task_id, operation, author, now):
        row = self.db.execute('SELECT source_event,content,deadline,created_at,cancelled FROM tasks WHERE id=?', (task_id,)).fetchone()
        assignments = self.db.execute('SELECT staff_id,done_at FROM assignments WHERE task_id=?', (task_id,)).fetchall()
        original = self.db.execute('SELECT content FROM task_originals WHERE task_id=?', (task_id,)).fetchone()
        payload = {'event_id': event_id, 'task_source_event': row[0], 'content': row[1], 'deadline': row[2],
                   'created_at': row[3], 'cancelled': bool(row[4]), 'assignees': [sid for sid, _ in assignments],
                   'done': {sid: done for sid, done in assignments if done is not None},
                   'operation': operation, 'author': author, 'recorded_at': now,
                   'original': original[0] if original else row[1]}
        self.db.execute('INSERT OR IGNORE INTO task_events VALUES (?,?,?,NULL)',
                        (event_id, json.dumps(payload, ensure_ascii=False), now))

    def set_enabled(self, enabled):
        config = self.settings()
        config["enabled"] = enabled
        self.db.execute("UPDATE settings SET value=? WHERE key='reminders'",
                        (json.dumps(config),))
        self.db.commit()

    def schedule_description(self):
        return ('từ sáng hôm sau khi nhận thông báo' if self.settings().get('start_policy') == 'next_morning'
                else 'từ 4 ngày trước deadline')

    def help(self):
        return ("Ollie_MT đã có lưu công việc và lịch nhắc.\n"
                f"• Lịch: 08:00 giờ Việt Nam mỗi ngày, {self.schedule_description()}.\n"
                "• Nơi nhận: nhóm này và tin nhắn riêng cho người phụ trách.\n\n"
                "• Nhắc cả leader; dừng khi hoàn thành, bị hủy hoặc đã qua deadline.\n"
                "Với thông báo họp: gửi @Ollie_MT kèm thông báo, có ngày/tháng/năm và giờ rõ ràng.\n\n"
                "Leader gửi mẫu sau; chọn @Trainer từ danh sách nếu giao cho người khác:\n"
                "giao việc\nNgười phụ trách: tôi\nNội dung: Nộp báo cáo đào tạo\n"
                "Deadline: 20/10/2026 17:00\n\n"
                "Các lệnh khác: danh sách; hoàn thành CV-1; hủy CV-1; "
                "đổi hạn CV-1 21/10/2026 17:00; trạng thái.\n"
                "Trainer có thể gửi ‘đăng ký Trainer’ để ghi nhận tài khoản của mình.\n"
                "Để kiểm tra lời nhắc, leader gửi: nhắc sau 2 phút: Kiểm tra Ollie_MT.\n"
                "Trong nhóm, mỗi lệnh cần @Ollie_MT. Bot đang chạy thử trong phiên này; "
                "cần nơi chạy liên tục để vận hành hằng ngày.")

    def handle(self, text, incoming, event_id, now=None):
        now = time.time() if now is None else now
        text = unicodedata.normalize("NFC", text or "").strip()
        text = re.sub(r"@Ollie_MT\b", "", text, flags=re.I).strip()
        command = folded(text)
        sender = incoming.sender_staff_id
        if not sender:
            return "Chưa xác định được tài khoản trong tổ chức. Bạn gửi từ tài khoản DingTalk nội bộ nhé."
        if command in ("dang ky trainer", "dang ky"):
            name = incoming.sender_nick or "Trainer"
            self.db.execute("INSERT INTO people VALUES (?, ?) ON CONFLICT(staff_id) "
                            "DO UPDATE SET name=excluded.name", (sender, name))
            self.db.commit()
            return f"Đã ghi nhận tài khoản của {name}. Leader có thể giao việc bằng cách chọn @ bạn."
        if command in ("huong dan", "help", "/start", "ban la ai"):
            return self.help()
        if command in ("trang thai", "cai dat"):
            config = self.settings()
            count = self.db.execute("SELECT COUNT(*) FROM tasks WHERE cancelled=0").fetchone()[0]
            bad = self.db.execute("SELECT COUNT(*) FROM outbox WHERE status IN ('error','unknown')").fetchone()[0]
            return (f"Lưu công việc: đang bật ({count} công việc).\n"
                    f"Lịch nhắc: {'đang bật' if config['enabled'] else 'đang tạm dừng'}.\n"
                    f"Giờ nhắc: 08:00 Việt Nam; {self.schedule_description()}.\n"
                    "Nơi gửi: nhóm này và riêng từng người phụ trách.\n"
                    + (f"Có {bad} lần gửi chưa xác nhận thành công; cần kiểm tra kết nối/quyền gửi.\n" if bad else "")
                    + "Chương trình đang chạy thử trong phiên làm việc này.")
        if command in ("danh sach", "viec cua toi"):
            return self.task_list(sender, now)
        if command in ("xin chao", "chao", "hello", "hi", "chao bot"):
            return "Chào bạn! Mình là Ollie_MT. Gõ ‘hướng dẫn’ để xem cách giao việc và đặt lời nhắc."
        if command in ("bat nhac viec", "tat nhac viec"):
            if sender != self.owner:
                return "Chỉ leader được bật hoặc tạm dừng lịch nhắc."
            self.set_enabled(command == "bat nhac viec")
            payload = {'event_id': event_id, 'operation': 'settings', 'author': sender,
                       'recorded_at': now, 'enabled': command == 'bat nhac viec'}
            self.db.execute('INSERT OR IGNORE INTO task_events VALUES (?,?,?,NULL)',
                            (event_id, json.dumps(payload), now))
            self.db.commit()
            return (f"Đã bật lịch nhắc lúc 08:00 Việt Nam, {self.schedule_description()}; gửi nhóm và riêng."
                    if command == "bat nhac viec" else "Đã tạm dừng gửi lời nhắc. Các công việc vẫn được lưu.")
        try:
            from announcements import has_deadline, notice_source_id
            structured_assignment = command.startswith("giao viec") and bool(
                re.search(r"(?m)^\s*(?:trainer|nguoi phu trach|nguoi nhan|cho)\s*:", command))
            if "thong bao" in command or (has_deadline(text) and not structured_assignment):
                if sender != self.owner:
                    return "Chỉ leader được tạo thông báo cần nhắc."
                if str(getattr(incoming, "conversation_type", "2")) != "2":
                    return "Hãy gửi thông báo kèm deadline trong nhóm AE CÂY KHẾ CHUA để giao việc cho Team."
                from announcements import parse_announcement
                source_time = getattr(incoming, "create_at", None)
                source_time = (float(source_time) / 1000 if source_time else now)
                content, deadline = parse_announcement(text, source_time)
                audience = self.state.get("audience_staff_ids", [])
                if not audience:
                    return (f"Bản rút gọn: {content}\nThời gian: {display_time(deadline)}\n"
                            "Chưa tạo lịch nhắc: cần xác định nhóm thông báo và danh sách người nhận.")
                source_id = notice_source_id(getattr(incoming, 'conversation_id', self.state.get('conversation_id', '')), sender, source_time, text)
                return self.save_task(content, deadline, incoming, source_id, source_time,
                                      list(dict.fromkeys([*audience, self.owner])))
            if re.match(r"^giao viec(?:\s|:|$)", command):
                if sender != self.owner:
                    return "Chỉ leader được tạo phân công công việc."
                return self.create_task(text, incoming, event_id, now)
            quick = re.fullmatch(r"nhac sau (\d+) phut\s*:\s*(.+)", command, re.S)
            if quick:
                if sender != self.owner:
                    return "Chỉ leader được tạo lời nhắc thử."
                minutes = int(quick[1])
                if not 1 <= minutes <= 1440:
                    raise ValueError("Thời gian nhắc cần từ 1 đến 1440 phút.")
                content = text.split(":", 1)[1].strip()
                if not content or len(content) > 1000:
                    raise ValueError("Nội dung lời nhắc cần từ 1 đến 1000 ký tự.")
                row = self.db.execute("SELECT id,due_at FROM alerts WHERE source_event=?", (event_id,)).fetchone()
                if row:
                    alert_id, due_at = row
                else:
                    due_at = now + minutes * 60
                    cursor = self.db.execute("INSERT INTO alerts (source_event,content,staff_id,due_at) "
                                             "VALUES (?,?,?,?)", (event_id, content, sender, due_at))
                    alert_id = cursor.lastrowid
                    self.db.commit()
                paused = " Lịch gửi đang tạm dừng; leader gõ ‘bật nhắc việc’ để tiếp tục." if not self.settings()["enabled"] else ""
                return (f"Đã lưu lời nhắc NR-{alert_id}: {content}.\n"
                        f"Lịch nhắc: {display_time(due_at)}, trong nhóm và riêng cho bạn." + paused)
            done = re.fullmatch(r"hoan thanh cv-?(\d+)", command)
            cancel = re.fullmatch(r"huy (cv|nr)-?(\d+)", command)
            change = re.fullmatch(r"doi han cv-?(\d+)\s+(.+)", command)
            if done:
                return self.complete_task(int(done[1]), sender, event_id, now)
            if cancel:
                if sender != self.owner:
                    return "Chỉ leader được hủy công việc hoặc lời nhắc."
                table = "tasks" if cancel[1] == "cv" else "alerts"
                cursor = self.db.execute(f"UPDATE {table} SET cancelled=1 WHERE id=?", (int(cancel[2]),))
                if table == 'tasks' and cursor.rowcount:
                    self.record_task_event(event_id, int(cancel[2]), 'cancel', sender, now)
                self.db.commit()
                if not cursor.rowcount:
                    raise ValueError("Không tìm thấy mã công việc/lời nhắc này.")
                return f"Đã hủy {cancel[1].upper()}-{cancel[2]}; dừng các lần nhắc tiếp theo."
            if change:
                if sender != self.owner:
                    return "Chỉ leader được đổi deadline."
                deadline = parse_deadline(change[2])
                cursor = self.db.execute("UPDATE tasks SET deadline=?,first_reminder_at=? WHERE id=? AND cancelled=0",
                                         (deadline, self.first_reminder(deadline, now), int(change[1])))
                if cursor.rowcount:
                    self.record_task_event(event_id, int(change[1]), 'change', sender, now)
                self.db.commit()
                if not cursor.rowcount:
                    raise ValueError("Không tìm thấy công việc đang hoạt động này.")
                return f"Đã đổi deadline CV-{change[1]} thành {display_time(deadline)}."
        except ValueError as exc:
            return str(exc)
        return ("Để lưu một công việc, gửi ‘giao việc’ kèm Người phụ trách, Nội dung và Deadline. "
                "Gõ ‘hướng dẫn’ để lấy mẫu; gõ ‘trạng thái’ để xem lịch nhắc.")

    def create_task(self, text, incoming, event_id, now):
        fields = {}
        for line in text.splitlines()[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                fields[folded(key)] = value.strip()
        assignee = fields.get("nguoi phu trach", "")
        content = fields.get("noi dung", "")
        deadline_text = fields.get("deadline", fields.get("han", ""))
        if not assignee or not content or not deadline_text:
            raise ValueError("Chưa lưu: cần đủ Người phụ trách, Nội dung và Deadline. Gõ ‘hướng dẫn’ để lấy mẫu.")
        if len(content) > 2000:
            raise ValueError("Nội dung công việc tối đa 2000 ký tự.")
        deadline = parse_deadline(deadline_text)
        if folded(assignee) in ("toi", "minh", "ban than"):
            staff_ids = [incoming.sender_staff_id]
        else:
            staff_ids = list(dict.fromkeys(user.staff_id for user in (incoming.at_users or [])
                                          if user.staff_id and user.dingtalk_id != incoming.chatbot_user_id))
            if not staff_ids:
                matches = self.db.execute("SELECT staff_id,name FROM people").fetchall()
                staff_ids = [sid for sid, name in matches if folded(name) == folded(assignee)]
                if len(staff_ids) != 1:
                    raise ValueError("Chưa lưu: hãy chọn @Trainer từ danh sách DingTalk ở dòng Người phụ trách; tránh gõ tên suông.")
        return self.save_task(content, deadline, incoming, event_id, now, staff_ids)

    def save_task(self, content, deadline, incoming, event_id, now, staff_ids):
        if deadline <= now:
            raise ValueError("Chưa lưu lịch nhắc: thời hạn đã qua. Bạn gửi ngày, tháng, năm và giờ mới nhé.")
        first_reminder = self.first_reminder(deadline, now)
        existing = self.db.execute("SELECT id FROM tasks WHERE source_event=?", (event_id,)).fetchone()
        if existing:
            task_id = existing[0]
        else:
            with self.db:
                cursor = self.db.execute("INSERT INTO tasks (source_event,created_by,content,deadline,created_at,first_reminder_at) "
                                         "VALUES (?,?,?,?,?,?)", (event_id, incoming.sender_staff_id, content, deadline, now, first_reminder))
                task_id = cursor.lastrowid
                for sid in staff_ids:
                    self.db.execute("INSERT OR IGNORE INTO people VALUES (?,?)", (sid, "Trainer được chọn"))
                    self.db.execute("INSERT INTO assignments (task_id,staff_id) VALUES (?,?)", (task_id, sid))
                original = getattr(incoming, 'original_text', None) or content
                self.db.execute('INSERT OR IGNORE INTO task_originals VALUES (?,?)', (task_id, original))
                self.record_task_event(event_id, task_id, 'create', incoming.sender_staff_id, now)
        names = ", ".join(self.name(sid) for sid in staff_ids)
        config = self.settings()
        first_reminder = self.db.execute("SELECT first_reminder_at FROM tasks WHERE id=?", (task_id,)).fetchone()[0]
        extra = "\nLịch gửi đang tạm dừng." if not config["enabled"] else ""
        first_text = (f"Lần nhắc đầu theo lịch: {display_time(first_reminder)}; nhóm và riêng, gồm cả leader."
                      if first_reminder < deadline else
                      "Không còn lượt 08:00 nào trước deadline; cần chọn lịch nhắc sớm hơn nếu muốn nhận lời nhắc.")
        return (f"Đã lưu CV-{task_id}: {content}\nNgười phụ trách: {names}\n"
                f"Deadline: {display_time(deadline)}\n"
                + first_text + extra)

    def first_reminder(self, deadline, now):
        config = self.settings()
        if config.get('start_policy') == 'next_morning':
            first = datetime.combine(local_time(now).date() + timedelta(days=1),
                                     datetime.min.time(), VIETNAM)
            return first.replace(hour=config['hour'], minute=config['minute']).timestamp()
        first_date = local_time(deadline).date() - timedelta(days=config["days_before"])
        first = datetime.combine(max(first_date, local_time(now).date()),
                                 datetime.min.time(), VIETNAM).replace(hour=config["hour"], minute=config["minute"])
        if first.timestamp() <= now:
            first += timedelta(days=1)
        return first.timestamp()

    def name(self, staff_id):
        row = self.db.execute("SELECT name FROM people WHERE staff_id=?", (staff_id,)).fetchone()
        return row[0] if row else "Trainer được chọn"

    def complete_task(self, task_id, sender, event_id=None, now=None):
        now = time.time() if now is None else now
        task = self.db.execute("SELECT cancelled FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task or task[0]:
            raise ValueError("Không tìm thấy công việc đang hoạt động này.")
        if sender == self.owner:
            self.db.execute("UPDATE assignments SET done_at=? WHERE task_id=? AND done_at IS NULL",
                            (time.time(), task_id))
            message = f"Đã đánh dấu CV-{task_id} hoàn thành cho tất cả người phụ trách; dừng nhắc việc này."
        else:
            assignment = self.db.execute("SELECT 1 FROM assignments WHERE task_id=? AND staff_id=?",
                                         (task_id, sender)).fetchone()
            if not assignment:
                raise ValueError("Bạn chưa được phân công công việc này.")
            self.db.execute("UPDATE assignments SET done_at=? WHERE task_id=? AND staff_id=?",
                            (time.time(), task_id, sender))
            message = f"Đã ghi nhận phần việc CV-{task_id} của {self.name(sender)} hoàn thành; dừng nhắc riêng cho bạn."
        self.record_task_event(event_id or f'complete:{task_id}:{sender}:{now}', task_id, 'complete', sender, now)
        self.db.commit()
        return message

    def pending_tasks(self, sender=None):
        query = ("SELECT t.id,t.content,t.deadline,a.staff_id FROM tasks t JOIN assignments a ON a.task_id=t.id "
                 "WHERE t.cancelled=0 AND a.done_at IS NULL")
        values = ()
        if sender:
            query += " AND a.staff_id=?"
            values = (sender,)
        return self.db.execute(query + " ORDER BY t.deadline,t.created_at,t.id,a.staff_id", values).fetchall()

    def task_list(self, sender, now):
        rows = self.pending_tasks(None if sender == self.owner else sender)
        if not rows:
            return "Hiện không có công việc chưa hoàn thành."
        lines = ["Công việc chưa hoàn thành (hạn gần nhất trước):"]
        grouped = self.group_tasks(rows)
        for number, (task_id, content, deadline, staff_ids) in enumerate(grouped[:40], 1):
            status = "QUÁ HẠN — " if deadline < now else ""
            names = ", ".join(self.name(sid) for sid in staff_ids)
            lines.append(f"{number}. CV-{task_id}: {status}{content}\n{names} — {display_time(deadline)}")
        if len(grouped) > 40:
            lines.append(f"Còn {len(grouped)-40} công việc khác.")
        return "\n\n".join(lines)

    @staticmethod
    def group_tasks(rows):
        grouped = {}
        for task_id, content, deadline, staff_id in rows:
            if task_id not in grouped:
                grouped[task_id] = (task_id, content, deadline, [])
            grouped[task_id][3].append(staff_id)
        return list(grouped.values())

    def prepare_jobs(self, now, include_daily=True):
        config = self.settings()
        if not config["enabled"]:
            return
        today = local_time(now)
        scheduled = today.replace(hour=config["hour"], minute=config["minute"], second=0, microsecond=0)
        if include_daily and now >= scheduled.timestamp():
            rows = self.due_tasks(today.date(), now=now)
            day = today.date().isoformat()
            if rows:
                self.add_job(f"daily:{day}:group", "daily", day, "group", self.state["conversation_id"], now)
                for staff_id in sorted({row[3] for row in rows} | {self.owner}):
                    self.add_job(f"daily:{day}:dm:{staff_id}", "daily", day, "dm", staff_id, now)
        alerts = self.db.execute("SELECT id,staff_id,due_at FROM alerts WHERE cancelled=0 AND due_at<=?", (now,)).fetchall()
        for alert_id, staff_id, due_at in alerts:
            self.add_job(f"alert:{alert_id}:group", "alert", str(alert_id), "group", self.state["conversation_id"], due_at)
            self.add_job(f"alert:{alert_id}:dm", "alert", str(alert_id), "dm", staff_id, due_at)
        self.db.commit()

    def due_tasks(self, day, sender=None, now=None):
        config = self.settings()
        scheduled = datetime.combine(day, datetime.min.time(), VIETNAM).replace(
            hour=config["hour"], minute=config["minute"]).timestamp()
        cutoff = scheduled if now is None else now
        eligible = {row[0] for row in self.db.execute(
            "SELECT id FROM tasks WHERE first_reminder_at<=?", (scheduled,))}
        return [row for row in self.pending_tasks(sender)
                if row[0] in eligible and row[2] > cutoff
                and (config.get('start_policy') == 'next_morning'
                     or local_time(row[2]).date() - timedelta(days=config["days_before"]) <= day)]

    def add_job(self, key, kind, reference, channel, target, due_at):
        self.db.execute("INSERT OR IGNORE INTO outbox (job_key,kind,reference,channel,target,due_at) "
                        "VALUES (?,?,?,?,?,?)", (key, kind, reference, channel, target, due_at))

    def next_jobs(self, now):
        return self.db.execute("SELECT job_key,kind,reference,channel,target FROM outbox "
                               "WHERE status IN ('pending','retry') AND due_at<=? ORDER BY due_at,job_key LIMIT 20", (now,)).fetchall()

    def job_content(self, job, now):
        _, kind, reference, channel, target = job
        if not self.settings()["enabled"]:
            return None
        if kind == "kpi":
            if not self.state.get("kpi_enabled"):
                return None
            row = self.db.execute("SELECT day,content FROM kpi_messages WHERE reference=?", (reference,)).fetchone()
            return row[1] if row and row[0] == local_time(now).date().isoformat() else None
        if kind == "alert":
            row = self.db.execute("SELECT content FROM alerts WHERE id=? AND cancelled=0", (int(reference),)).fetchone()
            if not row:
                return None
            return row[0]
        # Skip an old unsent digest; today's digest is rebuilt from current tasks.
        if reference != local_time(now).date().isoformat():
            return None
        personal = target if channel == "dm" and target != self.owner else None
        rows = self.due_tasks(local_time(now).date(), personal, now=now)
        if not rows:
            return None
        from daily_digest import format_deadline_digest
        message = format_deadline_digest(self.name(target), self.group_tasks(rows), now, group=channel == 'group')
        if len(message.encode("utf-8")) > 18000:
            message = ("Ollie_MT — bạn có nhiều công việc đến hạn hoặc quá hạn. "
                       "Gửi @Ollie_MT danh sách để xem các công việc theo deadline.")
        return message

    def begin_job(self, key, now):
        cursor = self.db.execute("UPDATE outbox SET status='sending', attempts=attempts+1, updated_at=? "
                                 "WHERE job_key=? AND status IN ('pending','retry')", (now, key))
        self.db.commit()
        return bool(cursor.rowcount)

    def finish_job(self, key, status, now, receipt=None, error=None):
        attempts = self.db.execute("SELECT attempts FROM outbox WHERE job_key=?", (key,)).fetchone()[0]
        if status == "retry" and attempts >= 3:
            status = "error"
        self.db.execute("UPDATE outbox SET status=?,receipt=?,error_code=?,updated_at=?,due_at=? WHERE job_key=?",
                        (status, receipt, error, now, now + min(900, 60 * 5 ** max(0, attempts-1)), key))
        self.db.commit()


class DeliveryError(Exception):
    def __init__(self, code, ambiguous=False):
        super().__init__(code)
        self.code = code
        self.ambiguous = ambiguous


class DingTalkSender:
    """Proactive application messages. Session webhooks are never reused."""

    def __init__(self, credentials, state):
        self.credentials = credentials
        self.state = state
        self.token = None
        self.token_until = 0

    def access_token(self):
        if self.token and time.time() < self.token_until:
            return self.token
        try:
            response = requests.post("https://api.dingtalk.com/v1.0/oauth2/accessToken", json={
                "appKey": self.credentials["appKey"], "appSecret": self.credentials["appSecret"]}, timeout=15)
        except requests.RequestException:
            raise DeliveryError("token_connection_failed") from None
        data = response.json()
        if not response.ok or not data.get("accessToken"):
            raise DeliveryError(self.error_code(data, response.status_code))
        self.token = data["accessToken"]
        self.token_until = time.time() + max(0, int(data.get("expireIn", 7200))-120)
        return self.token

    @staticmethod
    def error_code(data, status):
        value = str(data.get("code", f"http_{status}"))
        return re.sub(r"[^A-Za-z0-9_.-]", "", value)[:100] or f"http_{status}"

    def send(self, channel, target, content):
        if channel == "dm_open":
            return self.send_open_dingtalk_id(target, content)
        from daily_digest import MarkdownMessage
        markdown = isinstance(content, MarkdownMessage)
        param = {"title": "Ollie_MT — Nhắc deadline", "text": str(content)} if markdown else {"content": content}
        payload = {"robotCode": self.state["robot_code"], "msgKey": "sampleMarkdown" if markdown else "sampleText",
                   "msgParam": json.dumps(param, ensure_ascii=False)}
        if channel == "group":
            if target != self.state["conversation_id"]:
                raise DeliveryError("group_not_configured")
            endpoint = "groupMessages/send"
            payload["openConversationId"] = target
        elif channel == "dm":
            endpoint = "oToMessages/batchSend"
            payload["userIds"] = [target]
        else:
            raise DeliveryError("channel_not_configured")
        for attempt in range(2):
            token = self.access_token()
            try:
                response = requests.post(f"https://api.dingtalk.com/v1.0/robot/{endpoint}",
                    json=payload, headers={"x-acs-dingtalk-access-token": token}, timeout=20)
            except requests.RequestException:
                raise DeliveryError("send_connection_uncertain", ambiguous=True) from None
            try:
                data = response.json()
            except ValueError:
                raise DeliveryError("send_response_uncertain", ambiguous=True) from None
            if response.status_code == 401 and attempt == 0:
                self.token = None
                continue
            if not response.ok:
                raise DeliveryError(self.error_code(data, response.status_code))
            if data.get("invalidStaffIdList") or data.get("flowControlledStaffIdList"):
                raise DeliveryError("recipient_rejected")
            if not data.get("processQueryKey"):
                raise DeliveryError("missing_send_receipt", ambiguous=True)
            return str(data["processQueryKey"])
        raise DeliveryError("token_rejected")

    def send_open_dingtalk_id(self, target, content):
        if target not in self.state.get("allowed_open_dingtalk_ids", []):
            raise DeliveryError("recipient_not_configured")
        try:
            result = subprocess.run([
                "/workspace/dingtalk-tools/dws-workspace", "--profile", self.state["profile"],
                "--timeout", "20", "--yes", "chat", "message", "send-by-bot",
                "--robot-code", self.state["robot_code"], "--open-dingtalk-ids", target,
                "--title", "Tin nhắn từ Ollie_MT", "--text", content.replace("\n", "\n\n"),
            ], capture_output=True, text=True, timeout=35)
        except subprocess.TimeoutExpired:
            raise DeliveryError("send_result_uncertain", ambiguous=True) from None
        try:
            value = json.loads(result.stdout)
        except ValueError:
            raise DeliveryError("send_response_uncertain", ambiguous=True) from None
        if result.returncode != 0 or not (value.get("success") is True or value.get("ok") is True):
            raise DeliveryError("cli_send_rejected")
        details = value.get("result", value.get("data", {}))
        if isinstance(details, dict):
            if details.get("invalidStaffIdList") or details.get("flowControlledStaffIdList"):
                raise DeliveryError("recipient_rejected")
            receipt = details.get("processQueryKey") or details.get("openMessageId") or details.get("messageId")
            if receipt:
                return str(receipt)
        raise DeliveryError("missing_send_receipt", ambiguous=True)
