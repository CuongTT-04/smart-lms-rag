# Bản đầu vào W5 của Cường gửi Dương góp ý

Ngày soạn: 27/10/2026. Người phụ trách bản đề xuất: Trần Tuấn Cường — SV B. Người cần review: Vũ Nam Dương — SV A. Mốc source đối chiếu: `origin/main` tại `5c5bdef200fc839cfa1e5aa3d3fa609c7f5d20ba`.

**Cập nhật 28/10/2026: A đã đồng ý theo xác nhận của Cường; contract v0.2 đã ghi nhận. Quyền dùng nội bộ theo chỉ dẫn của Cường; pilot B 10 mẫu đang chờ review A. Xem [quality-report.md](quality-report.md) cho trạng thái triển khai. Nội dung dưới đây giữ bản đầu vào đã gửi A ngày 27/10 để đối chiếu lịch sử.**

**Trạng thái tại thời điểm soạn 27/10: DRAFT_PENDING_A_REVIEW.** Đây là bản cụ thể hóa B1 trong [phân công W5](phan-cong-w5.md), để A sửa/góp ý trước khi hai người khóa đầu vào. Chưa có xác nhận của A, chưa khóa dataset và chưa có mẫu thật nào được tính là đã nghiệm thu.

Đề xuất của B là làm instruction tuning để model biết trả lời theo bằng chứng, dẫn nguồn, gợi ý đúng chính sách và dừng khi thiếu căn cứ. RAG tiếp tục cung cấp tri thức từ học liệu có quyền; fine-tune không thay kiểm quyền của LMS và không dùng để ghi nhớ đáp án benchmark.

## 1 Những điểm B đề xuất A xác nhận

| Mã | Đề xuất để chốt | A cần góp ý vào đâu |
|---|---|---|
| D1 | W5 làm pilot 500 mẫu hợp lệ, A/B mỗi người 250; chưa tuyên bố đủ mục tiêu 1k–5k của W6 | Quy mô có làm được trong tuần không; có yêu cầu mới từ giảng viên khác đề cương cũ không |
| D2 | 300 QA, 100 summary, 50 hint, 50 thiếu căn cứ; mỗi người một nửa. Theo môn: THMLN 200, KTCTMLN/CNXHKH mỗi môn 150 | Tỷ trọng có phục vụ mục tiêu QLoRA của nhóm không; có cần ưu tiên QA nhiều hơn không |
| D3 | Mỗi PDF có một người biên soạn chính, nhận toàn bộ phạm vi trang; không cùng sinh hàng loạt trên một nguồn | Đổi document ownership nếu A/B quen phần khác; quyền nguồn còn phải xác minh |
| D4 | Prompt `bounded_guidance`; QA/summary là văn bản có citation, hint là mã thao tác, thiếu căn cứ là sentinel | Có đồng ý giữ contract hiện tại không; nếu đổi hint/prompt thì phải ghi quyết định khác trước khi sinh mẫu |
| D5 | Candidate theo schema; SFT là prompt/completion. Base/tokenizer Qwen2.5-7B cùng revision hiện có; sequence 4096, prompt 3072, completion 768 là ngân sách training pilot riêng | A đối chiếu chat template, EOS/mask và kế hoạch QLoRA W6; chưa coi ngân sách này đã qua training dry-run |
| D6 | Review chéo 100%; 9/10, ba tiêu chí kiến thức/grounding/hành vi phải đạt 2; không có tiêu chí 0 | Chấm chung pilot để hiệu chỉnh rubric; không thay ngưỡng sau khi thấy điểm test |
| D7 | Split theo nhóm tài liệu/họ biến thể, xấp xỉ 80/10/10, seed 42; bảo vệ benchmark và các bản dẫn xuất | A xác nhận protocol thí nghiệm và nhóm cần giữ lại để đánh giá |
| D8 | B giữ contract/validator/split/audit; A giữ generator/exporter/release/card; evidence chung ở `Evidence/W05` | Xác nhận giao diện bàn giao và người ghi duy nhất từng file |

Các lựa chọn trên là đề xuất, không phải các quyết định A đã đồng ý. Ghi phản hồi D1–D8 bằng APPROVE hoặc CHANGE kèm lý do trong PR/Issue. File [review-status.json](../../../data/instruction/w5/contract/review-status.json) hiện để toàn bộ quyết định PENDING; chỉ người có xác nhận thực mới cập nhật ngày/commit approval.

## 2 Gói đầu vào đã soạn

| File | Nội dung và cách dùng |
|---|---|
| [schema.json](../../../data/instruction/w5/contract/schema.json) | JSON Schema Draft 2020-12 cho candidate; trường không khai báo bị từ chối; tách fixture và dữ liệu thật |
| [quality-policy.json](../../../data/instruction/w5/contract/quality-policy.json) | Quota, rubric, hard reject, trường được phép vào model, quy tắc content hash và các kiểm tra ngữ nghĩa cần làm sau |
| [training-format.json](../../../data/instruction/w5/contract/training-format.json) | Model/revision, prompt builder, hash source, ngân sách, format SFT và các bước chưa kiểm chứng |
| [split-policy.json](../../../data/instruction/w5/contract/split-policy.json) | Seed, nhóm liên thông, tỷ lệ mục tiêu, validation và holdout |
| [source-manifest.json](../../../data/instruction/w5/contract/source-manifest.json) | 27 PDF, checksum, số trang kiểm thực tế, UUID offline và tình trạng quyền nguồn |
| [source_allocation.csv](../../../data/instruction/w5/contract/source_allocation.csv) | Một người phụ trách mỗi PDF, phạm vi trang và quota gợi ý; không phải nhãn split hoặc xác nhận quyền |
| [benchmark-exclusion-manifest.json](../../../data/instruction/w5/contract/benchmark-exclusion-manifest.json) | Snapshot/hash/ID và fingerprint của bộ 150 canonical cùng các bảng QA/guardrail liên quan còn trên main |
| [review-template.csv](../../../data/instruction/w5/contract/review-template.csv) | Header CSV review dùng chung; chưa có điểm hoặc xác nhận người thật |
| [fixture-source.json](../../../data/instruction/w5/contract/fixture-source.json) và [4 ví dụ JSONL](../../../data/fixtures/w5-instruction-contract.jsonl) | Nội dung minh họa do trợ lý hỗ trợ biên soạn riêng, không chép corpus/benchmark; dùng kiểm schema/parser, không tính vào 500 mẫu |
| [Preview prompt completion](../../../data/fixtures/w5-sft-contract-preview.jsonl) | Bốn ví dụ được dựng bằng `build_messages` hiện có, để A nhìn rõ input/target sau chuyển đổi; chưa tokenize hoặc dùng train |
| [scope-decision.md](scope-decision.md) | Phạm vi đề xuất và lệch lịch W5/W6 cần nhóm đối chiếu |
| [contract-bundle.json](../../../data/instruction/w5/contract/contract-bundle.json) | Danh mục/checksum gói review; không đồng nghĩa manifest phát hành dataset |
| [verification-report.json](../../../data/instruction/w5/contract/verification-report.json) | Kết quả kiểm gói draft thực tế và các phần chưa chạy; không thay audit dataset thật |

Tất cả tài liệu/JSON hiện là draft. Gói này không tạo generator, validator production, split plan thật, training run hoặc release dataset.

Kiểm tra gói draft đã thực hiện: schema hợp lệ về cấu trúc; bốn fixture qua schema, prompt projection và parser hiện có; tám biến thể sai bị schema từ chối, năm biến thể sai bị parser từ chối; checksum/page count của 27 PDF và quota A/B được đối chiếu. Các phép kiểm này không xác nhận quyền nguồn, human review, ngữ nghĩa dữ liệu thật hay training readiness.

## 3 Cách một mẫu đi qua pipeline LMS

```text
PDF/nguồn đã được xác minh dùng được
  → trích đoạn có trang và checksum
  → câu hỏi và target do A hoặc B biên soạn
  → kiểm cấu trúc và benchmark leakage
  → người còn lại đọc nguồn và review đúng content hash
  → B tạo split plan theo nhóm
  → A tạo prompt bằng build_messages và xuất completion
  → B kiểm token/EOS/mask và audit release
```

Model chỉ nhận question, mode, evidence và phần công khai của exercise. Các field source checksum, rights, review, target, rubric hoặc ground_truth không được tự động serialize chung vào user prompt.

Context trong candidate chứa metadata bổ sung để audit. Khi gọi `EvidenceContext`, chỉ lấy tám field được liệt kê trong `quality-policy.json:evidence_context_projection`, sau đó dùng prompt builder hiện có. Nhãn citation được tính theo vị trí evidence trong prompt cuối, không lấy từ số trang, ID `S1` hay thứ tự chunk trước khi budgeting. Mẫu bị đổi/chọn lại evidence phải sửa nhãn và review lại.

### 3.1 Đầu ra thô cần học

| Task | mode | Target |
|---|---|---|
| qa | qa | Tiếng Việt có `[1]`, `[2]` theo evidence, không JSON API |
| summary | qa | Tóm tắt đúng phần nguồn được hỏi, có citation; không thêm enum API mới |
| hint | hint | Một dòng `READ [n]`, `OUTLINE [n]`, hoặc `COMPARE [n] [m]`; COMPARE cần hai nhãn khác nhau có thật |
| insufficient_evidence | qa | Chỉ `INSUFFICIENT_EVIDENCE`; không câu giải thích/citation đi kèm |

Hint tự nhiên trên UI hiện do `parse_reading_hint` dựng từ mã thao tác. Không lấy câu UI đó làm target cho model rồi giữ parser cũ. Nếu A muốn fine-tune hint tự nhiên thì phải đề xuất sửa cả contract và parser ở một phạm vi khác.

Chế độ Kiểm tra, kick/ban/thu hồi quyền và đáp án/rubric nội bộ vẫn do backend xử lý. Không đưa bài nộp/hội thoại thật của học viên vào fine-tune và không dùng phản hồi 403 của API làm target LLM.

### 3.2 Candidate và file SFT là hai dạng khác nhau

Candidate có `record_id`, question, contexts, target, provenance và content hash để biên soạn/review. Record thật có ID `W5_A_00001` hoặc `W5_B_00001`. Fixture có ID `FX_W5_00001` và `source_identity_scope=fixture_only`, bắt buộc bị loại khỏi release.

Sau khi được duyệt, A xuất mỗi dòng SFT gồm `prompt` là hai message system/user và `completion` là một assistant message chứa `target_text`. Các metadata được nối lại bằng sidecar, không đi vào text học. Đây chưa phải JSON response `{request_id,status,answer,citations}` của API chatbot.

Hash mẫu là SHA256 của JSON UTF-8 sau NFC đệ quy cho giá trị string, sort key, không khoảng trắng phân cách; chỉ bỏ field `content_sha256`, giữ thứ tự array. Mọi field trong schema còn lại tham gia hash. Đổi question, context, target hoặc provenance thì review cũ hết hiệu lực.

JSON Schema chỉ kiểm hình thức. Chẳng hạn citation `[9]` không có trong prompt, COMPARE cùng một nhãn, sai checksum PDF hoặc câu trả lời sai kiến thức vẫn cần parser/validator/reviewer kiểm riêng; không tuyên bố schema đã bảo đảm các tính chất đó.

## 4 Phân nguồn và quyền sử dụng

Đã kiểm checksum byte và page count của 27 PDF, đối chiếu `data/data_manifest.csv` và `data/qa/source_map.json`. Đây là kiểm toàn vẹn nguồn, chưa phải review nội dung hoặc xác nhận quyền.

Phân công sơ bộ: A nhận chapter số lẻ, B nhận chapter số chẵn trong từng môn. Mỗi tài liệu có một người ghi candidate; quota cân bằng theo môn chứ không theo số file. Hai người có thể đổi nguồn trong CSV trước M0 nếu ghi lý do và không để một nguồn có hai chủ.

| Môn | A nhận | B nhận | Mục tiêu mỗi người |
|---|---|---|---:|
| THMLN | ch01, ch03, ch05, ch07, ch09, ch11, ch13 | ch02, ch04, ch06, ch08, ch10, ch12, ch14 | 100 |
| KTCTMLN | ch01, ch03, ch05 | ch02, ch04, ch06 | 75 |
| CNXHKH | ch01, ch03, ch05, ch07 | ch02, ch04, ch06 | 75 |
| Tổng | 14 PDF | 13 PDF | 250 |

CSV có page_start/page_end thực cho từng tài liệu và quota phân nhỏ. Đây là quota gợi ý: không nhân bản dữ liệu để đủ quota file ngắn, không chia cắt đoạn cần thiết hoặc nhận mẫu không đạt; có thể phân bổ lại trước freeze.

**Điểm còn thiếu cần A/B giải quyết:** manifest nguồn hiện ghi `rights_status=DECLARED_NOT_VERIFIED` cho các PDF. Gói review giữ nguyên trạng thái này, để `generation_authorized=false`, không tự coi lời khai dùng nghiên cứu là minh chứng đã được duyệt. Cần bổ sung căn cứ cho mục đích sử dụng dự kiến hoặc chọn nguồn khác có quyền phù hợp trước khi tạo/phát hành dataset thật. Có thể dùng fixture riêng để phát triển tool trong lúc làm rõ.

UUID trong source map là danh tính offline cho nghiên cứu, không chứng minh tài liệu đó đã công bố hoặc tài khoản có quyền đọc trong PostgreSQL của LMS. Dataset card phải nói rõ điều này.

## 5 Bảo vệ benchmark và chia tập

150 QA canonical là development trước QLoRA, chưa phải test độc lập. B vẫn đề xuất giữ chúng ngoài dataset fine-tune để so sánh trước/sau có ý nghĩa. Exclusion manifest còn khóa hash các bảng QA/nháp/review chứa question và guardrail liên quan trên main, để không bỏ lọt bản sao chỉ vì khác tên file. Số bản ghi cộng qua các alias không phải số QA độc lập mới.

Không dùng câu hỏi/đáp án chuẩn hoặc paraphrase của chúng làm seed tạo instruction. B có thể dùng chúng trong công cụ so khớp rò rỉ riêng; A không đưa nhãn đó vào prompt của model tạo mẫu hoặc prompt huấn luyện. Fingerprint hiện chỉ là exact-match sau chuẩn hóa; near-duplicate/ý nghĩa chưa được chấm và vẫn phải kiểm.

Corpus dùng cho RAG có thể trùng tài liệu làm căn cứ benchmark theo protocol; điều đó không cho phép dùng nhãn benchmark để fine-tune. Câu mới cùng chủ đề không tự bị coi là rò rỉ chỉ vì có thuật ngữ/đáp án ngắn giống nhau: phải xét cặp question/target và họ biến thể, ghi rõ quyết định.

Split sau khi review: B nối các nhóm cùng tài liệu/mọi version, họ biến thể, bản near-duplicate đã xác nhận và mẫu nhiều nguồn thành component, rồi chia nguyên component. Tỷ lệ 80/10/10 chỉ là mục tiêu; phải có cả ba tập và báo counts thật, không xé nhóm để ép đúng 400/50/50. Cần bộ test QA độc lập theo kế hoạch nghiên cứu riêng; instruction holdout không thay bộ đó.

## 6 Rubric và tiêu chí xuất dữ liệu

Mỗi mẫu thật được người còn lại chấm năm mục 0/1/2: instruction rõ; nội dung đúng; grounding/citation; hành vi task; ngôn ngữ/format. Đề xuất ACCEPT khi ít nhất 9/10, không mục nào 0 và ba mục nội dung/grounding/hành vi đều 2.

Lỗi bịa nguồn, sai kiến thức trọng yếu, hint lộ đáp án, dùng benchmark dẫn xuất, thông tin riêng tư, nguồn chưa xác minh dùng được hoặc fixture lọt vào release là blocker. Không lấy LLM judge/regex/checksum để tự ghi reviewer đã chấp nhận.

Review CSV không chứa hàng giả được duyệt sẵn. Tác giả nhận REVISE thì tự sửa candidate của mình; người review kiểm lại hash mới. REJECT được lưu ở findings để thống kê, không buộc xóa lịch sử và không được xuất. B tạo danh sách ID đủ điều kiện; A kiểm lại điều kiện khi export.

Trước khi mở rộng, A và B làm 10 pilot mỗi người và chấm chung 20 mẫu để thống nhất rubric. Bốn fixture trong gói này chỉ minh họa format, không thay 20 pilot đọc từ nguồn thật và không được ghi là đã qua peer review.

## 7 Giới hạn token và kiểm tra huấn luyện

Giữ base/tokenizer revision như pipeline hiện có. Ngân sách training pilot đề xuất là 4096 tổng token, prompt tối đa 3072 và completion tối đa 768, tính sau chat template/EOS. Không sửa profile online 6144/3584/1024 và không cam kết cấu hình training đã vừa VRAM T4 trước khi thử ở W6.

Đề xuất loss chỉ trên completion: token prompt/padding có label -100, còn token assistant/EOS được giám sát. Không mặc định template Qwen hỗ trợ `assistant_only_loss`; A cần kiểm phiên bản trainer và mask thực tế khi vào bước tương ứng.

Ở bước B1 này chưa tải tokenizer/model, chưa chạy tokenization hoặc optimizer, chưa đo training memory. `training-format.json` ghi các trạng thái NOT_RUN và trainer version chưa chọn. Không ghi số token minh họa thành số đo thật.

## 8 Cách A phản hồi và cách khóa M0

1. A đọc mục 1 và bốn ví dụ JSONL; đối chiếu với cách A muốn fine-tune và pipeline đã bàn giao.
2. A trả lời D1–D8: APPROVE hoặc CHANGE, nêu field/quy tắc cần đổi. Riêng quyền nguồn cần căn cứ cụ thể; đồng ý schema không có nghĩa đã duyệt quyền dữ liệu.
3. B sửa file sở hữu của B; cập nhật checksum gói review và nêu nội dung thay đổi. A không phải sửa cùng một schema trong nhánh riêng.
4. Sau khi có phản hồi thật, ghi người, ngày và commit review; B xác nhận lại. Chỉ chuyển locked=true khi các quyết định và điều kiện nguồn đã được giải quyết cho tập được chọn.
5. Ghi contract fingerprint vào từng run tiếp theo. Đổi schema/quota/prompt sau khi khóa phải tăng contract revision và đánh giá lại dữ liệu chịu ảnh hưởng.

**A có thể làm ngay:** góp ý contract, chuẩn bị generator/exporter bằng fixture, kiểm thiết kế prompt và chọn cách tokenization. **Chưa nên làm:** sinh hàng loạt theo một contract còn tranh luận, lấy 150 QA chuyển thẳng thành train, hoặc đánh dấu nguồn đã được cấp quyền khi chưa có căn cứ.

Bản gửi A là artifact để review, chưa tạo Issue/PR/tag hoặc gửi tin nhắn thay Cường. Cấu trúc Issue và review chéo vẫn theo bản phân công W5.
