# Kế hoạch nối W3 A/B và bàn giao Dương

**Yêu cầu:** ghép commit Dương `88d5520` vào nhánh Cường W3, đối chiếu notebook/worklog đính kèm, chuẩn bị đầu ra để Dương hoàn thành W3 trước hết ngày 16/10; ngày 17 viết báo cáo.

**Cách thực hiện:** dùng skill executing-plans, tự triển khai trong nhánh W3 hiện có, một lượt review độc lập cuối. Không đổi DB demo, không push, không tự xác nhận review của hai thành viên.

1. [x] Kiểm tra nhánh sạch, đọc commit, notebook và worklog; merge không commit để giữ lịch sử A.
2. [x] Viết test tích hợp thật FAISS + SQLite; nối scope live của B với RetrievalService A, kiểm tra catalog/index, preview và đổi quyền.
3. [x] Chốt riêng config tích hợp: chunk 512 token nội dung + 2 special = encoder 514; giữ nguyên snapshot/chunk ID và mặc định module A. Chặn config/tokenizer không khớp.
4. [x] Ghép QA theo ID, phát hiện xung đột, chuẩn hóa trang vật lý/UUID/hash; tạo 100 mẫu và review log, không gán chữ ký review con người.
5. [x] Thêm runner/notebook tích hợp dùng corpus thật, lưu/load snapshot, query và export Page Recall; chỉ ghi số thực chạy.
6. [x] Chạy test A/B và hồi quy; phân biệt mock embedding trong unit test, fixture sample, corpus thật và DB runtime.
7. [x] Review độc lập, sửa blocker, viết biên bản bàn giao với lệnh tái lập, output, người chịu trách nhiệm và hạn; commit trên nhánh Cường.

## Quyết định và tiến độ

- Ruling: dùng bridge phía Django gắn user/scope vào mỗi lần gọi; A không nhận allowlist từ client. Chi phí nếu sai: rò nguồn; phải có test thu hồi quyền trong lúc encode/search.
- Ruling: encoder tích hợp 514 thay vì sửa chunk 512 đã bàn giao. Lý do: 512 của B đếm nội dung, A đếm cả special token. Chi phí: index cũ config 512 phải build lại, không dùng chung snapshot.
- Phát hiện: 75 QA A và 50 QA B trùng đúng 25 pilot, nội dung/đáp án/trang trùng khớp; hợp nhất cho 100 ID/câu hỏi khác nhau. Review của Dương đối với phần B vẫn chờ xác nhận.
- Phát hiện: test roundtrip config trong commit A đã hỗ trợ cả offline True/False; notebook đính kèm còn cell vá test dư thừa. Không mang cell sửa source test vào notebook tích hợp.
- Final: Ruling: reviewer xếp thiếu CSV B trong gói là minor; nâng lên Important cho đầu ra bàn giao vì người nhận không tái sinh được QA bằng script được cung cấp. Sửa bằng test thiếu input RED→GREEN, thêm CSV và script đóng gói vào chính gói; chi phí nếu bỏ qua là phải lấy source bổ sung mới tái lập được.
- Task 2/3: complete — 8 test bridge/token contract RED (module chưa có) → GREEN; thêm 1 test corpus manifest RED→GREEN. Tokenizer BGE thật kiểm tra 1.048 chunk, encoded max 514.
- Task 4/5: complete — 100 QA hợp nhất, 99 source-check pending peer, KTCTMLN_QA_001 chờ kiểm tra nguồn. Runner test dùng synthetic vector đi qua save/load FAISS, scoring/error denominator và fresh-process reuse; không dùng số unit làm corpus Recall.
- Task 6: complete — package source đạt 112 AI test; backend runtime 273 pass/4 skip; isolated W2 27 pass. Lượt runtime đầu thiếu cache Docling đã dừng, lượt cuối tái dùng cache có sẵn, hoàn tất 40 giây; không thay code để né parser test.
- Task 7: complete — một review độc lập, không Critical/Important trong bridge/scoring; package thiếu CSV đã sửa và regression đạt. Chưa chạy full embedding/corpus Recall; phần này bàn giao Dương, không đánh dấu W3 nhóm hoàn tất.
