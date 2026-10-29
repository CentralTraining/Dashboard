# Nhập A để tính Target truyền thông — Cài đặt → Target — Dashboard chính 29/10/2026

Bản chính dùng đúng bản Test đã sửa vị trí. Danh sách Chiến dịch và luồng Lưu Target nhập tay giữ nguyên mã hiện hành. Tính năng mới nằm ngay tại **Cài đặt → Target**, trong bảng set Target của chiến dịch Truyền thông **Nội bộ** hoặc **Đối tác**.

## Thao tác

1. Mở https://centraltraining.github.io/Dashboard/, đăng nhập Admin → Cài đặt → Target.
2. Chọn đúng chiến dịch Truyền thông Nội bộ hoặc Đối tác.
3. Nếu Target đang chốt, bấm **Sửa Target** như giao diện hiện có.
4. Chọn một cách nhập:
   - Nhập Target từng Trainer bằng tay rồi bấm **Lưu Target**, như trước.
   - Bấm **Nhập A — Số bài/PG**, nhập A, xem trước target từng Trainer rồi bấm **Lưu Target** trong cửa sổ.
5. Bảng set Target sẽ hiển thị ngay các tổng đã tính và chốt lại theo luồng hiện có.

Công thức: **Target Trainer = A × số PG OPPO đang làm do Trainer phụ trách**. Ví dụ A=3, Trainer có 50 PG đang làm → Target 150 bài. A là số nguyên lớn hơn 0. Nút tính theo A là lựa chọn bổ sung; các ô nhập tay vẫn giữ nguyên.

## Quy tắc và dữ liệu

- Nhân sự lấy đúng tháng của chiến dịch. Chỉ đếm PG OPPO trạng thái Đang làm theo Trainer; loại Thai sản, OFF, CODE ĐẠI LÝ và thương hiệu khác.
- Mỗi Code chỉ tính một lần. Dòng trùng cùng phân công/trạng thái được gộp; cùng Code nhưng khác Trainer hoặc trạng thái thì dừng để kiểm tra trùng.
- PG thiếu Code dùng mã dòng đã lưu; không tự sinh mã. PG chưa gán Trainer hợp lệ có cảnh báo và chưa tính vào Trainer nào.
- Trainer không có PG đủ điều kiện được tính Target 0. Target lưu riêng theo chiến dịch; không thay Target của các chiến dịch khác.
- Khi tháng khóa thì không lưu. Nếu chưa có nhân sự đúng tháng, nguồn đọc/lưu lỗi hoặc nhân sự vừa thay đổi, hệ thống báo rõ và không tự tạo số liệu 0 thay nguồn thiếu.
- A chỉ áp dụng khi Admin nhập và lưu. Target chốt theo nhân sự tại thời điểm lưu; khi nhân sự thay đổi, có thể dùng lại nút Nhập A để tính lại. Sau đó vẫn có thể Sửa Target và điều chỉnh bằng tay.

Lưu bằng A dùng một lượt ghi campaigns + mediaTargets:<campaignId> để giữ cấu hình và số tổng nhất quán. Bảng Target được làm mới sau khi lưu thành công, không lưu cache Target cũ vào campaign. Không thay danh sách PG, số thực tế, records, schema, Secrets, backend, FTF, TikTok, FindMaster hoặc KPI Ollie. Không tự chọn A cho chiến dịch thật khi triển khai.

## Kiểm thử và xuất source

Đã kiểm thử bằng dữ liệu giả lập trên 1440/390/320 px: nút đúng Cài đặt → Target; không có nút ở Chiến dịch; nhập tay vẫn lưu; cả hai loại chiến dịch độc lập; đúng tháng; đếm PG đang làm/Code trùng; nguồn thiếu, lỗi lưu, khóa tháng và roster thay đổi; đổi tháng/tài khoản/chiến dịch khi đang lưu không ghi nhầm; đọc lại số Target bằng luồng KPI hiện có.

HTML đầy đủ: Dashboard-Chinh-2026-10-29-Target-Truyen-Thong-A-PG.html. Source ZIP có model.js, media-target-a.js, style.css, prepare.py, README và proof, không có Secrets hay dữ liệu người dùng thực. Đây là phiên bản Dashboard chính; bản Test giữ nguyên. Không tự điền A hoặc thay số Target của chiến dịch thật trong đợt triển khai.
