# W3 Cường — nhật ký thực hiện

Plan: docs/plans/2026-10-14-w3-cuong-thuc-hien.md
Branch: TranTuanCuong_B22DCVT073_W3Tasks

- Khởi đầu: nhánh W3 đã tồn tại và đang checkout; giữ các thay đổi tài liệu chưa commit. Thực hiện trong feature checkout hiện tại theo yêu cầu nhánh của người dùng, không chuyển Docker bind mount sang checkout khác.
- Ruling: chưa có retriever/index Dương trong workspace; không tạo embedding/retrieval giả để tuyên bố end-to-end. Xây interface và kiểm thử bằng provider fixture, rồi ghi phụ thuộc real index trong handoff.
- Ruling: indexing lỗi không thay trạng thái PDF EXTRACTED đang dùng W2; chunk artifact/manifest riêng, chưa thêm worker tự indexing hoặc READY giả.
- Ruling: adapter phải đối chiếu hit với catalog chunk đáng tin từ artifact server, không tin text/source provider hoặc client gửi.
- Pre-flight: chunk schema -> batch -> scope -> adapter giữ UUID document/version/page và config hash; tokenizer được inject cho tests, model revision thật cho artifact.
- Task 1/2: bắt đầu tests chunker trước implementation.

## Kết quả ngày 14/10

- Task 1/2: complete phía B; 5 unit tests chunker RED do chưa có function -> GREEN; schema/config thật, SHA model và chunk sample đã tạo.
- Task 3: complete; 2 batch tests RED do module thiếu -> GREEN; UUID/hash/physical-page validation, atomic JSONL/manifest, idempotency và catalog checksum.
- Task 4: complete; scope tests RED do module thiếu -> GREEN; giữ classroom/session enrollment và source publication.
- Task 5: complete boundary phía B; adapter tests RED -> GREEN; final integration với real retriever A pending. Ruling: bổ sung keyword-only catalog lấy từ manifest trusted; provider chỉ trả ID/score, không tự tạo provenance.
- Review độc lập: không thấy P1/critical; sửa P2 malformed provider ID/list/dict và huge score theo RED->GREEN; khóa CLI SHA commit để tái lập.
- Task 6: chuẩn bị 50 QA Cường có source-check; peer review Dương và nhận/review phần QA A pending. Không tự ghi là peer approved.
- Task 7: 21 W3 tests GREEN; runtime suite 269 tests OK (4 skipped PostgreSQL); isolated W2 27 tests GREEN. Ruling: chạy legacy fake-course tests bằng tests.documents_settings riêng và sửa assertion cũ owner-download theo yêu cầu đã chốt, không đổi production download.
- Real tokenizer probe: 27 PDF, 1.048 chunks; pypdf offline envelope được ghi đúng tên parser. Docling proof riêng: 29 trang/29 chunk, management command thật, SQLite in-memory, không chạm DB demo.
- Task 8: reproduce/error-analysis/evidence metadata chuẩn bị; video top-k thật pending A. Task 9: weekly report Markdown draft chuẩn bị, không ký hoàn thành nhóm W3.
- Chưa thực hiện: embedding, FAISS/Qdrant index, Recall, group dataset 100 approved QA, peer human review, PostgreSQL concurrency, tự index trong worker hoặc READY receipt.
