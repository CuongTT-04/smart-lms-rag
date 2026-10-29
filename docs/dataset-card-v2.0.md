# Dataset Card v2.0

## 1. Tổng quan

| Nội dung | Thông tin |
| --- | --- |
| Tên | SmartLMS AI-RAG Course Corpus & Instruction Dataset |
| Phiên bản / ngày cập nhật | v2.0 / 28/10/2026 |
| Bản trước | [Dataset card v1.0](dataset-card.md), giữ nguyên |
| Ngôn ngữ | Tiếng Việt |
| Corpus kế thừa | 27 PDF: 14 THMLN, 6 KTCTMLN, 7 CNXHKH |
| Instruction hiện có | 250 mẫu A, sử dụng 14 PDF được phân công |
| Mục đích | Chuẩn bị dữ liệu SFT cho thử nghiệm QLoRA nội bộ, phục vụ trả lời có căn cứ, tóm tắt, gợi ý và từ chối khi thiếu căn cứ |
| Trạng thái | A tự duyệt và kiểm kỹ thuật; B chưa duyệt cuối; chưa huấn luyện |

v2.0 bổ sung lớp dữ liệu instruction và gói SFT trên corpus v1.0, không tuyên bố thay đổi hoặc cấp phép lại các PDF. Mục tiêu nhóm là 500 mẫu, nhưng bản hiện tại **chỉ có 250 mẫu A**, không tính dữ liệu B chưa bàn giao.

## 2. Nguồn và phạm vi sử dụng

Nguồn PDF sưu tầm từ các liên kết chia sẻ không chính thức. Quyền nội dung thuộc chủ sở hữu gốc; trạng thái quyền vẫn là `DECLARED_NOT_VERIFIED`. Khả năng truy cập liên kết và cam kết nghiên cứu phi thương mại không phải bằng chứng đã được chủ sở hữu cấp phép.

A ghi nhận quyết định tiếp tục thử nghiệm nghiên cứu/học tập phi thương mại **nội bộ**, lưu dữ liệu trong `.private/instruction/`. Quyết định này không xác minh quyền nguồn; không cho phép phát hành công khai corpus, instruction hoặc adapter từ dữ liệu này. Nếu mở rộng phạm vi, cần xem xét lại căn cứ quyền trước khi sử dụng.

Nguồn A: THMLN các chương 01, 03, 05, 07, 09, 11, 13; KTCTMLN các chương 01, 03, 05; CNXHKH các chương 01, 03, 05, 07. Phạm vi trang và quota từng chương nằm trong [contract làm việc](../data/instruction/input-contract.json).

## 3. Thành phần dữ liệu

| Môn | QA | Tóm tắt | Gợi ý | Thiếu căn cứ | Tổng |
| --- | ---: | ---: | ---: | ---: | ---: |
| THMLN | 60 | 20 | 10 | 10 | 100 |
| KTCTMLN | 45 | 15 | 8 | 7 | 75 |
| CNXHKH | 45 | 15 | 7 | 8 | 75 |
| **Tổng** | **150** | **50** | **25** | **25** | **250** |

Đây là 250 mẫu instruction gồm nhiều loại tác vụ, **không phải bộ benchmark 150 QA** đã dùng đánh giá model. ID giữ theo schema đã thống nhất: `W5_A_00001` đến `W5_A_00250`.

Mỗi mẫu lưu câu hỏi/instruction, target, môn, tác giả, evidence, định danh tài liệu/phiên bản/trang, provenance và SHA-256 nội dung. Schema tại [record-schema.json](../data/instruction/record-schema.json). Review tách riêng và gắn với đúng hash; thay nội dung phải review lại.

## 4. Biên soạn và kiểm chất lượng

Quy trình: chọn đoạn PDF trong phân công, biên soạn câu hỏi và target, kiểm nguồn/trang/hash, kiểm định dạng và trùng, tự review nội dung rồi đóng gói. Giữ nguyên 10 pilot; bổ sung 240 mẫu theo sáu batch 40. Không dùng model/API để sinh các mẫu này.

- QA và summary: tiếng Việt, có trích dẫn theo vị trí evidence; không xuất API JSON vào completion.
- Hint: action `READ [n]`, `OUTLINE [n]` hoặc `COMPARE [n] [m]`, không đưa đáp án cuối vào target hint.
- Thiếu căn cứ: target `INSUFFICIENT_EVIDENCE`.
- 250 mẫu có SELF_REVIEW ACCEPT của A trên hash hiện tại. Rubric tối thiểu 9/10, không tiêu chí 0; nội dung, grounding/citation và hành vi task phải đạt 2/2.
- Kiểm trùng chính xác/ngữ đoạn với 199 fingerprint câu hỏi được bảo vệ và rà ý hỏi liên quan. Không sử dụng gold benchmark làm nguyên liệu; kiểm này không chứng minh loại bỏ mọi paraphrase hoặc leakage ngữ nghĩa.

Tự review và kiểm schema không phải xác nhận chất lượng model, quyền nguồn hoặc B nghiệm thu. Công cụ không tự cấp ACCEPT cho nội dung tùy ý.

## 5. Chia tập

Seed 42, mục tiêu 80/10/10. Chia nguyên component liên kết nguồn/tài liệu mọi phiên bản, biến thể và parent; không tách chương để ép số lượng.

| Tập | THMLN | KTCTMLN | CNXHKH | Tổng |
| --- | ---: | ---: | ---: | ---: |
| Train | 86 | 50 | 57 | 193 |
| Validation | 14 | 0 | 18 | 32 |
| Instruction holdout | 0 | 25 | 0 | 25 |

14 component không giao nhau giữa các tập. Tỷ lệ thực tế 77,2% / 12,8% / 10%. **Validation thiếu KTCTMLN; holdout chỉ có KTCTMLN**, nên không đại diện đánh giá cả ba môn. Holdout không dùng chọn cấu hình và không thay benchmark độc lập. Khi ghép dữ liệu A/B phải chia nhóm và audit lại toàn bộ, không nối các split riêng.

## 6. Định dạng SFT và kiểm kỹ thuật

Model/tokenizer đích `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`; Transformers `4.57.6`. Prompt dùng builder hiện có với phiên bản `bounded_guidance`, roles system/user; completion là assistant. Không đưa target, rubric hoặc review vào prompt.

| Kiểm tra bằng tokenizer thật | Kết quả |
| --- | --- |
| Số mẫu đạt | 250/250 |
| Prompt tối đa / ngân sách | 1.533 / 3.072 token |
| Completion kể cả định dạng tối đa / ngân sách | 87 / 768 token |
| Toàn chuỗi tối đa / ngân sách | 1.602 / 4.096 token |
| Template / target | Khớp prefix token và giải mã ngược target |
| EOS / loss | Một EOS trong completion; chỉ target và EOS được tính loss |
| Prompt / padding | Labels `-100`; padding phải theo bội số 8, attention 0 |
| Cắt ngầm | Không cho phép |

Đã kiểm bằng CPU, chỉ tải tokenizer/config, không tải trọng số hoặc nạp model. Sau bổ sung công cụ kiểm bàn giao: 77/77 test công cụ và 125/125 test hồi quy runtime đạt. Đã mở lại gói, kiểm checksum và tính lại token/labels của cả 250 mẫu. Chưa kiểm trainer/QLoRA thực chạy hoặc huấn luyện.

## 7. Artifact và tái lập

Các đường dẫn dưới đây tính từ gốc dự án; dữ liệu riêng tư không đi theo Git.

| Artifact | Đường dẫn |
| --- | --- |
| Mẫu gốc / review / báo cáo | `.private/instruction/candidates/member_a.jsonl`, `reviews.jsonl`, `review-report.json` |
| Gói SFT | `.private/instruction/releases/member_a/` |
| Kết quả kiểm lại | `.private/instruction/sft-verification.json` |
| Gói bàn giao riêng tư / checksum | `.private/instruction/handoff/member-a-handoff.zip`, `receipt.json` |
| Minh chứng tóm tắt, không chứa mẫu | `Evidence/W05/` |
| Log test | `.private/instruction/tooling-test-results.txt`, `.private/instruction/runtime-test-results.txt` |
| Công cụ chuẩn bị | `scripts/instruction/prepare_sft.py` |
| Quyết định và quy trình chi tiết | [instruction-input-review.md](instruction-input-review.md), mục 10 |

Gói SFT có 11 file: ba tập prompt/completion; ba tập tokenized chứa token IDs, attention mask và labels; `metadata.jsonl`; `split-plan.json`; `tokenization-audit.json`; `input-contract.snapshot.json`; `manifest.json`. Manifest ghi hash/kích thước 10 file còn lại, không hash chính nó. Kiểm gói theo snapshot contract đã lưu, không theo trạng thái cập nhật sau này của contract làm việc.

SHA-256 manifest hiện tại: `3b8ff2c1c874ba42554d19327417d35e3d6441b43c477e5a956257880f975b31`.

Trên máy đã có đầy đủ đầu vào riêng tư, kiểm lại bằng `python -X utf8 .private/instruction/verify_sft.py`. Tái lập trên máy khác cần bàn giao riêng nguồn, ZIP đầu vào, mẫu/review và tokenizer đúng revision cùng metadata; cài dependency tại `scripts/instruction/requirements.txt`. Không ghi đè gói đã audit.

## 8. Giới hạn và trạng thái bàn giao

- `training_ready=true` chỉ là dữ liệu đạt audit kỹ thuật cho thử nghiệm nội bộ, không phải đã huấn luyện, trainer đã chạy đúng hoặc model tốt hơn.
- Chưa có kết quả học, factuality sau fine-tune, hiệu quả QLoRA hay kiểm phân quyền DB/API từ bộ dữ liệu này.
- Dữ liệu chọn từ phạm vi nguồn A, độ phủ và ngôn ngữ PDF có giới hạn; split hiện lệch môn như mục 5.
- Quyền nguồn chưa xác minh; không phát hành công khai. B chưa duyệt cuối, review dữ liệu B đang chờ đầu vào; chưa nghiệm thu bộ 500 mẫu.
- Gói bàn giao A đã chuẩn bị; hướng dẫn kiểm trên máy mới và checklist B nằm ở mục 11 của tài liệu tổng hợp. Chưa gửi gói, tạo PR hoặc tag. Tiếp theo: chuyển riêng gói cho B, sửa theo review, tích hợp dữ liệu nhóm rồi audit lại phần thay đổi trước thử nghiệm huấn luyện.

## Tiếp nhận trên máy B ngày29/10/2026

Đã nhận ZIP và kiểm lại kỹ thuật trên CPU:250 mẫu,163 file bàn giao,10 file SFT và token/labels/padding đạt. Công cụ đã được kiểm lại với workspace hiện tại. Kết quả rà soát sơ bộ bằng công cụ đề nghị sửa W5_A_00116, W5_A_00139, W5_A_00146; chưa có human B approval hoặc group acceptance. Xem [báo cáo tiếp nhận](weekly/W5/tiep-nhan-member-a.md), receipt-verification và test-results trong Evidence/W05. Gói gốc và SELF_REVIEW giữ nguyên; cần A sửa/tái xuất rồi review lại hash mới. Chưa chia lại bộ500, chưa train.

## Cập nhật bộ chung29/10/2026

Đã tạo và audit CPU500 candidate, split385/57/58 đủ ba môn trong từng tập,3 bản sửa A có hash mới. Xem docs/weekly/W5/ket-qua-tich-hop-w5.md. Gói gốc giữ nguyên; peer confirmations vẫn cần thật, chưa train hoặc nghiệm thu nhóm.
