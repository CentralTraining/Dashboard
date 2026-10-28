# Dashboard chính — TikTok, FM và FTF AI — 28/10/2026

Trang chính: https://centraltraining.github.io/Dashboard/

HTML được chuyển nguyên byte từ bản Test đã kiểm thử tại commit `626590bc4eceecab93ce60cd5a7a4b73ba95fa2b`. Bản này gồm giao diện TikTok đồng bộ màu, tracking hashtag trong video Trainer đã kết nối, nguồn FM cho Truyền thông Nội bộ và sửa Tư vấn mẫu AI của FTF.

## Sử dụng

- **Truyền thông Nội bộ:** chọn đúng chiến dịch/tháng, bấm Sửa, chọn **Nguồn FM**, nhập **ID chiến dịch 6**, **Program ID 8**, rồi Lưu → Cập nhật Truyền thông từ hệ thống. Program 8 là **DIỆN MẠO MỚI - TRẢI NGHIỆM MỚI**. Nguồn cũ vẫn giữ mặc định Nội bộ (`noibo`) nếu Admin chưa đổi.
- **Đối tác → FTF:** chiến dịch đang kiểm tra là **22**. Bấm **Cập nhật FTF từ hệ thống**, xác thực tài khoản Dashboard trên trang nếu được yêu cầu. Chỉ `simulationStatusMap=dat` tính hoàn thành; `chua_dat` hiện Chưa đạt và không cộng; thiếu trạng thái hiện Chưa làm. Bấm số trong cột Tư vấn AI của shop để xem chi tiết. Trên điện thoại, chạm tên shop rồi chọn chỉ số AI trong thẻ thông tin.
- **Mở rộng → Xây kênh TikTok:** Tracking hashtag dùng cùng bộ lọc thời gian/khu vực/Trainer; đối chiếu cả tiêu đề và caption. Đây là phạm vi kênh Trainer đã kết nối, không tìm toàn TikTok. Chỉ số snapshot giữ nhãn nguồn và thời điểm; dữ liệu thiếu không tự đổi thành 0.

Các Target Admin, mốc follower, tài khoản và cấu hình chiến dịch giữ nguyên trong lần triển khai. Việc cập nhật data thật chỉ xảy ra khi người dùng chủ động thao tác và có quyền. Target AI bằng 0 không tự được thay bằng Target khác.

## Máy chủ và mã nguồn đầy đủ

ZIP chứa toàn bộ source đã triển khai và các file phụ thuộc:

- `supabase/functions/trainer-channel/` (9 file): Main v12, giữ nguyên callback và luồng native owner; chỉ sửa `index.ts` và `team-overview.ts` để bổ sung action đọc hashtag đã kiểm thử.
- `supabase/functions/otraining-media/` (1 file): Main v1, source giống adapter FM Test.
- `supabase/functions/otraining-ftf-ai/` (2 file): Main v1, source giống adapter FTF AI Test v4, có xác thực phiên Dashboard và lọc shop Trainer theo Target khu vực.
- `supabase/config.toml`: giữ JWT gateway của hai adapter otraining; `trainer-channel` giữ thiết lập tự xác thực như trước.

HTML đầy đủ là tệp tải riêng. Không có token, Cookie, giá trị Secrets hoặc dữ liệu cá nhân thật trong gói source.

`trainer-channel-api`, các adapter Test, `otraining-testonline` v51 và các function khác không thay đổi. Callback đã đăng ký vẫn là `/functions/v1/trainer-channel-test/oauth/callback`. Không chuyển hoặc reset dữ liệu kết nối, không yêu cầu cấp quyền TikTok lại chỉ vì lần phát hành này. Không sửa code gửi KPI, file trigger, Secrets hay nhánh `ollie-kpi-state`.

Header otraining hiện có chỉ gửi tới đúng dịch vụ và endpoint đã được Nghĩa cung cấp, theo luồng kết nối otraining đang dùng trên Main; không đọc/xuất giá trị hoặc thêm nơi nhận mới.

## Kiểm chứng

Kiểm thử giả lập trên đường dẫn Main ở 1440px/390px và thêm 320px cho hashtag. Đã kiểm tra luồng cập nhật FM/FTF, phạm vi Trainer, lỗi và phản hồi cũ, Target Admin, trạng thái Đạt/Chưa đạt/Chưa làm, hashtag và nhánh Main native owner.

Kiểm tra thực tế adapter FM Main trả đúng `fm/6/8` và tên chương trình. FTF AI thiếu hoặc giả phiên Dashboard trả 401; TikTok thiếu phiên trả 401, chữ ký native owner sai bị từ chối, callback/status hiện có giữ nguyên. Không giả mạo phiên tài khoản thật hoặc công bố nội dung riêng để kiểm tra; không khẳng định đã nhập data FTF mới trong phiên của Nghĩa trước khi Nghĩa bấm cập nhật có xác thực.
