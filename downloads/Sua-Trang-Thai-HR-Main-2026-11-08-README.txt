DASHBOARD CHÍNH — SỬA LƯU TRẠNG THÁI HR — 08/11/2026

Trang chính: https://centraltraining.github.io/Dashboard/

Sau triển khai, tải lại trang để dùng luồng lưu mới. Không cần đổi kết nối Google Sheet hoặc triển khai lại Apps Script.

HR chính và ghi chú ON/OFF được lưu đồng thời qua API có xác thực Dashboard. Trainer sửa các trường được phân quyền hoặc gửi yêu cầu; chỉ Admin áp dụng trạng thái chính thức. API kiểm tra lại quyền và tháng đang mở. Tab giữ dữ liệu cũ không được ghi đè quyết định đã duyệt mới hơn. Các tab chạy giao diện cũ phải tải lại trước khi lưu HR.

Giữ quy tắc HR cố định: source OFF chưa có quyết định OFF được duyệt không tự đổi trạng thái HR. Trạng thái khác Đang làm không tính trong các biểu đồ phân bổ và danh sách lọc Đang làm; vẫn giữ hồ sơ để đối soát. Tháng đã khóa được bảo vệ. Lịch cập nhật 23:59, thông báo/KPI và Google Apps Script không thay đổi.

Mã HTML đầy đủ ở tệp đính kèm phiên bản này. Mã máy chủ, SQL và kiểm thử đầy đủ được cung cấp riêng trong ZIP cho chủ hệ thống; không đưa mã xác thực máy chủ lên kho công khai.

Kiểm thử trước triển khai: Admin lưu đồng thời HR/ONOFF; lỗi và xung đột không lưu một phần; Trainer không tự duyệt hoặc sửa PG khác; giữ trạng thái đã duyệt qua đồng bộ; chặn ghi cũ; khóa tháng; dữ liệu lưu/snapshot/audit cùng khớp; giao diện 1440/390/320px. Tự động kiểm thử dùng dữ liệu giả lập.
