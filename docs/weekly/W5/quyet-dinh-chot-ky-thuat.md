# W5 — quyết định kỹ thuật của Trần Tuấn Cường

Ngày29/10/2026, Trần Tuấn Cường phụ trách và cho phép lựa chọn các phương án kỹ thuật phục vụ đồ án, với công cụ hỗ trợ thực hiện. Bộ500 mẫu đã kiểm định được chọn làm baseline nghiên cứu nội bộ để chuẩn bị W6.

Ngày29/10/2026, Trần Tuấn Cường xác nhận nhận trách nhiệm và thông qua các lựa chọn kỹ thuật dưới đây. Xác nhận này không thay cho review chéo hoặc nghiệm thu nhóm.

## Phương án đã chốt

- Giữ500 mẫu với quota300QA/100summary/50hint/50thiếu căn cứ, mỗi người250.
- Dùng ba bản chỉnh A00116/A00139/A00146 với provenance và hash mới; giữ nguyên gói gốc và review cũ để truy vết.
- Split385/57/58, seed42, nguyên27 component; cả ba môn và bốn task có mặt trong từng tập. Chấp nhận tỷ lệ gần80/10/10 thay vì phá nhóm nguồn.
- So nguồn bằng NFC và bỏ whitespace, không bỏ/thay ký tự khác. Tokenizer/revision/giới hạn lấy từ hợp đồng đóng băng trong gói.
- Giữ nghiên cứu nội bộ; không tải trọng số, không huấn luyện QLoRA trong W5, không phát hành nguồn/dataset công khai.

## Ý nghĩa quyết định

Trần Tuấn Cường chịu trách nhiệm về lựa chọn baseline kỹ thuật theo phạm vi đã cho phép; đây chưa phải xác nhận Dương đã review hoặc ký nghiệm thu. Không tạo điểm/PEER_REVIEW ACCEPT thay hai thành viên. Các cờ peer acceptance trong gói đã audit giữ nguyên để bảo toàn snapshot; owner-decision.json ghi riêng quyền chọn baseline hiện tại. Không sửa manifest cũ để biến kết quả kiểm máy thành xác nhận của người khác.

Có thể tiếp tục chuẩn bị thí nghiệm W6 từ baseline đã chọn mà không chờ thêm quyết định triển khai thông thường. Trainer/collator và cấu hình QLoRA phải được kiểm trong W6 trước khi train. Review chéo/PR của người thật theo yêu cầu giảng viên vẫn là minh chứng riêng; quyết định này không tuyên bố đã hoàn tất phần minh chứng đó hoặc bảo đảm được giảng viên nghiệm thu.

## Artifact

Gói .private/w5/group-v0.2/W5-internal-baseline-v1.0.zip gồm nguyên package đã audit, revision-log, verification, biểu mẫu peer và quyết định này. Có SHA256SUMS và receipt riêng; không kèm PDF/weights/token. Chỉ chuyển nội bộ. Chưa push, tạo issue, tag hoặc nộp.

## Xác nhận của Vũ Nam Dương — cập nhật29/10/2026

Theo thông tin Trần Tuấn Cường cung cấp, Vũ Nam Dương đã xác nhận kết quả thực hiện phù hợp. Người xác nhận: Vũ Nam Dương; người chuyển thông tin xác nhận: Trần Tuấn Cường. Xác nhận được ghi nhận ở mức kết quả kỹ thuật chung, không thay đổi người thực hiện theo phân công. Chưa có bảng điểm review theo từng ID/hash kèm theo xác nhận này; các biểu mẫu đó và trạng thái nghiệm thu trong gói đóng băng được theo dõi riêng.
