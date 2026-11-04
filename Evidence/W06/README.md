# W6 — bằng chứng chuẩn bị đầu vào bàn giao Dương

Ngày: **03/11/2026**. Milestone kế hoạch: **Tuan6**. Công việc **W6-02**, phụ trách Trần Tuấn Cường; người tiếp nhận trainer/GPU **Vũ Nam Dương, W6-01**. Hai mã này chưa phải số Issue GitHub. Trạng thái: **TECHNICAL_HANDOFF_READY_TRAINING_NOT_RUN**.

## Planned

Xác minh đầu vào W5, khóa contract, chuẩn bị pilot theo format citation Ayo hiện tại, kiểm tokenizer/EOS/loss mask, phân nguồn 250 mẫu mới/người và bàn giao để Dương triển khai trainer. Lần này không chạy huấn luyện, tạo Issue/PR, commit/push hoặc nộp milestone.

## Done

- Nhận ZIP gọn W5 đúng checksum, 500 mẫu (385/57/58). Kiểm từng file vật lý với ID/hash/split của sidecar và ranh giới nhóm nguồn/family.
- Khóa contract model/tokenizer/template, giao thức completion và giới hạn token. Chuẩn bị **128 train + 32 validation**, khóa **20 ca development** từ validation. Không dùng nội dung holdout hoặc benchmark để train/chỉnh cấu hình.
- Chuyển nhãn citation W5 đã chỉ rõ sang evidence unit duy nhất. Loại ba mẫu mơ hồ/không phù hợp, không đoán nguồn hoặc sửa để đủ quota.
- Kiểm **160/160** bằng tokenizer Qwen thật (Transformers 4.57.6, chạy CPU), prefix template, EOS, labels và không truncate. Chiều dài lớn nhất **1.405 token**; kiểm lại đoạn nguồn trên **94 trang PDF**.
- Chuẩn bị 500 slot ID/task/nguồn/split, **250/người**, chưa biên soạn câu hỏi/đáp án mới.
- Đóng gói riêng dữ liệu chọn, tokenizer, code/tests, contract, kế hoạch và guide. Giải nén gói cuối vào thư mục khác, xác thực receipt/hash toàn gói rồi tính lại payload/token/mask và chạy **37 unit tests** từ code trong gói: đạt. **46 tests hồi quy W5** chạy trong môi trường pinned: đạt.

## Evidence

| File | Chứng minh |
| --- | --- |
| `intake-report.json` | Nhận ZIP W5, counts, nguồn và giới hạn chứng cứ gói gọn |
| `pilot-verification.json` | Tính lại 160 payload/token/mask, source PDF và split, pin manifest bên ngoài |
| `handoff-verification.json` | Kiểm bản ZIP cuối giải nén độc lập, exact file set, 160 mẫu và bundled tests |
| `handoff-receipt.json` | SHA-256/kích thước ZIP riêng, pilot manifest và contract |
| `unit-tests.txt`, `w5-regression.txt`, `handoff-tests.txt` | Log thực, không chứa dữ liệu mẫu/PDF/secret |
| `test-results.json`, `metrics.csv` | Kết quả và số đo chuẩn bị; huấn luyện ghi NOT_RUN |
| `manifest.json` | Hash/kích thước evidence và code/config/docs cuối, reference artifact riêng |

Gói riêng: `D:/OHAYO-W6-Handoff-Duong-2026-11-03/W6-Cuong-to-Duong-v1.0.zip`. Receipt/guide/checksum nằm cùng thư mục. Không commit ZIP, dữ liệu tokenized, PDF, model weights hoặc secret. Code/config/số đếm/checksum và hướng dẫn trong repo không chứa nội dung bài học.

## Problems / giới hạn

- Chưa có gói hồ sơ review W5 đầy đủ. Cường đã cho phép bỏ phụ thuộc hồ sơ này trong phạm vi bàn giao kỹ thuật. Giữ nguyên `PENDING_ACTUAL_MEMBERS` và `DECLARED_NOT_VERIFIED`, không tạo review/nghiệm thu giả. Hash candidate đầy đủ được giữ từ metadata xác thực, không tuyên bố đã tái tính từ candidate không có trong ZIP gọn.
- Kiểm cấu trúc/provenance không phải chứng nhận ngữ nghĩa mọi câu. Dương cần xem mapping audit và báo ID/hash nếu cần sửa; không sửa trực tiếp gói đã khóa. Không tuyên bố fine-tune đã cải thiện model.
- Ba mẫu không vào pool chuyển đổi: W5_A_00139, W5_A_00146 (nguồn liên hợp chưa xác định duy nhất); W5_B_00008 (item nhiều dòng không tương thích). Pool hợp lệ còn 439, đủ quota.
- Lần thử hồi quy ban đầu bằng môi trường chính có Transformers khác pin bị chặn đúng guard version; chạy lại môi trường 4.57.6 đạt 46/46. Không thay dependency của backend/chatbot.

## Next week / việc tiếp nhận ngay

Dương kiểm contract/mapping, viết trainer và collator, chạy 2 optimizer steps smoke rồi 50 bước pilot thật, lưu config/log/checkpoint 25/50/final adapter. Sau đó Cường kiểm reload/resume và đánh giá 20 ca development. Hai người tiếp tục biên soạn/review 250 mẫu mới mỗi người để đạt mục tiêu dataset W6. **Chưa đủ điều kiện đóng Tuan6 hoặc ghi W6 đã hoàn thành.**

Hướng dẫn chi tiết: `docs/weekly/W6/ban-giao-duong.md`; phân công và tiêu chí cuối: `docs/weekly/W6/phan-cong-w6.md`.
