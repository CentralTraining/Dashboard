# Tra cứu dashboard Miền Trung với Ollie_MT

Nhắn riêng cho Ollie_MT từ tài khoản DingTalk đã được đối chiếu. Bộ tra cứu đọc
dữ liệu dùng chung của https://centraltraining.github.io/Dashboard/ ở thời điểm
hỏi; không dựa vào số liệu cũ trong lịch sử trò chuyện.

- Nghĩa: xem toàn bộ dữ liệu nghiệp vụ, hoặc chọn tháng/khu vực/Trainer.
- Trainer: chỉ xem khu vực đã đối chiếu cho tài khoản đó, kể cả khi yêu cầu
  “tất cả”. Tên gõ trong tin nhắn không đổi quyền truy cập.
- Tài khoản chưa được đối chiếu hoặc dữ liệu không xác định được khu vực:
  không cung cấp cho Trainer.
- Trong nhóm: chỉ hướng dẫn nhắn riêng, không trả dữ liệu dashboard.

## Các câu hỏi mẫu

```text
Dashboard có những dữ liệu nào?
Tháng 10/2026 có bao nhiêu PGs OPPO 0-1 sao?
Danh sách PGs mới tháng 10/2026
Chi tiết PGs mã PG <mã cần xem>
KPI tháng 10/2026
Target và tiến độ truyền thông nội bộ tháng 10/2026
Danh sách shop MWG
Biến động On/Off tháng 10/2026
Chi tiết Coaching hôm nay
Workshop đối tác đã hoàn thành tháng 10/2026
Chi tiết điểm CVTV tháng 10/2026
Tổng điểm CVTV cột total tháng 10/2026
Tổng S.O A7 Pro tháng 9/2026
```

Nghĩa có thể thêm khu vực hoặc tên đầy đủ của Trainer vào câu hỏi. Trainer hỏi
khu vực khác sẽ bị từ chối. Kết quả dài chia trang; nhắn `tiếp`, `trang 2` hoặc
`chi tiết mã PG ...`. Ngữ cảnh tra cứu tách theo tài khoản và cuộc trò chuyện,
hết hạn sau 24 giờ và được kiểm tra quyền lại ở mỗi câu hỏi.

## Dữ liệu hỗ trợ

KPI/target; PGs; On/Off; shop/phân công; nhân sự các hãng, đối tác và Sale;
S.O; đăng ký và kết quả Coaching; FTF; truyền thông; workshop; đào tạo CVTV,
PGs 3★; Test Online/Tư vấn AI; chiến dịch; các đề nghị chờ duyệt.

Mục S.O mặc định hiển thị tháng trước, theo cách dashboard đang dùng. Ghi rõ
tháng nếu muốn xem kỳ khác. Kết quả theo ngày chỉ được tính khi nguồn lưu ngày
thực tế; bot không đoán ngày từ dữ liệu tổng hợp tháng. Dữ liệu chưa lưu được
báo rõ, không coi là kết quả bằng 0. Các phép tổng/xếp hạng cần cột có số.

Bộ đọc hiện hỗ trợ các mẫu câu hỏi trên và biến thể theo bộ nhận dạng; không
cam kết xử lý mọi phép phân tích tự do. Khi câu hỏi chưa rõ, bot hướng dẫn
ghi rõ mục, tháng hoặc trường cần xem.

## Quyền và xử lý dữ liệu

`dashboard_qa.py` chọn khóa dữ liệu nghiệp vụ từ danh mục cố định, kiểm tra
staff ID đã xác thực rồi lọc khu vực trước khi tính tổng/đếm/xếp hạng. Các
bản ghi chỉ có mã PG hoặc shop được đối chiếu với danh sách cùng khu vực.
Dữ liệu không rõ sở hữu hoặc mâu thuẫn khu vực bị loại đối với Trainer.
Không đọc bảng tài khoản, không cung cấp khóa truy cập, không chạy SQL hay URL
do người dùng đưa vào và không sửa dữ liệu dashboard.

Câu trả lời tra cứu không được đưa vào bộ nhớ trò chuyện AI, log hay repository.
Các thông tin tra cứu chỉ trả qua DingTalk riêng cho tài khoản được phép. Không
gửi dữ liệu dashboard đến nhà cung cấp AI ngoài. Cấu hình và sổ tin nhắn riêng
vẫn nằm trong `runtime/`, ngoài Git. Bộ tra cứu không thay lịch KPI 08:00,
workflow, dashboard hoặc Secrets.

Kiểm tra: `python -m unittest -q test_dashboard_qa test_conversation test_response_handler`.
