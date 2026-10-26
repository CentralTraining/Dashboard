# TikTok API — Dashboard chính, 26/10/2026

Triển khai đúng HTML đã kiểm thử của Test lên https://centraltraining.github.io/Dashboard/.
Một bảng tiến độ và một nút Đồng bộ TikTok cho hai Sandbox. Không còn Web tracking.

## Sử dụng

- Tải lại Dashboard chính. Mở Mở rộng → Xây kênh.
- Quản lý kênh → Gán trang TikTok: giữ các kênh cũ ở Sandbox 1, chọn đúng Sandbox 2
  cho ba Trainer đã thêm vào Target users của Sandbox 2.
- Các kết nối đã có ở hai bản được sử dụng theo cùng một bộ xử lý; không yêu cầu
  đăng nhập lại chỉ vì chuyển trang. Kênh chưa cấp quyền cần Kết nối lần đầu.
- Kết nối hoặc đồng bộ trên một bản sẽ xuất hiện trên bản còn lại khi tải dữ liệu mới,
  theo cùng khoảng ngày, bộ lọc và quyền xem. Không cam kết mọi kênh đã cấp quyền thực tế;
  kiểm thử tự động dùng 13 kênh giả lập.
- Giữ URL callback đã đăng ký, các bộ khóa hiện có, mốc Admin và bản lưu kết nối.

## Kiến trúc máy chủ và bảo trì

- `trainer-channel-api` là bộ xử lý TikTok dùng chung cho cả hai giao diện, hiện phiên bản 2.
- `trainer-channel-test` chuyển yêu cầu và callback tới bộ xử lý chung, hiện phiên bản 14.
- `trainer-channel` chuyển yêu cầu công khai tới cùng bộ xử lý, hiện phiên bản 10.
  Kết nối cũ do bản chính sở hữu vẫn xử lý token tại chủ sở hữu cũ. Đường nội bộ chỉ
  nhận sync/connect có chữ ký HMAC máy chủ và vẫn xác thực phiên dashboard hiện tại.
- Namespace lưu `trainer-channel-test` trong bộ xử lý chung là địa chỉ dữ liệu cũ
  được giữ để không mất kết nối. Không được xóa hoặc xem đây là dữ liệu thử nghiệm tạm.
- Token hoạt động không được nhân bản giữa hai vùng lưu để làm mới độc lập. Các dữ liệu
  đã lưu trên Test và bản chính được đối chiếu theo đúng Sandbox, kênh và quyền tài khoản.
- Mốc Admin hợp lệ mới nhất theo `recordedAt` được dùng trên cả hai giao diện mà không
  tự xóa bản ghi cũ. Thiếu mốc thực tế ngày 01/10/2026 thì không dựng số liệu quá khứ.
- Thay đổi `trainer-channel-api` ảnh hưởng cả Dashboard chính và Test. Thay đổi giao diện
  riêng trên Test không tự động đồng nghĩa được phép thay bộ xử lý sản xuất dùng chung.

## Cấu hình giữ nguyên

Không đổi Client Key/Secret hoặc cấu hình ứng dụng TikTok. Giữ callback:

`https://qruxqlsbhyhwiqjdkyyc.supabase.co/functions/v1/trainer-channel-test/oauth/callback`

Sandbox 1 dùng bộ khóa hiện có; Sandbox 2 dùng `TIKTOK_TEST_SANDBOX2_CLIENT_KEY` và
`TIKTOK_TEST_SANDBOX2_CLIENT_SECRET`. Không đưa giá trị khóa vào mã hay file tải.
Ba function giữ `verify_jwt=false` để tiếp nhận OAuth; dữ liệu riêng và thao tác tài
khoản tiếp tục được xác thực bằng phiên dashboard, kiểm tra quyền hiện tại trên máy chủ.

## Xác minh

Đã kiểm thử: 7 kết nối cũ; 13 kênh theo mô hình 10 + 3; dữ liệu hai giao diện giống nhau;
callback quay về đúng trang; đổi mã và refresh bằng đúng bộ khóa; đọc không sao chép token;
phân quyền khu vực/chủ tài khoản; mốc Admin; từ chối chữ ký nội bộ sai và phiên thiếu;
giữ dữ liệu khi API lỗi. Giao diện chính đã kiểm tra trên điện thoại và máy tính.

Không sửa schema, Secrets, mã KPI/Ollie, sổ gửi hoặc nhánh `ollie-kpi-state`.
Gói tải gồm HTML đầy đủ, các function đã sửa cùng mọi phụ thuộc, chính sách và kết quả
kiểm tra tổng hợp. Không chứa dữ liệu Trainer, cookie, token thật hoặc Secrets.
