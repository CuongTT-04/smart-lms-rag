# Thống nhất đầu vào instruction dataset

**Ngày chốt:** 28/10/2026. **Người thực hiện và tự review:** Vũ Nam Dương (A). **Người kiểm tra cuối:** Trần Tuấn Cường (B).

A/B đã thống nhất phản hồi D1–D8. A triển khai liên tục đến gói bàn giao, tự kiểm tra và sửa trong quá trình làm; B review sau cùng, A tiếp tục sửa theo yêu cầu. Không cần chờ B duyệt từng pilot hoặc batch. Bản ghi dùng cho công cụ: [input-contract.json](../data/instruction/input-contract.json).

## 1. Các quyết định đã thống nhất

| Mục | Quyết định |
| --- | --- |
| **D1. Phạm vi** | Chuẩn bị pilot 500 instruction được chấp nhận, A/B mỗi người 250. Chưa huấn luyện adapter hoặc thay model online. Đây là mục tiêu nhóm; việc điều chỉnh lịch W5/W6 và hybrid/rerank cần đối chiếu kế hoạch chung. |
| **D2. Phân bố** | Mỗi người 150 QA, 50 summary, 25 hint, 25 thiếu căn cứ; theo môn THMLN 100, KTCTMLN 75, CNXHKH 75. Không nhân bản để đủ quota; báo số thực đạt. |
| **D3. Nguồn** | Giữ phân công chương lẻ cho A, chương chẵn cho B. A quyết định tiếp tục thử nghiệm nghiên cứu nội bộ khi quyền nguồn chưa xác minh; chấp nhận mẫu đúng rubric trong phạm vi này, không xác nhận cấp phép hoặc cho phép phát hành. |
| **D4. Đầu ra** | Giữ schema candidate và ID gốc. QA/summary là văn bản có citation; hint là mã thao tác; thiếu căn cứ là sentinel. Không dùng JSON API làm target. |
| **D5. Training format** | Dùng prompt/completion từ `build_messages`, prompt `bounded_guidance`, Qwen/tokenizer đúng revision. Ngân sách sequence/prompt/completion 4096/3072/768; kiểm tokenizer, EOS và loss mask trước nghiệm thu định dạng. |
| **D6. Review** | A tự review phần A theo rubric và hash; B review cuối. Giữ ngưỡng 9/10, không tiêu chí 0, nội dung/grounding/hành vi đều đạt 2. Sửa nội dung thì review lại. |
| **D7. Split** | Bảo vệ benchmark, chia nguyên nhóm nguồn/họ biến thể; seed 42, mục tiêu 80/10/10, ba tập không rỗng. Không xé nhóm để ép số lượng. |
| **D8. Bàn giao** | A hoàn thiện công cụ, dữ liệu và candidate thuộc phần mình; bàn giao một lần để B kiểm cuối rồi sửa tiếp. File đặt tên theo chức năng; giữ `Evidence/W05`, milestone `Tuan5`, tag `w05` theo quy ước chung. |

## 2. Phần dữ liệu A phụ trách

| Môn | Tài liệu | Số mẫu mục tiêu |
| --- | --- | ---: |
| THMLN | ch01, ch03, ch05, ch07, ch09, ch11, ch13 | 100 |
| KTCTMLN | ch01, ch03, ch05 | 75 |
| CNXHKH | ch01, ch03, ch05, ch07 | 75 |
| **Tổng** | **14 PDF** | **250** |

Mỗi mẫu lưu câu hỏi, evidence có trang/checksum, target, provenance và content hash. Dữ liệu B chỉ được kiểm/review khi có bàn giao; không tạo thay rồi gán tác giả B hoặc tính đủ 500 khi chưa đủ.

**Tình trạng nguồn:** 27 PDF khớp checksum và danh tính nguồn hiện tại. Hồ sơ gốc vẫn ghi `DECLARED_NOT_VERIFIED`, chưa có tham chiếu chứng cứ quyền sử dụng. A quyết định tiếp tục nghiên cứu phi thương mại nội bộ dù quyền chưa xác minh; đây là ngoại lệ quy trình được ghi nhận, không phải chứng cứ cấp phép hoặc kết luận pháp lý. Mẫu gắn `UNVERIFIED:<source_group_id>`, lưu trong `.private/instruction`; được chấp nhận riêng cho nghiên cứu sau review nội dung, chỉ huấn luyện sau audit kỹ thuật, không được phát hành. Mẫu nghiên cứu, mẫu B đã duyệt và release cuối được đếm riêng; fixture không tính là dữ liệu thật.

## 3. Quy cách mẫu và gói SFT

| Loại | Mode | Target |
| --- | --- | --- |
| QA | `qa` | Tiếng Việt có `[1]`, `[2]` theo nguồn hỗ trợ; câu trắc nghiệm theo quy tắc parser |
| Summary | `qa` | Tóm tắt đúng phạm vi được hỏi, có citation |
| Hint | `hint` | Một dòng `READ [n]`, `OUTLINE [n]` hoặc `COMPARE [n] [m]`; hai nhãn COMPARE khác nhau |
| Thiếu căn cứ | `qa` | Chỉ `INSUFFICIENT_EVIDENCE` |

- Giữ ID `W5_A_*`, `W5_B_*`; fixture `FX_W5_*` không vào release.
- Prompt gồm system/user; completion gồm một assistant message chứa target. Metadata, review, rubric, đáp án chuẩn không lọt vào system/user hoặc text huấn luyện ngoài target.
- Chỉ lấy tám field `EvidenceContext` đã quy định. Nhãn citation theo thứ tự evidence trong prompt cuối; đổi evidence/target phải tính lại hash và review.
- Base/tokenizer: `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`; Transformers tham chiếu 4.57.6. Không đổi cấu hình chatbot online.
- Đếm token sau chat template, kiểm toàn chuỗi, EOS và ranh giới completion. Prompt/padding có label `-100`, target không rỗng; không cắt ngầm hoặc mặc định template hỗ trợ `assistant_only_loss`.

## 4. Kiểm tra và nghiệm thu

**Quy trình:** công cụ/test → 10 pilot A → tự review và sửa → mở rộng theo batch 25–50 → xuất candidate → B review cuối → A sửa, tái xuất và kiểm lại.

- Review chấm 0/1/2 cho instruction, nội dung, grounding/citation, hành vi task và ngôn ngữ/format. Bịa nguồn, sai kiến thức trọng yếu, hint lộ đáp án, leakage, thông tin riêng tư hoặc nguồn chưa đủ điều kiện là blocker dù tổng điểm cao.
- Ghi tự review của A và nghiệm thu của B riêng biệt: reviewer, loại review, ID/hash, điểm, decision, ngày và lý do. Không dùng tự review để ghi B đã duyệt; review hết hiệu lực khi nội dung đổi.
- Hash SHA-256 trên JSON UTF-8, NFC đệ quy giá trị string, sort key, không khoảng trắng phân cách; chỉ bỏ `content_sha256`, giữ thứ tự array.
- Không lấy câu hỏi/đáp án hoặc paraphrase của 150 QA và các bộ trong exclusion manifest làm instruction. Near-duplicate phải được xem xét, không tự loại chỉ vì chung thuật ngữ.
- Split nguyên component gồm cùng tài liệu/mọi version, họ biến thể, near-duplicate đã xác nhận và liên kết nhiều nguồn. Validation dùng chọn cấu hình; instruction holdout không dùng chỉnh prompt/epoch/ngưỡng, không thay bộ QA test độc lập.
- Candidate thông thường ghi `CANDIDATE_PENDING_B_REVIEW`. Ngoại lệ nghiên cứu nội bộ được bật rõ ràng bằng `--internal-research`, ghi `INTERNAL_RESEARCH_CANDIDATE_PENDING_AUDIT`, không đổi quyền nguồn thành đã xác minh. Release cuối vẫn phải có review của B trên đúng hash và audit đạt; mẫu B, nếu dùng, phải có review của A. Khi B yêu cầu sửa, A cập nhật artifact/hash và kiểm lại phần bị ảnh hưởng.

## 5. Đầu ra và bàn giao

| Đầu ra của A | Đường dẫn dự kiến |
| --- | --- |
| Generator/recipe và test | `scripts/instruction/generate_candidates.py`, `scripts/instruction/tests/` |
| Exporter và test | `scripts/instruction/export_sft_dataset.py`, `scripts/instruction/tests/` |
| Candidate A | `.private/instruction/candidates/member_a.jsonl` |
| Review A | `.private/instruction/candidates/reviews.jsonl` |
| Gói xuất | `.private/instruction/releases/` |
| Dataset card v2.0 (cùng thư mục bản v1.0) | `docs/dataset-card-v2.0.md` |
| Minh chứng chung | `Evidence/W05/` |

Gói xuất cơ bản gồm `train.jsonl`, `validation.jsonl`, `instruction_holdout.jsonl`, `metadata.jsonl` và manifest. Bàn giao kèm dataset card, log test, review, split/tokenization và danh sách vấn đề. Giữ nội dung riêng tư ngoài Git; dùng link riêng và checksum. Gói A đã xuất và kiểm ở mục 10; dataset card đã bổ sung tại [dataset-card-v2.0.md](dataset-card-v2.0.md), giữ nguyên bản v1.0 tại `docs/dataset-card.md`. Việc có dataset card không đồng nghĩa toàn bộ bàn giao hoặc B nghiệm thu đã hoàn thành.

## 6. Mốc đầu vào và trạng thái hiện tại

- Gói gốc: `W5-Input-Review-Duong-2026-10-27.zip`; SHA-256 `0b1ffed823e29e7e9faed5ed052978f8d6387c02f70d2583fe4a7bf333f59f5f`. Bản riêng tư tại `.private/instruction/input.zip`; ZIP gốc giữ nguyên.
- Base đối chiếu: `5c5bdef200fc839cfa1e5aa3d3fa609c7f5d20ba`. Đã kiểm 15/15 file được bundle liệt kê, sáu hash source và 4/4 preview khớp prompt builder.
- Dùng hash source map hiện tại `a0d4c0c4318cf7dc2b9618468957fdaacb8560ebc7123beb2d50ca3173031483`; hash tham chiếu cũ trong gói được ghi riêng trong JSON để truy vết, không sửa source map.
- **Đã thống nhất đầu vào kỹ thuật và phân công.** Đã có 10 mẫu pilot từ PDF, tự review ACCEPT cho nghiên cứu nội bộ. Quyền nguồn vẫn chưa xác minh; B chưa nghiệm thu.
- **Sau mở rộng bước 4:** đã có 250 mẫu A tự duyệt nội bộ, giữ nguyên 10 pilot; tổng hợp và đường dẫn tại mục 9. Chưa tạo dữ liệu thay B hoặc ghi B đã duyệt.
- **Hiện tại, sau bước 6:** đã xuất và kiểm kỹ thuật gói SFT cho 250 mẫu A; kết quả tại mục 10. Bước 5 review dữ liệu B vẫn chờ đầu vào, không được tính hoàn thành. Chưa huấn luyện.

## 7. Công cụ và cách kiểm tra bằng CPU

**Đã có:** bộ đóng gói bản nháp thành candidate, validator, exporter và test. Không tải model/tokenizer, không gọi API, không dùng GPU. Schema gốc được giữ nguyên byte trong `data/instruction/record-schema.json`; các kiểm tra bổ sung nằm trong validator.

Chạy tại thư mục gốc dự án:

```powershell
python -m pip install -r scripts/instruction/requirements.txt
python -X utf8 -m unittest discover -s scripts/instruction/tests -v
```

**Recipe biên soạn:** chọn đoạn nguồn đúng quyền/trang/phân công → viết câu hỏi độc lập với benchmark → viết target theo bảng mục 3 → lưu provenance → kiểm → tự review trên đúng hash. Không lấy gold/đáp án benchmark làm nguyên liệu. Không tự sinh điểm ACCEPT.

- Bản nháp JSONL chứa đủ trường candidate trong schema, **trừ** `record_id` và `content_sha256`. Công cụ cấp hai trường này. `text_sha256` là SHA-256 UTF-8 của nguyên văn evidence; `source_checksum` là SHA-256 byte PDF.
- Sinh candidate không có nghĩa tự viết đáp án: công cụ nhận câu hỏi/target đã biên soạn, kiểm tra rồi đóng gói. Bản nháp thiếu trường/sai target bị chặn.
- Chạy tiếp cùng bản nháp không tăng ID hoặc ghi trùng. Đổi nội dung của mẫu đã có sẽ báo lỗi, không ghi đè; phải quản lý bản sửa và review lại trước khi xuất.

Ví dụ lệnh cho dữ liệu thật, sau khi hồ sơ quyền nguồn đã được cập nhật và xác minh trong contract/bundle tương ứng:

```powershell
python scripts/instruction/generate_candidates.py --drafts .private/instruction/drafts/member_a.jsonl --output .private/instruction/candidates/member_a.jsonl --member A
python scripts/instruction/export_sft_dataset.py --inputs .private/instruction/candidates/member_a.jsonl --reviews .private/instruction/reviews.csv --split-plan .private/instruction/split-plan.json --output .private/instruction/releases/candidate
```

Review nhận CSV hoặc JSONL, đúng các cột `review_fields` trong contract, có `review_kind=SELF_REVIEW`, người review trùng tác giả và hash hiện tại. Điểm 0/1/2 phải đạt rubric; không chấp nhận review thiếu, cũ hoặc còn yêu cầu sửa trên cùng hash. `split-plan.json` gồm `seed: 42`, `assignments` ánh xạ ID → `train`/`validation`/`instruction_holdout`, và `record_hashes` ánh xạ ID → hash hiện tại. Ba tập không rỗng, không tách component nguồn/biến thể/parent; báo phân bố thực tế thay vì ép đủ tỷ lệ.

**Fixture:** thêm `--preview` vào cả hai lệnh, dùng dữ liệu `fixture_only`, lưu ở đường dẫn riêng. Các test đã bao phủ luồng CLI này bằng dữ liệu tự biên soạn; không cần ZIP riêng hay PDF giáo trình để chạy test. Review giả lập trong test chỉ kiểm công cụ, không tính là mẫu được duyệt.

**Giới hạn nghiệm thu:** mặc định xuất `CANDIDATE_PENDING_B_REVIEW`; fixture là `FIXTURE_PREVIEW_NOT_DATASET`, số mẫu thật bằng 0. Chế độ nghiên cứu riêng được mô tả ở mục 8. Exporter chưa cấp release cuối hoặc xác nhận ngân sách token/EOS/loss mask. Những kiểm tra này và review cuối của B vẫn thuộc bước bàn giao. Checksum benchmark chấp nhận đúng byte hoặc chuyển CRLF → LF có ghi nhận; không bỏ qua thay đổi nội dung.

**Kết quả bước công cụ ngày 28/10/2026, trước khi bổ sung pilot:** 46/46 test công cụ đạt trong 6,317 giây; 125/125 test hồi quy provider/pipeline/guardrail/checks/evaluation đạt trong 2,340 giây, không chạy model thật. Đã kiểm cả đọc PDF tự biên soạn bằng pypdf, CLI chạy tiếp và xuất đủ năm file. Các mẫu/điểm giả lập trong bài test không tính là dữ liệu thật. Log hiện tại (được cập nhật ở mục 8): `.private/instruction/tooling-test-results.txt`, `.private/instruction/runtime-test-results.txt`; tổng hợp `.private/instruction/tooling-verification.json`.

## 8. Pilot nghiên cứu riêng tư

**Quyết định hiện tại ngày 28/10/2026:** A tiếp tục sử dụng dữ liệu cho thử nghiệm nghiên cứu/học tập phi thương mại nội bộ dù quyền chưa xác minh, không giả định đã được cấp phép và không phát hành dữ liệu/adapter. `--private-draft` dùng để biên soạn; `--internal-research` dùng khi xuất candidate nghiên cứu sau review và có split plan. Cả hai cần contract cho phép và đầu ra trong `.private/instruction`. Validator vẫn kiểm schema/hash, PDF/trang/evidence, phân công nguồn, target và benchmark. Mặc định không bật ngoại lệ; chế độ xuất thông thường vẫn chặn nguồn chưa xác minh.

| Nội dung | Kết quả |
| --- | --- |
| Số mẫu pilot | 10, ID `W5_A_00001` đến `W5_A_00010` |
| Loại task | 6 QA, 2 summary, 1 hint, 1 thiếu căn cứ |
| Theo môn | 4 THMLN, 3 KTCTMLN, 3 CNXHKH |
| Nguồn | THMLN ch11 trang PDF 1–2; KTCTMLN ch03 trang 13, 22; CNXHKH ch07 trang 5 |
| Tự review nội dung | 10/10 mẫu ACCEPT cho nghiên cứu nội bộ, mỗi mẫu 10/10; B chưa duyệt |
| Sửa evidence | Hai mẫu CNXHKH 00008/00010 đã thu gọn đúng phạm vi, bỏ phần lỗi không cần thiết và sửa khoảng trắng; đối chiếu lại ký tự/trang, tính hash và review lại |
| Benchmark | Qua kiểm trùng chính xác/ngram với 199 fingerprint được bảo vệ; đã rà ý hỏi liên quan. Không coi đây là chứng minh chống mọi paraphrase |
| Quyền nguồn / review B | Chưa xác minh / B chưa duyệt |
| Đếm nghiệm thu | **10 mẫu tự duyệt cho nghiên cứu nội bộ; 0 mẫu B duyệt/release cuối** |
| Xuất SFT | Mặc định vẫn chặn `SOURCE_RIGHTS_UNVERIFIED`; xuất nghiên cứu cần cờ riêng, review hợp lệ và split plan. Chưa xuất SFT cho pilot này |
| Sẵn sàng huấn luyện | **Chưa**: chưa kiểm split chính thức, tokenizer/chat template, EOS và loss mask; chưa chạy huấn luyện |

**Ba file đầu ra riêng tư:**
- `.private/instruction/pilot/pilot.jsonl`: câu hỏi, target, evidence, trang, provenance và hash.
- `.private/instruction/pilot/reviews.csv`: ACCEPT giới hạn nghiên cứu nội bộ, nhận xét, người tự review A và hash từng mẫu; hai mẫu sửa có hash cũ tại `re_review_of`; không giả lập B duyệt.
- `.private/instruction/pilot/review-report.json`: tổng hợp, checksum/kích thước hai file trên, quyết định phạm vi nghiên cứu và các audit chưa chạy. Bản pilot/review cũ được giữ trong `before-research-update.zip` cùng thư mục.

**Chạy lại bản nháp:** giữ đầu ra riêng tư và bật cờ rõ ràng:

```powershell
python scripts/instruction/generate_candidates.py --drafts .private/instruction/drafts/member_a.jsonl --output .private/instruction/candidates/member_a.jsonl --member A --private-draft
```

Để tái lập đúng pilot hiện tại trên máy này: `python -X utf8 .private/instruction/build_pilot.py`. Script đọc PDF gốc, đóng gói các mẫu đã biên soạn và chạy kiểm tra; không gọi model hoặc tạo điểm review cho dữ liệu tùy ý. Chạy lại không thêm mẫu trùng; không tự ghi đè câu hỏi/target đã thay đổi. Phần riêng tư không được Git theo dõi.

**Khi đã có split plan hợp lệ**, có thể xuất candidate nghiên cứu bằng lệnh sau (chưa chạy lệnh này cho pilot):

```powershell
python scripts/instruction/export_sft_dataset.py --inputs .private/instruction/pilot/pilot.jsonl --reviews .private/instruction/pilot/reviews.csv --split-plan .private/instruction/split-plan.json --output .private/instruction/releases/research --internal-research
```

Manifest ghi `INTERNAL_RESEARCH_CANDIDATE_PENDING_AUDIT`, quyền chưa xác minh, không cho phép phát hành, B chưa duyệt và `training_ready=false`. Cờ nghiên cứu không bỏ qua lỗi nguồn, review cũ, split sai hoặc tự xác nhận audit chưa chạy.

**Kiểm thử sau cập nhật:** 55/55 test công cụ và 125/125 test hồi quy đạt trên CPU. Test bao phủ mặc định chặn, ngoại lệ cần bật rõ ràng, không xuất ra ngoài đường dẫn riêng tư và không bỏ qua review/split. Không dùng GPU, chưa chạy tokenizer/EOS/loss mask, chưa huấn luyện.

**Đi tiếp:** có thể mở rộng dữ liệu nghiên cứu nội bộ theo batch 25–50 sau tự review. 10 mẫu này được tính vào phần tự duyệt nội bộ của A, không phải 250 mẫu đã hoàn thành hoặc dữ liệu B đã duyệt. Trước khi train vẫn phải kiểm split/tokenizer/EOS/mask; khi bàn giao cuối, B kiểm trên đúng hash và A sửa tiếp. Quyết định nội bộ không thay thế căn cứ quyền nếu mở rộng phạm vi hoặc phát hành.

## 9. Hoàn thiện 250 mẫu A

**Bước 4 đã hoàn thành trong phạm vi nghiên cứu nội bộ:** giữ nguyên 10 pilot, bổ sung 240 mẫu thành sáu batch 40 mẫu, với số lượng cộng dồn 50 → 90 → 130 → 170 → 210 → 250. Mỗi mẫu có câu hỏi/target được biên soạn theo đoạn PDF, định danh và trang nguồn, checksum PDF/text, provenance và content hash. Không gọi Qwen/API hay dùng GPU để sinh dữ liệu.

| Môn | QA | Summary | Hint | Thiếu căn cứ | Tổng |
| --- | ---: | ---: | ---: | ---: | ---: |
| THMLN | 60 | 20 | 10 | 10 | 100 |
| KTCTMLN | 45 | 15 | 8 | 7 | 75 |
| CNXHKH | 45 | 15 | 7 | 8 | 75 |
| **Tổng** | **150** | **50** | **25** | **25** | **250** |

Đã kiểm đúng số mẫu của từng chương trong 14 PDF phân công ở contract. Các nội dung bao phủ nhiều chủ đề, ví dụ lịch sử thuật ngữ, phạm trù, nhận thức, cộng đồng người, pháp quyền/khoa học/thẩm mỹ; lịch sử học thuyết kinh tế, chi phí/lợi nhuận, sở hữu/thể chế; không tưởng phê phán, các nghĩa của chủ nghĩa xã hội, biến đổi nhóm xã hội và gia đình. Không thêm mẫu gán tác giả B hoặc đổi benchmark để đạt quota.

**Ba file đầu ra chính, giữ riêng tư:**
- `.private/instruction/candidates/member_a.jsonl`: 250 mẫu `W5_A_00001`–`W5_A_00250`; 10 mẫu đầu khớp nguyên nội dung/hash của pilot sau cập nhật bước 3.
- `.private/instruction/candidates/reviews.jsonl`: 250 tự review của A, có nhận xét riêng và ACCEPT giới hạn nghiên cứu nội bộ trên hash hiện tại.
- `.private/instruction/candidates/review-report.json`: thống kê môn/task/chương, sáu batch, kết quả kiểm và checksum/kích thước hai file trên.

**Kiểm chứng:** schema, target/citation, nguồn/trang/checksum, phân công, trùng chính xác và ngữ đoạn ký tự, hash review và quota đều qua kiểm tra. Đối chiếu với 199 fingerprint câu hỏi được bảo vệ, giữ nguyên nội dung benchmark. Đã rà các ý hỏi nguồn và những cặp gần về câu chữ; đây không phải chứng minh tuyệt đối không có mọi biến thể ngữ nghĩa. Tự review dữ liệu không phải điểm factuality của model hoặc chứng nhận B nghiệm thu.

**Chạy lại trên máy đang có nguồn và gói đầu vào:** `python -X utf8 .private/instruction/build_member.py`. Các đặc tả biên soạn nằm trong `.private/instruction/authoring/`; không lấy benchmark làm template. Chạy lại giữ ID, nội dung và review đã có; dữ liệu thay đổi sẽ bị chặn để xử lý phiên bản/review lại, không ghi đè ngầm hoặc cắt mất batch sau. Các file riêng tư không tự đi theo commit Git.

**Test công cụ:** 56/56 test đạt, gồm chạy tiếp từ batch cũ mà vẫn giữ mẫu ở batch sau; 125/125 test hồi quy provider/pipeline/guardrail/checks/evaluation đạt. Log CPU nằm ở `.private/instruction/tooling-test-results.txt` và `.private/instruction/runtime-test-results.txt`.

**Trạng thái cuối bước 4:** A có 250 mẫu tự duyệt cho nghiên cứu nội bộ; **0 mẫu B duyệt/release cuối**. Quyền nguồn vẫn `DECLARED_NOT_VERIFIED`, không phát hành. Chưa xuất gói SFT chính thức, chưa chia split, kiểm tokenizer/chat template/EOS/loss mask hoặc huấn luyện. Các bước đó và review dữ liệu B (khi B bàn giao) là công việc tiếp theo, không được suy từ việc đủ 250 mẫu là đã hoàn thành.

## 10. Xuất và kiểm gói SFT của A

**Bước 6 hoàn thành cho 250 mẫu A trong phạm vi nghiên cứu nội bộ.** Không bao gồm dữ liệu B, không tính bước 5 đã xong, không phải release 500 mẫu của nhóm. A tự review; B kiểm sau cùng và A sửa theo kết quả đó. Các trạng thái chưa audit ở mục 7–9 là lịch sử trước bước này.

### Chia tập theo nhóm nguồn

Giữ nguyên 14 component nguồn: cùng tài liệu/mọi phiên bản, họ biến thể, parent và liên kết nhiều nguồn không đi sang tập khác. Seed 42, mục tiêu 80/10/10; chọn phương án theo sai lệch số mẫu, môn và task, không xé chương để ép đúng tỷ lệ.

| Tập | THMLN | KTCTMLN | CNXHKH | Tổng | Tỷ lệ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train | 86 | 50 | 57 | 193 | 77,2% |
| Validation | 14 | 0 | 18 | 32 | 12,8% |
| Instruction holdout | 0 | 25 | 0 | 25 | 10,0% |

| Tập | QA | Summary | Hint | Thiếu căn cứ |
| --- | ---: | ---: | ---: | ---: |
| Train | 116 | 39 | 19 | 19 |
| Validation | 19 | 6 | 3 | 4 |
| Instruction holdout | 15 | 5 | 3 | 2 |

**Giới hạn:** validation thiếu KTCTMLN, holdout chỉ có KTCTMLN; không dùng kết quả này để kết luận chất lượng cả ba môn. Khi nhận dữ liệu B, phải chia lại toàn bộ theo component và audit lại, không nối hai bộ split riêng. Holdout không dùng chọn cấu hình và không thay benchmark QA độc lập.

### Tokenizer và nhãn huấn luyện

Dùng tokenizer thật `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`, Transformers `4.57.6`. Chỉ tải file tokenizer/config, kiểm revision và checksum; không tải trọng số hoặc nạp model.

| Kiểm tra | Kết quả |
| --- | --- |
| Số mẫu kiểm thực tế | 250/250 đạt |
| Prompt dài nhất / giới hạn | 1.533 / 3.072 token |
| Completion dài nhất, kể cả định dạng / giới hạn | 87 / 768 token |
| Toàn chuỗi dài nhất / giới hạn | 1.602 / 4.096 token |
| Chat template | Khớp prefix văn bản và token; giải mã target khớp nguyên nội dung |
| EOS | Đúng một EOS trong completion; EOS được tính loss |
| Loss mask | Chỉ target và EOS có nhãn; prompt, định dạng sau EOS và padding là `-100` |
| Batch padding | Đệm phải theo bội số 8; padding có attention 0, không làm mất EOS thật |
| Cắt nội dung | Không cắt ngầm, vượt ngân sách sẽ báo lỗi |
| Huấn luyện / GPU | Chưa huấn luyện / không dùng GPU |

Nhãn không được dịch trước một vị trí; causal LM sẽ xử lý dịch nhãn khi tính loss. Không giả định thư viện trainer tự hỗ trợ assistant-only loss. Cấu hình trainer/QLoRA và khả năng học thực tế chưa được kiểm trong bước này.

### Gói đầu ra và minh chứng

Thư mục riêng tư: `.private/instruction/releases/member_a/`, gồm **11 file**:

| File | Vai trò |
| --- | --- |
| `train.jsonl`, `validation.jsonl`, `instruction_holdout.jsonl` | Prompt/completion đúng chat roles, giữ nguyên target đã duyệt |
| `tokenized/train.jsonl`, `tokenized/validation.jsonl`, `tokenized/instruction_holdout.jsonl` | Token IDs, attention mask và labels đã kiểm |
| `metadata.jsonl` | Nguồn, trang, hash và liên kết từng dòng với mẫu gốc |
| `split-plan.json` | Phân tập theo ID/hash, phân bố và phương pháp chọn component |
| `tokenization-audit.json` | Tokenizer, template, số token và kiểm tra từng mẫu |
| `input-contract.snapshot.json` | Chụp contract đầu vào đúng lúc đóng gói |
| `manifest.json` | Phạm vi, trạng thái và SHA-256/kích thước 10 file còn lại |

Manifest không hash chính nó. Các cập nhật trạng thái trong contract làm việc sau khi audit không sửa snapshot đã đóng gói; khi kiểm tính toàn vẹn phải đối chiếu snapshot trong gói.

**Kiểm chứng lại từ file đã lưu:** đọc lại 250 mẫu và review đúng hash, kiểm 10 checksum/kích thước, tính lại toàn bộ token/labels bằng tokenizer thật, đối chiếu metadata và kiểm lại batch. Kết quả `PASSED` tại `.private/instruction/sft-verification.json`; manifest SHA-256 `3b8ff2c1c874ba42554d19327417d35e3d6441b43c477e5a956257880f975b31`.

**Kiểm thử:** 71/71 test công cụ và 125/125 test hồi quy runtime đạt. Test bao phủ tách nhóm, tính quyết định của split, EOS, roundtrip, ngân sách, mask, padding khi PAD trùng EOS, sửa tokenizer sai revision/checksum và không công bố gói sẵn sàng nếu audit lỗi. Log vẫn ở `.private/instruction/tooling-test-results.txt`, `.private/instruction/runtime-test-results.txt`; tổng hợp `.private/instruction/tooling-verification.json`.

### Cách kiểm lại

Trên máy hiện tại đã có nguồn, ZIP đầu vào và tokenizer riêng:

```powershell
python -X utf8 .private/instruction/verify_sft.py
```

Đóng gói lại sang thư mục **mới** bằng `.private/instruction/run_sft.py <duong-dan-goi-moi>`. Không ghi đè gói đã audit. Helper dùng môi trường tokenizer riêng tại `.private/instruction/tokenizer-runtime`; không cần Torch/GPU. Công cụ chính để tái lập trên môi trường có đúng dependency là:

```powershell
python scripts/instruction/prepare_sft.py --records .private/instruction/candidates/member_a.jsonl --reviews .private/instruction/candidates/reviews.jsonl --tokenizer .private/instruction/tokenizer --output .private/instruction/releases/member_a_new
```

Các file `.private/` không đi theo Git: cần bàn giao riêng cả dữ liệu/review, tokenizer có metadata revision, nguồn và ZIP đầu vào để tái lập. Công cụ sẽ chặn thiếu đầu vào, nguồn sai checksum hoặc gói đích đã tồn tại.

**Kết luận:** `MEMBER_A_INTERNAL_RESEARCH_TECHNICALLY_AUDITED`; `training_ready=true` chỉ nói **dữ liệu đã qua kiểm kỹ thuật cho thử nghiệm nội bộ**, không xác nhận trainer/QLoRA, chất lượng model, quyền nguồn hoặc nghiệm thu nhóm. Quyền vẫn `DECLARED_NOT_VERIFIED`, không phát hành công khai. Huấn luyện `NOT_RUN`, review dữ liệu B `PENDING_INPUT`, B duyệt cuối `PENDING`. Bước tiếp theo là hoàn thiện dataset card và bàn giao phần A; review B và tích hợp nhóm được làm khi có đầu vào.

## 11. Bàn giao phần A

**Đã chuẩn bị phần còn lại của bước 7:** dataset card v2.0, gói riêng tư, checksum, minh chứng, demo kiểm lại và hướng dẫn cho máy mới. Đây là trạng thái chuẩn bị bàn giao, không phải B đã nhận/duyệt hoặc PR đã được review. Không tạo commit, PR hoặc tag tự động.

| Đầu ra | Vị trí |
| --- | --- |
| Dataset card | `docs/dataset-card-v2.0.md`, giữ nguyên bản v1.0 |
| ZIP riêng tư | `.private/instruction/handoff/member-a-handoff.zip` |
| SHA-256 ZIP và kết quả tự kiểm | `.private/instruction/handoff/receipt.json` |
| Manifest từng file | `handoff-manifest.json` ở gốc ZIP |
| Minh chứng để đưa vào Git | `Evidence/W05/README.md`, `metrics.csv`, `test-results.json`, `manifest.json` |

ZIP chứa mẫu/review, gói SFT nguyên trạng, nguồn PDF A cần đối chiếu, ZIP đầu vào, tokenizer cùng metadata revision, mã công cụ/test/runtime cần thiết, đặc tả biên soạn và tài liệu. Không kèm trọng số Qwen, môi trường cài sẵn, token, `.env`, cache tùy tiện hoặc dữ liệu B. Benchmark chỉ dùng làm đầu vào kiểm loại trừ, không xuất làm mẫu train. Gói có nội dung nguồn chưa xác minh quyền, **chỉ chuyển riêng cho B trong phạm vi nội bộ**, không đính kèm vào PR công khai.

### B kiểm trên máy mới

1. Nhận ZIP qua kênh riêng và nhận SHA-256 từ `receipt.json` qua kênh đối chiếu riêng. Mã kiểm lấy từ nhánh/commit bàn giao đã đối chiếu, không chạy mã từ ZIP chưa kiểm.
2. Tại repo, chạy kiểm tính toàn vẹn bằng Python chuẩn, không cần GPU hoặc dependency:

```powershell
python scripts/instruction/verify_handoff.py --archive "D:\Downloads\member-a-handoff.zip" --sha256 "<SHA256_DUONG_GUI>"
```

Lệnh kiểm hash ZIP, danh mục, kích thước/hash từng file và chặn đường dẫn bất thường; **không giải nén, không thực thi nội dung và không chấm chất lượng**. Hash chỉ có ý nghĩa khi B đã nhận đúng từ A, không tự chứng minh người gửi.

3. Sau khi kiểm đạt, giải nén vào thư mục mới, không ghi đè repo hoặc gói đang dùng. Mở terminal tại gốc thư mục vừa giải nén. Dùng Python 3.13 như môi trường đã kiểm, tạo môi trường riêng và cài dependency:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scripts/instruction/requirements.txt tokenizers==0.22.2
.\.venv\Scripts\python.exe -X utf8 .private/instruction/verify_sft.py
```

Cài dependency cần Internet lần đầu; tokenizer đã ở trong ZIP nên bước kiểm lại không tải model/tokenizer hoặc cần tài khoản Kaggle. Script dùng CPU, đọc snapshot contract trong gói SFT và đối chiếu nguồn, review, split, template, token/labels, batch padding của 250 mẫu. Kỳ vọng `PASSED`, số mẫu 250, split 193/32/25, 14 component, 10 file hash của gói SFT khớp; model/GPU không dùng, training `NOT_RUN`. Đây cũng là **demo kỹ thuật đã thực hiện**, không phải demo suy luận model hoặc QLoRA đã học.

4. Có thể chạy lại test công cụ:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s scripts/instruction/tests -v
```

Kết quả hiện tại: **77/77 test công cụ, 125/125 test hồi quy đạt**. Log chi tiết giữ trong ZIP; `Evidence/W05/test-results.json` chỉ lưu tổng hợp/hash và kết quả demo, không chứa câu hỏi, target hay đoạn PDF.

### B cần kiểm và A xử lý tiếp

- Review nội dung 250 mẫu A: kiến thức, evidence/trang, citation, hint không lộ đáp án và thiếu căn cứ đúng; ghi PEER_REVIEW của B trên đúng content hash, không lấy điểm SELF_REVIEW làm nghiệm thu B.
- Xem phân bố/split: validation thiếu KTCTMLN, holdout chỉ KTCTMLN; không tuyên bố đánh giá đủ ba môn. Khi có dữ liệu B, A review phần B rồi tạo split chung và audit lại.
- Kiểm contract, schema, provenance, benchmark exclusion, tokenizer/template/EOS/mask và manifest đúng phiên bản. Nguồn vẫn chưa xác minh quyền; không đổi trạng thái đó chỉ vì B nhận gói.
- Gửi lỗi theo ID/hash, tiêu chí, lý do và đề nghị sửa. A sửa mẫu, tính hash/review lại, tái xuất gói mới và kiểm lại; giữ gói cũ để truy vết.
- Tích hợp và review PR qua milestone `Tuan5`. Chỉ chốt tag `w05` sau kiểm chung; bản này chưa tạo PR, tag, xác nhận B duyệt hoặc chạy training.

**Phần việc sẵn sàng gửi B:** công cụ CPU, 250 mẫu A tự review, gói SFT đã audit, dataset card v2.0, gói chuyển riêng và minh chứng. **Phần chưa hoàn thành:** chuyển file thực tế cho B, B review cuối, review/tích hợp dữ liệu B, PR review/tag và huấn luyện (ngoài phạm vi chuẩn bị dữ liệu hiện tại).
