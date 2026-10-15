# Biên bản bàn giao W3 — Cường → Dương

**Ngày lập:** 15/10/2026. **Mục đích:** nối code A/B, bàn giao đầu vào/lệnh chạy để hoàn thành kỹ thuật W3 hết ngày **16/10**; ngày **17/10** viết báo cáo.

**Bên chuẩn bị:** Trần Tuấn Cường — B22DCVT073. **Bên nhận dự kiến:** Vũ Nam Dương — B22DCVT119. Đây là biên bản kỹ thuật chuẩn bị cho hai thành viên đối chiếu; chưa có xác nhận nhận bàn giao hay chữ ký thay Dương.

## 1. Phiên bản nguồn

| Thành phần | Phiên bản |
|---|---|
| Code Dương đã nhận | `88d5520` trên `VuNamDuong_B22DCVT119_W3Tasks` |
| Code Cường đã có | `1ef69c7`; cập nhật tài liệu `dae41c6` |
| Nhánh tích hợp | `TranTuanCuong_B22DCVT073_W3Tasks`; merge giữ cả lịch sử A/B |
| Commit chứa biên bản | Xác định bằng `git log -1 --format=%H -- docs/reports/w3-ban-giao-duong.md` sau commit |
| Tài liệu đầu vào đã đối chiếu | `D:/ohayo-retrieval-baseline.ipynb`, `D:/w3-a-worklog.md`; giữ nguyên bản đính kèm |

Chưa push hoặc tạo PR. Dương cần nhận commit tích hợp qua repository/remote do nhóm thống nhất trước khi chạy; không chỉ lấy lại commit A cũ. Gói source kiểm chứng nằm tại `.private/w3-handoff-package/ohayo-smartlms.zip`; gói bàn giao sau commit nằm tại `.private/w3-delivery-20261015/ohayo-smartlms.zip`, có manifest checksum và kèm biên bản/hướng dẫn. Không tự công khai corpus/weights/artifacts.

## 2. Nội dung đã ghép

| Đầu ra | Trạng thái và bằng chứng |
|---|---|
| Embedding + FAISS + lưu/load + evaluation của A | Đã merge nguyên commit; 108 test A giữ được, tổng AI sau tích hợp 112 test đạt trong gói source |
| Chunk/catalog B → index A | Loader kiểm tra config/hash/UUID/count per-version và corpus; từ chối trùng ID, drift metadata và index/catalog khác text |
| Quyền B → RetrievalService A | `backend/apps/documents/dense_retrieval.py`: server scope, lọc trước top-k, kiểm tra lại DB, giữ owner preview; test FAISS thật + SQLite với vector xác định |
| Config tích hợp | BGE-M3 revision khóa; chunk 512 token nội dung, encoder 514 gồm 2 special; không truncate, không đổi ID chunk cũ |
| QA chung | 75 A + 50 B − 25 pilot trùng = **100 câu khác nhau**, giữ original pilot; 7 hint; JSON labels chuẩn hóa UUID/trang vật lý |
| Tái lập | `scripts/run_w3_baseline.py`, notebook mới và `w3-ab-reproduce.md`; runner lưu/load, top-10, xuất kết quả từng QA và metrics |
| Gói Kaggle | Đã bổ sung input QA B và README thiếu trong commit A; chạy đủ 112 test AI từ gói đã đóng |

## 3. Dữ liệu bàn giao và giới hạn

| Artifact | Vị trí | Nội dung |
|---|---|---|
| Corpus + chunk | `backend/.private/w3/corpus_manifest.json`, `backend/.private/w3/documents/` | 27 PDF, 1.048 chunk; **pypdf probe**, UUID5 offline; có checksum/config/offset/trang; Git ignore |
| Corpus gốc | `data/corpus/` | PDF để đối chiếu trang, cùng snapshot với manifest; kiểm tra hash trước đo |
| Dataset chung | `data/qa/qa_w3_v1.0.csv` và `.json` | CSV để review; JSON chuẩn hóa dùng runner/evaluation; chưa là held-out test set |
| Source mapping | `data/qa/w3_source_map.json` | Subject/file → course/document/version/checksum và số trang |
| Review log | `data/qa/qa_review_log.csv` | 99 source-check pending peer; **`KTCTMLN_QA_001` cần review nguồn**; 0 câu được ghi human peer approved |
| Preflight đã chạy | `docs/reports/w3-ab-preflight-verification.json` | 27 PDF/1.048 chunk/100 QA khớp artifact; tokenizer thật, lớn nhất 514 token |
| Notebook tích hợp | `notebooks/w3_retrieval_baseline.ipynb` | JSON/cú pháp 5 code cell đã kiểm tra; **chưa Run All model thật trên Kaggle** |
| Hướng dẫn đầy đủ | `docs/reports/w3-ab-reproduce.md` | Cài môi trường, build/validate/query/reload, runtime bridge và đóng gói |

99 câu source-check kế thừa bằng chứng từ hai bộ, không thay thế duyệt ngữ nghĩa câu hỏi/đáp án của con người. Riêng 25 câu pilot trùng có nội dung/đáp án/trang thống nhất nên chỉ tính một lần. QA còn pending không được ghi “đã nghiệm thu 100 QA”.

**Không ghép ID probe với DB runtime.** Phần Docling runtime một PDF (29 trang/29 chunk) là bằng chứng B trước đó, khác snapshot offline. Muốn demo chatbot truy nguồn DB cần build index từ đúng DocumentVersion/runtime manifests; bridge đã có nhưng không tự index hay thêm API chatbot.

## 4. Kiểm chứng đã thực hiện

| Nhóm | Kết quả | Phạm vi |
|---|---|---|
| AI trong gói đã đóng | **112/112 đạt** | A108 + token contract, merge QA, runner build/reload/error, package input; vector test là synthetic, không gọi model embedding |
| Backend runtime | **273 đạt, 4 skip / 277** | Django SQLite, quyền/version/API cũ; thêm 7 test dense bridge + 1 test corpus; 4 concurrency chỉ chạy trên PostgreSQL |
| Upload/worker W2 riêng | **27/27 đạt** | Fixture settings riêng, không DB demo |
| Corpus/tokenizer | **27 PDF, 1.048 chunk, 100 nhãn khớp** | BGE-M3 tokenizer thật; chưa inference BGE-M3 toàn corpus |
| Review code độc lập | Không có Critical/Important trong bridge/scoring | Thiếu CSV trong package được phát hiện, nâng thành blocker tái lập và sửa bằng regression RED→GREEN |

Tổng các nhóm code trên: **412 test đạt, 4 skip**; không cộng lần chạy lại cùng test thành test mới. Logs: `w3-ab-tests-package.txt`, `w3-ab-tests-runtime-final.txt`, `w3-ab-tests-isolated.txt`. Unit runner kiểm tra lỗi retrieval vẫn nằm trong denominator; metric 0/1 từ unit fixture **không phải Recall corpus**.

**Chưa xác nhận:** 1.048 vector model thật, final index corpus và checksum, Recall thực trên 100 QA đã review, clean-kernel Kaggle Run All, demo/PR và nghiệm thu của nhóm. Notebook A đính kèm cho bằng chứng sample model thật 12 chunk; không suy thành kết quả toàn corpus. Không báo Recall@5 ≥0,80 khi chưa đo.

## 5. Phần Dương nhận và thực hiện tiếp

| Mốc đề xuất (16/10) | Việc Dương làm | Output cụ thể / điều kiện xong |
|---|---|---|
| M1 — trước 10:00 | Nhận source/27 PDF hoặc đầy đủ chunk artifacts; xác nhận config 514, UUID, sample query | Preflight log đúng 27/1.048/100, kiểm tra hash, môi trường `pip freeze`; không dùng ZIP sample cũ |
| M2 — trước 12:00 | Review 50 câu B; phối hợp Cường review 49 câu A và `KTCTMLN_QA_001` | `qa_review_log.csv`: reviewer, ngày/ghi chú sửa; CSV và JSON cùng nhãn mới; đủ 100 QA nguồn hỗ trợ hoặc báo phần thiếu |
| M3 — trước 15:00 | Chạy BGE-M3 thật, build full index, query top-10 cả 100 QA | `index/` đủ pointer + generation/hash; `predictions.json`, `retrieval_results.csv`, `metrics.json`; 100 dòng, giữ lỗi; Page Recall/Hit@1/3/5/10 |
| M4 — trước 17:00 | Restart kernel, Run All notebook; reload index cùng config; phân tích lỗi | Notebook có outputs, log clean-run và pip freeze; kiểm tra 3 truy vấn reload không đổi top-k; bảng QA miss/nguyên nhân/nguồn cụ thể |
| M5 — trước 20:00 | Bàn giao kết quả cho Cường để tổng hợp/demo và review chéo code | Commit/PR theo quy trình nhóm; vị trí artifact/hash; video query → đúng trang + reload + case sai quyền từ DB; danh sách phần chưa đạt |

Giờ là mốc phối hợp đề xuất, không phải xác nhận Dương đã nhận lịch. Ngày 17/10 dành báo cáo. Nếu inference chậm: đo batch nhỏ để ước lượng, dùng GPU phù hợp, giữ một config và báo phạm vi thực; không thay model hoặc bỏ mẫu khó để làm đẹp số.

## 6. Phần Cường còn phối hợp

- Review ngữ nghĩa 49 QA THMLN của A; đối chiếu pilot `KTCTMLN_QA_001` với trang PDF, xử lý ghi chú còn thiếu.
- Nhận kết quả thật từ Dương, đối chiếu một số phép tính Page Recall thủ công; bổ sung error analysis, evidence manifest và demo theo đúng snapshot.
- Kiểm tra demo quyền bằng DB/runtime IDs, chạy 4 test PostgreSQL concurrency nếu điều kiện nghiệm thu yêu cầu; không tính SQLite skip là đạt.
- Ngày 17 viết báo cáo W3 với số liệu thật và đóng góp từng người. Chưa có final Recall thì ghi thiếu, không lấy số fixture thay vào.

## 7. Xác nhận nhận bàn giao (để trống)

- Dương đã nhận source commit: …
- Đã nhận đủ corpus/chunk artifacts, kiểm tra hash: …
- Dataset/config chốt dùng cho lần đo: …
- Đường dẫn kết quả/model/index và checksum: …
- Phần tồn đọng, người phụ trách và hẹn hoàn tất: …
- Cường xác nhận: … ; Dương xác nhận: …
