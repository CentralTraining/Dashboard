# Find Master — Bắt cặp thi đua | Dashboard chính | 28/10/2026

Mở https://centraltraining.github.io/Dashboard/ → Tiến độ KPI → Nội bộ → PGs Master / Find Master → **Bắt cặp thi đua**.

## Trainer sử dụng

1. Chọn đúng tháng và chiến dịch Find Master đã chốt danh sách PG.
2. Chọn **Bắt cặp thi đua**. Nếu được hỏi, nhập mật khẩu Dashboard để xác thực quyền.
3. Bấm **Tạo nhóm**, chọn hai PG mình phụ trách; nếu tổng danh sách của Trainer lẻ thì được tạo một nhóm ba PG.
4. Tên nhóm tự lấy tên các thành viên theo thứ tự chọn, ví dụ **Sen - An**. Bấm **Lưu nhóm**.
5. Xem bảng theo Trainer hoặc khu vực. Cột **Số cặp** có dấu **+** mở danh sách nhóm, kênh, thành viên và kết quả từng mốc. Nhóm ba được tính là một nhóm.
6. Dùng **Sửa** để đổi thành viên hoặc **Xóa** để giải phóng PG cho nhóm khác. Một PG chỉ thuộc một nhóm trong cùng chiến dịch/Trainer. Không ghép PG khác Trainer.
7. Bấm **Tải lại** sau khi kết quả Find Master được cập nhật. Nhóm chỉ đạt một mốc khi tất cả thành viên đã đạt chính mốc đó.

M1: Pass Test; M2: Tự luận; M3: Tư vấn AI; M4: Câu chuyện; M5: Truyền thông. Dấu `?` là còn thiếu kết quả. Không suy ra đạt từ số sao, số lượt hoặc ngưỡng. Nếu PG bị thay đổi khỏi roster, nhóm được báo cần ghép lại, không tự tính đạt và không tự xóa.

Trainer xem trong khu vực được cấp quyền và chỉ sửa nhóm của chính mình; Admin quản lý toàn bộ. Tháng đã khóa hoặc danh sách chưa chốt thì không sửa nhóm. Cần ít nhất hai PG để lập nhóm.

## Phạm vi triển khai

- Đã chuyển chức năng bắt cặp đã kiểm thử từ Test sang Dashboard chính theo yêu cầu Nghĩa.
- HTML đầy đủ: `Dashboard-Chinh-2026-10-28-Find-Master-Bat-Cap.html`, cùng nội dung `index.html` trên Dashboard chính.
- Function mới `pgsm-pairs` v1, gateway `verify_jwt=true`, thêm xác thực phiên Dashboard phía máy chủ. Giữ tương thích phiên Workshop hiện có, không đổi chức năng Workshop.
- Chỉ lưu bảng mới `public.pgsm_pair_groups`. Khóa chính `(campaign_id, trainer_id)`, JSON nhóm theo Trainer, version để phát hiện hai phiên lưu đồng thời. RLS bật, anon/authenticated không có quyền trực tiếp; chỉ backend service role truy cập sau kiểm tra quyền Dashboard.
- Không sửa `pgsMaster:*`, đăng ký PG, Target, kết quả thi cá nhân, tài khoản, Secrets, TikTok, workflow KPI hoặc sổ gửi.
- Không tự tạo nhóm cho người dùng. Bảng khởi tạo rỗng; Trainer chọn thành viên phù hợp thực tế.

## Mã nguồn và phục hồi

ZIP kèm đủ `index.ts`, `access.ts`, `model.js`, `schema.sql` và cấu hình function. Không kèm Secrets hoặc dữ liệu riêng.

`schema.sql` đã được áp dụng một lần trên dự án hiện tại để tạo bảng mới; không chạy lại trên bảng đã tồn tại. Khi cài trên môi trường khác, cần có cấu trúc Dashboard/KV/tài khoản Master tương ứng. Bộ này không phải Dashboard độc lập.

Function Main `pgsm-pairs` đã triển khai trước khi chuyển HTML. Test và Main dùng cùng bảng nhóm và roster hiện có. Không tạo lại bảng, xóa nhóm, thay Secrets hoặc chép đè function khác.

## Kiểm tra

- Kiểm thử dữ liệu giả lập: tạo/sửa/xóa nhóm, nhóm hai/ba, trùng thành viên, cả nhóm đạt mốc, thiếu dữ liệu, đổi quyền/khóa tháng, phiên lưu đồng thời, lỗi lưu và phản hồi cũ.
- Trình duyệt chạy HTML đầy đủ và handler/backend thực với cơ sở dữ liệu giả lập tại các chiều rộng 1440, 768, 390, 320 px; giữ trang cá nhân hiện có.
- Triển khai thật: đối chiếu chính xác source function, kiểm tra RLS/quyền bảng, xác nhận không có nhóm giả lập; yêu cầu thiếu/giả phiên Dashboard và đọc bảng bằng anon bị từ chối.
- Không sử dụng tài khoản hay tạo nhóm PG thật trong kiểm thử tự động.

Các kết quả máy đọc được nằm trong tệp verification đi kèm.
