# Đề xuất quyết định phạm vi đầu vào W5

Ngày: 27/10/2026. Người soạn: Trần Tuấn Cường — B. Người cần review: Vũ Nam Dương — A. Trạng thái ban đầu: PROPOSED_PENDING_A_REVIEW. Cập nhật 28/10: A đã đồng ý theo báo cáo của Cường; contract v0.2 ghi nguồn được phép nghiên cứu nội bộ theo chỉ dẫn người dùng, không phải giấy phép công khai. Source base: `5c5bdef200fc839cfa1e5aa3d3fa609c7f5d20ba`.

## Bối cảnh

Yêu cầu người dùng ngày 27/10 là chuẩn bị instruction dataset cho QLoRA và kiểm tra chất lượng mẫu ở W5. Đề cương chi tiết cũ ghi W5 hybrid/rerank và W6 build dataset/training dry-run với 1k–5k instruction. Quyết định này ghi rõ lệch lịch, không tự xác nhận giảng viên đã duyệt và không loại bỏ hybrid/rerank khỏi đồ án.

## Đề xuất

- W5 chuẩn bị pilot 500 mẫu hợp lệ được review chéo; A/B mỗi người 250. Số này là đề xuất của kế hoạch, không phải yêu cầu số lượng mới của giảng viên.
- A/B cùng khóa schema, nguồn/quyền, format thô phù hợp chatbot, split và rubric trước sinh hàng loạt.
- Không coi 150 QA development hiện có là instruction được phép dùng train hoặc test độc lập; giữ benchmark và nhãn ngoài fine-tune.
- W5 không yêu cầu adapter hoàn chỉnh. Training dry-run/huấn luyện và việc mở rộng đủ mục tiêu W6 phải được ghi riêng trong kế hoạch kế tiếp.
- Tiếp tục giữ hạng mục hybrid/rerank trong kế hoạch tổng thể; hai người cần xác định lịch thực hiện sau khi đối chiếu với giảng viên.
- Bộ 27 PDF có quyền ở trạng thái DECLARED_NOT_VERIFIED; chỉ được coi đủ điều kiện tạo/phát hành dataset khi nhóm có căn cứ sử dụng phù hợp. Fixture tự biên soạn không thay corpus nghiên cứu.

## Điều kiện xác nhận

1. A phản hồi D1–D8 trong bản [đầu vào W5](chot-dau-vao-w5.md).
2. Nhóm đối chiếu thay đổi lịch/quy mô với yêu cầu được áp dụng thực tế và lưu tham chiếu xác nhận nếu có.
3. B cập nhật contract theo góp ý; A review phiên bản/commit cuối. Ghi approval thực trong review-status.json, không tạo chữ ký/ngày duyệt giả.

A approval được ghi nhận theo lời Cường; chưa có xác nhận điều chỉnh lịch của giảng viên hoặc mẫu thật được peer review nghiệm thu. Xem quality-report.md cho tiến độ mới.
