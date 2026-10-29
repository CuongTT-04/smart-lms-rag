# Kế hoạch phân công W5 chuẩn bị instruction dataset cho QLoRA

Ngày lập: 27/10/2026. Tuần thực hiện: 25–31/10/2026. Nhóm E2.

| Vai trò | Thành viên | Trách nhiệm chính |
|---|---|---|
| SV A | Vũ Nam Dương — B22DCVT119 | Quy trình tạo mẫu, 250 mẫu hợp lệ, xuất dữ liệu SFT và dataset card |
| SV B | Trần Tuấn Cường — B22DCVT073 | Hợp đồng dữ liệu, 250 mẫu hợp lệ, kiểm định chất lượng, chia tập và evidence |

**Mục tiêu:** có một bộ instruction pilot đã kiểm tra, tách tập và quản lý phiên bản để bàn giao sang giai đoạn huấn luyện QLoRA. Cả hai thành viên đều làm dữ liệu, code, review và báo cáo; không chia theo kiểu một người chỉ code, người kia chỉ viết báo cáo.

**Cập nhật 28/10:** A đồng ý đầu vào theo xác nhận của Cường; đã triển khai công cụ B2/B4/B5, sửa pilot và chuẩn bị 250 draft B theo yêu cầu tiếp tục. Chưa có human peer review hoặc 250 mẫu ACCEPT. Xem [tiến độ thực tế](quality-report.md). Các phát biểu draft dưới đây là trạng thái lúc lập kế hoạch, không thay trạng thái mới.

**Trạng thái khi lập kế hoạch:** đây là kế hoạch và đặc tả đầu ra, chưa phải kết quả đã hoàn thành. Phần B1 đã có [gói đầu vào draft gửi A review](chot-dau-vao-w5.md), gồm schema/policy/manifest/phân nguồn và fixture minh họa; chưa được A duyệt hoặc khóa. Các script pipeline, dữ liệu thật và kết quả nghiệm thu còn là đầu ra cần thực hiện. Chưa tạo Issue, Milestone, PR hoặc tag trên GitHub bằng việc viết các tài liệu này.

## 1 Căn cứ và phạm vi tuần

### 1.1 Phân biệt yêu cầu và đề xuất

| Căn cứ | Nội dung | Cách áp dụng |
|---|---|---|
| Yêu cầu W5 người dùng chốt ngày 27/10 | Chuẩn bị instruction dataset cho QLoRA; kiểm tra chất lượng mẫu | Là phạm vi của bản phân công này |
| Ảnh hướng dẫn Git từ W4 | Một milestone tuần; Issue riêng từng sinh viên và kết quả; PR được thành viên khác review; tag/commit cuối tuần | Dùng milestone `Tuan5`, hai Issue chính và tag `w05` |
| `D:/ĐATN_Đề cương chi tiết.docx`, mục 11 | W5: hybrid/rerank, bảng so sánh retrieval, 200 QA frozen dev. W6: build QLoRA dataset và training dry-run, 1k–5k instruction samples | Có lệch lịch với yêu cầu hiện tại. Bản này đưa phần chuẩn bị dataset lên W5 theo yêu cầu mới, không coi hybrid/rerank đã hoàn tất hoặc đã bị loại khỏi đồ án |
| Đề cương mục 8, 10, 12 và SRS | Tách fine-tune/evaluation; nguồn có quyền; dữ liệu có phiên bản; review chéo; evidence tái lập được | Áp dụng cho toàn bộ task |

SV B ghi thay đổi lịch và ảnh hưởng sang W6 trong decision log W5; SV A review. Nhóm cần đối chiếu việc điều chỉnh với lịch được giảng viên chấp nhận. Tài liệu này không tự xác nhận giảng viên đã duyệt đổi lịch.

**Đề xuất quy mô W5:** 500 mẫu sau lọc và review, mỗi người chịu trách nhiệm 250 mẫu. Đây là mốc pilot do kế hoạch đề xuất, không phải con số bắt buộc được trích từ yêu cầu W5. Mục tiêu 1k–5k của dòng W6 trong đề cương vẫn cần xử lý ở kế hoạch W6; không dùng 500 mẫu để tuyên bố đã đạt mục tiêu đó. Nếu giảng viên yêu cầu đủ 1.000 mẫu ngay W5, giữ nguyên hợp đồng/quy trình và tăng phần mỗi người lên 500 trước khi khóa M0.

### 1.2 Đầu vào đã đối chiếu

Mốc đối chiếu đã cập nhật theo `origin/main`: commit `5c5bdef200fc839cfa1e5aa3d3fa609c7f5d20ba` (`5c5bdef`, merge PR #6 của Dương). Đã đọc trực tiếp nội dung tại commit này sau khi fetch ngày 27/10/2026, không chỉ đổi tên hash trong báo cáo.

Tại commit `5c5bdef`, repo có 27 PDF thuộc THMLN, KTCTMLN và CNXHKH; `data/qa/qa_baseline.json` có 100 câu và `qa_additions.json` có 50 câu, tổng 150 ID khác nhau. `Evidence/W04/README.md` xác định đây là tập development trước QLoRA, không phải held-out test độc lập; cũng không phải 150 instruction được tự động duyệt để train.

Commit mới bổ sung `Evidence/W04/{README.md,manifest.json,metrics.csv,test-results.txt,figures/}` và dọn các bản dữ liệu W3 cũ. Các file QA canonical, source map, SRS và contract/prompt/parser được tham chiếu trong kế hoạch không đổi so với lần rà soát trước. Vì vậy, phân công kỹ thuật vẫn giữ, nhưng evidence W5 phải theo cấu trúc `Evidence/W05` của main hiện hành. Khi bắt đầu thực thi, hai người đồng bộ về cùng base `5c5bdef` hoặc commit main mới hơn đã cùng kiểm tra và ghi lại ở M0.

Các điểm nối kỹ thuật cần tái sử dụng:

- `backend/apps/ai/rag/context_builder.py`: `build_messages` tạo system/user prompt và nhãn evidence.
- `backend/apps/ai/rag/base.py`: `EvidenceContext`, `ExerciseContext`, `GenerationConfig`.
- `backend/apps/ai/rag/citations.py`: `parse_answer`, quy tắc citation và sentinel.
- `backend/apps/ai/rag/guardrails.py`: `parse_reading_hint`.
- `backend/apps/ai/providers/base.py`: base model Qwen2.5-7B-Instruct, revision `a09a35458c702b33eeacc393d103063234e8bc28`.

Quyền dùng dữ liệu cần rà soát lại: dataset card hiện chỉ ghi nguồn chia sẻ không chính thức và cam kết nghiên cứu phi thương mại, chưa đủ để tự khẳng định quyền công bố lại toàn văn hoặc dataset huấn luyện. Những nguồn chưa rõ phải ghi trạng thái chưa xác minh; không tự đánh dấu đã được cấp quyền.

Nếu chưa có đủ nguồn xác minh được cho mục đích dự kiến, B đề xuất nguồn mở/có giấy phép phù hợp hoặc xin xác nhận quyền; A review thay đổi source manifest và phần ảnh hưởng đến benchmark. Có thể tiếp tục viết tool bằng fixture tự biên soạn, nhưng không lấy fixture hay nguồn chưa rõ quyền để ghi bộ 500 mẫu thật đã đạt.

### 1.3 Ngoài phạm vi nghiệm thu W5 này

- Chưa yêu cầu huấn luyện QLoRA hoàn chỉnh, tạo adapter tốt hơn baseline hoặc thay model phục vụ chatbot.
- Không thay UI chat, memory, PostgreSQL nghiệp vụ, cấu hình GPU online hay logic phân quyền.
- Không ghi đè prompt/baseline W3–W4 để làm đẹp số liệu.
- Kiểm tra tokenizer, format và nhãn loss là đầu ra W5; không gọi đó là training dry-run đã chạy optimizer. Training dry-run theo lịch đề cương được xử lý riêng ở W6.
- Bộ holdout của instruction pilot không thay thế benchmark QA độc lập theo SRS, cũng không hoàn tất RAGAS/factuality cuối đồ án.

## 2 Kết quả chung và tiêu chí chốt tuần

| Mã | Đầu ra chung | Điều kiện nghiệm thu |
|---|---|---|
| O1 | Hợp đồng instruction v1 | Schema, quyền nguồn, quy tắc citation, split, rubric, model/tokenizer/prompt được A và B chốt ở M0 |
| O2 | 500 instruction pilot | 250 của A, 250 của B; ID duy nhất; tất cả vượt kiểm tra cấu trúc và có review nội dung của người còn lại |
| O3 | Ba tập phục vụ nghiên cứu | Train/validation/instruction holdout theo nhóm nguồn, xấp xỉ 80/10/10; không giao ID, họ biến thể hoặc nhóm nguồn qua các tập |
| O4 | Gói xuất cho SFT | JSONL prompt/completion, metadata truy vết, manifest/checksum; tokenizer và mask kiểm tra được trên CPU |
| O5 | Báo cáo chất lượng | Số mẫu đầu vào/loại/sửa/chấp nhận, lý do, phân bố môn/task/token, kiểm tra leakage, kết quả review và giới hạn |
| O6 | Weekly Evidence Package | Báo cáo 1–2 trang PDF hoặc DOCX, link hai Issue/PR/commit, card/manifest, kết quả JSON/CSV, video/demo ngắn và tag `w05` |

Mẫu bị reject không được tính vào O2. Không đủ số lượng thì ghi đúng số thực đạt và phần chưa hoàn thành, không nhân bản câu hỏi hoặc sửa báo cáo để đủ 500.

### 2.1 Phân bố mục tiêu

| Loại mẫu | Tổng bộ pilot | Mỗi thành viên | Đầu ra model cần học |
|---|---:|---:|---|
| Hỏi đáp có căn cứ | 300 | 150 | Câu trả lời tiếng Việt, citation đúng đoạn hỗ trợ |
| Tóm tắt một phạm vi có nguồn | 100 | 50 | Tóm tắt ngắn, không thêm kiến thức ngoài; citation hợp lệ |
| Gợi ý ôn tập | 50 | 25 | Mã thao tác đọc đúng contract hint hiện có, không đáp án cuối |
| Thiếu căn cứ | 50 | 25 | Đúng sentinel `INSUFFICIENT_EVIDENCE`, không đáp án/citation đi kèm |
| Tổng | 500 | 250 | Mẫu khác nhau có chất lượng, không chỉ đổi vài từ |

Phân bố môn mục tiêu toàn bộ: THMLN 200, KTCTMLN 150, CNXHKH 150; mỗi người tương ứng 100/75/75. Không ép chính xác phân bố từng split bằng cách phá nhóm chống leakage. Mọi thay đổi quota phải ghi trước khi khóa release, kèm số thực tế.

SV B phân chia các section/page group cho A và B trong `source_allocation.csv` tại M0. Hai người không cùng sinh mẫu cho một nhóm nguồn được giao, trừ phần bổ sung được ghi rõ. Các nhóm nguồn khác nhau nhưng trùng ý vẫn phải qua kiểm tra near-duplicate.

## 3 Hợp đồng dữ liệu dùng chung

SV B là người ghi file hợp đồng; SV A xác nhận khả năng xuất và dùng được với pipeline. Sau M0, không đổi tên field/enum/format trong nhánh cá nhân; mọi thay đổi hợp đồng phải qua PR nhỏ được cả hai thống nhất.

### 3.1 Bản ghi gốc để biên soạn và kiểm tra

| Field | Quy tắc bắt buộc |
|---|---|
| `schema_version` | `w5-instruction-v1` |
| `record_id` | A dùng `W5_A_00001`…; B dùng `W5_B_00001`…; không dùng lại ID QA benchmark |
| `author_member`, `course_code`, `language` | `A` hoặc `B`; môn trong danh mục khóa; ngôn ngữ `vi` |
| `task_type` | `qa`, `summary`, `hint`, `insufficient_evidence` |
| `mode` | `hint` cho task hint; `qa` cho ba task còn lại. Không thêm mode API summary/refusal mới |
| `question`, `contexts`, `exercise` | Câu hỏi và evidence thực sự đưa vào prompt; exercise chỉ có đề/lựa chọn công khai hoặc null |
| `contexts[]` | Các field của EvidenceContext hiện có; thêm checksum PDF/text và liên kết quyền nguồn trong metadata, không truyền field phụ tùy ý vào dataclass |
| `target_text` | Đầu ra thô model cần sinh, theo mục 3.2; không phải JSON response API |
| `source_group_ids`, `variant_family_id`, `parent_record_id` | Nhóm nguồn và họ biến thể để chống chia trùng train/validation/holdout; parent có thể null |
| `provenance` | Người biên soạn, manual/synthetic, model/prompt/recipe hỗ trợ nếu có, thời gian; không nhận output LLM như đã được người duyệt |
| `prompt_version`, `source_identity_scope` | Pilot mặc định `bounded_guidance`; nguồn `offline_corpus`, không giả định UUID offline đã có quyền trong DB LMS |
| `content_sha256` | Hash nội dung chuẩn hóa gồm question/contexts/exercise/target và provenance cần khóa; loại chính field hash và trạng thái review ra khỏi phép băm |

Review để ở CSV riêng: `record_id`, `content_sha256`, `reviewer_member`, `reviewed_at`, các điểm rubric, `decision`, `reason`, `re_review_of`. Review chỉ hợp lệ khi hash khớp bản ghi đang xuất; tác giả sửa nội dung thì phải review lại.

### 3.2 Format khớp code hiện tại

1. QA và summary: `target_text` là tiếng Việt kèm `[1]`, `[2]` trỏ đến evidence sau lựa chọn/budgeting. Không học theo JSON `{status, answer, citations}`, nhãn `[S1]` hoặc metadata nguồn tự sinh. Với câu trắc nghiệm, tuân thủ kiểm tra phương án trong parser hiện có.
2. Hint với `bounded_guidance`: chỉ một dòng `READ [n]`, `OUTLINE [n]` hoặc `COMPARE [n] [m]`; COMPARE cần hai nhãn khác nhau có trong prompt. Không dùng câu gợi ý tự nhiên ở UI làm target, vì UI/pipeline hiện render câu đó từ mã thao tác.
3. Thiếu căn cứ: chỉ `INSUFFICIENT_EVIDENCE`. Mỗi mẫu phải có lý do nội dung không đủ căn cứ trong review; không gắn sentinel cho trường hợp nguồn thực sự bác bỏ một nhận định và có thể trả lời đúng/sai.
4. Citation tồn tại về mặt ID chưa đủ: người review phải kiểm nguồn thực sự hỗ trợ từng ý. Trích dẫn đúng trang nhưng sai nội dung là lỗi nghiêm trọng.
5. Không đưa `ground_truth`, đáp án đúng, expected_points, rubric hay thông tin xử lý nội bộ vào system/user prompt. `target_text` là nhãn huấn luyện ở completion, được tách rõ khỏi input.
6. Không lấy nguyên các case sai quyền/HTTP 403 của backend làm target trả lời của LLM. Những ca đó vẫn thuộc kiểm thử policy của ứng dụng.

Nếu nhóm muốn fine-tune hint tự nhiên thay vì mã thao tác, phải đổi contract/parser/prompt có chủ đích và tách phiên bản thí nghiệm; không tự trộn hai dạng trong release W5 này.

### 3.3 Gói SFT và ngân sách token

Chọn conversational prompt-completion: mỗi dòng train/validation/holdout có `prompt` gồm system + user và `completion` gồm một assistant message. Nội dung prompt được tạo từ hợp đồng hiện có bằng `build_messages`; metadata/review nằm trong sidecar, không nằm trong lời đáp cần học.

Base model/tokenizer: `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`. Bản chuẩn bị W5 dùng tokenizer theo Transformers 4.57.6 của môi trường hiện tại; ghi hash chat template, phiên bản thư viện và prompt source commit vào manifest. Không tự nâng thư viện của notebook inference đang dùng.

**Ngân sách pilot đề xuất:** sequence tối đa 4096 token; prompt tối đa 3072, completion tối đa 768, kiểm lại cả chuỗi sau chat template và EOS. Đây là cấu hình chuẩn bị training riêng để thử tài nguyên ở W6, không sửa profile online 6144/3584/1024. Mẫu quá dài được sửa/chọn lại evidence rồi review lại; không cắt mất target hoặc đoạn được citation một cách âm thầm.

Kiểm tra loss theo completion: prompt/padding có label `-100`, có token target được học và EOS đúng tokenizer. Không mặc nhiên bật `assistant_only_loss` nếu chat template chưa hỗ trợ assistant mask; kiểm đường prompt-completion và `completion_only_loss` theo phiên bản trainer được khóa khi vào W6.

W5 chỉ cần tokenizer và batch fixture trên CPU, không cần nạp model 7B hoặc chạy optimizer. Không gọi hàm đếm token có tác dụng nạp cả model chỉ để kiểm format.

## 4 Phân công công việc cho từng thành viên

### 4.1 SV A Vũ Nam Dương

| Task | Công việc cụ thể | Đầu ra do A sở hữu | Tiêu chí hoàn tất |
|---|---|---|---|
| A1 | Review hợp đồng B; tạo pilot 10 mẫu đa dạng; xác nhận prompt/completion và target hint | Pilot trong `.private/w5/candidates/member_a.jsonl`; phản hồi hợp đồng trong PR | 10 mẫu gồm đủ bốn task; không dùng câu benchmark; B duyệt trước khi sinh hàng loạt |
| A2 | Viết recipe/script tạo ứng viên từ section được giao; cho phép biên soạn thủ công và LLM hỗ trợ; lưu provenance; hoàn thiện 250 mẫu | `scripts/w5/generate_candidates.py`; `.private/w5/candidates/member_a.jsonl`; `scripts/w5/tests/test_generation_recipe.py` | Tạo/restart batch theo ID, không ghi đè mẫu đã review; 250 mẫu cuối được B duyệt; 150/50/25/25 theo task |
| A3 | Review 250 mẫu của B theo rubric; ghi lỗi cụ thể, kiểm PDF và hint/refusal; gửi lại để B sửa | `data/instruction/w5/reviews/member_a_reviews_b.csv` | Reviewer A, hash đúng, decision rõ; không tự sửa file candidate của B; mẫu sửa được review lại |
| A4 | Viết exporter lấy mẫu đã duyệt, áp split plan của B, tạo prompt/completion, sidecar và manifest | `scripts/w5/export_sft_dataset.py`; `scripts/w5/tests/test_export_sft_dataset.py`; `.private/w5/releases/v0.1/`; `data/instruction/w5/release-manifest.json` | Không xuất mẫu thiếu review/hết hiệu lực; không đọc nhãn benchmark để dựng target; hash/count khớp; chạy lại cùng input/seed cho cùng artifact nội dung |
| A5 | Viết instruction dataset card và bàn giao gói dữ liệu riêng tư có checksum cho B; cung cấp demo/phần báo cáo về tạo mẫu và SFT export | `docs/weekly/W5/instruction-dataset-card.md`; link gói riêng tư trong manifest | Có nguồn/quyền, phân bố, schema, split, provenance, hạn chế; B tải được artifact thật và đối chiếu checksum |

Test tối thiểu A: chạy lại không tạo ID trùng; recipe không nhận QA benchmark làm seed; exporter từ chối mẫu chưa duyệt/hash đổi; hint giữ đúng mã thao tác; metadata không lọt vào assistant completion; seed/split plan không tự đổi.

### 4.2 SV B Trần Tuấn Cường

| Task | Công việc cụ thể | Đầu ra do B sở hữu | Tiêu chí hoàn tất |
|---|---|---|---|
| B1 | Khóa schema, quota, rubric, ngân sách token, nguồn có quyền, danh sách benchmark phải loại và phân section cho hai người | `data/instruction/w5/contract/schema.json`, `quality-policy.json`, `split-policy.json`, `source-manifest.json`, `benchmark-exclusion-manifest.json`, `source_allocation.csv`; `docs/weekly/W5/scope-decision.md` | A review; đủ dữ liệu để A làm pilot không cần đoán field; trạng thái quyền nguồn và lệch lịch được ghi thật |
| B2 | Viết validator/check source/citation; lọc trùng exact và gắn cờ near-duplicate; kiểm chống benchmark leakage | `scripts/w5/validate_instruction_dataset.py`; `scripts/w5/tests/test_quality_validation.py` | Fixture tốt qua; fixture xấu thất bại đúng lý do; không gọi model để tự xác nhận human review |
| B3 | Tạo pilot 10 mẫu rồi hoàn thiện 250 mẫu thuộc section B | `.private/w5/candidates/member_b.jsonl` | Được A review; cùng quota task với A; biên soạn có provenance, không sửa candidate A |
| B4 | Review 250 mẫu A, lưu rubric và yêu cầu sửa; xây split plan theo nhóm đã khử trùng | `data/instruction/w5/reviews/member_b_reviews_a.csv`; `scripts/w5/create_split_plan.py`; `data/instruction/w5/split-plan.json`; `scripts/w5/tests/test_split_plan.py` | Tất cả mẫu A có human review; không có cùng họ/nhóm nguồn ở nhiều tập; split seed 42 và danh sách ID được khóa |
| B5 | Viết kiểm tra tokenizer/chat template/mask trên gói A xuất; audit release; tổng hợp quality và evidence | `scripts/w5/check_training_format.py`; `scripts/w5/tests/test_training_format.py`; `data/instruction/w5/quality/{quality-report.json,tokenization-report.json,findings.csv}`; `docs/weekly/W5/quality-report.md`; `Evidence/W05/{README.md,manifest.json,metrics.csv,test-results.txt}`; bản nộp 1–2 trang và demo | Kiểm trên artifact hash cố định; có counts/reject/review/token/split; test CPU đạt; báo cáo không ghi training hoặc factuality đã đạt nếu chưa chạy |

Test tối thiểu B: sai checksum/trang/ID citation; mất nguồn sau budgeting; prompt chứa nhãn nội bộ; ID/near-duplicate qua split; benchmark paraphrase bị gắn cờ; hint lộ đáp án/sai format; sentinel trộn đáp án; mẫu dài/EOS sai/không có target token; review sai hash/người review là tác giả.

## 5 Phân quyền ghi file để tránh xung đột

Các đường dẫn tính từ thư mục gốc repo. `.private/` là artifact riêng tư đã bị Git bỏ qua; dữ liệu nội dung không tự lên Git theo kế hoạch này.

| Phạm vi | Người ghi duy nhất | Người còn lại làm gì |
|---|---|---|
| Contract, allocation, exclusion manifest, split policy/plan | B | A review PR, không tự sửa ở nhánh A |
| Candidate `member_a.jsonl` | A | B đọc và ghi findings trong review của B |
| Candidate `member_b.jsonl` | B | A đọc và ghi findings trong review của A |
| `member_a_reviews_b.csv` | A | B sửa candidate của mình, không sửa điểm/decision của A |
| `member_b_reviews_a.csv` | B | A sửa candidate của mình, không sửa điểm/decision của B |
| Generator, exporter, test tương ứng; release payload và release manifest; instruction card | A | B review và kiểm artifact |
| Validator, split builder, tokenizer checker và test tương ứng; quality artifacts/report và evidence | B | A review và đối chiếu số liệu |

Chưa cần sửa file dùng chung W3/W4, runtime AI hoặc dữ liệu 150 QA. Nếu phát hiện bắt buộc sửa, tạo PR nhỏ riêng gắn Issue, thống nhất người ghi trước; không lẫn thay đổi đó với hàng trăm dòng dataset.

CSV/JSON dùng UTF-8, JSONL một record/dòng, stable ID và thứ tự xuất theo `record_id`. Không dùng Excel tự đổi ID/mã hóa. Không cùng append vào một CSV hoặc dùng một file JSONL chung khi hai nhánh chưa hợp nhất.

### 5.1 Chống vòng chờ giữa hai người

1. B giao schema + fixture + danh sách section ngay M0. A dùng fixture để viết exporter/generator, không chờ B có đủ 250 mẫu.
2. A và B tạo nội dung ở file riêng song song. Validator B chạy trên fixture trước, rồi chạy trên dữ liệu thật của cả hai.
3. Peer review được chuyển giao theo batch 25–50 mẫu với hash, không đợi đủ 500 mới review.
4. A chỉ xuất release sau khi B bàn giao split plan và review A; A đồng thời hoàn tất review B.
5. B audit gói release sau cùng. Nếu lỗi, trả findings theo ID cho đúng tác giả; A tái xuất, B kiểm lại đúng hash mới rồi mới tag.

## 6 Kiểm tra chất lượng mẫu

### 6.1 Kiểm tra tự động trên toàn bộ tập

- Schema/type/enum, ID duy nhất, field bắt buộc và Unicode hợp lệ.
- Checksum PDF, trang vật lý bắt đầu từ 1, text/anchor/section thực; source không bị sửa sau review.
- Prompt không có ground_truth/đáp án/rubric; exercise chỉ whitelist field công khai.
- QA/summary qua parser citation; hint qua parser thao tác; refusal đúng sentinel. Đây là kiểm hình thức, không tự chứng minh đúng ngữ nghĩa.
- Exact duplicate sau chuẩn hóa; near-duplicate câu hỏi và cặp question/target. Đề xuất dùng character 5-gram Jaccard từ 0,85 để gắn cờ; người review quyết định, không tự xóa các câu chỉ vì cùng thuật ngữ phổ biến.
- Trùng với 150 QA hiện có và các benchmark/guardrail khác được chốt ở exclusion manifest; gắn cờ cả bản diễn đạt lại. Không dùng model để paraphrase benchmark rồi đưa vào train.
- Token count của prompt/completion/full sequence, chat template, EOS, loss mask và nonempty target.
- Không có dữ liệu tài khoản, token, hội thoại hoặc bài nộp học viên thật; quyền nguồn có trạng thái được nhóm xác minh cho mục đích sử dụng dự kiến.

### 6.2 Human review trên toàn bộ 500 mẫu phát hành

Mỗi mẫu được người còn lại kiểm đối chiếu nguồn. Chấm 0/1/2 cho năm tiêu chí: (1) instruction rõ và hữu ích; (2) đúng nội dung; (3) evidence hỗ trợ/citation chính xác; (4) đúng hành vi task, nhất là hint và thiếu căn cứ; (5) tiếng Việt/format sạch.

**Ngưỡng đề xuất phải khóa ở M0:** ít nhất 9/10, không tiêu chí nào 0; các mục nội dung, evidence và hành vi task phải đạt 2. Mẫu có bịa nguồn, sai kiến thức trọng yếu, lộ đáp án hint, benchmark leakage, thông tin riêng tư hoặc quyền nguồn chưa được xác minh không được chấp nhận dù tổng điểm cao.

Decision gồm `ACCEPT`, `REVISE`, `REJECT`; mỗi REVISE/REJECT có lý do. Không gán human approval từ LLM judge, regex, source checksum hoặc nhãn tác giả tự đánh giá. AI có thể giúp phát hiện lỗi, nhưng người review phải đọc và ký xác nhận phần mình chịu trách nhiệm.

Hai người cùng chấm thử 20 pilot để hiệu chỉnh rubric ở M1. Nếu bất đồng, sửa giải thích tiêu chí rồi chấm lại; bất đồng chưa giải quyết thì giữ mẫu ngoài release, không trung bình điểm để tự cho qua.

### 6.3 Chia tập và chống leakage

- Khóa benchmark 150 QA cùng hash đầu vào ngay M0; thêm bộ đánh giá mới trước khi sử dụng chúng. Không sửa benchmark để làm cho checker hết báo trùng.
- Có thể cùng dùng corpus môn học làm căn cứ RAG, nhưng không dùng câu hỏi, nhãn/đáp án hoặc biến thể benchmark để fine-tune hay sinh instruction. Trùng thuật ngữ/kiến thức phổ thông được ghi nhận và xét thủ công, không mặc nhiên là bằng chứng rò rỉ.
- Nhóm nguồn mặc định theo `course_code + document identity` gồm mọi version của tài liệu đó. Cùng nhóm nguồn, bản gần trùng hoặc họ paraphrase phải ở một split. Mẫu nhiều nguồn nối các nhóm liên quan thành một component.
- Nhắm 80/10/10 trên các component, seed 42, với đại diện task/môn khi khả thi. Báo counts thực; không buộc đúng 400/50/50 bằng cách xé nhóm. Nếu component quá lớn làm split không hợp lý, thay cách chọn nguồn/mẫu trước khi freeze và ghi quyết định.
- Cả ba split phải có mẫu; báo số component và phân bố task/môn của từng split. Không chấp nhận một bộ chỉ có train hoặc một holdout rỗng dù tổng số mẫu đủ 500.
- Validation được dùng chọn cấu hình huấn luyện ở tuần sau; instruction holdout khóa và không dùng chỉnh prompt, threshold hoặc chọn epoch. Không dùng mọi phần của JSONL release làm train.
- Instruction holdout là đánh giá nội bộ dataset; benchmark test độc lập tối thiểu theo SRS cần kế hoạch riêng. Không gọi 50 instruction holdout là đã đạt 200 QA test độc lập của SRS.

## 7 Milestone và lịch bàn giao

Milestone GitHub duy nhất cho tuần: **`Tuan5`**, thời hạn 31/10/2026 theo giờ Việt Nam. Các mốc M0–M4 dưới đây là checkpoint nội bộ, không phải năm milestone GitHub khác nhau. Lịch thực thi dưới đây bắt đầu từ ngày lập kế hoạch; không ghi ngược rằng công việc đã hoàn thành ngày 25–26/10.

| Mốc | Hạn đề xuất | A bàn giao | B bàn giao | Điều kiện đi tiếp |
|---|---|---|---|---|
| M0 Khóa hợp đồng | 27/10 | Review schema, chốt target/prompt và khả năng export | Contract, source allocation/quyền, exclusion manifest, scope decision | Cả hai đồng ý; có fixture để làm song song |
| M1 Pilot | 28/10 | 10 mẫu, generator/exporter skeleton và test fixture | 10 mẫu, validator/split/tokenization fixture | Chấm thử 20 mẫu; hiểu thống nhất rubric; không sinh hàng loạt trên format sai |
| M2 Đủ ứng viên | 29/10 | Batch nội dung hướng tới 250 mẫu cuối, test exporter | Batch nội dung hướng tới 250 mẫu cuối, báo lỗi tự động | Toàn bộ ứng viên có nguồn/provenance; review chuyển theo batch đã bắt đầu |
| M3 Hoàn tất peer review | 30/10 | Review B, sửa mẫu A, card nháp | Review A, sửa mẫu B, split plan và audit nháp | Có 500 mẫu được duyệt đúng hash hoặc ghi rõ thiếu hụt; không còn lỗi nghiêm trọng trong tập được chọn |
| M4 Khóa và nộp | 31/10 | Gói SFT v0.1, manifest, card và demo xuất dữ liệu | Audit cuối, báo cáo/evidence 1–2 trang và kết quả JSON/CSV | Checksum khớp; PR review chéo; hai Issue đóng theo kết quả thật; tag `w05` đúng commit tích hợp |

Nguồn có vấn đề quyền hoặc không đủ mẫu đạt chất lượng là blocker nội dung phải báo ngay M1/M2. Không chờ ngày cuối mới thông báo thiếu đầu vào.

## 8 Issue và PR đúng cấu trúc hướng dẫn

### 8.1 Hai Issue chính với tiêu đề dùng nguyên văn

**Issue A**

```text
Vũ Nam Dương B22DCVT119 – Instruction dataset QLoRA W5 và bộ xuất SFT
```

Assignee: Vũ Nam Dương. Milestone: `Tuan5`. Reviewer các PR: Trần Tuấn Cường.

Nội dung checklist Issue A:

- [ ] A1: 10 pilot đúng contract được B duyệt.
- [ ] A2: generator/recipe và test; 250 mẫu A đủ quota, không trùng benchmark, được B review.
- [ ] A3: CSV review 250 mẫu B, đúng hash/người/ngày/lý do.
- [ ] A4: exporter và test; train/validation/instruction holdout + metadata + release manifest.
- [ ] A5: dataset card, artifact riêng tư tải được và checksum khớp; demo phần việc A.
- [ ] PR được B review; Evidence có link commit, số mẫu thực đạt và phần chưa đạt.

**Issue B**

```text
Trần Tuấn Cường B22DCVT073 – Bộ kiểm định chất lượng instruction dataset QLoRA W5
```

Assignee: Trần Tuấn Cường. Milestone: `Tuan5`. Reviewer các PR: Vũ Nam Dương.

Nội dung checklist Issue B:

- [ ] B1: contract/schema, quyền nguồn, allocation, exclusion manifest và scope decision được A review.
- [ ] B2: validator và test cho source/citation/duplicate/leakage.
- [ ] B3: 250 mẫu B đủ quota được A review.
- [ ] B4: CSV review 250 mẫu A; split plan/code/test và seed khóa.
- [ ] B5: tokenizer/mask checker, test CPU, quality artifacts và báo cáo; Weekly Evidence Package.
- [ ] Audit artifact cuối khớp manifest; PR được A review; Evidence ghi kết quả thật.

GitHub tự cấp số Issue. Không tự đặt `#xx` trong title, không bịa số Issue/PR. Sau khi tạo, gắn số thật vào commit message và PR; PR trung gian dùng `Refs`, chỉ PR hoàn tất phần việc mới dùng `Closes` để tránh đóng Issue sớm.

### 8.2 Trình tự PR không gây vòng phụ thuộc

Mỗi Issue có thể có nhiều PR; ảnh hướng dẫn minh họa PR theo sinh viên, không bắt buộc chỉ một PR cho cả tuần.

| PR đề xuất | Tác giả | Reviewer | Nội dung và phụ thuộc |
|---|---|---|---|
| W5 B1 Khóa hợp đồng dữ liệu và bộ kiểm tra fixture | B | A | Merge sớm contract/tools/fixtures để A không chờ; chưa đóng Issue B |
| W5 A1 Tạo ứng viên instruction và công cụ xuất SFT | A | B | Generator, candidate A ở artifact riêng tư và exporter/tests; review nội dung bắt đầu; chưa đóng Issue A |
| W5 B2 Hoàn thiện mẫu B và review mẫu A | B | A | Candidate B, CSV review A, split plan/tool; dựa trên batch A đã bàn giao; chưa đóng Issue B |
| W5 A2 Phát hành instruction pilot và dataset card | A | B | CSV review B, export gói đủ review, release manifest/card; chốt phần việc A sau audit cần thiết |
| W5 B3 Kiểm định release và Weekly Evidence Package | B | A | Audit đúng release hash, quality report, evidence; chốt phần việc B sau đối chiếu cuối |

Candidate/private artifacts trong bảng được chia sẻ bằng link và checksum, không có nghĩa commit nguyên JSONL riêng tư vào PR. Nếu audit cuối phát hiện lỗi, mở lại checklist liên quan và A tái xuất trước khi tag.

Nhánh đề xuất: `codex/w5-duong-instruction-data` và `codex/w5-cuong-dataset-quality`; tạo từ cùng base được khóa ở M0, đồng bộ main sau PR contract. Đây là tên đề xuất; không tự tạo nhánh hoặc thay checkout bằng bản kế hoạch.

### 8.3 Cấu trúc evidence cuối tuần

```text
Milestone Tuan5
├── Issue của SV A → dataset pilot, exporter, card, review B
├── Issue của SV B → contract, validator, split, audit, review A
├── PR do A mở → B review
├── PR do B mở → A review
└── Tag cuối tuần w05 → commit đã tích hợp và kiểm chứng
```

Tag `w05` suy ra từ mẫu `w04` trong ảnh. Chỉ tạo sau kiểm chứng; không di chuyển tag đã công bố để thay kết quả cũ. Nếu tag đã tồn tại, ghi nhận và thống nhất bản sửa thay vì ghi đè.

## 9 Lệnh và phép kiểm phải bàn giao khi triển khai

Những script dưới đây **chưa tồn tại tại thời điểm lập kế hoạch**. Đây là giao diện CLI cần hai người thực hiện thống nhất; không chạy chúng như lệnh đang có sẵn. Đường dẫn payload ở `.private/` không đưa lên Git. Các fixture unit test phải tự chứa và không cần tải model/GPU.

```powershell
python -m unittest discover -s scripts/w5/tests -p "test_*.py"

python scripts/w5/validate_instruction_dataset.py --contract data/instruction/w5/contract --inputs .private/w5/candidates/member_a.jsonl .private/w5/candidates/member_b.jsonl --reviews data/instruction/w5/reviews --report data/instruction/w5/quality/quality-report.json --findings data/instruction/w5/quality/findings.csv

python scripts/w5/create_split_plan.py --inputs .private/w5/candidates/member_a.jsonl .private/w5/candidates/member_b.jsonl --reviews data/instruction/w5/reviews --policy data/instruction/w5/contract/split-policy.json --seed 42 --output data/instruction/w5/split-plan.json

python scripts/w5/export_sft_dataset.py --inputs .private/w5/candidates/member_a.jsonl .private/w5/candidates/member_b.jsonl --reviews data/instruction/w5/reviews --contract data/instruction/w5/contract --split-plan data/instruction/w5/split-plan.json --output .private/w5/releases/v0.1 --manifest data/instruction/w5/release-manifest.json

python scripts/w5/check_training_format.py --release .private/w5/releases/v0.1 --manifest data/instruction/w5/release-manifest.json --report data/instruction/w5/quality/tokenization-report.json
```

Validator ghi counts/findings cho toàn bộ ứng viên và danh sách `eligible_record_ids` có review ACCEPT đúng hash. Mẫu REJECT/REVISE được giữ trong thống kê nhưng không vào release; mẫu đã REJECT không làm mọi lượt xuất sau đó thất bại. Nonzero khi bản ghi đang được chọn giữ có lỗi cấu trúc/nội dung blocker, thiếu review hoặc review hết hiệu lực, hay không đạt số lượng/split đã khóa. Findings ghi ID và lý do, không coi thao tác gắn cờ là tự sửa. Split/export kiểm lại cùng điều kiện hợp lệ và chỉ nhận các ID đã được hai CSV review xác nhận. Tokenizer checker tải hoặc đọc tokenizer đúng revision, không tải trọng số Qwen; lỗi mạng/tokenizer là lỗi môi trường, không báo thành dataset pass.

Payload release cần có `train.jsonl`, `validation.jsonl`, `instruction_holdout.jsonl`, `metadata.jsonl` và bản sao manifest. Mỗi dòng SFT giữ `record_id` trong metadata sidecar để nối lại nguồn/review; nếu dùng ID trong file SFT thì loader phải loại cột đó khỏi text học. Manifest trong repo và bản sao trong gói phải cùng nội dung, không tự chứa checksum của chính nó.

Quality report có hai trạng thái kiểm: audit candidates trước export và audit final sau export. Kết luận final phải chứa hash release manifest đã kiểm, số mẫu từng split, số review hợp lệ và kết quả tokenization; không dùng kết quả fixture để ghi dataset thật đã pass.

## 10 Hồ sơ nộp và cách xác nhận hoàn thành

SV B tổng hợp `Evidence/W05/README.md` với bảng **Planned — Done — Evidence — Problems — Next week** theo từng A1–A5/B1–B5. A cung cấp nội dung phần mình, B là người ghi bộ evidence tổng hợp để tránh xung đột. Kế thừa cấu trúc `Evidence/W04` tại main `5c5bdef`: `manifest.json` ghi commit/hash artifact và trạng thái kiểm chứng; `metrics.csv` ghi số lượng/phân bố/kết quả kiểm; `test-results.txt` lưu lệnh, thời điểm và kết quả chạy thật. Chỉ thêm `figures/` khi có hình phục vụ minh chứng, không thay log bằng ảnh chụp.

Bản báo cáo nộp LMS 1–2 trang PDF/DOCX phải có: scope W5 và lệch lịch đã ghi nhận; đóng góp từng người; số mẫu thực; split; kiểm chất lượng/leakage; link Issue/PR/tag; checksum/card; giới hạn và việc chuyển W6. Video/demo ngắn cho thấy validator từ chối ít nhất một fixture lỗi và kiểm tra một mẫu thật từ PDF → prompt → target → review → split; không cần dựng demo huấn luyện chưa diễn ra.

Trước đóng tuần, cả hai kiểm:

- [ ] Đã xác nhận phạm vi/lịch W5 và ghi quyết định; không bỏ quên hybrid/rerank trong kế hoạch tổng thể.
- [ ] Hợp đồng và nguồn dùng được đã khóa; chưa rõ quyền thì không tuyên bố đủ điều kiện phát hành.
- [ ] Có 500 mẫu hợp lệ được peer review đúng hash, hoặc báo đúng phần thiếu.
- [ ] Không dùng 150 QA benchmark/biến thể làm instruction; không giao nhóm qua split.
- [ ] Export đúng target thô QA/hint/refusal, không dùng JSON API hoặc hint UI sai contract.
- [ ] Unit test, validator dữ liệu thật, split audit và tokenizer checker có log/exit code rõ.
- [ ] A và B truy cập được cùng artifact, hash/count/card/report khớp nhau.
- [ ] PR được người còn lại review; không tự approve PR của mình.
- [ ] Evidence 1–2 trang và kết quả máy đọc được sẵn sàng; tag `w05` trỏ đúng commit kiểm chứng.
- [ ] W6 nhận được dataset card, payload, hash, split, tokenization report và danh sách vấn đề; chưa ghi adapter/train/factuality đã hoàn tất.

## 11 Tài liệu đối chiếu

- Đề cương nguồn: `D:/ĐATN_Đề cương chi tiết.docx`, mục 8, 10–12; bảng W5/W6.
- [SRS hiện tại](../../SRS.md), phần nghiên cứu/dataset/evaluation; [phạm vi MVP](../../srs/mvp-scope.md).
- [Dataset card corpus](../../dataset-card.md); dữ liệu `data/qa/qa_baseline.json`, `qa_additions.json`, `source_map.json`.
- [TRL Dataset formats](https://huggingface.co/docs/trl/dataset_formats): định dạng conversational prompt-completion.
- [TRL SFT Trainer](https://huggingface.co/docs/trl/sft_trainer): completion-only loss và điều kiện assistant mask. Khi triển khai phải khóa phiên bản tương thích, không tự coi tài liệu latest là phiên bản đã cài.
