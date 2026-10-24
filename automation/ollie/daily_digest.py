"""Short personal deadline digests with stable daily wishes and usable links."""
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo


class MarkdownMessage(str):
    """A string carrying the native DingTalk Markdown message type."""


WISHES = (
    'Mỗi ngày tiến một bước, thành công sẽ gần hơn.',
    'Chúc bạn vững tinh thần và hoàn thành từng mục tiêu hôm nay!',
    'Một khởi đầu chủ động sẽ tạo nên một ngày hiệu quả.',
    'Kiên trì hôm nay, bứt phá ngày mai.',
    'Chúc bạn tự tin, tập trung và luôn tìm được cách làm tốt hơn!',
    'Làm từng việc thật tốt, kết quả sẽ dần tạo khác biệt.',
    'Chúc bạn một ngày nhiều ý tưởng và phối hợp thuận lợi!',
    'Bắt đầu từ việc quan trọng nhất, bạn sẽ tiến xa hơn.',
    'Mỗi thử thách là một cơ hội để trưởng thành.',
    'Chúc bạn giữ nhịp làm việc tốt và dành thời gian cho bản thân!',
    'Chủ động một chút hôm nay, nhẹ nhàng hơn vào ngày mai.',
    'Chúc bạn nhiều năng lượng để biến kế hoạch thành kết quả!',
    'Tốt hơn chính mình của ngày hôm qua là một thành công.',
    'Chia sẻ kiến thức là nhân đôi giá trị.',
    'Chúc bạn bình tĩnh, sáng suốt và xử lý công việc thuận lợi!',
    'Mục tiêu lớn bắt đầu từ những hành động nhỏ hôm nay.',
    'Chúc bạn một ngày học hỏi nhiều điều mới và tạo được giá trị!',
    'Kỷ luật nhỏ tạo nên thành công lớn.',
    'Chúc bạn phối hợp tốt cùng đồng đội và về đích đúng hẹn!',
    'Hành động hôm nay, kết quả ngày mai.',
    'Chúc bạn làm việc có trọng tâm và giữ tinh thần tích cực!',
    'Đồng đội mạnh, mục tiêu sẽ gần hơn.',
    'Chúc bạn tìm thấy niềm vui trong từng việc hoàn thành!',
    'Từng bước chắc chắn sẽ giúp bạn đi được đường dài.',
    'Chúc bạn một ngày chủ động, hiệu quả và nhiều tin vui!',
    'Tận tâm với việc nhỏ sẽ tạo nền tảng cho thành công lớn.',
    'Chúc bạn giữ được sự tự tin khi gặp những thử thách mới!',
    'Sắp xếp tốt hôm nay, tiến gần mục tiêu ngày mai.',
    'Chúc bạn khởi đầu đầy hứng khởi và kết thúc thật hài lòng!',
    'Lan tỏa năng lượng, cùng nhau tiến bộ.',
    'Chúc bạn hoàn thành những điều quan trọng và có một ngày đáng nhớ!',
)


def given_name(value):
    words = unicodedata.normalize('NFC', str(value)).strip().split()
    return words[-1].title() if words else 'bạn'


def split_links(value):
    """Separate links without dropping useful inline labels or changing URLs."""
    destinations = []
    def remember(url):
        if url not in destinations: destinations.append(url)
        return ''
    def markdown_link(match):
        remember(match[2])
        label = match[1].strip()
        return '' if label == match[2] or re.fullmatch(r'link(?:\s+\d+)?', label, re.I) else label
    text = re.sub(r'\[([^\]]*)\]\((https?://[^\s]+)\)', markdown_link, str(value))
    text = re.sub(r'https?://[^\s<>]+', lambda m: remember(m[0].rstrip('\\')), text)
    text = re.sub(r'(?m)^\s*(?:🔗\s*)?(?:Link(?: Zoom| điền| nộp| đăng ký)?|Đường dẫn|Biểu mẫu)\s*:\s*$', '', text, flags=re.I)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text, destinations


def link_labels(destinations):
    links = []
    for index, url in enumerate(destinations, 1):
        # The DingTalk client chooses link text colour. A red indicator works
        # without relying on unsupported HTML or changing a joining URL.
        label = 'Link' if len(destinations) == 1 else f'Link {index}'
        destination = url
        links.append(f'🔴 **[{label}]({destination})**')
    return ' · '.join(links)


def compact_links(value):
    """Only change display labels; preserve the complete destination and codes."""
    text, destinations = split_links(value)
    links = link_labels(destinations)
    return text + ('\n' + links if links else '')


def concise_task_details(value):
    """Remove presentation boilerplate, never cut actions, quantities or access codes.

    The saved notice stays intact. This local formatter makes no AI/API calls.
    """
    text, destinations = split_links(value)
    actions, notes, seen = [], [], set()
    in_notes = False
    for raw in text.splitlines():
        line = re.sub(r'@Ollie_MT\b', '', raw, flags=re.I).strip().rstrip('\\')
        line = re.sub(r'\*\*|__|`', '', line)
        line = re.sub(r'^\s*(?:[-+•*]\s+|\d+[.)]\s+)', '', line)
        line = re.sub(r'^[^\wÀ-ỹ]+', '', line).strip()
        line = re.sub(r'\s+', ' ', line)
        if not line or re.fullmatch(r'[_=\-—–\s]+', line): continue
        if line.casefold() in ('image', 'ảnh', 'hình ảnh', '@tất cả', 'tất cả'): continue
        if re.fullmatch(r'như\b.*?\bgửi lại chi tiết thông tin(?: và các công việc cần làm)?[.!]*', line, re.I): continue
        if re.fullmatch(r'(?:dear|kính gửi|xin chào|chào)\s+(?:anh em(?: Trainer)?|các bạn|mọi người|cả (?:Team|nhà))[\s,!.]*', line, re.I): continue
        if re.fullmatch(r'(?:trân trọng|cảm ơn(?: (?:anh em|mọi người|các bạn))?|hẹn gặp (?:anh em|mọi người|các bạn)(?: vào (?:chiều|sáng) mai)?)[\s,!.]*', line, re.I): continue
        if re.match(r'^(?:deadline|hạn (?:hoàn thành|cuối|chót)|thời gian(?: hoàn thành)?)\s*[:：]', line, re.I): continue
        line = re.sub(r'^thông báo\s*[:：—–-]?\s*', '', line, flags=re.I)
        line = re.sub(r'^chương trình\s*[:：—–-]\s*', '', line, flags=re.I)
        line = re.sub(r'^nội dung(?: công việc)?\s*[:：]\s*', '', line, flags=re.I).strip()
        line = re.sub(r'^trước tiên(?:\s+(?:anh em|mọi người|các bạn))?\s+', '', line, flags=re.I)
        note = re.match(r'^(?:lưu ý|chú ý|yêu cầu|quan trọng)\s*[:：]\s*(.*)$', line, re.I)
        if note:
            in_notes = True
            line = note[1].strip()
        access = re.match(r'^(?:ID(?: cuộc họp| họp)?|meeting ID|mật (?:mã|khẩu)|passcode|password|hình thức|địa điểm)\s*[:：]', line, re.I)
        if not line: continue
        line = re.sub(r'\s+', ' ', line)
        key = line.casefold()
        if key in seen: continue
        seen.add(key)
        (notes if in_notes or access else actions).append(line)
    return '; '.join(actions) or 'Công việc theo thông báo', notes, destinations


def format_deadline_digest(name, tasks, now, group=False):
    """Tasks are (id, content, deadline, assignees), sorted by the caller."""
    local = datetime.fromtimestamp(now, ZoneInfo('Asia/Ho_Chi_Minh'))
    name = 'cả Team' if group else given_name(name)
    lines = [f'Xin chào {name}!' if not group else 'Xin chào cả Team!',
             '🌟 ' + WISHES[(local.date().toordinal() - 1) % len(WISHES)], '',
             '📌 Việc cần hoàn thành:']
    for index, (_, content, deadline, _) in enumerate(tasks, 1):
        due = datetime.fromtimestamp(deadline, ZoneInfo('Asia/Ho_Chi_Minh'))
        action, notes, destinations = concise_task_details(content)
        lines.extend(['', f'{index}. {action}',
                      '⏰ Hạn: ' + due.strftime('%H:%M · %d/%m/%Y')])
        if notes: lines.append('📝 Lưu ý: ' + '; '.join(notes))
        if destinations: lines.append(link_labels(destinations))
    return MarkdownMessage('\n'.join(lines))

