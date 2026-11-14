# W7 - Phân công so sánh Base LLM, RAG và tuned+RAG

**Thời gian** 08-14/11/2026. Cập nhật kết quả ngày 14/11/2026.  
**Milestone** `Tuan07`. Mã việc `W7-01`, `W7-02`; số Issue GitHub lấy từ Issue thực tế khi tạo.  
**Thành viên** Vũ Nam Dương (A, B22DCVT119) và Trần Tuấn Cường (B, B22DCVT073).

## 1. Mục tiêu và phiên bản đang sử dụng

So sánh **Base LLM vs RAG vs tuned+RAG trên cùng benchmark 300 câu**, có output thực, đánh giá cùng rubric, bảng số liệu, biểu đồ và artifact tái lập. Theo quyết định của Cường, nhóm đưa phép so sánh lên W7, sớm hơn mốc comparison W8 trong đề cương.

Nguồn hướng dẫn hiện tại là `docs/comparison.md`, đặc biệt mục 10 về kết quả nhóm và tái lập. Code và schema đang dùng nằm trong `scripts/comparison/`, `data/comparison/`, các notebook tại `notebooks/`. Bộ chuẩn bị W7 ban đầu đã được thay thế và lưu riêng để truy vết.

Dùng benchmark/cache cuối Dương bàn giao trong `comparison-handoff.zip`. Dương đã mở rộng train trên 770 mẫu với 114 validation, giữ riêng 116 holdout; adapter mới đạt 193 updates/một epoch và được chọn bằng dev trước khi khóa main. Phương án này thay adapter pilot 50 updates của kế hoạch ban đầu. Adapter cuối có SHA-256 `51713be1e630135099f95ed08c89b5be8669b75c9e1908a1346c5c9cc4942ae7`.

## 2. Điều kiện so sánh chung

| Nội dung | Quy định đã khóa |
|---|---|
| Base | Qwen2.5-7B-Instruct gốc, không bật adapter, không nhận retrieval |
| RAG | Cùng base, tắt adapter, nhận contexts truy xuất thật |
| Tuned+RAG | Cùng base, bật adapter đã chọn, nhận đúng messages/context/token IDs của RAG |
| Model | Revision `a09a35458c702b33eeacc393d103063234e8bc28`, NF4 double quant FP16 |
| Benchmark | 300 câu, 100/môn CNXHKH, KTCTMLN, THMLN; 120 factual, 90 explanation, 30 multi-page, 60 insufficient |
| Development | 30 câu ngoài main, dùng kiểm runner và chọn cấu hình/adapter trước main |
| Generation | Greedy, seed42, một beam, tối đa512 output token/4096 input token, timeout90 giây, một T4 |
| Số lượt | 300×3=900 output chính; giữ lỗi/timeout/output_limit trong mẫu số |
| Kiểm nguồn | Đúng document/version/checksum/trang vật lý; kiểm train/validation thực và giao kiến thức đã công bố |
| Đánh giá | Agent theo rubric tự động; đối chiếu nguồn, che arm khi chấm và khóa review trước ghép |

Một review agent đầy đủ trên mỗi ID/hash là đủ cho bước kiểm nội dung benchmark. Agent ghi lý do, nguồn đã đối chiếu, kiểm trùng và kiểm toàn scope cho câu thiếu căn cứ, xử lý findings trước khi khóa. Không chờ A/B duyệt tay. Output main không được dùng để chọn lại adapter/prompt hoặc sửa benchmark nhằm tăng điểm.

Chấm đúng/đủ cho cả ba phương pháp. Faithfulness/citation dùng cùng đơn vị structured item bảo thủ cho hai nhánh RAG; mọi ý quan trọng trong item phải được nguồn hỗ trợ. Base ghi N/A cho chỉ số nguồn/citation. Exact host judge revision/decoding không được nền tảng cung cấp, ghi rõ giới hạn này thay vì gán thông số chưa xác minh.

## 3. W7-01 - Vũ Nam Dương

**Tiêu đề Issue** `W7-01 – Vũ Nam Dương – Chạy so sánh Base LLM, RAG và tuned+RAG`.

| Công việc | Đầu vào | Đầu ra | Trạng thái |
|---|---|---|---|
| Kiểm benchmark và chuẩn hóa dữ liệu | Candidate, source registry, 1.000 instruction, train/val/holdout, findings | Benchmark/reference/review cuối, mapping/hash, kiểm giới hạn leakage | Đã bàn giao |
| Chuẩn bị model và retrieval | Cùng base, dữ liệu chuẩn hóa, PDF đúng checksum | Adapter193/config/checkpoint/log, BGE-M3/FAISS/cache và input ba nhánh đã khóa | Đã bàn giao |
| Runner và chạy GPU | Gói inference frozen, 30 dev và 300 main | Code/test/notebook, smoke/dev/main, raw/timing/runtime/LoRA-state, receipt | Đã bàn giao 900 main output |
| Đánh giá phần A | Output che arm, reference/rubric/contexts | 450 primary +45 secondary, lý do/nguồn, phân tích riêng | Hoàn thành |
| Evidence cuối | Kết quả nhóm Cường gửi lại, code/test/receipt/run cuối | Evidence/W07 theo layout đã thống nhất, số liệu và hash truy ngược cùng run | Dương làm sau cùng |

## 4. W7-02 - Trần Tuấn Cường

**Tiêu đề Issue** `W7-02 – Trần Tuấn Cường – Kiểm độc lập và tổng hợp so sánh Base LLM, RAG, tuned+RAG`.

| Công việc | Đầu vào | Đầu ra | Trạng thái |
|---|---|---|---|
| Tiếp nhận gói | comparison-handoff.zip, receipt và restore-map | Kiểm ZIP và609 file, phục hồi chọn lọc, giữ bản gốc | Hoàn thành |
| Kiểm độc lập | Raw900, freeze/config, adapter, tokenizer, PDF/caches | Kiểm đủ ID/arm/hash/lịch/LoRA,990 tokenized inputs,1.500 context và352 gold-page bindings | Hoàn thành |
| Chấm phần B | blinded-b.jsonl và cùng rubric/item policy | 450 primary +45 secondary, review-lock, lý do/nguồn; agent chấm mù theo batch | Hoàn thành |
| Ghép và phân xử | Review gốc A/B đã khóa | 900 primary +90 secondary; đồng thuận,14 output phân xử, giữ lý do và bản gốc | Hoàn thành |
| Scorer và báo cáo | Raw/review/phân xử/rubric/hash cuối | Metrics theo môn/loại, lỗi, paired CI,4 biểu đồ,báo cáo MD/PDF2 trang và hướng dẫn | Hoàn thành |
| Bàn giao Dương | Kết quả nhóm và kiểm/test | member-b-w7-handoff.zip, receipt, README tiếp nhận | Hoàn thành |

## 5. File và điểm tiếp nhận

| File/module | Vai trò |
|---|---|
| `scripts/comparison/runner.py`, `main_entry.py`, `intake_main.py` | Chạy và xác thực output ba nhánh |
| `scripts/comparison/benchmark.py`, `prepare_data.py`, `retrieval.py`, `packing.py`, `freeze.py` | Chuẩn bị và khóa dữ liệu/cache |
| `scripts/comparison/main_scoring.py` | Review và phân tích phần A, parser/assignment/metrics dùng chung |
| `scripts/comparison/group_scoring.py` | Khóa review B, kiểm binding, phân xử và tổng hợp nhóm |
| `scripts/comparison/group_report.py` | Báo cáo và biểu đồ từ số liệu nhóm |
| `data/comparison/` | Prompt và schema input/output |
| `notebooks/comparison.ipynb`, `comparison_training.ipynb`, `comparison_main.ipynb` | Các bước dev, training, main trên Kaggle |
| `docs/comparison.md` | Phương pháp, lịch sử, kết quả nhóm và lệnh tái lập |

Dữ liệu riêng được giữ theo skeleton `.private/comparison/`: benchmark-v3/training-v2/retrieval-v2/frozen-experiment trong `prepared/`, main gốc trong `runs/main-intake/`, review A ở `assessment/main/`, review B ở `assessment/member-b-v1/`, phân xử ở `assessment/adjudication-v1/`, kết quả cuối ở `assessment/group-v2/`.

Gói gửi Dương tại `.private/comparison/handoff/cuong-v1/` có ZIP, receipt và README. File `restore-map.json` trong ZIP ghi vị trí tiếp nhận. Code/docs dùng chung cần so diff khi tích hợp. Các artifact gốc và gói đã đóng được giữ riêng; những thay đổi tiếp theo xuất revision mới.

## 6. Kết quả nhóm và tiêu chí hoàn thành

Có 900 output thực, gồm897 completed và3 output_limit. Kết quả rubric trên300 câu mỗi phương pháp: Base335/600 (55,83%), RAG454/600 (75,67%), tuned+RAG457/600 (76,17%). Tuned-RAG chênh0,50 điểm phần trăm, CI95%[-3,17;4,33]; chưa đủ cơ sở khẳng định tuning cải thiện correctness chắc chắn. Chi tiết nguồn/citation/latency, mẫu số, giới hạn judge và phạm vi benchmark ở báo cáo nhóm.

- [x] Cùng benchmark, base revision, quantization/decoding; RAG/tuned dùng cùng contexts/messages/token IDs.
- [x] Có900 output và ghi đầy đủ lỗi, cấu hình và artifact tái lập.
- [x] Đủ900 primary +90 secondary, giữ review gốc và phân xử thực bằng agent.
- [x] Có metrics, paired CI, bảng theo môn/loại, lỗi, biểu đồ và báo cáo nhóm.
- [x] Có kiểm/test, gói tải được, checksum và kiểm lại sau giải nén.
- [ ] Dương hoàn thiện Evidence/W07 cuối cùng và quy trình PR/review của nhóm.

Evidence/W07 cuối gồm README.md, metrics.csv, test-results.txt, manifest.json và figures/. Chỉ đưa kết quả tổng hợp/bằng chứng phù hợp lên Git; dữ liệu, gold, raw, review chi tiết, weights và ZIP được bàn giao riêng. Không suy điểm nhóm từ điểm nửa tập của A, không yêu cầu tuned thắng mới đạt mốc so sánh. PR/commit/milestone dùng số thực do GitHub cấp.
