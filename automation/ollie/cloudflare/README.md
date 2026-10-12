# Ollie_MT — điểm nhận thông báo miễn phí

Dashboard và lịch 08:00 vẫn ở GitHub. Worker này nhận thông báo có
@Ollie_MT qua chế độ HTTP, lưu bản gốc và deadline dưới dạng mã hóa trong
nguồn Supabase hiện có. Nghĩa tạo thông báo; Trainer được đánh dấu hoàn
thành phần việc của mình. Không cần Mac luôn bật.

## Kết nối Cloudflare (5 bước)

1. Tạo/đăng nhập tài khoản miễn phí tại https://dash.cloudflare.com/.
2. Mở **Workers & Pages** để kích hoạt tài khoản Workers; lấy **Account ID**.
3. Vào hồ sơ → **API Tokens → Create Token → Edit Cloudflare Workers**,
   chọn đúng tài khoản của mình và tạo token.
4. Trong repo `CentralTraining/Dashboard`, vào **Settings → Secrets and
   variables → Actions**, thêm `CLOUDFLARE_API_TOKEN` và
   `CLOUDFLARE_ACCOUNT_ID`. `OLLIE_KPI_CONFIG_JSON` đã có, không cần sửa.
5. Chạy **Actions → Deploy Ollie receiver → Run workflow**. Sau khi thành
   công, lấy URL Worker để cấu hình mục robot DingTalk sang HTTP và phát
   hành phiên bản mới. Chỉ chuyển khỏi Stream khi endpoint đã kiểm tra xong.

Phần triển khai có thể được thực hiện bởi trợ lý sau khi 2 Secret Cloudflare
được cung cấp. Token chỉ nằm trong GitHub Secrets, không đưa vào chat hoặc
mã nguồn. Gói Workers Free có hạn mức 100.000 request/ngày; không cần gói
trả phí cho quy mô hiện tại. Giới hạn của nhà cung cấp có thể thay đổi.

## Thông báo mẫu

```text
@Ollie_MT
THÔNG BÁO NỘP BÁO CÁO
Mỗi Trainer nộp báo cáo đào tạo tuần và cập nhật 2 video.
Deadline: 20/10/2026 17:00
Link: https://centraltraining.github.io/Dashboard/
```

Thông báo họp giữ nguyên link có đủ tham số, ID và mật mã. Mỗi thông báo
cần một deadline rõ ràng; ngày tương đối dùng thời điểm gửi. Thiếu năm,
ngày mâu thuẫn hoặc thời hạn đã qua thì hỏi lại, không tự tạo deadline.
Deadline công việc chỉ có ngày được hiểu là 23:59 Việt Nam; họp cần cả giờ.

Lệnh sau khi chuyển sang HTTP: `hướng dẫn`, `danh sách`, `hoàn thành CV-<mã>`,
`hủy CV-<mã>`, `đổi hạn CV-<mã> 21/10/2026 17:00`. Lấy mã trong `danh sách`.
Không hiển thị mã trong bản nhắc hằng ngày. Hủy và đổi hạn dành cho Nghĩa.
Lệnh quản lý thông báo trên dashboard dùng các nút trong thẻ Trainer.

Ngày mới nhận lời chúc khác nhau. Danh sách hằng ngày sắp theo deadline gần
nhất, rồi thời điểm tạo. Việc mới bắt đầu từ 08:00 sáng hôm sau; dừng khi
hoàn thành, hủy hoặc qua deadline. Link hiển thị bằng chữ **Link** có dấu
🔴; màu chữ liên kết do DingTalk quyết định.

Không giữ sessionWebhook để gửi về sau. Lịch GitHub dùng Open API và sổ
chống gửi lặp đã mã hóa. Dữ liệu trong thẻ Trainer chỉ được nhắc nếu đã nhập
deadline; không suy đoán ngày kết thúc từ tên chiến dịch KPI.
