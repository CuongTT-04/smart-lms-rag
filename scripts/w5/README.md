# W5 — công cụ kiểm định của Trần Tuấn Cường

## Demo trên máy hiện tại

```powershell
powershell -ExecutionPolicy Bypass -File scripts/w5/demo_checks.ps1 -Candidate .private/w5/candidates/member_b.jsonl -Payload .private/w5/expanded/member_b-sft-preview.jsonl
```

Lệnh chạy test, fixture, tokenizer, candidate B và kiểm việc từ chối fixture/dữ liệu chưa review khi tạo release. Output demo nằm trong `.private/w5/demo`. Bỏ hai tham số Candidate/Payload nếu chỉ demo fixture từ checkout chưa có dữ liệu riêng tư. Dùng `-Python` để chỉ runtime khác đã cài đúng requirements.

Ngày 28/10: B đã chuẩn bị 250 **draft chờ review**, không phải 250 mẫu đã ACCEPT. Xem `docs/weekly/W5/quality-report.md`; gói review có bản HTML đọc được và CSV trống điểm. `expanded/*-sft-preview.jsonl` vẫn là preview để kiểm format, không thay exporter/release do A sở hữu.

Các script chạy offline, không cần Django/PostgreSQL hoặc model weights. Source dùng danh tính corpus nghiên cứu; không suy ra quyền trong LMS. Trạng thái nguồn `USER_AUTHORIZED_INTERNAL_RESEARCH` ghi theo chỉ dẫn của người dùng ngày 28/10/2026, không phải bằng chứng giấy phép độc lập hoặc quyền phát hành công khai.

## Cài runtime riêng

Không cài đè thư viện đang phục vụ chatbot/Kaggle:

```powershell
.\.venv\Scripts\python.exe -m venv .private/w5/tokenizer-runtime
.\.private\w5\tokenizer-runtime\Scripts\python.exe -m pip install -r scripts/w5/requirements-tokenizer.txt
.\.venv\Scripts\python.exe -B -m unittest discover -s scripts/w5/tests
```

Tokenizer chỉ tải các file tokenizer/config/template của Qwen2.5-7B tại revision khóa trong `training-format.json`; không tải safetensors. Môi trường riêng không cần torch. pypdf được khóa cùng phiên bản backend vì khác phiên bản có thể trích text khác nhau. Template và source prompt/parser có checksum, thay đổi phải cập nhật contract/review trước khi audit tiếp.

## B2 — kiểm candidate

```powershell
.\.venv\Scripts\python.exe -B scripts/w5/validate_instruction_dataset.py --input .private/w5/candidates/member_b.jsonl --report data/instruction/w5/quality/member-b-pilot-validation.json
.\.venv\Scripts\python.exe -B scripts/w5/validate_instruction_dataset.py --input data/fixtures/w5-instruction-contract.jsonl --fixture-mode --report data/instruction/w5/quality/fixture-validation.json
```

`candidate` kiểm cấu trúc/hash, PDF checksum/trang/text, phân nguồn, parser target, trùng và benchmark; kết quả `passed` ở giai đoạn này không phải nghiệm thu kiến thức. `eligible_ids` chỉ chứa mẫu thật có review hợp lệ, đúng hash và không còn finding. `fixture_only` không bao giờ được tính cho release.

`--stage release` yêu cầu contract locked, review chéo ACCEPT hiện hành, đủ quota tổng/theo người/theo task/theo môn và không còn finding. Ngưỡng rubric lấy từ contract: ít nhất 9/10, không mục nào 0, ba tiêu chí trọng yếu phải 2. CSV review theo `review-template.csv`; tác giả không tự duyệt. Script không tạo điểm review.

### Xử lý mẫu gần trùng

`character_5gram_jaccard >= 0.85` chỉ gắn cờ, không chứng minh trùng ngữ nghĩa. Kiểm cả câu hỏi và target dài sau bỏ nhãn citation; bỏ qua target ngắn dùng chung như READ hoặc sentinel. Câu hỏi benchmark trùng chính xác và tái sử dụng nguyên đáp án benchmark dài bị chặn. Paraphrase xa còn cần người review đối chiếu nguồn/benchmark; không tuyên bố đã kiểm đủ ngữ nghĩa bằng Jaccard.

Khi có finding gần trùng, reviewer điền CSV adjudication rồi truyền `--adjudications path.csv`:

```text
record_id,other_id,content_sha256,other_sha256,reviewer_member,reviewed_at,decision,reason
```

Với cặp candidate, `other_id` là ID bên kia, hai hash là content hash hiện hành. Với benchmark, `other_id` và `other_sha256` đều là hash được finding trả ra. `DISTINCT` cần lý do độc lập; `SAME_FAMILY` chỉ dành cặp candidate, buộc cùng component khi chia tập. Không dùng adjudication để bỏ qua exact benchmark, nguồn sai hoặc lỗi cấu trúc.

## B4 — chia tập sau khi review

```powershell
.\.venv\Scripts\python.exe -B scripts/w5/create_split_plan.py --input .private/w5/candidates/member_a.jsonl .private/w5/candidates/member_b.jsonl --reviews data/instruction/w5/reviews/member_a_reviews_b.csv data/instruction/w5/reviews/member_b_reviews_a.csv --report data/instruction/w5/split-plan.json
```

Công cụ tự kiểm lại release gates thay vì tin một file quality report có thể đã cũ. Union theo tài liệu/mọi version, variant family, parent và cặp gần trùng đã xác nhận. Cần ít nhất ba component, seed 42, mục tiêu 80/10/10. Không xé component để ép tỷ lệ; báo counts/task/môn thực tế. Cần cân đối lại nguồn trước freeze nếu tỷ lệ thực tế không phù hợp.

## B5 — kiểm tokenizer/format

Kiểm pilot chưa review:

```powershell
.\.private\w5\tokenizer-runtime\Scripts\python.exe -B scripts/w5/check_training_format.py --input .private/w5/candidates/member_b.jsonl --payload .private/w5/pilot/member_b-sft-preview.jsonl --draft-mode --report data/instruction/w5/quality/member-b-pilot-tokenization.json
```

Kiểm fixture: thay input/payload bằng hai file `data/fixtures/w5-*.jsonl`, dùng `--fixture-mode` thay `--draft-mode`. Payload preview xếp theo record_id; chúng không phải release A và không chứng minh đã đủ điều kiện train.

Kiểm gói xuất thật của A:

```powershell
.\.private\w5\tokenizer-runtime\Scripts\python.exe -B scripts/w5/check_training_format.py --input .private/w5/candidates/member_a.jsonl .private/w5/candidates/member_b.jsonl --reviews data/instruction/w5/reviews/member_a_reviews_b.csv data/instruction/w5/reviews/member_b_reviews_a.csv --payload .private/w5/releases/v0.1/train.jsonl .private/w5/releases/v0.1/validation.jsonl .private/w5/releases/v0.1/instruction_holdout.jsonl --sidecar .private/w5/releases/v0.1/train.metadata.jsonl .private/w5/releases/v0.1/validation.metadata.jsonl .private/w5/releases/v0.1/instruction_holdout.metadata.jsonl --split-plan data/instruction/w5/split-plan.json --report data/instruction/w5/quality/tokenization-report.json
```

### Giao diện bàn giao cho A

- `common.load_contract`, `common.content_hash`, `common.projected`, `common.digest` có thể dùng lại trong generator/exporter A; B không sở hữu exporter.
- Candidate theo schema đã chốt; SFT mỗi dòng chỉ có `prompt` (system/user) và `completion` (assistant). Không serialize provenance, target hoặc review vào prompt.
- Sidecar phải có `record_id`, `content_sha256`, `split`, `sft_sha256`. `sft_sha256=common.digest(payload)`; hash canonical NFC/sort keys, không phải SHA của cả file. Có thể thêm metadata audit khác trong sidecar.
- Dòng sidecar tương ứng đúng dòng payload; các file sidecar/payload được truyền vào CLI theo cùng thứ tự. CLI nối bằng ID và kiểm trùng/thiếu, hash và split, không mặc định thứ tự thư mục.
- Hash cả file ở release manifest dùng SHA256 bytes. Checker báo hash thực của input để B đối chiếu manifest A; chưa có manifest/artifact A thì chưa ghi audit release đã xong.
- Đây là giao diện triển khai tối thiểu để A đối chiếu exporter trước bàn giao; nếu A đã chọn layout khác, thống nhất adapter/contract revision trước export, không tự sửa file của A.

Checker dựng lại prompt độc lập từ candidate, đối chiếu payload, đếm toàn bộ template/EOS, yêu cầu full sequence có prompt prefix chính xác, chặn special/role tokens trong dữ liệu và không truncation. Ngân sách 3072/768/4096. Mask được kiểm ở mức CPU reference completion-only: prompt/padding dùng -100; trainer/collator thật phải kiểm tiếp ở W6. `training_ready=false` vì công cụ không chạy training hoặc chứng minh chất lượng adapter.

## Exit code và artifact

- `0`: bước kiểm yêu cầu đã qua; xem `stage`, `fixture_mode`, `draft_mode`, `eligible_ids` trước diễn giải.
- `1`: dữ liệu/quality/format không đạt; đọc findings trong report.
- `2`: lỗi cấu hình/I/O/dependency; không dùng report cũ của lần chạy trước.
- Report không được ghi đè candidate, review/adjudication, contract, benchmark, PDF hoặc payload/sidecar. Ghi file JSON bằng tên tạm ngẫu nhiên rồi replace.
- Dữ liệu thật và gói review ở `.private/w5/`, không tự đưa PDF/trích đoạn lên GitHub. Public report chỉ chứa ID/hash/count/findings, không chứa câu hỏi/đáp án/đoạn PDF.

## Gói chung500 mẫu

Module scripts.w5.group_candidate cung cấp prepare_group(records, output, tokenizer_folder, input_paths=...) và verify_group_package(folder, tokenizer_folder, expected_manifest_sha256). Dùng runtime pinned riêng, không cần Kaggle/GPU. Tokenizer đã nằm trong bản bàn giao A được kiểm SHA. Hàm prepare không ghi đè gói đích; dùng thư mục mới cho mỗi phiên bản. Hàm verify yêu cầu hash manifest đã nhận từ kênh tin cậy và tái tính từ payload đã lưu.

Gói hiện tại .private/w5/group-v0.2/package, kết quả verification.json và revision-log.json cùng thư mục. Xem docs/weekly/W5/ket-qua-tich-hop-w5.md. Normalizer nhóm là opt-in, không tự thay policy validator cũ; snapshot ghi rõ NFC_REMOVE_WHITESPACE. Các input gốc giữ nguyên. Gói luôn pending peer confirmations; không tạo SELF_REVIEW/PEER_REVIEW ACCEPT tự động.
