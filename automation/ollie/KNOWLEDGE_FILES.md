# Tài liệu đào tạo cho Ollie_MT

Nghĩa nạp tài liệu qua tin nhắn riêng. Bot đọc nội dung tại chỗ, lưu thành kho
tham khảo và lấy trích đoạn phù hợp khi trả lời. Đây là bổ sung nguồn kiến thức,
không phải huấn luyện lại trọng số của mô hình.

## Cách dùng

1. Gửi trực tiếp tệp Word, PDF, ảnh hoặc video vào tin nhắn riêng với Ollie_MT.
2. Bot xác nhận đã xếp hàng; đây chưa phải xác nhận đọc xong.
3. Chờ tin nhắn riêng có mã `TL-…` và thông báo phạm vi/nội dung đã nhận được.
4. Nghĩa hoặc Trainer hỏi `Theo tài liệu TL-1, ...`, hoặc hỏi nội dung liên quan
   như `Thông số pin của sản phẩm trong tài liệu là gì?`.
5. Nhắn `tài liệu` để xem danh sách; Nghĩa dùng `gỡ tài liệu TL-1` để ngừng dùng
   nguồn. Gỡ chỉ ngừng tra cứu, vẫn giữ bản gốc riêng để đối chiếu.

Chỉ leader đã đối chiếu được nạp/gỡ. Tài liệu đào tạo được dùng chung cho 13
Trainer đã đối chiếu và Nghĩa theo lựa chọn của Nghĩa. Tài khoản khác bị từ chối;
trả lời chỉ qua tin nhắn riêng. Tệp nhận trong nhóm không tự nhập làm kiến thức.
Trong một tin nhắn xử lý tối đa 5 tệp. Tệp chưa nhận được sự kiện từ DingTalk
không thể được bot xử lý; nên gửi dưới dạng tệp trực tiếp, thay vì một link web.

## Định dạng và giới hạn

| Tệp | Nội dung đọc | Giới hạn |
| --- | --- | --- |
| Word `.docx` | Đoạn văn, bảng, chữ trong ảnh nhúng | 100 MB; tối đa 30 ảnh nhúng |
| Word `.doc` | Văn bản bằng antiword | Nên lưu lại thành `.docx` nếu tệp lỗi hoặc có nội dung đồ họa |
| PDF | Chữ; OCR với trang scan/ít chữ | 100 trang, 100 MB; gửi bản không khóa |
| PNG/JPG/WEBP/BMP/TIFF | Nhận chữ Việt/Anh | 32 triệu pixel; không phân tích hình không có chữ |
| MP4/MOV/MKV/WEBM/AVI | Lời nói và chữ trên khung hình mẫu, có mốc thời gian | 20 phút, 100 MB; tối đa 60 khung hình |

Ảnh mờ, giọng nói không rõ, bảng phức tạp và cảnh video nhanh có thể bị nhận sai
hoặc bỏ sót. Bot thông báo giới hạn và dẫn tên tài liệu, trang/đoạn/mốc thời gian.
Đối chiếu lại nguồn với thông số quan trọng. Tóm tắt bằng trích đoạn không cam
kết bao quát mọi trang trong một tài liệu dài. Không có nội dung đủ rõ thì bot
báo chưa đọc được, không xác nhận đã học thành công.

## Bảo mật

Kho tài liệu, bản gốc và đoạn trích nằm trong `runtime/knowledge/`, ngoài Git;
không đưa vào dashboard, Supabase, log hoặc nhà cung cấp AI bên ngoài. PDF/Word
không thực thi macro; trích đoạn chỉ làm dữ liệu tham khảo, không được dùng làm
lệnh gửi tin, đọc dashboard hoặc thay đổi quyền. Mô hình trả lời chỉ nhận các
đoạn trích đã lọc quyền, chạy trên địa chỉ loopback của môi trường hiện tại.

Quyền dashboard vẫn kiểm tra riêng theo tài khoản/khu vực. Tài liệu nhận diện
có KPI/dashboard hoặc nhãn khóa API được giữ riêng cho Nghĩa, không dùng làm
kiến thức chung cho Team. Việc nhận diện từ khóa có thể giữ riêng cả tài liệu
hướng dẫn KPI; kiểm tra phạm vi trong tin báo sau khi nhập.

Tin báo xử lý chỉ đánh dấu tiếp nhận khi DingTalk trả mã tiếp nhận. Kết quả
gửi không rõ giữ `unknown` và không tự gửi lại. Tải tệp dùng API chính thức
DingTalk rồi chỉ tải từ các miền lưu trữ đã cho phép; không tải URL người hỏi
tự đưa. Nếu API từ chối quyền, bot báo lỗi để kiểm tra quyền tải tệp của robot.

## Công cụ và cài đặt

Các thư viện/công cụ nguồn mở chạy tại chỗ: python-docx, pypdf, Tesseract
vie+eng, ffmpeg, antiword và faster-whisper với mô hình multilingual small.
Không cần khóa dịch vụ AI trả phí. Chi phí/tài nguyên của nơi chạy vẫn phụ
thuộc môi trường; cần giữ môi trường đang chạy để nhận và xử lý tệp.

`pip install -r requirements-knowledge.txt`. Cài Tesseract/ffmpeg/pdftoppm;
đặt dữ liệu OCR vào `runtime/knowledge/models/tessdata`, mô hình small tại
`runtime/knowledge/models/whisper`, antiword tại
`runtime/knowledge/bin/antiword-package/usr/bin/antiword` kèm bảng mã trong
`usr/share/antiword`. Thiết lập riêng `runtime/knowledge/settings.json`:

```json
{"enabled":true,"default_scope":"team","external_inference":false}
```

Kiểm tra: `python -m unittest -q test_knowledge test_response_handler test_conversation test_dashboard_qa`.

Nguồn:
- [DingTalk: nhận các loại tin nhắn/tệp](https://open-dingtalk.github.io/developerpedia/docs/learn/bot/message/)
- [DingTalk: tải tệp robot nhận](https://open.dingtalk.com/document/orgapp/download-the-file-content-of-the-robot-receiving-message)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Tesseract dữ liệu OCR](https://github.com/tesseract-ocr/tessdata_fast)
