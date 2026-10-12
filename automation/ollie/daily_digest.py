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


def compact_links(value):
    """Only change display labels; preserve the complete destination and codes."""
    destinations = []
    def remember(url):
        if url not in destinations: destinations.append(url)
        return ''
    text = re.sub(r'\[([^\]]*)\]\((https?://[^\s]+)\)', lambda m: remember(m[2]), str(value))
    text = re.sub(r'https?://[^\s<>]+', lambda m: remember(m[0].rstrip('\\')), text)
    text = re.sub(r'(?m)^\s*(?:🔗\s*)?(?:Link(?: Zoom)?|Đường dẫn)\s*:\s*$', '', text, flags=re.I)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    links = []
    for index, url in enumerate(destinations, 1):
        # The DingTalk client chooses link text colour. A red indicator works
        # without relying on unsupported HTML or changing a joining URL.
        label = 'Link' if len(destinations) == 1 else f'Link {index}'
        destination = url
        links.append(f'🔴 **[{label}]({destination})**')
    return text + ('\n' + ' · '.join(links) if links else '')


def format_deadline_digest(name, tasks, now, group=False):
    """Tasks are (id, content, deadline, assignees), sorted by the caller."""
    local = datetime.fromtimestamp(now, ZoneInfo('Asia/Ho_Chi_Minh'))
    name = 'cả Team' if group else given_name(name)
    lines = [f'Xin chào {name}! Chúc bạn một ngày mới vui vẻ!' if not group else
             'Xin chào cả Team! Chúc mọi người một ngày mới vui vẻ!',
             '🌟 ' + WISHES[(local.date().toordinal() - 1) % len(WISHES)], '',
             '📌 Hôm nay hãy nhớ những hạng mục cần hoàn thành!']
    for index, (_, content, deadline, _) in enumerate(tasks, 1):
        due = datetime.fromtimestamp(deadline, ZoneInfo('Asia/Ho_Chi_Minh'))
        lines.extend(['', f'{index}. {compact_links(content)}',
                      '⏰ Thời gian cần hoàn thành: ' + due.strftime('%H:%M · %d/%m/%Y')])
    lines.extend(['', 'Hãy nhớ sắp xếp công việc để hoàn thành deadline nhé!'])
    return MarkdownMessage('\n'.join(lines))
