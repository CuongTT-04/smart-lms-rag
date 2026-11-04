# Bàn giao đầu vào pilot QLoRA W6 cho Vũ Nam Dương

Người phụ trách chuẩn bị: **Trần Tuấn Cường — W6-02**. Người tiếp nhận trainer/GPU: **Vũ Nam Dương — W6-01**. Milestone dự kiến: **Tuan6**. W6-01/W6-02 là mã công việc, chưa phải số Issue GitHub. Ngày cập nhật: **03/11/2026**.

## 1. Gói này dùng để làm gì?

Đây là đầu vào kỹ thuật để Dương viết trainer/collator, chạy GPU smoke và pilot QLoRA. Đã chuẩn bị **128 train + 32 validation**, tokenizer Qwen thật, contract, công cụ kiểm và bảng phân nguồn cho 500 mẫu mới. **Chưa huấn luyện, chưa có adapter/checkpoint fine-tune, chưa biên soạn 500 mẫu mới, chưa hoàn thành toàn bộ W6.**

Gói gửi riêng gồm `W6-Cuong-to-Duong-v1.0.zip` và `W6-Cuong-to-Duong-v1.0.receipt.json`. Giữ hai file cạnh nhau; đối chiếu SHA-256 ZIP với receipt trước khi chạy công cụ trong ZIP. Không đưa ZIP hoặc thư mục dữ liệu giải nén lên PR công khai.

Gói W5 đầu vào đã xác minh là `ohayo-instruction.zip`, 199.937 byte, SHA-256:

```text
8bcc3af65024f2d90d8a921da58dbc8f31909c52b66da943d1e4c488fb6f0036
```

Gói có 500 mẫu, chia 385 train / 57 validation / 58 instruction holdout. Gói W6 chỉ chứa 160 mẫu đã chọn từ train/validation, **không chứa nội dung holdout, PDF nguồn, model weights hoặc secret**. Chỉ danh sách ID holdout bị cấm được giữ trong selection để phát hiện lấy nhầm.

Theo quyết định của Cường, thiếu gói hồ sơ review W5 đầy đủ không chặn việc bàn giao kỹ thuật này. Trạng thái gốc vẫn là `PENDING_ACTUAL_MEMBERS` và `DECLARED_NOT_VERIFIED`; không biến kiểm tự động thành review/nghiệm thu của con người. Hash nội dung candidate W5 được giữ từ sidecar trong ZIP xác thực, không tuyên bố đã tính lại từ candidate đầy đủ vốn không có trong ZIP gọn.

## 2. Mở gói và kiểm trên máy mới

Giải nén ZIP vào một thư mục mới. Không sửa dữ liệu bên trong gói; lưu báo cáo kết quả ra thư mục cha. Máy kiểm chỉ cần Python 3.11 trở lên và các thư viện trong `source/scripts/w6/requirements-data.txt`; **không cần GPU, Kaggle, ngrok hay tải trọng số Qwen**. Dùng môi trường riêng nếu môi trường hiện tại khác version; không cài đè môi trường chatbot đang chạy.

Ví dụ sau khi giải nén thành thư mục `W6-Cuong-to-Duong-v1.0`:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\W6-Cuong-to-Duong-v1.0.zip
python -m venv .venv-w6-check
.\.venv-w6-check\Scripts\python.exe -m pip install -r .\W6-Cuong-to-Duong-v1.0\source\scripts\w6\requirements-data.txt
Set-Location .\W6-Cuong-to-Duong-v1.0
..\.venv-w6-check\Scripts\python.exe -B verify_handoff.py --receipt ..\W6-Cuong-to-Duong-v1.0.receipt.json --archive ..\W6-Cuong-to-Duong-v1.0.zip --report ..\duong-verification.json --run-tests
```

Kết quả mong đợi: `W6_HANDOFF_VERIFIED`, báo cáo `passed: true`, `training: NOT_RUN`. Thông báo Transformers không tìm thấy PyTorch trong môi trường kiểm CPU này là bình thường: bước này chỉ dùng tokenizer. Nếu muốn đối chiếu PDF thật, thêm `--source-root <đường_dẫn_checkout_có_data/corpus>`; các PDF phải khớp registry nguồn. Không cần PDF để kiểm lại payload/token/mask từ các đoạn nguồn đã bàn giao.

## 3. Bên trong có những gì?

| Đường dẫn sau giải nén | Mục đích |
| --- | --- |
| `README.md` | Hướng dẫn đang đọc |
| `docs/weekly/W6/phan-cong-w6.md` | Kế hoạch đầy đủ, cấu hình pilot, ownership và tiêu chí checkpoint/log của W6-01/W6-02 |
| `package-manifest.json`, `SHA256SUMS.txt` | Hash/kích thước từng file; receipt bên ngoài khóa manifest |
| `verify_handoff.py` | Kiểm bytes toàn gói trước khi import code, rồi kiểm dữ liệu/token/mask và chạy unit test |
| `data/pilot-v2/train.jsonl`, `validation.jsonl` | Prompt/target huấn luyện đã chuyển format |
| `data/pilot-v2/tokenized-*.jsonl` | Token IDs, attention mask, labels **chưa padding** |
| `data/pilot-v2/*.metadata.jsonl` | ID gốc, hash, split, tác giả, nhóm nguồn, phương pháp chuyển; không đưa vào model |
| `data/pilot-v2/source-rows.jsonl` | 160 payload W5 gốc cùng sidecar, phục vụ tính lại chuyển đổi |
| `data/pilot-v2/mapping-audit.html` | Mở bằng trình duyệt để đối chiếu câu hỏi, target cũ/mới và nguồn từng mẫu |
| `data/pilot-v2/selection.json`, `evaluation-selection.json` | ID pilot và 20 ca development đã khóa; không dùng holdout |
| `data/pilot-v2/tokenization-report.json`, `source-verification.json` | Kết quả kiểm thực tế và các giới hạn |
| `data/pilot-v2/training-contract.json` | Contract bất biến dùng cho pilot này |
| `tokenizer/` | Năm file tokenizer local, không phải trọng số model |
| `source/scripts/w6/` | Công cụ chuẩn bị/kiểm/đóng gói và unit tests |
| `source/backend/apps/ai/` | Snapshot các module prompt/parser cần để tái kiểm; không phải backend triển khai đầy đủ |
| `source/data/w6/record-allocation.csv`, `source-allocation.json` | 500 **slot kế hoạch** để hai người tạo 250 mẫu mới mỗi người |
| `reports/preparation-verification.json` | Báo cáo kiểm độc lập trước khi đóng gói |

Không chạy `bootstrap.py` lại trong gói giải nén để thay contract. Nhận đúng contract đã đóng gói; nếu cần đổi giao thức/giới hạn, trao đổi với Cường rồi xuất phiên bản dữ liệu và receipt mới.

## 4. Dữ liệu pilot đã kiểm những gì?

| Tập | Số mẫu | THMLN / KTCTMLN / CNXHKH | QA / tóm tắt / gợi ý / thiếu căn cứ |
| --- | ---: | --- | --- |
| Train | 128 | 52 / 38 / 38 | 77 / 25 / 13 / 13 |
| Validation | 32 | 12 / 10 / 10 | 19 / 7 / 3 / 3 |

Chọn bằng seed 42 và quota đồng thời theo môn/task, không chọn tùy ý sau khi xem loss. Giữ nguyên ranh giới nhóm nguồn/family từ W5; không lấy holdout vào train, validation hoặc 20 ca development. Kiểm PDF nguồn khớp checksum và đoạn văn trên **94 trang khác nhau**. Cả 160 mẫu khớp payload gốc, sidecar, token IDs, EOS, loss mask; chiều dài lớn nhất **1.405 token**, không cắt ngầm.

Loại khỏi pool chuyển đổi: `W5_A_00139`, `W5_A_00146` có một ý gắn đồng thời nhiều nguồn nhưng chưa xác định duy nhất evidence unit; `W5_B_00008` có target nhiều dòng không đáp ứng mỗi item một đoạn. Không đoán nguồn hoặc sửa nội dung các mẫu này để đủ quota. Vẫn chọn đủ 128/32 từ pool hợp lệ.

Đây là kiểm cấu trúc, truy vết nguồn, token và chuyển giao thức; **không thay thế đánh giá ngữ nghĩa thủ công toàn bộ 160 mẫu**. Dương mở `mapping-audit.html` trước GPU smoke, báo ID/hash nếu thấy câu sai/ngữ nghĩa nguồn chưa đủ. Không sửa trực tiếp gói đã khóa.

## 5. Contract model, format và collator

- Base: `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`; Transformers **4.57.6**.
- Tokenizer/template khớp asset trong gói; EOS **151645**, PAD **151643**. Template SHA-256: `cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f`.
- Giới hạn prompt **1536**, completion **512**, toàn chuỗi **2048** token. Vượt ngưỡng phải báo và xử lý thành phiên bản mới, không truncate im lặng.
- Mỗi dòng payload có `prompt` dạng danh sách message và `completion` dạng assistant message. QA/tóm tắt dùng `evidence_citations_v2`: JSON `{"items":[{"text":"…","evidence_id":"E1.1"}]}`. Thiếu căn cứ dùng `{"items":[]}`. Gợi ý giữ giao thức READ/OUTLINE/COMPARE của W5; không ép mọi task thành cùng JSON QA.
- Mỗi dòng tokenized có `record_id`, `input_ids`, `attention_mask`, `labels` và số đếm. Chỉ ba trường **input_ids/attention_mask/labels** đi vào model. Không truyền metadata, ID, source hash hoặc số đếm như tham số model.
- Prompt được mask **-100**. Completion và đúng một EOS assistant được tính loss. Newline định dạng sau EOS nếu có được mask **-100**. Model CausalLM tự shift labels: **không shift lần thứ hai**.
- Dữ liệu **chưa padding**. Collator của Dương pad bên phải tới bội số 8: `input_ids=151643`, `attention_mask=0`, `labels=-100`, tensor kiểu `torch.long`. Giữ nguyên loss mask đã có; không tạo lại labels bằng toàn bộ input IDs. Pad token ID khác EOS, không mask nhầm EOS thật.
- Citation chuyển từ nhãn W5 đã chỉ rõ sang evidence unit duy nhất. Không gắn mọi nguồn vào mọi ý, không tự đoán nguồn bằng similarity. Nguồn trong history không thay được evidence của lượt hiện tại.

## 6. Dương làm tiếp phần nào?

1. Kiểm gói, lưu báo cáo kiểm và phản hồi ID/hash nếu cần sửa dữ liệu; xác nhận trainer dùng đúng contract trong receipt.
2. Viết trainer/collator thuộc W6-01 theo `docs/weekly/W6/phan-cong-w6.md` có sẵn trong gói; unit test collator dùng fixture, test mask/pad/EOS thật khi smoke. Môi trường kiểm CPU ở trên chưa phải dependency môi trường huấn luyện; khóa thêm torch/CUDA/PEFT/bitsandbytes thực chạy.
3. Chạy GPU smoke **2 optimizer steps** trước; chỉ mở pilot khi loss hữu hạn, base frozen, LoRA trainable và adapter tensor thực sự đổi.
4. Chạy pilot **50 optimizer steps**, lưu checkpoint bước **25/50**, final adapter, config thực, seed, dependency, log loss/time/VRAM và hash dữ liệu. Đây là việc chưa chạy trong gói bàn giao này.
5. Gửi Cường adapter cùng base revision/tokenizer, checkpoint resume đầy đủ và receipt để Cường kiểm reload/resume ở process mới và so sánh 20 ca development. `ohayo-model` NF4 đang dùng để phục vụ chatbot là base checkpoint, không phải bằng chứng đã fine-tune.
6. Biên soạn phần **250 mẫu mới của Dương** theo `record-allocation.csv`; Cường làm 250 mẫu của Cường. Các slot chỉ khóa ID/task/nguồn/split và chưa có câu hỏi/đáp án. Không nối hai split tự chia riêng; giữ ranh giới nguồn đã cấp.

Không cần hai secret ngrok/inference để kiểm gói hay huấn luyện offline. Không thay adapter trong chatbot đang chạy cho đến bước kiểm tích hợp riêng. Chưa tạo Issue/PR, push, nộp hoặc đóng milestone trong lần chuẩn bị này.

## 7. Phản hồi tiếp nhận ngắn gọn

Gửi Cường: ZIP SHA-256 đã nhận; `duong-verification.json`; contract SHA đang dùng; kết quả xem mapping; nếu có vấn đề thì ghi record ID/hash và lý do. Sau smoke/pilot, bổ sung run ID, config/data hash, checkpoint/adapter/log và receipt. Những phần chưa chạy ghi `NOT_RUN`, không dùng kết quả mock thay cho GPU thật.
