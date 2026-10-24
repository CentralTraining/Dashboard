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
    def test_short_day_month_uses_original_posting_year_and_exact_evening_hour(self):
        posted = datetime(2026, 10, 23, 12, tzinfo=VIETNAM).timestamp()
        for text in (
            'THÔNG BÁO LĂNG KÍNH FIND X10\nNộp nội dung chương trình.\nDeadline: 22h ngày 25.10',
            'Thông báo lăng kính Find X10, hoàn thành trước 22h ngày 25.10',
            'Lăng kính Find X10 — 22h ngày 25.10',
            'Lăng kính Find X10\nThời gian: 22:00, 25/10',
        ):
            with self.subTest(text=text):
                self.assertTrue(has_deadline(text))
                summary, due = parse_announcement(text, posted)
                self.assertIn('find x10', summary.casefold())
                self.assertEqual(datetime.fromtimestamp(due, VIETNAM).isoformat(), '2026-10-25T22:00:00+07:00')

    def test_inline_registration_notice_keeps_work_and_both_complete_links(self):
        from daily_digest import format_deadline_digest
        posted = datetime(2026, 10, 23, 12, tzinfo=VIETNAM).timestamp()
        form = 'https://docs.google.com/spreadsheets/d/SYNTHETIC_FORM/edit?gid=0#gid=0'
        image = 'https://example.test/notice-image.jpg'
        text = ("CHƯƠNG TRÌNH - LĂNG KÍNH FINDX10 SERIES\n"
                "Như các thông tin trưa nay đã họp nhanh về Chương trình thi đua truyền thông FindX10 giữa các khu vực, Leader gửi lại chi tiết thông tin và các công việc cần làm.\n"
                f"Trước tiên anh em điền link đăng kí page đăng bài trước 22h ngày 25/10 [{form}]({form})\n"
                f"[image]({image})\n=======\n@Tất cả")
        text = text.replace(' ', '\u00a0')
        summary, due = parse_announcement(text, posted)
        self.assertEqual(datetime.fromtimestamp(due, VIETNAM).isoformat(), '2026-10-25T22:00:00+07:00')
        rendered = format_deadline_digest('Trainer thử nghiệm', [(1, summary, due, ['synthetic'])], posted)
        self.assertIn('điền link đăng kí page đăng bài', rendered)
        self.assertNotIn('Như các thông tin', rendered)
        self.assertNotIn('image;', rendered)
        self.assertNotIn('Tất cả', rendered)
        self.assertEqual(rendered.count(form), 1)
        self.assertEqual(rendered.count(image), 1)

    def test_nbsp_due_labels_are_read_and_link_destinations_are_unchanged(self):
        posted = datetime(2026, 10, 23, 12, tzinfo=VIETNAM).timestamp()
        link = 'https://example.test/form?token=abc%2B123&entry=2'
        text = f'Nộp báo cáo\nHạn\u00a0hoàn\u00a0thành:\u00a022h\u00a0ngày\u00a025/10\nLink: {link}'
        self.assertTrue(has_deadline(text))
        summary, due = parse_announcement(text, posted)
        self.assertIn(link, summary)
        self.assertEqual(datetime.fromtimestamp(due, VIETNAM).hour, 22)

    def test_bare_sheet_link_after_short_date_does_not_become_an_extra_clock(self):
        posted = datetime(2026, 10, 23, 12, tzinfo=VIETNAM).timestamp()
        for link in ('https://example.test/form?gid=0', 'https://example.test/form?session=14:00&gid=0'):
            with self.subTest(link=link):
                summary, due = parse_announcement(f'Điền link đăng kí page trước 22h ngày 25/10 {link}', posted)
                self.assertEqual(datetime.fromtimestamp(due, VIETNAM).isoformat(), '2026-10-25T22:00:00+07:00')
                self.assertIn('Điền link đăng kí page', summary)
                self.assertIn(link, summary)

    def test_short_dates_do_not_reschedule_old_notices_or_guess_distant_years(self):
        posted = datetime(2026, 10, 24, 12, tzinfo=VIETNAM).timestamp()
        for date in ('23.10', '25.2', '31.2'):
            with self.subTest(date=date), self.assertRaises(ValueError):
                parse_announcement(f'Nộp báo cáo\nDeadline: 22h ngày {date}', posted)
        december = datetime(2026, 12, 30, 12, tzinfo=VIETNAM).timestamp()
        _, due = parse_announcement('Nộp báo cáo\nDeadline: 22h ngày 2.1', december)
        self.assertEqual(datetime.fromtimestamp(due, VIETNAM).isoformat(), '2027-01-02T22:00:00+07:00')

    def test_multiple_natural_deadlines_and_conflicting_relative_dates_stay_ambiguous(self):
        posted = datetime(2026, 10, 23, 12, tzinfo=VIETNAM).timestamp()
        with self.assertRaises(ValueError):
            parse_announcement('Nộp 2 video\n22h ngày 25.10\n17h ngày 26.10', posted)
        with self.assertRaisesRegex(ValueError, 'không khớp'):
            parse_announcement('Nộp báo cáo\nDeadline: 22h ngày mai 25.10', posted)

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

