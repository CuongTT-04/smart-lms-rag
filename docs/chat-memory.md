# Phiên chat theo tài liệu và context nhiều lượt

## Sử dụng

Mở học liệu và Trợ lý AI. Chatbot khôi phục phiên gần nhất của tài khoản/tài liệu trong phạm vi khóa, lớp và buổi học hiện tại. **Chat mới** mở hội thoại trống, giữ nguyên phiên cũ; bản ghi phiên được tạo khi gửi câu hỏi đầu tiên. **Lịch sử** cho phép chọn phiên đã lưu và tiếp tục hỏi. Có phân trang phiên và lượt chat cũ.

Hội thoại lưu PostgreSQL, không phụ thuộc localStorage. Tải lại trang hoặc đăng nhập lại cùng tài khoản vẫn lấy được lịch sử khi còn quyền. Chuyển tài liệu hoặc phiên bản không mang memory sang tài liệu khác. Học liệu bị thu hồi hoặc người dùng mất quyền thì API không trả transcript/citation cũ. TEST vẫn chặn trợ lý và lịch sử; gợi ý bài PRACTICE hiện giữ luồng độc lập.

## Context gửi model

Backend chỉ đọc các lượt COMPLETED của chính phiên, tối đa bốn cặp. Gateway dùng protocol `chat_history_v1`, đếm bằng tokenizer thật và giới hạn history tối đa 768 token trong ngân sách input hiện có. Lượt cũ bị bỏ nguyên cặp khi cần; evidence phải còn ít nhất một chunk vừa ngân sách. Lịch sử đầy đủ hiển thị trong UI không có nghĩa toàn bộ được gửi model.

Các lượt trước dùng để hiểu câu hỏi tiếp, không được coi là bằng chứng. Citation số cũ được loại khỏi memory; trả lời mới chỉ dẫn các nguồn thực sự trong prompt hiện tại. Retrieval dùng câu hiện tại và chủ đề của câu hỏi trước, trong đúng scope tài liệu đã kiểm quyền. Không dùng answer cũ như gold hoặc dữ liệu fine-tune.

Stateless requests không gửi history, giữ prompt/baseline cũ. Bài ôn tập không tự dùng memory của tài liệu. Hai replica không giữ memory người dùng ở biến toàn cục; mỗi request nhận history riêng từ server.

## Cập nhật backend và Kaggle

Backend cần migration `ai.0002_chat_conversations`. Với Docker:

```powershell
docker compose exec -T backend python manage.py migrate
docker compose up -d --build frontend
```

Gateway cũ không hỗ trợ protocol này; backend sẽ báo cấu hình chưa đồng bộ, không giả vờ đã gửi memory thành công. Xuất cell mới từ source:

```powershell
.\.venv\Scripts\python.exe scripts/append_kaggle_memory.py --export D:\ohayo-chat-memory-startup-cell.py
```

Copy toàn bộ file vào một code cell mới cuối notebook Kaggle. Chọn **Restart & Clear Cell Outputs**, bật T4 x2 + Internet, giữ checkpoint Input và hai Secrets `NGROK_AUTHTOKEN`/`OHAYO_INFERENCE_TOKEN`, rồi chỉ chạy cell cuối. Không Run All, không tạo checkpoint hoặc đánh giá lại QA. Notebook trong repo đã được append cell mới mà giữ mọi cell cũ.

Sau `SAN SANG` và `DUAL_GPU_READY`, thay URL thực trong lệnh:

```powershell
.\.venv\Scripts\python.exe scripts/configure_kaggle_inference.py --url https://TEN-ENDPOINT.ngrok-free.dev --use-env-token --dual-gpu --chat-memory
docker compose up -d --no-deps backend
```

Helper xác thực health có `capabilities` chứa `chat_history_v1` rồi mới ghi cấu hình. Dùng đúng token cũ; không gửi token vào chat/output. Nếu chỉ có gateway cũ, helper từ chối ghi config. HTTP health thông thường không thay kiểm chứng model trả lời có dùng history.

## Kiểm tra

1. Hỏi một câu có căn cứ trong học liệu; hỏi tiếp “giải thích rõ hơn ý đó”. Kiểm source/citation, không chỉ xem UI có lưu câu cũ.
2. Nhấn Chat mới; phiên trống không gửi memory của phiên trước.
3. Mở Lịch sử, chọn phiên cũ; câu hỏi, câu trả lời, nguồn và đánh giá phải khôi phục. F5 rồi mở lại để kiểm DB.
4. Đổi tài liệu; không thấy phiên/câu hỏi tài liệu trước. Thu hồi nguồn hoặc quyền và gọi API lại phải bị chặn.
5. Khi đang xử lý, nhấn Chat mới/chọn phiên khác: response cũ không được hiển thị vào phiên mới. Việc đóng request trình duyệt không bảo đảm hủy GPU; kết quả hợp lệ có thể được lưu ở phiên cũ.

API dùng client_message_id để retry cùng lượt không sinh trùng. Chỉ một lượt PENDING mỗi phiên, lease 180 giây; không giữ transaction DB khi gọi model. Lượt treo quá lease chuyển FAILED khi đọc/gửi tiếp; kết quả về muộn không được ghi đè lượt mới. Error/FAILED không vào context.

Các test dùng model/tokenizer giả lập chỉ chứng minh logic, quyền và ngân sách theo counter, không thay kiểm chứng chất lượng Qwen hoặc độ trễ thực. Không tự dùng hội thoại người học cho instruction dataset W5.

## Thông báo lỗi model

Cell khởi động mới công bố capability `validation_details_v1`. Gateway chỉ gửi mã nguyên nhân thuộc danh sách cho phép (thiếu citation, nguồn không hợp lệ, sai định dạng, sai ngôn ngữ, kết quả trống hoặc phương án không khớp); không gửi output lỗi hoặc exception riêng tư. Backend chuyển thành mã lỗi công khai, lưu cùng lượt FAILED và frontend hiển thị nguyên nhân/cách xử lý. Với gateway cũ hoặc lỗi chưa xác định, thông báo nói rõ dịch vụ chưa cung cấp nguyên nhân chi tiết; không suy đoán lỗi citation. Sau khi cập nhật source, xuất lại cell bằng lệnh trên rồi thay nội dung cell cuối Kaggle và restart Python.
