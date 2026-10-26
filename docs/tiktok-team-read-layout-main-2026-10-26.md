# TikTok — bố cục mới và Trainer xem toàn team — Dashboard chính 26/10/2026

Triển khai đúng HTML bản Test đã kiểm tra tại CentralTraining/Test commit 7fc3e74017f3cd74634214c593a96f555be68afb theo yêu cầu Nghĩa.

## Giao diện

- Bảng Tiến độ bài đăng bên trái khoảng 41%, bảng Follow · View · Like · Share bên phải khoảng 59%; có thêm chỗ cho tên Trainer và cặp số follower hiện tại / tăng trưởng.
- Bộ lọc tuần/tháng/khoảng ngày, khu vực và Trainer dùng nhãn, viền xanh bo góc và căn hàng theo các mục Dashboard. Điện thoại chia hàng gọn, không tràn ngang.
- Giữ nguyên logic tăng Follow theo tháng: tháng 10 dùng mốc Admin đã đặt; từ tháng sau dùng lần ghi nhận thực tế đầu tiên trong ngày 01. Thiếu mốc để trống. Tổng và trung bình ghi số kênh đủ dữ liệu. View/Like/Share vẫn theo video đăng trong kỳ.

## Quyền xem và thao tác

- Trong riêng mục Xây kênh TikTok, Trainer hợp lệ đã đăng nhập xem được chỉ số của mình và tất cả Trainer khác, lọc theo mọi khu vực và Trainer; trung bình là của toàn team.
- Main và Test cùng dùng team-overview.ts đã kiểm tra để đọc dữ liệu mã hóa dùng chung. Không trả token OAuth/refresh, Client Secret, openId hoặc hồ sơ đăng nhập. Không sao chép hoặc đổi grant khi xem.
- Quyền gán kênh, đặt mốc Admin, kết nối và đồng bộ giữ cơ chế cũ trong trainer-channel-api. Trainer chỉ kết nối kênh của mình; đồng bộ theo khu vực được giao. Khi xem ngoài khu vực, nút Đồng bộ tải lại chỉ số đã lưu.
- Main vẫn giữ signed owner route để refresh grant Main ở đúng bản ghi gốc. Mọi callback giữ nguyên, không yêu cầu cấp quyền hoặc đăng nhập lại chỉ vì đợt giao diện/quyền đọc này.
- Các chức năng khác của Dashboard giữ phạm vi quyền cũ. Không thay shared controller trainer-channel-api, Secrets, callback TikTok hoặc dữ liệu/mốc Admin.

## Triển khai backend

Project qruxqlsbhyhwiqjdkyyc, trainer-channel version 11, source SHA-256 b6b4b15b5db0ad19b872c075e1ff6dacbb79badc97a39383f0a547ea89b3bbc0. Gồm đúng 9 source/dependency files trong gói. Test vẫn ở trainer-channel-test version 15; shared API version 2 không sửa.

## Kiểm tra

Backend và trình duyệt bằng dữ liệu giả lập: Trainer xem toàn bộ 13 kênh cả khu vực khác; DTO Main/Test giống nhau; không ghi khi đọc hoặc trả thông tin xác thực; quyền ghi/kết nối không vượt phạm vi; token giả, tài khoản khóa/đổi mật khẩu/vai trò bị chặn; 2 Sandbox và grant Main cũ giữ đúng; native Main refresh và callback hoàn tất đúng URL Dashboard. Giao diện chính 390/1440 px không tràn ngang, có đủ 13 dòng, lọc khu vực/Trainer và lịch sử, có trung bình toàn team, chỉ hiện kết nối bản thân, không gửi sync ngoài phạm vi. Bố cục/bộ lọc đã kiểm tra 320/390/1024/1440/1920 px trên Test.

Gói chứa HTML đầy đủ và toàn bộ source/dependencies của function Main thực sự triển khai. Không chứa Secrets, thông tin đăng nhập hoặc dữ liệu Trainer thật.
