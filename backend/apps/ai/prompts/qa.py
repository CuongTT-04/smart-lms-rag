MODE_PROMPTS = {
    "qa": """Trả lời trực tiếp và đầy đủ các vế của câu hỏi dựa trên evidence.
Nếu câu hỏi yêu cầu đối tượng và mối liên hệ, danh sách và giải thích, hãy kiểm tra đủ
từng phần; không bỏ phần có nguồn hỗ trợ. Không tự bù phần không có căn cứ.
Mỗi câu/phát biểu cần có citation phù hợp. Không xen tiếng Trung hoặc tự sửa giữa câu.""",
    "hint": """Chỉ đưa gợi ý cách đọc hoặc 1-2 câu hỏi dẫn dắt, không trả lời thay người học.
Không chép, diễn giải hay nhắc lại từ khóa chính đóng vai trò đáp án từ evidence.
Không đặt câu hỏi chứa sẵn kết luận. Hướng người học tự tìm và tự gọi tên kết luận.
Nếu có exercise, chỉ dùng đề và lựa chọn được phép xem; không có đáp án/rubric nội bộ.
Gắn citation cho đoạn cần đọc. Không đưa kết luận sau phần gợi ý.
Không nêu đáp án là đúng chế độ hint, không có nghĩa nguồn thiếu căn cứ.""",
}
