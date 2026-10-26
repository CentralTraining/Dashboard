# TikTok — dùng lại callback đã đăng ký

Phiên bản ngày **26/10/2026**. Bản sửa kết nối máy chủ cho Dashboard chính và Test.

## Hành vi

- Giữ địa chỉ callback đã dùng cho bản Test:
  `https://qruxqlsbhyhwiqjdkyyc.supabase.co/functions/v1/trainer-channel-test/oauth/callback`.
- Phiên do Dashboard chính tạo có state riêng và được chuyển tới function chính để
  xác minh, đổi mã và lưu kết nối. Người dùng quay về Dashboard chính.
- Phiên Test giữ nguyên luồng cũ, khóa ứng dụng và dữ liệu Test riêng.
- Không sửa cấu hình ứng dụng TikTok, Client Key/Secret hoặc quyền đã cấp.
- Không chuyển toàn bộ giao diện/chức năng mới của Test sang Dashboard chính.

## Phạm vi và bảo vệ

- Function chính phiên bản 7; Test phiên bản 9. Giữ `verify_jwt=false` hiện có cho
  OAuth callback công khai; mọi thao tác tài khoản tiếp tục tự xác thực phiên dashboard.
- Điểm chuyển tiếp chỉ có một đích cố định trong cùng dự án Supabase. Không nhận
  URL đích từ query hoặc từ file nhập; chỉ chuyển `state`, `code`, `error`.
- State vẫn được lưu mã hóa, có hạn 10 phút và dùng một lần. Máy chủ chính kiểm tra
  tài khoản hiện tại, kênh được gán và phiên bản dữ liệu trước khi đổi mã.
- Địa chỉ callback khi đổi mã đúng với địa chỉ đã dùng lúc mở đăng nhập.
  Các phiên chính tạo trước bản sửa vẫn dùng được địa chỉ cũ của chính phiên đó.
- Không sửa kết nối Trainer đã lưu, mốc Admin, dữ liệu video/follower hoặc số liệu quét.
- Không thay KPI/Ollie, sổ gửi, Secrets hay nhánh `ollie-kpi-state`.

## Sử dụng

Trainer mở Dashboard chính và bấm **Kết nối** lại để tạo phiên mới.
Các kênh đã kết nối được giữ nguyên. Không cần vào TikTok Developers để đổi URL.

Bản sửa khắc phục đường callback. Việc đăng nhập và cấp quyền thực tế vẫn do TikTok
quyết định theo trạng thái ứng dụng và tài khoản được phép sử dụng; kiểm thử tự động
dùng tài khoản giả lập, không đăng nhập thay Trainer.

## Kiểm tra

- Luồng chính → callback chung → máy chủ chính → Dashboard chính.
- Luồng Test cũ, hai bộ khóa và hai vùng dữ liệu độc lập.
- Chống dùng lại state, hết hạn, tài khoản bị khóa, đổi kênh giữa lúc đăng nhập,
  tài khoản TikTok sai, tham số trùng và chuyển hướng ngoài hệ thống.
- Giữ mốc Admin và các chức năng follower, video, quét thủ công trước đây.
- Kiểm tra endpoint đã triển khai: hai function trả cùng callback; yêu cầu kết nối
  thiếu phiên bị từ chối; callback với state không tồn tại không tạo kết nối.

Gói tải gồm toàn bộ function đã sửa và các phụ thuộc; không kèm Secrets, cookie,
mã cấp quyền thật hoặc dữ liệu Trainer. HTML đầy đủ được cung cấp riêng theo từng bản.
