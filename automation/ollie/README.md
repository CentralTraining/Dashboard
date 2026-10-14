# Lịch KPI trên GitHub

Dashboard vẫn ở https://centraltraining.github.io/Dashboard/. GitHub Actions
đọc nguồn Supabase đang dùng và gửi báo cáo bằng ứng dụng Ollie_MT đã phát hành.
Không cần Netlify hoặc đổi dashboard sang nơi khác.

Lịch ngoài GitHub có thể kích hoạt bản nhắc bằng cách cập nhật đúng file
`automation/ollie/kpi-trigger.json` trên nhánh `main`. File chỉ chứa ngày và
thời điểm yêu cầu, không chứa dữ liệu KPI, danh tính hay thông tin đăng nhập.
GitHub chạy workflow ngay theo sự kiện `push` của file này, dùng cùng sổ gửi
với cron và lượt gửi bù. Vì vậy cùng một ngày không gửi lại tin đã tiếp nhận.
Ứng dụng GitHub được kết nối phải tạo commit này; commit bằng token nội bộ
`GITHUB_TOKEN` của Actions sẽ không tự kích hoạt workflow khác.

Lịch 08:00 còn gửi danh sách việc có deadline từ thông báo Nghĩa đăng trong
nhóm AE CÂY KHẾ CHUA. Không nhập công việc trên dashboard. Việc mới được
nhắc từ sáng hôm sau; các việc sắp theo deadline gần nhất rồi thời điểm tạo.
Mỗi Trainer có lời chào bằng tên và lời chúc đổi mỗi ngày; link được thu gọn
thành chữ Link nhưng giữ nguyên URL đích, ID họp và mật mã.
Việc hoàn thành, bị hủy hoặc qua deadline không được nhắc tiếp.
Chỉ dữ liệu có deadline rõ ràng mới vào danh sách việc; không đoán ngày
kết thúc từ tên chiến dịch KPI.

Workflow **Ollie group notices** đọc lịch sử nhóm mỗi 15 phút bằng kết nối
DingTalk của Nghĩa đã được cấp quyền. Chỉ thông báo của đúng Nghĩa trong
đúng nhóm được tạo thành việc. Không cần @bot để bộ đọc lịch sử nhận tin.
Trước bản nhắc 08:00, bộ đọc chạy lại để lấy cả thông báo vừa đăng.
Thông tin đăng nhập được giữ trong sổ trạng thái đã mã hóa, không đưa
token hoặc bản thông báo gốc vào log hay mã nguồn. Bộ đọc này không cần
Cloudflare hoặc Mac bật liên tục. Phản hồi trò chuyện ngay khi @bot vẫn
là chức năng riêng của Stream/HTTP; `cloudflare/README.md` mô tả tùy chọn HTTP.

Trong khoảng 08:00 đến trước 12:00 giờ Việt Nam, workflow đọc nhóm còn kiểm
tra và gửi bù bản nhắc buổi sáng nếu workflow KPI chưa gửi được. Hai workflow
dùng cùng sổ gửi và cùng khóa chạy: tin đã được DingTalk tiếp nhận không gửi
lại. Lỗi đăng nhập hoặc tải CLI của bộ đọc nhóm không ngăn bước gửi KPI bù.
Ngoài khoảng giờ này, workflow chỉ đọc thông báo. Chạy thủ công mặc định
không gửi tin; chọn `catchup=true` khi cần kiểm tra lượt gửi bù buổi sáng.

Báo cáo cá nhân dùng tên gọi và 3 nhóm 🏫 Nội bộ, 🤝 Đối tác, 📣 Truyền
thông. Chỉ số có target trong tháng mới được hiển thị, theo mẫu
`Unbox A7 Pro NB: 50/51 · 98%`. Tên chiến dịch được rút ngắn, cụm số dùng
khoảng trắng không ngắt dòng. Các đơn vị khác nhau giữ thành chỉ số riêng.
Bản tổng hợp gửi riêng cho Nghĩa có 13 Trainer, mỗi người 3 phần trăm tiến
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
5. Kiểm tra lần chạy đầu và tin nhắn DingTalk: 13 Trainer nhận báo cáo cá nhân,
   Nghĩa nhận tổng hợp riêng. KPI không gửi lên nhóm chung.

`0 1 * * *` là 08:00 giờ Việt Nam. GitHub có thể chạy trễ khi hàng đợi bận;
lịch Actions không cam kết gửi đúng từng giây. Các lượt dự phòng lúc 08:17,
08:37, 08:57, 09:17, 09:37 và 09:57 kiểm tra và gửi bù phần chưa gửi trong
ngày. Sổ gửi đã mã hóa giữ nguyên kết quả: Trainer đã được DingTalk tiếp
nhận tin nhắn sẽ không nhận lại ở lượt dự phòng. Kết quả gửi chưa rõ ràng
vẫn cần kiểm tra, không tự gửi lại. Repo công khai phải có hoạt
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

GitHub Actions chạy **đọc thông báo nhóm và lịch gửi**, không giữ kết nối Stream liên tục để bot
trò chuyện ngay với mọi người. Phần phản hồi hội thoại hiện vẫn do chương
trình chạy thử xử lý; muốn phần này chạy 24/7 cần một máy chạy liên tục.
