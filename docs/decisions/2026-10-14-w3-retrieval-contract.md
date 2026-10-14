# ADR W3 — chunk và ranh giới quyền retrieval

Ngày: 14/10/2026. Chủ trì phần B: Trần Tuấn Cường. Trạng thái: hợp đồng phía B đã triển khai; chờ đối chiếu interface/index của Dương, không coi là biên bản hai người đã phê duyệt.

## Quyết định

- Schema/config ở `backend/config/w3/`; BGE-M3 tokenizer khóa SHA `5617a9f61b028005a4858fdac845db406aefb181`, max 512, overlap mục tiêu 64, NFC/LF. Paragraph/sentence boundary chỉ chọn khi vẫn bảo đảm budget; câu dài dùng offsets, không decode token rồi coi là nguồn nguyên bản.
- FAISS dense baseline là đề xuất phần index A, không được tạo sẵn bằng fixture ở phần B. Hai phía chốt `search(query=..., allowed_version_ids=tuple, top_k=int)` trả list `{chunk_id, score}`; text/source dựng từ catalog B đã kiểm tra hash.
- `resolve_scope` chỉ xác định nguồn đủ quyền để tìm; EXTRACTED không tự chứng minh đã indexing. Model/index unavailable do provider báo 503. Không cập nhật `READY`, `indexed_at` hay workflow publish W2 khi chỉ có chunk.
- JSONL và manifest content-addressed trong private storage, ghi nguyên tử. Generation gắn extraction/config/title; original checksum kiểm tra ở batch runtime; retry không append chunk.
- Owner preview chỉ khi gọi explicit `preview=True`, lấy `active_version` hoặc bản công bố; không tự lấy latest chưa xác định. Student dùng published version, cả CourseMember và enrollment lớp nếu tài liệu có session. Session draft/removed không mở rộng sang toàn course.
- Chế độ qa/hint có cùng scope. Answer key riêng không thuộc corpus student. Adapter là boundary nội bộ, không thêm raw-text API/frontend public.
- Cường phụ trách pilot CSV dòng 26–50 (KTCTMLN_QA_002–013 và CNXHKH_QA_001–013), thêm 25 QA mới. Tập được chuẩn bị với agent source-check và chờ peer review; không sửa pilot gốc hoặc tự ký review thay Dương.

## Kiểm chứng và giới hạn

Probe 27 PDF dùng **pypdf** để tạo input offline, kiểm chứng tokenizer thật/offset/coverage/idempotency, không gọi là Docling corpus extraction. Probe riêng dùng **Docling thật** và DB SQLite in-memory, chạy management command trên một DocumentVersion; không đổi DB demo. Không có embedding/index/Recall và không có nghiệm thu PostgreSQL concurrency trong phần B hiện tại.

Tokenizer config unit test cho phép revision fixture; operator command bắt SHA commit thật, không chấp nhận `main`/tag mutable. Catalog là server-owned artifact, không chấp nhận catalog từ request data. Khi triển khai endpoint W4 phải giữ ranh giới này và kiểm tra quyền trước trả phản hồi AI.
