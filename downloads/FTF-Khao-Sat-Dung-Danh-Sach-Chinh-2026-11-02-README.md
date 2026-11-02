# FTF — Khảo sát theo danh sách check-in chiến dịch — Dashboard chính 02/11/2026

Vào Tiến độ KPI → Đối tác → FTF. Bấm ô Khảo sát để xem danh sách người và trạng thái tương ứng; số tổng và chi tiết dùng cùng snapshot. Cập nhật FTF từ hệ thống sẽ lấy trạng thái từ surveyMap của danh sách người check-in thuộc đúng shop/chiến dịch, mỗi shop_id + user_id chỉ tính một lần. Một người xuất hiện ở hai shop vẫn được tính theo từng shop giống báo cáo nguồn.

Không dùng survey_count của luồng tổng hợp shop để tạo các dòng khảo sát HV 1, HV 2… Nguồn thiếu/không khớp campaign, month, shop hoặc còn trạng thái không rõ sẽ dừng cập nhật và giữ số liệu đã lưu. Nguồn AI và khảo sát cùng một yêu cầu download-all đã kiểm tra phiên Dashboard và quyền khu vực.

Giữ Target theo kênh Admin đã đặt, Target khảo sát động theo HR Training, các chỉ số HR/Test/AI và các chức năng khác. File nhập thủ công vẫn dùng dữ liệu khảo sát thực của file. HTML chính giống hệt bản Test đã kiểm thử.

Function thay duy nhất otraining-ftf-ai, verify_jwt=true; xác thực access.ts giữ nguyên. Không thay Secrets/schema hoặc các function khác/Test. Mã nguồn đầy đủ được gửi riêng cho chủ tài khoản; không đăng gói máy chủ chứa mã xác thực lên GitHub công khai.

Sửa dữ liệu đang lưu (nếu được thực hiện) được đối soát riêng từ nguồn mới, chỉ các trường khảo sát thuộc phạm vi đã xác minh và số tổng khảo sát liên quan; bảo vệ bằng hash/version để không ghi đè một cập nhật đồng thời. Không gán một số tổng cố định, không sửa Target hoặc reset cả tháng. Chứng cứ dữ liệu thật được giữ riêng, không đưa vào tệp tải công khai.

Kiểm thử dùng dữ liệu minh họa: số khảo sát và chi tiết cùng nguồn, bản ghi trùng trong một shop, cùng người ở hai shop, auth/scope, missing/unknown/error và stale context giữ nguyên dữ liệu; Target Admin và các chỉ số khác được giữ. Probe live chỉ dùng phiên thiếu/giả để kiểm tra từ chối 401, không tạo dữ liệu thử thật.
