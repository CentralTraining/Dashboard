# Dashboard chính — Target theo danh sách PGs — 03/11/2026

Đã chuyển giao diện đã kiểm thử trên Test: Tất cả PGs / Theo danh sách cho Test Online và Tư vấn AI & Check shop. Giữ bản sửa Google Sheet: xác minh tên tab và gid trước khi đọc CSV, giữ tên tab có dấu cách cuối và hiện danh sách PG để xem trước.

Hai danh sách đã chốt trên Test (25 PG mỗi chiến dịch) được chuyển riêng sang environment=main bằng kiểm tra version/payload trước khi ghi. Không ghi đè Main nếu đã có dữ liệu; không sửa dữ liệu Test, kết quả gốc, Secrets, ledger hoặc các endpoint TikTok.

## Sử dụng

1. Mở https://centraltraining.github.io/Dashboard/ và tải lại bằng Ctrl+F5 / Cmd+Shift+R.
2. Vào Cài đặt → Target → chọn đúng tháng và chiến dịch. Hai danh sách đã nhập được giữ khi chuyển bản chính.
3. Khi cần sửa, bấm Sửa Target → Theo danh sách → Import Target từ Google Sheet.
4. Nhập link và tên tab, bấm Lấy dữ liệu & Xem trước → Dùng danh sách này → Lưu Target.

Target, số hoàn thành, Home và Excel dùng cùng danh sách PG OPPO Đang làm. Dòng trùng gộp; mã/tên/phân công chưa khớp chặn lưu. Ngưỡng X không nhân vào Target.

## Backend và báo cáo

- campaign-target-roster v1 giữ JWT gateway bật và xác thực Dashboard; bốn source/dependencies giống Test v3, chỉ environment=main.
- campaign-target-report chỉ trả số tổng hợp đã phân quyền, không trả tên PG, mã PG hoặc danh sách thành viên. JWT gateway vẫn bật. Người dùng cần phiên Dashboard hợp lệ; workflow KPI dùng GitHub OIDC ngắn hạn có chữ ký, đúng audience/repository/nhánh/main/workflow. Không chuyển GitHub API token đến Supabase; không có quyền đọc số liệu ẩn danh.
- Workflow Ollie KPI giữ trigger và bộ gửi/ledger cũ; thêm quyền id-token: write để xin OIDC ngắn hạn. Không thêm Secrets và không kích hoạt gửi trong lần triển khai.
- kpi.py lấy số tổng hợp riêng theo campaign, kiểm tra sourceVersions với dữ liệu gốc và thử lại một lần nếu nguồn đổi. Không đủ xác thực hoặc nguồn không khớp thì dừng, không tự lấy toàn bộ PG thay thế danh sách.
- Các runtime ngoài GitHub Actions muốn đọc số liệu frequency qua phiên bản kpi.py này cần phiên Dashboard được cấp quyền. Không tự triển khai lại dịch vụ chat ngoài repository trong lần chuyển giao diện này.

Nguồn đầy đủ của hai function và dependencies nằm trong ZIP riêng cho chủ sở hữu; không đăng source auth hay dữ liệu PG công khai. HTML đầy đủ được xuất riêng.
