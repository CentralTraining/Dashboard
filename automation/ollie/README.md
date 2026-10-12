# Lịch KPI trên GitHub

Dashboard vẫn ở https://centraltraining.github.io/Dashboard/. GitHub Actions
đọc nguồn Supabase đang dùng và gửi báo cáo bằng ứng dụng Ollie_MT đã phát hành.
Không cần Netlify hoặc đổi dashboard sang nơi khác.

Báo cáo cá nhân dùng tên gọi và 3 nhóm 🏫 Nội bộ, 🤝 Đối tác, 📣 Truyền
thông. Chỉ số có target trong tháng mới được hiển thị, theo mẫu
`Unbox A7 Pro NB: 50/51 · 98%`. Tên chiến dịch được rút ngắn, cụm số dùng
khoảng trắng không ngắt dòng. Các đơn vị khác nhau giữ thành chỉ số riêng.
Bản tổng hợp cho nhóm và Nghĩa có 13 Trainer, mỗi người 3 phần trăm tiến
độ, cùng lưu ý cần tập trung theo từng nhóm. WS đối tác được ghi rõ là số
liệu chung khu vực. Phần trăm mỗi nhóm lấy trung bình chỉ số có target,
giới hạn mỗi chỉ số ở 100% trước khi tính trung bình.

## Cách áp dụng

1. Thêm `.github/workflows/ollie-kpi.yml` và thư mục `automation/ollie/` từ bộ
   file đã chuẩn bị vào nhánh mặc định của repo `centraltraining/Dashboard`.
2. Trong Settings → Secrets and variables → Actions, tạo một repository
   secret `OLLIE_KPI_CONFIG_JSON` bằng cấu hình riêng đã chuẩn bị. Cấu hình
   này bao gồm khóa mã hóa sổ gửi; không đưa khóa, tài khoản Trainer hoặc thư
   mục `runtime/` vào Git.
3. Vào Actions → Ollie KPI daily → Run workflow, giữ **send=false** để kiểm tra
   nguồn dữ liệu và đủ 13 Trainer mà không gửi thêm tin nhắn.
4. Sau khi bước kiểm tra thành công, tắt **riêng lịch KPI** của chương trình
   đang chạy thử để tránh hai nơi cùng gửi. Lịch GitHub tự chạy từ lần 08:00
   tiếp theo sau ngày bắt đầu trong cấu hình; mỗi ngày chỉ tạo một bản nhắc.
5. Kiểm tra lần chạy đầu và tin nhắn DingTalk: nhóm nhận tổng hợp, 13 Trainer
   nhận báo cáo cá nhân, Nghĩa nhận tổng hợp riêng.

`0 1 * * *` là 08:00 giờ Việt Nam. GitHub có thể chạy trễ khi hàng đợi bận;
lịch Actions không cam kết gửi đúng từng giây. Repo công khai phải có hoạt
động trong 60 ngày để lịch không tự bị GitHub ngừng do không hoạt động.

## Dữ liệu và kiểm soát gửi lặp

Nhánh riêng `ollie-kpi-state` lưu SQLite **đã mã hóa AES-GCM**, không chứa mã
HTML dashboard hoặc nội dung bản rõ. Actions cần `contents: write` để cập
nhật sổ gửi này. Khóa mã hóa lưu trong repository secret, không thay khóa
hoặc xóa nhánh trạng thái khi đang vận hành mà chưa chuyển sổ gửi.

Sổ ghi nhận trạng thái trước khi gọi DingTalk. Đã có mã tiếp nhận thì không
gửi lại. Mất kết quả giữa chừng giữ `unknown` để kiểm tra, không tự gửi lặp.
Lỗi bị từ chối rõ ràng giữ `retry` cho lần chạy tiếp theo. Log chỉ ghi số lượng
và mã lỗi, không in nội dung, tài khoản hoặc khóa. Dữ liệu KPI lấy mới ở mỗi
ngày; nếu mất nguồn hoặc thiếu Trainer, không tạo số 0 giả.

GitHub Actions chạy **lịch gửi KPI**, không giữ kết nối Stream liên tục để bot
trò chuyện ngay với mọi người. Phần phản hồi hội thoại hiện vẫn do chương
trình chạy thử xử lý; muốn phần này chạy 24/7 cần một máy chạy liên tục.
