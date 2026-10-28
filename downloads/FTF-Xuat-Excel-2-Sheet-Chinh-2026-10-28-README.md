# Xuất Excel FTF Đối tác — Dashboard chính 28/10/2026

Mở https://centraltraining.github.io/Dashboard/, đăng nhập, chọn tháng → Tiến độ KPI → Đối tác → FTF → danh sách shop. Nút **⇩ Xuất Excel (2 sheet)** nằm phía trái, trên bộ lọc của danh sách shop. Chọn bộ lọc rồi bấm xuất; nhập lại mật khẩu Dashboard khi được yêu cầu.

- `Tong Hop F2F`: Mã Shop, Tên Shop, Kênh, Vùng, Khu vực, Tỉnh/Thành, Quận/Huyện, Ngày, Giờ, Người Train, SĐT Người Train, Sale QL, SL Dự Kiến, Số Đã Train, Trạng Thái.
- `Chi Tiet Check-in`: Chiến dịch, Mã Shop, Kênh, Vùng, Khu vực, Tỉnh, Shop, Sale Quản lý, Người Train, Tên học viên, Trạng thái tư vấn mẫu, Test online, Khảo sát, Điểm Hài lòng.

File `BaoCao_FTF_<ID chiến dịch>_<tháng>.xlsx` xuất toàn bộ shop khớp bộ lọc, bao gồm các trang tiếp theo. Trainer xuất shop của chính Trainer theo Target FTF; Admin xuất các shop trong phạm vi đang xem. Hai sheet lấy cùng một phản hồi nguồn FTF của chiến dịch đã cấu hình. Người Train là người thực hiện tại nguồn, có thể khác Trainer phụ trách shop.

Chi tiết học viên dùng check-in thực từ allAttendees/nameMap; không dùng các dòng đếm HV do bộ import cũ sinh ra. AI đọc riêng simulationStatusMap: dat=Đạt, chua_dat=Chưa đạt, thiếu=Chưa làm. Test là Pass/Fail/Chưa làm; khảo sát Done/Chưa; trạng thái lạ ghi Chưa xác định. Điểm chưa có để trống. Mã shop/điện thoại giữ text và số 0 đầu, số lượng/điểm dùng number. Ngày/giờ theo Việt Nam, cùng quy tắc báo cáo gốc.

Nếu nguồn thiếu dữ liệu/shop không khớp/ID chiến dịch đã đổi/quyền thay đổi/lỗi mạng, hệ thống báo rõ và không tạo file thiếu. Đổi tháng/bộ lọc trong lúc lấy dữ liệu sẽ không tải kết quả cũ. Khi Admin đổi ID chiến dịch, cập nhật FTF để danh sách shop khớp nguồn mới rồi xuất.

## Phiên bản và source

Tính năng dùng đúng module giao diện và adapter đã kiểm thử tại Test commit `920f4d791899cef05d5ffaa59d9cfb52eb8566aa`, áp dụng lên Main hiện hành `eefe7c5f54805fdabae4bd8bce97904bb898f0e7`. Giữ các tính năng Main khác hiện hành, gồm bản vá duyệt FindMaster và luồng bắt cặp Main đang dùng.

HTML đầy đủ tải riêng: `Dashboard-Chinh-2026-10-28-FTF-Xuat-Excel-2-Sheet.html`.

ZIP source có module giao diện `ftf-export.js`, toàn bộ `index.ts`, `access.ts`, `model.js` của function mới `otraining-ftf-export`, cấu hình verify_jwt=true, manifest và kết quả kiểm thử. Function Main dùng source giống hệt Test, bắt buộc phiên Dashboard đã ký; kiểm tra lại quyền/phân công phía server trước và sau khi lấy nguồn. Dùng credential server hiện có; không đưa Secrets hoặc dữ liệu người dùng thật vào gói source.

Không thay schema, Target, dữ liệu thật, Secrets, callback TikTok hay Edge Function cũ. Không xuất hoặc công bố XLSX dữ liệu thực trong tự động hóa.

## Xác minh

Luồng trên đường dẫn Dashboard chính đã kiểm thử bằng dữ liệu giả lập ở 1440/390/320 px: tải và đọc lại XLSX thực, đúng 15/14 cột, lọc nhiều trang, phân quyền Trainer, số 0 đầu, kiểu dữ liệu, tên dạng công thức giữ text, thiếu điểm để trống, lỗi/đổi tháng không tải file. Không ghi KV.

Source function Main được đọc lại đối chiếu chính xác với Test; function cũ giữ nguyên. Kiểm tra live thiếu/giả phiên Dashboard đều trả 401 trước khi đọc nguồn riêng. Chưa chạy tự động bằng tài khoản Trainer/Admin thật. Xác nhận GitHub Pages và hash public trong publication.json lưu tại workspace của đợt triển khai.
