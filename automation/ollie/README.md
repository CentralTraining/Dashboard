# Ollie_MT — lưu công việc và nhắc deadline

Đây là chương trình nhận tin nhắn mới bằng DingTalk Stream và trả lời tiếng Việt.
Trong nhóm, người dùng cần chọn đúng bot trong danh sách @ rồi gửi tin nhắn.
Tin nhắn riêng gửi trực tiếp cho bot cũng được xử lý.

Lịch đã chốt: 08:00 mỗi ngày theo giờ Việt Nam, từ 4 ngày theo lịch trước
deadline, gửi trong nhóm đã cấu hình và riêng từng người phụ trách, gồm cả leader. Việc mới
được tạo sau 08:00 bắt đầu ở lần nhắc 08:00 kế tiếp. Dừng nhắc khi đã qua
deadline, hoàn thành hoặc bị hủy. Danh sách vẫn giữ việc quá hạn để tra cứu.
Dữ liệu lưu trong SQLite ở `runtime/`.

Trong nhóm, chọn @Ollie_MT khi gửi từng lệnh. Bot nhận các lệnh giao việc theo
mẫu và trò chuyện bằng mô hình chạy tại chỗ. Phần trò chuyện không tự thay đổi
dữ liệu hay tạo lịch thay cho các lệnh đã kiểm tra.

```text
giao việc
Người phụ trách: tôi
Nội dung: Nộp báo cáo đào tạo
Deadline: 20/10/2026 17:00
```

Chọn @Trainer thật từ danh sách ở dòng Người phụ trách để giao cho người khác.
Trainer có thể gửi `đăng ký Trainer` để lưu tên và tài khoản của chính mình.
Mỗi người phụ trách có trạng thái hoàn thành riêng. Chỉ leader tạo công việc,
đổi hạn, hủy hoặc bật/tắt lịch; Trainer được hoàn thành phần việc của mình.

Thông báo họp có tiêu đề THÔNG BÁO, một dòng Thời gian/Deadline và giờ/ngày
rõ ràng được rút gọn thành một buổi họp. Các mục agenda không tạo thành các
công việc riêng. Ngày tương đối dùng thời điểm tin nhắn theo giờ Việt Nam;
ngày/tháng/thứ mâu thuẫn hoặc thiếu năm thì hỏi lại. Nhắc toàn bộ danh sách
`audience_staff_ids` đã xác nhận, cùng leader. Khi chưa có danh sách, chỉ đưa
bản rút gọn và không tuyên bố tạo lịch nhắc cho tất cả mọi người.

Link tham gia họp được giữ đầy đủ, gồm cả tham số trong URL. ID cuộc họp và
mật mã được giữ nguyên; phần thông tin tham gia không bị cắt theo giới hạn
rút gọn agenda.

Mỗi bản nhắc đánh số công việc theo deadline gần nhất và gộp các phân công
cùng một việc. Riêng leader nhận bản tổng hợp tất cả việc cần nhắc.

Lịch lời chào riêng: 19:39 giờ Việt Nam hằng ngày, gửi vào nhóm được xác nhận.
Nội dung và trạng thái bật/tắt nằm trong `runtime/greeting-schedule.json`.

- `hướng dẫn` / `trạng thái`
- `danh sách` / `việc của tôi`
- `hoàn thành CV-1` (leader: toàn bộ phân công; Trainer: phần việc cá nhân)
- `đổi hạn CV-1 21/10/2026 17:00`
- `hủy CV-1` / `hủy NR-1`
- `nhắc sau 2 phút: Kiểm tra Ollie_MT` (nhóm và riêng cho leader)
- `tắt nhắc việc` / `bật nhắc việc`

Lời nhắc đặt theo phút gửi nguyên nội dung đã lưu. Mã NR, người nhận và thời
điểm gửi được giữ trong dữ liệu quản lý, không ghép vào tin nhắn gửi đi. Với
nhắc công việc theo deadline, vẫn hiển thị thời hạn công việc và thứ tự ưu tiên.

Lời nhắc chủ động dùng Open API của ứng dụng. Outbox tách trạng thái gửi cho
nhóm và từng người; một nơi bị lỗi không làm gửi lại nơi đã được chấp nhận.
Chỉ ghi nhận `accepted` khi DingTalk trả mã tiếp nhận. Trạng thái này chưa
chứng minh thông báo đã hiển thị trên thiết bị. Yêu cầu gửi có kết quả không
rõ (timeout/interrupted) giữ `unknown` để tránh tự động gửi lặp.

Chạy thử:

```bash
/workspace/ollie-bot/.venv/bin/python /workspace/ollie-bot/app.py
```

Ứng dụng đọc thông tin xác thực từ tệp riêng trong thư mục cấu hình của CLI;
không đưa khóa vào mã nguồn hoặc tham số lệnh. Chỉ dùng sessionWebhook để trả
lời ngay, không lưu webhook để gửi các lời nhắc trong tương lai. Trạng thái kết
nối và sổ chống xử lý lại tin nhắn nằm trong `runtime/`, được loại khỏi Git.

Kết nối KPI đọc dữ liệu dùng chung của dashboard tại
https://centraltraining.github.io/Dashboard/ qua Supabase. Bot chỉ đọc các
khóa KPI cần thiết; không đọc bảng tài khoản hoặc sửa dữ liệu dashboard.
Mỗi lần nhắc lấy dữ liệu mới của tháng hiện tại theo giờ Việt Nam.

Lịch KPI: 08:00 Việt Nam hằng ngày, bắt đầu 13/10/2026. Chỉ gửi riêng:
13 Trainer nhận báo cáo cá nhân và Nghĩa nhận bản tổng hợp. Không gửi KPI vào nhóm.
Đã đối chiếu đủ 13 Trainer, gồm Trần Phong Độ; nhóm có 14 thành viên người.
Tên hiển thị chỉ dùng tên gọi. Báo cáo cá nhân chia 3 nhóm: Nội bộ, Đối tác,
Truyền thông; chỉ hiển thị chỉ số có target lớn hơn 0 trong tháng hiện tại.
Tên chiến dịch được rút gọn; mỗi dòng dùng `đã làm/target · %`, giữ cụm số
liệu bằng khoảng trắng không ngắt dòng. Các đơn vị khác nhau (shop, học viên,
bài, buổi) vẫn là các chỉ số riêng, không cộng thành một số lượng.
Nội bộ gồm Coaching và Workshop nội bộ; Đối tác gồm FTF và WS đối tác;
Truyền thông gồm chiến dịch nội bộ và đối tác. WS đối tác là số liệu chung
theo khu vực, có ký hiệu riêng; không cộng lặp thành kết quả toàn Team.
Bản tổng hợp liệt kê 13 Trainer, mỗi người có 3 phần trăm tiến độ. Phần
cần tập trung chọn một chỉ số chưa đạt có tiến độ thấp nhất trong mỗi nhóm.
Phần trăm nhóm là trung bình các chỉ số có target, giới hạn mỗi chỉ số ở
100% để kết quả vượt target không che các chỉ số chưa hoàn thành.

Cấu hình nguồn và người nhận nằm trong `runtime/kpi/`; không đưa khóa nguồn
hoặc thông tin tài khoản vào Git. `settings.json` điều khiển lịch KPI,
`health.json` ghi lần chuẩn bị gần nhất, còn SQLite ghi lần chạy mỗi ngày
và trạng thái gửi cho từng nơi nhận. Mất nguồn hoặc thiếu đối chiếu Trainer
sẽ chờ và báo lỗi nội bộ, không tạo báo cáo có số 0 giả.

Lịch KPI chạy trên GitHub Actions với sổ gửi đã mã hóa; xem
`github-actions/README.md`. Phần trò chuyện Stream và nhắc deadline thường
hiện chạy trong môi trường làm việc của phiên này; cần một nơi chạy liên
tục và sao lưu SQLite để phần đó vận hành 24/7. Chưa tự động mở rộng bot
sang những nhóm khác.

Kiểm tra: `.venv/bin/python -m unittest -v test_tracker test_announcements test_kpi test_kpi_scheduler test_github_daily`.

SDK chính thức: https://github.com/open-dingtalk/dingtalk-stream-sdk-python

Tra cứu dữ liệu dashboard qua tin nhắn riêng: xem [hướng dẫn](DASHBOARD_CHAT.md).
Quyền được kiểm tra từ tài khoản DingTalk cho từng câu hỏi; Trainer chỉ xem khu vực
đã đối chiếu, leader xem toàn bộ dữ liệu nghiệp vụ. Không gửi dữ liệu tra cứu đến
mô hình AI hay nhà cung cấp ngoài. Kiểm tra phân quyền và hội thoại:
`.venv/bin/python -m unittest -q test_dashboard_qa test_conversation test_response_handler`.

Open API: https://open.dingtalk.com/document/orgapp/the-robot-sends-a-group-message
