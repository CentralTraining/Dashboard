import unittest
from datetime import datetime
from announcements import parse_meeting, meeting_deadline, summarize_meeting,parse_announcement,has_deadline
from tracker import VIETNAM


SAMPLE='''📢 THÔNG BÁO HỌP TRAINER TOÀN QUỐC
Dear anh em Trainer,
+ Truyền thông OPPO A7 Pro
+ Kế hoạch content Buds3s
+ Review hoạt động IoT Month
+ Cập nhật hoạt động team OCS
⏰ Thời gian: 14:00, ngày mai – Thứ Bảy 12.9
💻 Hình thức: Online qua Zoom
🔗 Link Zoom: https://example.zoom.us/j/12345678901?pwd=example%2Btoken.1&source=test
ID cuộc họp: 123 4567 8901
Mật mã: 001901
'''


class AnnouncementChecks(unittest.TestCase):
    def test_natural_inline_deadline_retains_the_work_and_vietnam_hour(self):
        source=datetime(2026,10,14,9,tzinfo=VIETNAM).timestamp()
        for suffix in ('trước 17h ngày 20/10/2026','chậm nhất 17 giờ 30 ngày 20/10/2026','Deadline 20/10/2026 17:00'):
            text='THÔNG BÁO\nMỗi Trainer nộp 2 video '+suffix
            summary,due=parse_announcement(text,source)
            self.assertIn('Mỗi Trainer nộp 2 video',summary)
            self.assertEqual(datetime.fromtimestamp(due,VIETNAM).hour,17)
        self.assertEqual(datetime.fromtimestamp(parse_announcement('Nộp báo cáo\nHạn cuối: 2026-10-20',source)[1],VIETNAM).isoformat(),'2026-10-20T23:59:00+07:00')
        self.assertFalse(has_deadline('Tôi đã hoàn thành việc trước đó'))
        self.assertFalse(has_deadline('Deadline là gì'))
        self.assertFalse(has_deadline('Thời gian sử dụng pin của sản phẩm là bao lâu'))

    def test_sample_is_one_meeting_not_four_assignments(self):
        source=datetime(2026,9,11,9,tzinfo=VIETNAM).timestamp()
        summary,deadline=parse_meeting(SAMPLE,source)
        self.assertIn('OPPO A7 Pro, Buds3s, IoT Month, OCS',summary)
        self.assertIn('Zoom',summary)
        self.assertIn('https://example.zoom.us/j/12345678901?pwd=example%2Btoken.1&source=test',summary)
        self.assertIn('ID cuộc họp: 123 4567 8901',summary)
        self.assertIn('Mật mã: 001901',summary)
        self.assertEqual(deadline,datetime(2026,9,12,14,tzinfo=VIETNAM).timestamp())

    def test_markdown_link_keeps_complete_target_without_duplicate(self):
        url='https://example.zoom.us/j/12345678901?pwd=example%2Btoken.1&source=test'
        text=f'📢 THÔNG BÁO HỌP\nLink Zoom:\n[{url}]({url})\nID cuộc họp: 123 4567 8901\\\nMật mã: 001901\\'
        summary=summarize_meeting(text)
        self.assertEqual(summary.count(url),1)
        self.assertIn('ID cuộc họp: 123 4567 8901',summary)
        self.assertIn('Mật mã: 001901',summary)

    def test_long_access_information_is_not_truncated_with_agenda(self):
        url='https://example.zoom.us/j/12345678901?pwd='+('a'*900)
        summary=summarize_meeting('📢 THÔNG BÁO HỌP\n- '+('agenda '*200)+f'\nLink Zoom: {url}\nMeeting ID: 123 4567 8901\nPasscode: 000001')
        self.assertIn(url,summary)
        self.assertIn('Meeting ID: 123 4567 8901',summary)
        self.assertIn('Passcode: 000001',summary)

    def test_old_forwarded_sample_does_not_become_tomorrow(self):
        source=datetime(2026,10,11,9,tzinfo=VIETNAM).timestamp()
        with self.assertRaisesRegex(ValueError,'không khớp'):
            parse_meeting(SAMPLE,source)

    def test_missing_year_and_wrong_weekday_request_clarification(self):
        source=datetime(2026,10,11,9,tzinfo=VIETNAM).timestamp()
        with self.assertRaisesRegex(ValueError,'tháng và năm'):
            meeting_deadline('Thời gian: 14:00, 12.9',source)
        with self.assertRaisesRegex(ValueError,'thứ trong tuần'):
            meeting_deadline('Thời gian: 14:00, Thứ Bảy 20/10/2026',source)


if __name__=='__main__':
    unittest.main()
