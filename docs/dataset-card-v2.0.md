# OHAYO Instruction Dataset v2.0

## 1. Tổng quan

OHAYO Instruction là bộ dữ liệu tiếng Việt của dự án SmartLMS AI-RAG, dùng để chuẩn bị huấn luyện có giám sát (SFT) và thử nghiệm QLoRA cho trợ lý học tập trả lời dựa trên tài liệu.

| Thuộc tính | Thông tin |
| --- | --- |
| Phiên bản / cập nhật | v2.0 / 30/10/2026 |
| Ngôn ngữ | Tiếng Việt |
| Quy mô | 500 mẫu instruction từ 27 PDF |
| Lĩnh vực | Triết học Mác – Lênin (THMLN), Kinh tế chính trị Mác – Lênin (KTCTMLN), Chủ nghĩa xã hội khoa học (CNXHKH) |
| Model đích | `Qwen/Qwen2.5-7B-Instruct` |
| Định dạng | JSONL, conversational prompt/completion |
| Trạng thái | Bản ứng viên hoàn thiện kỹ thuật cho nghiên cứu nội bộ; chưa phải bản phát hành công khai |
| Huấn luyện | Chưa huấn luyện QLoRA; chưa có kết quả sau fine-tune |

v2.0 kế thừa corpus trong [dataset card v1.0](dataset-card.md), bổ sung instruction và bộ SFT đã chia tập. **500 mẫu instruction không phải benchmark 150 QA** dùng đánh giá mô hình.

## 2. Nguồn và phạm vi sử dụng

Corpus gồm 14 PDF THMLN, 6 PDF KTCTMLN và 7 PDF CNXHKH, được sưu tầm từ các liên kết chia sẻ. Instruction được biên soạn dựa trên đoạn trích cụ thể, không bổ sung kiến thức ngoài để bù phần nguồn thiếu.

Mỗi đoạn có định danh tài liệu/phiên bản, số trang vật lý trong PDF và SHA-256 để truy nguyên. Văn bản nguồn giữ dấu vết bản gốc; kiểm vị trí trang chỉ chuẩn hóa Unicode và khoảng trắng, không sửa nội dung để khớp nguồn.

**Quyền nguồn: `DECLARED_NOT_VERIFIED`.** Truy cập được liên kết không đồng nghĩa được cấp phép huấn luyện hoặc tái phân phối. Phạm vi dự án ghi nhận là nghiên cứu, học tập phi thương mại nội bộ; đây không phải giấy phép của chủ sở hữu tài liệu.

- Lưu và chia sẻ qua kho riêng tư có kiểm soát truy cập.
- Không phát hành công khai corpus, instruction hoặc sản phẩm phái sinh khi chưa làm rõ quyền tương ứng.
- Khi thay đổi mục đích hoặc phạm vi sử dụng, cần đánh giá lại căn cứ quyền nguồn.

## 3. Thành phần và hành vi đầu ra

| Môn học | QA | Tóm tắt | Gợi ý | Thiếu căn cứ | Tổng |
| --- | ---: | ---: | ---: | ---: | ---: |
| THMLN | 120 | 40 | 20 | 20 | 200 |
| KTCTMLN | 90 | 30 | 16 | 14 | 150 |
| CNXHKH | 90 | 30 | 14 | 16 | 150 |
| **Tổng** | **300** | **100** | **50** | **50** | **500** |

- **QA:** trả lời trực tiếp bằng tiếng Việt, gắn `[1]`, `[2]` theo evidence thực sự hỗ trợ phát biểu.
- **Tóm tắt:** giữ ý chính của nguồn, không thêm nhận định ngoài căn cứ; có citation tương ứng.
- **Gợi ý:** target là `READ [n]`, `OUTLINE [n]` hoặc `COMPARE [n] [m]`, không chứa đáp án cuối. Đây là hành động cho pipeline, không phải đoạn gợi ý hoàn chỉnh để hiển thị trực tiếp.
- **Thiếu căn cứ:** chỉ xuất `INSUFFICIENT_EVIDENCE`.

## 4. Cấu trúc và biên soạn

Mỗi dòng SFT có hai trường:

| Trường | Nội dung |
| --- | --- |
| `prompt` | Message `system` và `user`, chứa yêu cầu, evidence và thông tin bài tập công khai nếu có |
| `completion` | Một message `assistant` chứa target mong đợi |

Prompt sử dụng phiên bản `bounded_guidance`. Target, rubric, review và metadata quản lý không được thêm vào prompt như thông tin đầu vào.

Quy trình: chọn đoạn PDF → viết yêu cầu/target → thử trên 20 mẫu pilot → mở rộng → kiểm nguồn và nội dung → sửa, cập nhật hash → chia tập → xuất và audit. Review gắn với hash; thay nội dung phải kiểm và review lại.

Metadata tách riêng gồm ID, hash nội dung, split, vị trí dòng, hash SFT, môn/tác vụ và thông tin nguồn. ID có tiền tố lịch sử được giữ ổn định để truy nguyên, không phải dữ liệu cần đưa vào mô hình. Schema bản ghi đầy đủ: [record-schema.json](../data/instruction/record-schema.json).

## 5. Chia tập và chống leakage

Seed **42**; chia nguyên **27 component liên kết nguồn**, bao gồm quan hệ tài liệu/phiên bản, biến thể và mẫu cha. Không tách cùng nhóm sang nhiều tập để ép đúng tỷ lệ.

| Tập | THMLN | KTCTMLN | CNXHKH | Tổng | Tỷ lệ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train | 172 | 100 | 113 | **385** | 77,0% |
| Validation | 14 | 25 | 18 | **57** | 11,4% |
| Instruction holdout | 14 | 25 | 19 | **58** | 11,6% |

Mỗi tập có đủ ba môn và bốn loại tác vụ. 80/10/10 là mục tiêu gần đúng; ưu tiên không giao nhóm nguồn và duy trì độ phủ môn học.

Validation dùng theo dõi và chọn cấu hình. Instruction holdout chỉ đánh giá sau cùng, không dùng train hoặc chọn cấu hình; không thay benchmark 150 QA độc lập.

Kiểm chống leakage gồm ID, câu hỏi/target được bảo vệ và sàng lọc trùng/gần trùng; danh mục có 199 fingerprint câu hỏi được bảo vệ. Không sử dụng gold benchmark hoặc biến thể làm mẫu huấn luyện. Các kiểm tra này không bảo đảm phát hiện mọi trùng ngữ nghĩa hoặc mọi giao nhau về chủ đề/trang nguồn.

## 6. Kiểm định

| Hạng mục | Kết quả hiện có |
| --- | --- |
| Pilot nội dung | 20/20 mẫu hiện tại được đọc, đánh giá theo nguồn; không có yêu cầu sửa hoặc loại |
| Cấu trúc, nguồn và benchmark screening | 500 mẫu được kiểm bằng công cụ trên gói đầy đủ |
| Token hóa | 500/500 mẫu được audit bằng tokenizer thật đúng revision, kiểm lại token/EOS/labels |
| Chia tập | 385/57/58 mẫu; 27 component không giao tập |
| Đọc lại gói đầy đủ | Mở lại và kiểm 12 tệp payload |
| ZIP rút gọn | 6 file; checksum, số mẫu, metadata và SFT khớp bản đã audit |
| Kiểm thử công cụ/runtime | 248 test CPU đạt trong đợt kiểm tích hợp gần nhất |

Rubric gồm độ rõ yêu cầu, độ đúng, grounding/citation, hành vi tác vụ và ngôn ngữ/định dạng. Ngưỡng chấp nhận: ít nhất 9/10, không tiêu chí 0; độ đúng, grounding/citation và hành vi phải đạt 2/2.

Kiểm kỹ thuật không tự chấm chất lượng ngữ nghĩa. Đọc 20 mẫu pilot không được suy rộng thành nghiệm thu nội dung độc lập của cả 500 mẫu. Trạng thái nghiệm thu trong gói đóng băng được giữ nguyên; không suy ra chữ ký nghiệm thu từ kết quả máy kiểm.

## 7. Chuẩn bị huấn luyện

Model/tokenizer: `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`. Môi trường token hóa tham chiếu: Transformers `4.57.6`, tokenizers `0.22.2`, huggingface-hub `0.36.2`.

| Tham số dữ liệu | Giá trị |
| --- | --- |
| Ngân sách prompt / completion / toàn chuỗi | 3.072 / 768 / 4.096 token |
| Chat template | Template tokenizer đúng revision |
| Loss | Chỉ completion và EOS của completion |
| Labels prompt, padding, định dạng sau EOS | `-100` |
| EOS / PAD ID | `151645` / `151643` |
| Padding | Bên phải, bội số 8; attention padding bằng 0 |
| Cắt ngầm | Không cho phép |

Nạp JSONL bằng công cụ hỗ trợ conversational prompt/completion. Không nối nội dung message bằng tay, không tính loss trên prompt, không dịch labels hai lần. Nếu đổi tokenizer/collator hoặc bật packing, phải kiểm lại ranh giới mẫu và mask.

Gói rút gọn không kèm tokenized files vì có thể tạo lại. **Phải token hóa và kiểm token/EOS/mask trước huấn luyện.** Model weights, tokenizer assets, trainer và cấu hình QLoRA được chuẩn bị riêng; dataset không phải chương trình huấn luyện độc lập.

## 8. Phân phối và minh chứng

Dữ liệu SFT của 500 mẫu sau khi xuất được phân phối qua các file sau::

| File | Vai trò |
| --- | --- |
| `train.jsonl` | 385 mẫu huấn luyện |
| `validation.jsonl` | 57 mẫu validation |
| `instruction_holdout.jsonl` | 58 mẫu đánh giá giữ riêng |
| `metadata.jsonl` | 500 dòng metadata truy nguyên, không đưa vào prompt |
| `dataset-config.json` | Tokenizer, ngân sách token, preprocessing và phạm vi sử dụng |
| `manifest.json` | SHA-256 và kích thước các file còn lại, không tự hash chính nó |

Các file này được nén lại bằng 1 file ZIP nằm ngoài dự án, phục vụ cho việc tái sử dụng. ZIP không chứa PDF, model, bản nháp, review chi tiết hoặc log. Gói lưu trữ đầy đủ được giữ riêng để truy nguyên và tái kiểm nguồn.

## 9. Giới hạn

- Dữ liệu nhỏ, chỉ bao phủ ba môn và tài liệu đã chọn; không đại diện mọi câu hỏi hoặc cách diễn đạt.
- Độ đúng được đánh giá theo nguồn, không phải kiểm chứng độc lập mọi phát biểu ngoài thực tế. Nguồn có thể chứa lỗi OCR hoặc hạn chế của tài liệu gốc.
- Citation hoặc khớp trang không đủ chứng minh mọi phát biểu được hỗ trợ; kiểm trùng không bảo đảm loại hết leakage ngữ nghĩa.
- Chưa có kết quả trainer thực chạy, chất lượng sau QLoRA, factuality sau fine-tune hoặc tác động tới độ trễ. Dataset không chứng minh phân quyền DB/API hoặc khả năng chống prompt injection của ứng dụng.
- Quyền nguồn chưa xác minh. Hoàn thiện kỹ thuật không tự biến dữ liệu thành bản được cấp phép hoặc nghiệm thu công khai.
