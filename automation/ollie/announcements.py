"""Extract a concise meeting reminder without guessing conflicting dates."""

import re
import hashlib
import json
import unicodedata
from datetime import datetime, timedelta
from tracker import VIETNAM, folded
from daily_digest import split_links


def notice_source_id(group, owner, posted, text):
    text = re.sub(r"@Ollie_MT\b", "", unicodedata.normalize("NFC", text), flags=re.I)
    text = text.replace("\r\n", "\n").strip()
    payload = json.dumps([group, owner, int(posted), text], ensure_ascii=False, separators=(",", ":"))
    return "group:" + hashlib.sha256(payload.encode()).hexdigest()


DUE_CUE = re.compile(r"\b(?:deadline|han (?:hoan thanh|chot|cuoi)|thoi gian(?: hoan thanh)?|hoan thanh truoc|cham nhat)\b\s*(?:[:：]|(?=\d{1,2}(?:[:h./-]|\s*gio)|20\d{2}-|ngay\s+(?:mai|kia|\d)|hom nay))|\btruoc\s+(?=\d{1,2}(?:[:h./-]|\s*gio)|ngay\s+(?:mai|kia|\d))",re.I)
NATURAL_DUE = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3])\s*(?:(?:h|gio)\s*(?:[0-5]\d)?|:[0-5]\d)\s*[,—–-]?\s*ngay\s+\d{1,2}[./-]\d{1,2}(?:[./-]20\d{2})?(?![\d./-])", re.I)


def notice_spacing(text):
    # Copied DingTalk notices often use NBSP between words, including due labels.
    return re.sub(r'[^\S\n]+', ' ', str(text).replace('\r\n', '\n'))


def has_deadline(text):
    value = folded(notice_spacing(text))
    return bool(DUE_CUE.search(value) or NATURAL_DUE.search(value))


def deadline_line(text):
    line=folded(notice_spacing(text)).replace('：',':')
    line=re.sub(r"(?<!\d)([01]?\d|2[0-3])\s*(?:h|gio)\s*([0-5]\d)?(?!\d)",lambda m:f"{int(m[1]):02}:{m[2] or '00'}",line)
    line=re.sub(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b",lambda m:f'{m[3]}/{m[2]}/{m[1]}',line)
    return line


def meeting_access(text):
    """Retain usable links and joining credentials outside the summary limit."""
    # Markdown often repeats a URL as both the label and destination. Keep one
    # complete copy, including every query parameter, rather than shortening it.
    _, urls = split_links(text)
    details = [f"🔗 Link: {url}" for url in urls]
    labels = {"id cuoc hop", "meeting id", "id hop", "id", "mat ma",
              "mat khau", "passcode", "password", "meeting passcode"}
    for raw in text.splitlines():
        line = re.sub(r"^[^\wÀ-ỹ]+", "", raw.strip().rstrip("\\")).strip()
        if ":" not in line:
            continue
        label = re.sub(r"\*\*|__|`", "", line.split(":", 1)[0])
        if folded(label) in labels and line not in details:
            details.append(line)
    return "\n".join(details)


def summarize_meeting(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = next((line for line in lines if "thong bao" in folded(line)), "Họp Trainer")
    title = re.sub(r"^[^\wÀ-ỹ]+", "", title)
    title = re.sub(r"^thông báo\s*", "", title, flags=re.I).strip(" :—–-")
    if title.isupper():
        title = title.capitalize().replace("trainer", "Trainer")
    topics = []
    for line in lines:
        if re.match(r"^[+•*-]\s*", line):
            topic = re.sub(r"^[+•*-]\s*", "", line).strip()
            topic = re.sub(r"^(truyền thông|kế hoạch content|review hoạt động|cập nhật hoạt động team)\s+",
                           "", topic, flags=re.I)
            topics.append(topic[:100])
    summary = title[:180]
    if topics:
        summary += " — " + ", ".join(topics[:6])
    if "zoom" in folded(text):
        summary += " (online qua Zoom)"
    elif "online" in folded(text):
        summary += " (online)"
    access = meeting_access(text)
    return summary[:700] + ("\n" + access if access else "")


def meeting_deadline(text, source_time):
    text = notice_spacing(text)
    lines = [line for line in text.splitlines() if has_deadline(line)]
    if len(lines) != 1:
        raise ValueError("Chưa lưu: cần một dòng Thời gian hoặc Deadline cho mỗi thông báo.")
    line = deadline_line(lines[0])
    # A natural notice can put "ngày mai" in its heading while the time
    # field contains only a clock. Resolve it against the posting day.
    relatives = ("ngay mai", "hom nay", "ngay kia")
    if not any(value in line for value in relatives) and not re.search(r"\d[./-]\d", line):
        heading = folded(next((value for value in text.splitlines() if value.strip()), ""))
        found = [value for value in relatives if value in heading]
        if len(found) > 1:
            raise ValueError("Chưa lưu: tiêu đề có nhiều ngày; cần ghi một deadline rõ ràng.")
        if found:
            line += " " + found[0]
    times = re.findall(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", line)
    if len(times) != 1:
        raise ValueError("Chưa lưu: thời gian cần một giờ rõ ràng, ví dụ 14:00.")
    hour, minute = map(int, times[0])
    original_day = datetime.fromtimestamp(source_time, VIETNAM).date()
    relative = None
    if "ngay mai" in line:
        relative = original_day + timedelta(days=1)
    elif "hom nay" in line:
        relative = original_day
    elif "ngay kia" in line:
        relative = original_day + timedelta(days=2)
    full = re.search(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](20\d{2})(?!\d)", line)
    short = re.search(r"(?<!\d)(\d{1,2})[./-](\d{1,2})(?![\d./-])", line)
    if full:
        day, month, year = map(int, full.groups())
        try:
            date = datetime(year, month, day).date()
        except ValueError:
            raise ValueError("Chưa lưu: ngày họp không hợp lệ.") from None
        if relative is not None and date != relative:
            raise ValueError("Chưa lưu: ngày cụ thể và ‘ngày mai/hôm nay’ không khớp. Gửi ngày, tháng, năm chính xác nhé.")
    elif relative is not None:
        date = relative
        if short and tuple(map(int, short.groups())) != (date.day, date.month):
            raise ValueError("Chưa lưu: ‘ngày mai’ và ngày/tháng ghi trong thông báo không khớp. Gửi ngày, tháng, năm chính xác nhé.")
    elif short:
        day, month = map(int, short.groups())
        year = original_day.year + int(original_day.month == 12 and month == 1)
        try:
            date = datetime(year, month, day).date()
        except ValueError:
            raise ValueError("Chưa lưu: ngày hoàn thành không hợp lệ.") from None
        # Use the original posting date, never today's replay/capture date.
        # Do not roll an old/forwarded deadline into the following year.
        if not 0 <= (date - original_day).days <= 90:
            raise ValueError("Chưa lưu: ngày thiếu năm ngoài khoảng 90 ngày từ tin gốc; cần ngày, tháng và năm đầy đủ.")
    else:
        raise ValueError("Chưa lưu: cần ngày, tháng và năm, ví dụ Thời gian: 14:00, 20/10/2026.")
    weekdays = {"thu hai":0,"thu ba":1,"thu tu":2,"thu nam":3,"thu sau":4,"thu bay":5,"chu nhat":6}
    for name, value in weekdays.items():
        if re.search(r"\b" + re.escape(name) + r"\b", line) and date.weekday() != value:
            raise ValueError("Chưa lưu: thứ trong tuần không khớp với ngày họp. Bạn kiểm tra lại ngày nhé.")
    return datetime.combine(date, datetime.min.time(), VIETNAM).replace(hour=hour,minute=minute).timestamp()


def parse_meeting(text, source_time):
    text = notice_spacing(text)
    return summarize_meeting(text), meeting_deadline(text, source_time)


def parse_announcement(text, source_time):
    """Meetings keep joining details; other notices retain actions and quantities."""
    text = notice_spacing(text)
    title = next((line for line in text.splitlines() if 'thong bao' in folded(line)), '')
    if re.search(r'\bhop\b|\bmeeting\b', folded(title)):
        return parse_meeting(text, source_time)
    lines = [line for line in text.splitlines() if has_deadline(line)]
    if len(lines) != 1:
        raise ValueError('Chưa lưu: mỗi thông báo cần một dòng Deadline hoặc Hạn hoàn thành rõ ràng.')
    deadline_text = text
    if not re.search(r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)', deadline_line(lines[0])):
        # An explicitly dated all-day deadline ends at 23:59 Vietnam time.
        deadline_text = text.replace(lines[0], lines[0] + ' 23:59')
    deadline = meeting_deadline(deadline_text, source_time)
    access = meeting_access(text)
    clean = []
    for line in text.splitlines():
        value = line.strip().rstrip('\\')
        label = folded(re.sub(r'^[^\wÀ-ỹ]+', '', value))
        if line in lines:
            cue=DUE_CUE.search(folded(value)) or NATURAL_DUE.search(folded(value))
            value=value[:cue.start()].strip(' :—–-') if cue else ''
            value=re.sub(r'^[^\wÀ-ỹ]+','',value).strip()
        value, _ = split_links(value)
        if not value: continue
        if label.startswith(('dear ', 'xin chao', 'anh em sap xep', 'hen gap', 'id cuoc hop:', 'mat ma:', 'link:', 'link zoom:')): continue
        if 'thong bao' in label: value = re.sub(r'(?i)^.*?thông báo\s*', '', value).strip(' :—–-')
        clean.append(value)
    summary = '\n'.join(clean).strip()
    if not summary: raise ValueError('Chưa lưu: thông báo chưa có nội dung công việc.')
    if len(summary) > 2000:
        raise ValueError('Chưa lưu: nội dung quá dài; hãy tách thông báo theo từng việc và deadline.')
    return summary + ('\n' + access if access else ''), deadline

