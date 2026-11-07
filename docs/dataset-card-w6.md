# Dataset card — W6 group technical candidate

Phiên bản: 1.000 mẫu, ứng viên kỹ thuật ngày 06/11/2026. **Không phải bản phát hành đã được hai thành viên nghiệm thu; chưa train trên 1.000 mẫu.**

## Thành phần và phân chia

| Nguồn | Số mẫu | Train | Validation | Instruction holdout |
|---|---:|---:|---:|---:|
| W5 từ ZIP đã khóa | 500 | 385 | 57 | 58 |
| W6 Dương — A | 250 | 199 | 18 | 33 |
| W6 Cường — B | 250 | 186 | 39 | 25 |
| Tổng | 1.000 | 770 | 114 | 116 |

Tổng task: 600 QA, 200 summary, 100 hint, 100 insufficient-evidence. Tổng môn: 400 THMLN, 300 KTCTMLN, 300 CNXHKH. Các số là số record, không phải số tài liệu hay số lượt review.

250 mẫu B theo đúng allocation chẵn đã khóa: 150 QA/50 summary/25 hint/25 thiếu căn cứ; 100 THMLN/75 KTCTMLN/75 CNXHKH. Không tạo nội dung mang tác giả A thay Dương. Trường owner xác định phần việc; trường provenance xác định cách biên soạn.

## Tạo mẫu và chất lượng

Dương bàn giao 250 mẫu A kèm spec, source/page/hash, SELF_REVIEW và SFT. Tiếp nhận đã dựng lại từ nguồn PDF và kiểm kỹ thuật cả 250 mẫu trên 60 trang vật lý.

Mẫu B được biên soạn có hỗ trợ, chọn đoạn mới trực tiếp từ PDF, viết lại 150 câu QA theo nội dung cụ thể, sửa 5 lựa chọn nguồn không hoàn chỉnh và disambiguate anchor lặp. Provenance giữ `model_assisted`; không ghi thành biên soạn thủ công hay human peer approval. `AUTOMATED_REVIEW` là kết quả công cụ, còn xác nhận nội dung của owner/peer chưa được tạo. File `self-review.jsonl` giữ tên tương thích công cụ; xem `review_kind` để biết loại review thực tế.

Phiên bản B v2 thay ba summary thiếu tiền ngữ `W6_B_00025`, `W6_B_00145`, `W6_B_00194`, với context mới tự đủ nghĩa và tóm tắt tương ứng. Revision log giữ hash cũ/mới; v1 không bị sửa. Đã xuất lại và kiểm bộ chung v2; số lượng và split không thay đổi.

Giới hạn cần review kỹ trước W7: summary B hiện là tóm tắt trích chọn một luận điểm, thường gần nguyên văn; nhiều câu dựa vào một đoạn ngắn, chưa bao phủ câu hỏi liên trang hoặc hội thoại nối tiếp. Hint B tập trung hành động READ; mẫu thiếu căn cứ chủ yếu hỏi số liệu năm 2025 không có trong đoạn. Đây là thiên lệch recipe, cần đa dạng hóa ở lượt chất lượng, không dùng số lượng để khẳng định độ phủ ứng dụng. Một số khoảng trắng OCR vẫn có trong nguồn để giữ provenance; không tự suy diễn thuật ngữ còn mơ hồ.

## Format và loss

500 payload W5 kế thừa được giữ nguyên từ ZIP xác thực, kể cả định dạng cũ. 500 mẫu mới dùng evidence ID cho QA/summary, `items:[]` cho thiếu căn cứ và action cho hint. **Bộ 1.000 hiện hỗn hợp format, `training_ready=false`.** Đây là cách bảo toàn đầu vào đã khóa, không âm thầm đổi target cũ.

Trước huấn luyện nhóm ở W7 cần version mới chuyển đồng nhất 500 mẫu cũ, kiểm lại căn cứ từng ý, hash và review sau chuyển. Pilot 128/32 dùng trong W6 là artifact riêng đã chuyển format và khóa trước đó, không lấy bộ 1.000 thay vào run cũ.

Tokenization thực bằng tokenizer Qwen đúng revision của contract, không tải trọng số 7B. Đã kiểm 1.000 mẫu, sequence dài nhất 1.602 token, không cắt ngầm. Chỉ completion và một EOS được tính loss; prompt và padding được mask. Holdout được lưu tách riêng, không dùng train hay chọn cấu hình.

## Chống rò và truy vết

Giữ nguyên split nguồn của W5; nhóm nguồn/variant family không được đi qua split. Kiểm ID, payload hash, schema/citation và exact/5-gram giữa các mẫu mới, 500 mẫu W5 và benchmark bị bảo vệ. Kiểm này không phải chứng minh tuyệt đối không trùng ngữ nghĩa. Sidecar chỉ ghi metadata; metadata không được chèn vào prompt ngoài payload đã kiểm.

ZIP W5: SHA-256 `8bcc3af65024f2d90d8a921da58dbc8f31909c52b66da943d1e4c488fb6f0036`. Không thay bằng full candidate cũ trên máy vì 9 hash khác bản bàn giao. ZIP nhóm và hai manifest A/B được pin tại receipt và manifest của bộ ứng viên.

## Trạng thái sử dụng

Chỉ nghiên cứu nội bộ. Quyền nguồn `DECLARED_NOT_VERIFIED`; không đưa PDF, raw samples, tokenized files, ZIP hay trọng số lên Git/PR công khai. Không dùng candidate để kết luận chất lượng, nội dung chính trị/triết học vẫn cần đối chiếu học liệu và review chuyên môn phù hợp. Bản phát hành cần owner/peer review theo ID + content hash và quyết định nhóm; tài liệu này không thay các xác nhận đó.
