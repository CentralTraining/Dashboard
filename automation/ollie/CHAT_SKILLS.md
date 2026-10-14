# Ollie_MT — hội thoại AI tại chỗ

## Đã tích hợp

- `skills/internal-comms`: skill mẫu từ Anthropic, giấy phép Apache-2.0, giữ nguyên nguồn và giấy phép. Các hướng dẫn FAQ, thông báo và trao đổi được điều chỉnh cho team trong các skill riêng dưới đây.
- `skills/ollie-conversation`: trò chuyện tiếng Việt, xưng mình, nhớ tên do người dùng cung cấp, trả lời ngắn, hỏi phần chưa rõ.
- `skills/ollie-team-support`: soạn thông báo, giải thích nghiệp vụ và cách dùng KPI; giữ link, ID và mật mã cuộc họp.
- `skills/ollie-reminders`: hướng dẫn các lệnh có sẵn, không tự xác nhận một thao tác chưa được thực thi.

Skill là hướng dẫn được nạp khi trả lời; không phải huấn luyện lại trọng số mô hình. Muốn sửa giọng văn, chỉnh skill tương ứng. Tài liệu sản phẩm OPPO chính thức có thể thêm vào tài liệu tham khảo sau; hiện chưa được nạp và bot không nên suy đoán thông số.

## Miễn phí và phạm vi dữ liệu

Chạy Qwen bằng llama.cpp trên máy đang vận hành bộ nhận DingTalk Stream. Không dùng Gemini, OpenAI hoặc một nhà cung cấp suy luận bên ngoài. Bộ gọi AI chỉ chấp nhận endpoint cố định `http://127.0.0.1:18081/v1/chat/completions`, không chuyển hướng, không đi qua HTTP proxy. Dịch vụ chỉ lắng nghe loopback, có khóa cục bộ và tắt log nội dung. Không có phí API AI; môi trường chạy vẫn phải hoạt động để bot trò chuyện.

KPI được bộ đọc và formatter hiện có trả trực tiếp, không đưa bảng dashboard vào prompt AI. Trong nhóm chung, bot yêu cầu hỏi riêng. Trong DM, tài khoản Trainer đã đối chiếu chỉ nhận dữ liệu khu vực của tài khoản đó; Nghĩa nhận tổng hợp toàn team. Tên tự gõ trong câu hỏi không thay thế đối chiếu tài khoản. Thiếu đối chiếu hoặc thiếu khu vực sẽ từ chối trả số liệu, không đoán.

Lịch sử hội thoại tách theo tài khoản và cuộc trò chuyện, dùng tối đa ba lượt trước trong 24 giờ, dọn sau 7 ngày. Chỉ ghi nhớ sau khi DingTalk chấp nhận trả lời. KPI và kết quả lệnh không được đưa vào lịch sử AI. Nhật ký kỹ thuật chỉ ghi trạng thái, không ghi bảng dashboard hoặc nội dung người dùng.

## Khởi động

1. Tải binary llama.cpp và model GGUF từ nguồn chính thức, kiểm tra SHA của model; đặt trong `runtime/local-ai/`. Không đưa model, khóa hay dữ liệu runtime vào Git.
2. Manifest riêng `runtime/local-ai/manifest.json` chỉ định một model đã hỗ trợ. Mô hình đã chọn: `Qwen/Qwen3-4B-GGUF`, Q4_K_M từ nguồn Qwen chính thức. Bản 1.7B có thể chạy nhẹ hơn nhưng cần đánh giá chất lượng riêng trước khi thay thế.
3. Sao chép `ai-settings.example.json` sang `runtime/ai-settings.json`, đặt `enabled=true` cho mô hình tại chỗ đã được cài. Chương trình tạo khóa cục bộ trong `runtime/local-ai/api-key.txt`; không gửi khóa này trong chat.
4. Chạy `app.py` như bộ nhận Stream hiện tại. Bộ giám sát kiểm tra mô hình mỗi 20 giây và khởi động lại khi mô hình dừng. GitHub Actions tiếp tục phụ trách lịch KPI đã có; Actions không phải máy chạy hội thoại liên tục.

Không bật một API đám mây để thay thế khi model lỗi; bot trả lời dự phòng và giữ các lệnh hiện có. Không công bố dữ liệu runtime, lịch sử, credentials hoặc báo cáo KPI trong repository.

## Thử trong DingTalk

Nhắn riêng hoặc chọn @Ollie_MT trong nhóm đã cấu hình:

- “Chào Ollie, mình tên Minh. Hôm nay sao rồi?”
- “Mình vừa nói mình tên gì?”
- “Mình đang nhiều việc, giúp mình sắp xếp nhé.”
- “Soạn giúp thông báo họp, thời gian …, link …, ID …, mật mã ….”
- “KPI khu vực của tôi thế nào?” (chỉ DM; dữ liệu theo quyền)

Mô hình nhỏ trên CPU có giới hạn chất lượng và tốc độ; chưa thể coi mọi câu trả lời là đúng. Các thao tác giao việc/đổi hạn/hủy vẫn đi qua bộ lệnh kiểm soát quyền hiện có. Chương trình chỉ xác nhận đã làm khi bộ lệnh có kết quả thật.

Nguồn skill: https://github.com/anthropics/skills/tree/main/skills/internal-comms

Nguồn model: https://huggingface.co/Qwen/Qwen3-4B-GGUF

Runtime: https://github.com/ggml-org/llama.cpp
