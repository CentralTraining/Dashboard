# Truyền thông Nội bộ — Xuất Excel 2 sheet — Dashboard chính 29/10/2026

Vào Tiến độ KPI → Truyền thông → Nội bộ. Chọn tháng, chiến dịch và bộ lọc. Nút **Xuất Excel truyền thông (2 sheet)** ở góc trái phía trên danh sách PGs chưa hoàn thành.

- `TienDoTruyenThong`: Mã NV, Tên nhân viên, Vùng, Khu vực, Đã duyệt FB, Bị loại FB, Đã duyệt TT, Bị loại TT; bốn cột của chương trình đang chọn: Nộp, Đúng, Target, Tỷ lệ (%).
- `ChiTietLink`: Mã NV, Tên nhân viên, Vùng, Khu vực, Tên chương trình, Platform, Link, Trạng thái, View, Tim/Like, Comment, Share, Favorite. Mỗi link nguồn là một dòng, giữ cả approved/rejected và trạng thái khác.

Xuất toàn bộ PG OPPO Đang làm khớp bộ lọc, gồm đã và chưa hoàn thành, không giới hạn trang hiện tại. Nút xuất riêng PGs chưa hoàn thành vẫn giữ nguyên. Nếu muốn xuất một Trainer, chọn Trainer ở bộ lọc. Bộ lọc khu vực, Trainer, Sale toàn trang và khu vực/Trainer/tìm kiếm của danh sách đều được áp dụng. Admin được xuất toàn phạm vi; Trainer chỉ khu vực được quản lý, kiểm tra lại trên máy chủ, không dựa vào dropdown để cấp quyền.

Dữ liệu bài đăng lấy mới từ đúng endpoint `api/media-dashboard/employees` và hợp đồng xuất Excel của trang nguồn `quanly_kqtt.html`. Chọn program bằng Program ID đã lưu, hoặc khớp tên trong chế độ Nội bộ cũ. Nguồn FM bắt buộc Program ID. Cột Target/Tỷ lệ là dữ liệu từng PG từ nguồn như mẫu, không lấy target tổng Trainer chia đều. Các cột Đã duyệt/Bị loại FB/TT giữ nguyên số tổng do nguồn trả về; bốn cột chương trình và sheet link chỉ thuộc chương trình đã chọn.

Nhân sự, phân công và khu vực dựa trên DATA của tháng đã chọn trong Dashboard. PG chưa có bản ghi/chương trình từ nguồn vẫn có dòng, nhưng ô số liệu để trống và thông báo số PG thiếu dữ liệu sau xuất. Chỉ số tương tác thiếu để trống; số 0 thực từ nguồn giữ là 0. Không tự suy ra tương tác hay tạo bài giả từ tổng số approved. Dữ liệu nguồn thiếu link dù đã có bài nộp sẽ báo lỗi và không tạo file thiếu. Mã nhân viên được ghi dạng text để giữ số 0 đầu. Tất cả hai sheet cùng một lượt đọc nguồn.

Đăng nhập xuất dùng phiên Dashboard đã có; nếu hết phiên xác thực riêng, nhập lại mật khẩu Dashboard ở hộp xác thực. Kiểm tra lại tài khoản, quyền, tháng, chiến dịch và phân công sau khi đọc nguồn. Đổi tháng/tài khoản/bộ lọc trong lúc xuất sẽ hủy kết quả cũ.

Function mới trên Main: `otraining-media-export`, verify_jwt=true, gồm index.ts + access.ts + model.js. Tái dùng credential máy chủ `OTRAINING_USER_INFO` có sẵn; không gửi credential ra client, không thêm/đổi Secrets. Giữ nguyên các function cũ, schema, Target, PG, kết quả đã lưu, KPI trigger và ledger. Chức năng xuất chỉ đọc dữ liệu.

Source ZIP có đủ mã function và module giao diện; không chứa khóa, người dùng thật hay Excel dữ liệu thật. HTML đầy đủ tải riêng tại downloads. Kiểm thử backend và browser 1440/390/320 px dùng dữ liệu giả lập, có tải XLSX thực và đọc lại. Live chỉ kiểm tra thiếu/giả phiên bị từ chối 401, không trích xuất dữ liệu riêng bằng công cụ. Giao diện chính dùng đúng HTML Test đã kiểm thử; kiểm thử lại trên route Dashboard. Bản Test giữ nguyên.

Đã triển khai theo yêu cầu Nghĩa: source Main giống hệt Test, endpoint `otraining-media-export`, verify_jwt=true. Không cần đổi cấu hình hoặc Secrets. Không di chuyển/ghi lại dữ liệu nghiệp vụ; nút xuất chỉ đọc số liệu.
