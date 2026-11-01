# Find Master — Kiểm tra thành viên bắt cặp — Dashboard chính 01/11/2026

Vào Tiến độ KPI → Nội bộ → Find Master. Phiên bản này đưa đúng HTML đã kiểm thử trên Test lên Dashboard chính, gồm cột Thâm niên (tháng), cảnh báo HR trên danh sách cá nhân và kiểm tra thành viên bắt cặp.

PG đã loại khỏi Master hoặc HR khác Đang làm hiện đỏ và không được chọn ghép mới. Cặp cũ có thành viên không hợp lệ hiện đỏ, có lý do; không được gửi hoặc duyệt final. Thành viên đã mất khỏi roster vẫn xuất hiện trong trình sửa để bỏ chọn. Nhóm nháp/đã trả lại có thể sửa hoặc xóa; danh sách đang chờ/đã duyệt phải được Admin Trả lại chỉnh sửa trước. Không tự sửa, xóa hay duyệt dữ liệu đang lưu.

Máy chủ đọc DATA OPPO của đúng tháng chiến dịch, đối chiếu Code, danh sách Master đã chốt, cờ loại và Trainer phụ trách. HR chưa có, thiếu PG, trạng thái trống hoặc mã trùng có trạng thái mâu thuẫn sẽ báo chưa xác minh và chặn thao tác; không suy đoán Đã nghỉ. Nhóm 2 hoặc một nhóm 3 khi lẻ tính theo số PG hợp lệ. Không đổi Target cá nhân, kết quả M1–M5 hoặc danh sách Master. Phê duyệt cũ còn hợp lệ giữ nguyên nhờ tương thích thuật toán revision v2.

Function thay duy nhất `pgsm-pairs`, verify_jwt=true, ENVIRONMENT='main'. Gồm đầy đủ index.ts/access.ts/model.js. Xác thực phiên Dashboard và quyền cũ giữ nguyên; Trainer chỉ sửa nhóm của chính mình, đọc/xuất trong khu vực được quản lý, Admin toàn phạm vi. Đọc KV và nguồn legacy pgsm_pair_groups; chỉ ghi pgsm_pair_workflows qua thao tác có xác thực. Không chạy schema, không copy Test sang Main, không đổi Secrets hoặc function TikTok/callback.

Đã kiểm thử backend và trình duyệt bằng dữ liệu minh họa: lưu/gửi/final/trả lại, giữ duyệt v2 hợp lệ, HR thay đổi giữa thao tác, member mất khỏi roster, parity, phiên thiếu/giả, quyền, stale revision và Excel giữ mã dạng text/cột cuối Tên cặp. Các kiểm thử không tạo, gửi hoặc duyệt nhóm thực tế.

Tệp HTML là toàn bộ Dashboard chính; đường dẫn /Dashboard/ chọn endpoint chính. ZIP là mã đầy đủ function đã sửa, model/UI/CSS và tài liệu kiểm chứng, không chứa Secrets hoặc dữ liệu người dùng. Nếu phục hồi, giữ nguyên ENVIRONMENT='main', slug pgsm-pairs, verify_jwt=true và toàn bộ phụ thuộc; triển khai function trước HTML. Không chạy lại schema hoặc sao chép dữ liệu workflow giữa môi trường. Việc sửa dữ liệu và duyệt danh sách phải thực hiện qua giao diện bằng tài khoản có quyền.
