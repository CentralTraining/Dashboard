# Mốc follower 01/11/2026 — Dashboard chính

Mở https://centraltraining.github.io/Dashboard/ và đăng nhập Admin.

1. Vào Mở rộng → Xây kênh TikTok.
2. Bấm Quản lý kênh → Mốc follower 01/11.
3. Chọn TRẦN PHONG ĐỘ hoặc Trainer cần bổ sung mốc, kiểm tra đúng @kênh.
4. Nhập số follower thực tế ngày 01/11/2026 và bấm Lưu mốc 01/11.
5. Chọn Tháng → tháng 11/2026 để xem mức tăng. Bấm Follow để xem nguồn Admin nhập.

Nếu TikTok API đã có số ghi nhận ngày 01/11, hệ thống giữ mốc API và khóa nhập. Số 0 được chấp nhận khi đó là số thực tế. Không dùng số hôm nay thay cho ngày 01/11.

Mốc tháng 10, kết nối, lịch sử follower và số liệu khác đang có được giữ nguyên. Mốc mới gắn với ID tài khoản, Sandbox và nguồn Admin nhập; không chèn điểm TikTok giả vào lịch sử. Khác tài khoản không dùng lại mốc; đổi username cùng ID vẫn giữ mốc thủ công.

Mốc bản chính được lưu riêng. Nếu đã thử nhập trên Test, hãy nhập lại số thực tế trên Dashboard chính. Không tự chuyển số Test sang dữ liệu chính thức.

Frontend giống đúng bản Test đã kiểm thử. Bộ xử lý Main giữ native owner, callback, phân quyền và API dùng chung. Kiểm thử bằng dữ liệu giả lập và live phiên thiếu/giả không đọc hoặc ghi dữ liệu riêng. Không thay Secrets, schema hay tự động hóa KPI.

Full HTML được cung cấp để lưu phiên bản. Full source bộ xử lý được gửi riêng cho chủ dự án, không đăng mã xác thực vào kho tải công khai.
