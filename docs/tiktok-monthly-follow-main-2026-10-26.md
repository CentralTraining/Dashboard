# TikTok — tăng follow theo tháng — Dashboard chính 26/10/2026

- Tháng 10/2026 dùng mốc ngày 01/10 Admin đã nhập, không ghi đè mốc.
- Từ tháng 11/2026 dùng lần ghi nhận TikTok API đầu tiên trong ngày 01 theo giờ Việt Nam. Các lần quét tiếp theo không dịch mốc. Cần đồng bộ trong ngày 01; hệ thống hiện tự đồng bộ khi trang đang mở, không có tác vụ chụp mốc khi trang đóng. Thiếu mốc thực tế thì để trống, không suy ra từ ngày khác.
- Thẻ Tăng Follow hiện tổng tăng của các kênh đủ dữ liệu, kèm số kênh đã tính. Không ẩn toàn bộ tổng khi chỉ một kênh thiếu dữ liệu.
- Thêm trung bình FL tăng của toàn team trong phạm vi tài khoản: tổng tăng / số kênh đủ dữ liệu; ghi rõ mẫu số khi còn thiếu kênh. Bộ lọc Trainer không đổi trung bình toàn team. Trainer chỉ thấy trung bình khu vực được phép.
- Cột Follow hiện số hiện tại trước / mức tăng tháng sau; số tăng giảm giữ đúng dấu. Giá trị lớn được rút gọn trong bảng, tooltip và lịch sử giữ số đầy đủ.
- Chọn tháng: tính từ mốc đầu tháng đến lần ghi nhận cuối trong tháng, tối đa hôm nay. Tuần/khoảng ngày: dùng tháng chứa ngày cuối kỳ, tối đa hôm nay. Khoảng hoàn toàn tương lai chưa có số tăng. Số hiện tại luôn là số mới nhất đã ghi, kể cả khi xem tháng cũ; thời điểm hiện rõ trong tooltip.
- Các số liệu Bài đăng/View/Like/Share vẫn theo video đăng trong kỳ đã chọn. Bố cục hai bảng và bảng nhịp đăng giữ nguyên.

Triển khai nguyên HTML đã kiểm thử tại CentralTraining/Test commit de18e7bd44ff8e1b60abfac4edb2d24417bff616 vào Dashboard chính theo yêu cầu Nghĩa. Thay đổi chỉ nằm ở hai khối Xây kênh; các phần còn lại giống bản chính trước đó. Không thay Edge Functions dùng chung, OAuth callback, khóa, kết nối, số liệu, mốc Admin, tự động hóa hoặc sổ gửi KPI.

## Kiểm tra

- Mô hình: mốc Admin ưu tiên; chuyển tháng/năm; 00:00 giờ Việt Nam; nhiều lần quét ngày 01; thiếu mốc; kỳ tương lai; khoảng qua tháng; mốc 0; tăng âm; tổng một phần và trung bình; không sửa lịch sử. Mã lưu lịch sử hiện có giữ mốc đầu ngày nên không cần sửa backend.
- Trình duyệt 320, 390, 1024, 1440, 1920 px với dữ liệu giả lập: hai số Follow không bị cắt; không cuộn ngang; thẻ tổng/trung bình/độ phủ; lịch sử và bộ lọc hoạt động; giữ phân quyền; không ghi dữ liệu qua kiểm thử.
- Kiểm tra hồi quy giao diện máy tính/điện thoại: menu, bảng chỉ số, quản lý kênh, video và lịch sử, bộ lọc, tài khoản Trainer và trạng thái tháng KPI.

Các số trong kiểm thử là dữ liệu giả lập, không phải báo cáo Trainer thật.
