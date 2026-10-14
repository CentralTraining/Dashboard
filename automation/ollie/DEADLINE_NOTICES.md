# Thông báo nhóm và lịch nhắc deadline

Nghĩa đăng thông báo trong nhóm AE CÂY KHẾ CHUA đã được đối chiếu. Bot chỉ lấy
thông báo từ tài khoản Nghĩa trong nhóm này; thành viên khác không tự tạo lịch
cho cả Team. Nội dung và deadline được lưu trong kho riêng đã mã hóa của bộ
nhắc việc; không cần nhập lại vào dashboard.

## Cách sử dụng

1. Đăng thông báo gồm nội dung việc và một deadline rõ ràng.
2. Có thể @Ollie_MT để nhận xác nhận ngay; thông báo không @bot được lấy qua
   đợt quét lịch sử nhóm, giữ thời điểm đăng gốc để tính lượt nhắc đầu.
3. Lịch 08:00 giờ Việt Nam bắt đầu từ sáng hôm sau, chỉ gửi riêng Trainer
   được phân công và Nghĩa. Thông báo cho cả Team được giao cho 13 Trainer.
4. Danh sách ưu tiên deadline gần nhất; nếu cùng deadline dùng thời điểm đăng.
   Bot giữ link đầy đủ, ID/mật mã họp, rút gọn phần trình bày và đổi lời chúc
   đầu ngày. Mỗi công việc có mã CV để đối chiếu.
5. Trainer nhắn `hoàn thành CV-1` để dừng nhắc phần của mình; Nghĩa có thể
   `đổi hạn CV-1 21/10/2026 17:00`, `hủy CV-1`, hoặc `hoàn thành CV-1` cho cả Team.

Ví dụ:

```text
📢 THÔNG BÁO
Mỗi Trainer nộp 2 video Unbox A7 Pro.
Deadline: 20/10/2026 17:00
```

Các cách khác được nhận:

```text
Mỗi Trainer nộp 2 video trước 17h ngày 20/10/2026.
Hạn cuối: 2026-10-20
Thời gian hoàn thành: 20/10/2026 17:00
```

Deadline chỉ có ngày dùng 23:59 ngày đó. Buổi họp cần giờ rõ ràng. Bot không
đoán ngày/năm hoặc tự sửa “ngày mai” khi mâu thuẫn với ngày ghi rõ; thông báo
thiếu hoặc có nhiều deadline cần bổ sung/tách từng việc để được tạo lịch.

## Vận hành

GitHub Actions đặt lịch chính 08:00 và có lượt khởi động trước lúc 07:55, đọc
thông báo rồi đợi đến 08:00 trước khi gửi. Lượt quét nhóm và các lượt kiểm tra
buổi sáng hỗ trợ gửi bù; sổ gửi mã hóa giữ các tin đã được DingTalk tiếp nhận,
không tự gửi lại kết quả không rõ. GitHub có thể xếp hàng hoặc trễ lịch; lịch
08:00 không phải cam kết gửi chính xác từng giây. Phần Stream nhận thông báo
có @bot khi môi trường bot đang chạy; lượt quét nhóm hoạt động độc lập.

Tin nhắc dừng khi hoàn thành, bị hủy hoặc qua deadline. Không tạo tin nhắc
deadline trống khi không còn việc đến lượt cần nhắc. Những thông báo chưa đủ
ngày giờ không được coi là đã tạo lịch. Các nguồn dữ liệu/Secrets, dashboard
và nội dung KPI không đổi theo chính sách nhắc deadline này.
