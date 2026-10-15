# Báo cáo W3 — phần Trần Tuấn Cường

Ngày chuẩn bị: 14/10/2026. Nhánh: `TranTuanCuong_B22DCVT073_W3Tasks`. Bản nháp phục vụ báo cáo ngày 17/10, chưa là xác nhận hoàn thành toàn bộ W3 của nhóm.

## Planned và Done

Đề cương W3 yêu cầu chunking, embedding, FAISS/Qdrant baseline, retrieval notebook và Recall@k trên 100 QA. Phần Cường tập trung chunk schema, tạo chunk từ extraction, quản lý nguồn/phiên bản và kiểm soát quyền retrieval; phần Dương phụ trách embedding/index/tìm kiếm và phép đo.

Đã triển khai chunking theo từng trang PDF, giới hạn 512 token, overlap mục tiêu 64, normalization NFC/LF, ID ổn định và offsets nguồn. Batch kiểm tra UUID/checksum/page count với DocumentVersion, ghi JSONL/manifest nguyên tử và đọc catalog có kiểm tra checksum. Command operator khóa tokenizer revision bằng SHA commit.

Đã có scope resolver theo quyền course/classroom/session, bản đang công bố và nguồn chưa gỡ. Adapter nhận retriever qua interface, không tin text/source provider, đối chiếu catalog và kiểm tra lại quyền trước trả kết quả. Có kiểm thử thu hồi quyền hoặc công bố trong khi search, scope rỗng, draft/removed source và output provider lỗi.

## Evidence và kết quả thực tế

- 21 kiểm thử W3 đạt. Hồi quy runtime: 269 tests, OK với 4 tests PostgreSQL concurrency bị skip; nhóm upload/worker W2 riêng: 27 tests đạt. Không tính 4 tests skipped là đạt.
- Probe tokenizer BGE-M3 thật trên 27 PDF: 1.048 chunk; kiểm tra giới hạn token, trang/offset, bao phủ văn bản, retry và checksum. Probe này dùng pypdf cho extraction offline, không gọi là toàn corpus Docling đã chạy.
- Probe Docling 2.135.0 với DB in-memory: PDF KTCTMLN ch01 có 29 trang, command tạo 29 chunk; PDF giữ EXTRACTED và indexed_at null. Không sửa DB demo.
- Chuẩn bị 50 QA phần Cường gồm 25 pilot +25 mới, 7 mẫu hint; có evidence trang và checksum/version mapping. Agent đã hỗ trợ đối chiếu nguồn, trạng thái peer review vẫn pending, chưa gán nhãn đã được Dương/giảng viên review.
- Source và hướng dẫn ở nhánh W3; reports JSON/test log được lưu cùng metadata. Chunk lớn và artifact tokenizer trong private output, không đưa vào Git thường.

## Problems

Chưa nhận real embedding/index/retriever/notebook và kết quả từ Dương trong workspace nên chưa có Recall/top-k thật hoặc video demo truy xuất. Mock provider chỉ dùng trong unit test, không được tính là baseline. Chưa review chéo đủ 100 QA nhóm, chưa đánh giá concurrency PostgreSQL và chưa có persistent indexing receipt/background indexing.

Một test W2 còn kỳ vọng owner không được tải original; đã cập nhật theo yêu cầu hiện tại: owner tải lại tệp gốc, protected student bị chặn. Không đổi logic tải bản sạch hoặc workflow công bố trong lần này.

## Next week và phần cần chốt trước ngày 16

Nhận index/interface/model manifest và 50 QA phần Dương; review chéo; chạy provider thật với scope trên hai khóa; lưu results từng mẫu, Page Recall@1/3/5/10 và phân tích miss. Chốt source/config/data và demo trước viết báo cáo 17/10. W4 triển khai sinh trả lời/gợi ý có nguồn trên pipeline đã kiểm chứng; không dùng báo cáo chunking để tuyên bố chatbot đã hoàn thành.
