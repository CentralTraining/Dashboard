# Find Master — khắc phục trạng thái duyệt không đồng bộ | 28/10/2026

Thay đổi chỉ nằm trong luồng Admin duyệt yêu cầu thêm/loại PGs. Không thay Target 5 mốc, phân công Trainer, kết quả thi, bắt cặp, TikTok, Secrets hoặc Edge Functions.

## Nguyên nhân trong code cũ

Danh sách Master được lưu trước, hàng đợi yêu cầu lưu sau bằng hai HTTP request độc lập. Nếu chỉ bước đầu được xác nhận, hai bản ghi có thể không đồng bộ: Master đã áp dụng yêu cầu nhưng hàng đợi còn pending. Khi bấm duyệt lại yêu cầu loại, code tìm PG trong registered trước khi kiểm tra approvedRequestIds; vì PG đã bị loại, chương trình báo nhầm Trainer không phụ trách.

Dữ liệu vận hành đã xác nhận có trạng thái này. Không có đủ log lịch sử để kết luận lần ghi hàng đợi ban đầu thất bại vì mất mạng hay bị phiên cũ ghi đè.

## Cách sửa

- Duyệt mới: dùng một multi-row upsert vào kv_store cho cả Master và hàng đợi trong cùng một PostgREST/Postgres transaction; không còn hai bước commit rời nhau.
- Yêu cầu cũ đã áp dụng: kiểm tra ID đã xác nhận, trạng thái loại/thêm và danh sách chính thức. Nếu khớp, chỉ hoàn tất hàng đợi, không thêm/loại PG lần nữa.
- Không cho từ chối lại yêu cầu đã áp dụng. Nếu bằng chứng không khớp, dừng đối soát thay vì tự áp dụng lại.
- Phân biệt không còn trong Master với thực sự sai Trainer. Kiểm tra sở hữu Trainer vẫn giữ nguyên.
- Không đọc được snapshot Master/hàng đợi thì không duyệt; thao tác chuẩn bị không làm biến đổi bộ nhớ cache của dữ liệu đã xác nhận.
- Nếu mất phản hồi, thông báo kết quả chưa xác nhận và yêu cầu tải lại trước khi thao tác tiếp.

## Kiểm tra

Kiểm thử bằng dữ liệu giả lập cho thêm/loại, trạng thái cũ bị kẹt, mất kết nối trước/sau commit, thiếu snapshot, sai Trainer, từ chối và bảo toàn kết quả cá nhân/các yêu cầu khác. Kiểm tra browser HTML đầy đủ ở 1440 và 390 px. Không sử dụng dữ liệu PG thực trong file export.

Hai yêu cầu vận hành đã có xác nhận áp dụng được đối soát trạng thái riêng, có điều kiện kiểm tra hash Master và hàng đợi; giữ nguyên danh sách Master và mọi yêu cầu khác. Không tự phê duyệt một yêu cầu mới chưa có bằng chứng đã áp dụng.

Tệp HTML là bản đầy đủ, không phải patch. Xem manifest để biết phạm vi Test hoặc Main. Không cần đổi cấu hình Supabase hay Secrets.
