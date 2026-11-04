DASHBOARD CHÍNH — NHÂN BẢN CHIẾN DỊCH LIÊN TỤC — 04/11/2026

Cài đặt → Chiến dịch → chọn chiến dịch T10 → Nhân bản → chọn T11 → giữ ô Giữ Target, cấu hình và danh sách đã cài đặt → Nhân bản.

Giữ tên, Campaign/Program ID nguồn, X, A bài/PG, trạng thái chốt và các cấu hình hiện có. Sao chép Target theo Trainer/khu vực và các danh sách import riêng của chiến dịch.
Find Master giữ danh sách PGs/shop, ngưỡng 5 mốc, tiến độ tích lũy, các cặp và trạng thái duyệt. Dấu duyệt nguồn giữ nguyên người/thời điểm đã xác nhận; không tạo một lần duyệt mới. HR tháng mới tiếp tục kiểm tra: Off/đã loại/thiếu HR làm nhóm không hợp lệ và không tính đạt.
Cập nhật cùng Campaign ID OTraining tiếp tục giữ các mốc đã đạt; đổi ID nguồn thì không gộp mốc của nguồn khác. Các kết quả tháng thông thường (FTF, truyền thông, khảo sát...) không tự chép thành thành tích tháng mới.
Nếu tháng đích có Target khác trong cùng hạng mục, hệ thống dừng để giữ dữ liệu đang có. Chỉ chạy sao chép khi Admin bấm Nhân bản; các bản sao cũ không tự bị sửa.

Backend: campaign-clone Main v1, JWT gateway true + fresh Dashboard Admin auth; RPC clone_campaign_main_v1 SECURITY INVOKER, chỉ service_role được gọi. Đọc đúng namespace Main, giữ legacy read-only; không lấy nhóm/dữ liệu private Test sang Main. Cả lượt lưu cùng transaction CAS, có rollback và chống tạo trùng khi thử lại.
Đã kiểm thử Main bằng dữ liệu giả lập: PostgreSQL PGlite0.3.14, quyền Admin/Trainer, stale/lock/idempotency/rollback và UI1440/768/390/320. Live thiếu/giả phiên 401, anon RPC bị từ chối. Không nhân bản chiến dịch thật trong kiểm thử.
Giao diện byte-exact bản Test đã kiểm thử. Secrets, các function cũ và lịch/sổ gửi KPI không đổi. Mã nguồn auth chỉ cấp ZIP riêng, không public repository. Trong gói mã nguồn, pair-workflow-fixture-schema.sql CHỈ dành cho PostgreSQL thử nghiệm trống, không chạy lên database thật.
