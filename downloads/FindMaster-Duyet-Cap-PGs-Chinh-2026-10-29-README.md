# Find Master — Admin duyệt cặp PGs — Dashboard chính 29/10/2026

Luồng Trainer gửi danh sách cặp và Admin duyệt final đã có trên Dashboard chính: https://centraltraining.github.io/Dashboard/.

## Trainer thao tác

1. Vào Tiến độ KPI → Nội bộ → Find Master, chọn đúng tháng/chiến dịch.
2. Mở danh sách cặp. Các nhóm đã tạo trên bản chính được giữ nguyên và hiển thị dạng Nháp.
3. Ghép đủ danh sách PGs mình phụ trách: 2 PG một nhóm; có thể có một nhóm 3 nếu tổng PG là số lẻ. Lưu nhóm nháp.
4. Bấm **Lưu & gửi Admin duyệt**, xác nhận gửi. Danh sách chuyển **Chờ duyệt** và khóa chỉnh sửa.
5. Nếu Admin trả lại, đọc lý do, sửa nhóm, gửi duyệt lại.

Lưu nhóm nháp chưa phải gửi duyệt. Nếu chưa ghép đủ PG, hệ thống chỉ rõ phần còn thiếu và chưa cho gửi. Nhóm cũ không tự được gửi hoặc duyệt. Kết quả Test không tự chuyển vào Dashboard chính.

## Admin thao tác

1. Vào cùng mục Find Master → mở danh sách cặp.
2. Mở khung **Admin duyệt final**. Có thể lọc khu vực, Trainer và trạng thái Chờ duyệt.
3. Kiểm tra đủ thành viên/nhóm và bấm **✓ Duyệt final**, xác nhận. Trạng thái chuyển **Đã duyệt final**.
4. Muốn Trainer chỉnh sửa, chọn **Trả lại chỉnh sửa** và nhập lý do. Chỉ Admin được duyệt/trả lại.

Nút duyệt xuất hiện khi Trainer đã gửi danh sách hợp lệ; nếu chỉ lưu nhóm nháp thì chưa có danh sách Chờ duyệt. Tháng đã khóa không được gửi/duyệt. Nếu nhân sự hoặc shop thay đổi sau khi gửi, Admin trả lại để Trainer kiểm tra và gửi lại; cập nhật kết quả M1–M5 không làm mất duyệt.

Có nút xuất Excel cặp PGs; mỗi PG một dòng, giữ đủ thành viên của nhóm khi lọc kênh, cột cuối là Tên cặp. Code/Mã NV/Mã shop giữ dạng text và số 0 đầu. Mã NV dùng mã đã được lưu, không tự tạo Staff ID.

## Phiên bản kỹ thuật

Nguyên nhân ban đầu: giao diện và function Main vẫn dùng phiên bản bắt cặp v1; luồng gửi/duyệt và Excel cặp v2 mới có ở Test. Đợt cập nhật FTF trước đó chỉ chuyển tính năng FTF.

Bản sửa giữ nguyên toàn bộ Main ngoài ba khối model/UI/style bắt cặp; các khối này giống Test đã kiểm thử. Main function `pgsm-pairs` v2 dùng đúng source Test với hằng ENVIRONMENT='main'. Bảng pgsm_pair_workflows đã có; không chạy tạo bảng hay migrate dữ liệu. Nhóm legacy pgsm_pair_groups chỉ đọc; khi Trainer chủ động lưu/gửi mới tạo bản ghi workflow Main riêng. Không tự tạo yêu cầu, không tự duyệt, không mang trạng thái Test sang Main.

Source đầy đủ gồm index.ts, access.ts, model.js và cấu hình verify_jwt=true, module UI/CSS. HTML đầy đủ tải riêng: Dashboard-Chinh-2026-10-29-FindMaster-Duyet-Cap-PGs.html. Không có Secrets hoặc dữ liệu người dùng thực trong source ZIP.

Backend kiểm tra quyền Dashboard mới nhất, roster và version trước khi lưu; chỉ Admin được final/trả lại; khóa sửa pending/approved và ngăn ghi đè phiên cũ. RLS bảng nhóm/workflow bật, anon/authenticated không có quyền trực tiếp. Main/Test tách namespace. Không thay Target, nhân sự Master, kết quả cá nhân, FTF Excel, TikTok, Secrets, KPI trigger hay sổ gửi.

Kiểm thử backend và trình duyệt trên đường dẫn Main ở 1440/768/390/320 px bằng dữ liệu giả lập: lưu nháp, gửi đủ danh sách, final, trả lại có lý do, khóa sửa, xung đột version/roster, phân quyền, tải và đọc Excel thực. Live phiên thiếu/giả đều 401. Đối chiếu hash nhóm legacy và workflow Test trước/sau triển khai không đổi; không tạo workflow Main thật trong kiểm thử tự động.
