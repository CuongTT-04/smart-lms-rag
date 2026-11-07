# Phân công W6 thử nghiệm QLoRA và bàn giao bằng chứng huấn luyện

Ngày lập: 01/11/2026. Thời gian thực hiện: 01–07/11/2026. Nhóm E2.

Đây là kế hoạch thực hiện, chưa phải báo cáo đã huấn luyện. Kết quả cần đạt trong tuần là một lần huấn luyện QLoRA nhỏ có cập nhật trọng số adapter thật, lưu đủ cấu hình, checkpoint và log; người còn lại nạp lại được adapter và kiểm tra được việc tiếp tục huấn luyện. Đồng thời hoàn thiện đầu vào tối thiểu 1.000 instruction mẫu theo dòng W6 trong đề cương.

Theo yêu cầu của Cường, tài liệu chỉ dùng mã công việc **W6-01** và **W6-02**; chưa tạo milestone, Issue, PR hay tag trên GitHub. Hai mã này không phải số Issue `#` do GitHub cấp.

## 1 Căn cứ và phạm vi cần đạt

| Căn cứ | Nội dung áp dụng |
|---|---|
| Yêu cầu hiện tại | Fine-tune/QLoRA thử nghiệm nhỏ; lưu config/checkpoint/log; chia rõ cho hai người và có đầu vào, đầu ra để bàn giao |
| Đề cương mục 11 | W6 ngày 01–07/11: build QLoRA dataset và training dry-run; dataset card, training log; quy mô 1.000–5.000 instruction mẫu |
| Đề cương mục 10 và 12 | Công việc qua milestone/Issue; có commit/PR gắn Issue; review chéo; dữ liệu lớn/model weights ở kho riêng với checksum và manifest; cả hai đều có đóng góp kỹ thuật và báo cáo |
| Kết quả W5 hiện có | 500 mẫu; 385 train, 57 validation, 58 instruction holdout; đã kiểm kỹ thuật, chưa có lần huấn luyện QLoRA được chứng minh |
| Chatbot hiện tại | Qwen2.5-7B-Instruct; hội thoại QA dùng `evidence_citations_v2`, chọn mã đoạn rồi backend tạo citation |

Đề cương được đọc từ `D:/ĐATN_Đề cương chi tiết.docx`, SHA-256 `4efa6d00169abc238b7dadaf7bce2a108d0d02e83a67d764767da6327e8a92da`. Checkout đối chiếu là `main`, commit `331173baf9e1d38f3acb6e45f9ed01a31ee501e5`. Người thực hiện phải ghi thêm commit thật chứa code W6 khi bắt đầu chạy; không dùng commit của bản kế hoạch làm bằng chứng đã triển khai trainer.

W5 đã đưa công việc chuẩn bị instruction dataset lên trước lịch gốc. Kế hoạch này nối tiếp công việc thực tế đó, không tự tuyên bố giảng viên đã duyệt thay đổi lịch. Hạng mục hybrid/rerank của lịch cũ vẫn là backlog cần đối chiếu riêng, không được ghi đã hoàn tất nhờ thí nghiệm QLoRA.

### 1.1 Phân biệt mục tiêu dataset và mục tiêu huấn luyện

| Mốc | Yêu cầu cụ thể | Không được đánh đồng với |
|---|---|---|
| Dataset W6 | Ít nhất 1.000 mẫu hợp lệ tổng cộng, kế thừa 500 W5 và thêm 500 mới; có nguồn, review, chia tập, audit | Nhân đôi/paraphrase máy móc 500 dòng hoặc chỉ đổi định dạng rồi đếm thành mẫu mới |
| GPU smoke | 2 optimizer step thật với backward/update, kiểm loss/mask/VRAM | Chỉ import thư viện, tokenize hoặc chạy inference |
| QLoRA pilot | 50 optimizer step trên 128 mẫu train; 32 mẫu validation riêng; lưu checkpoint và adapter | Huấn luyện toàn bộ 1.000 mẫu hoặc kết luận adapter tốt hơn model gốc |
| Kiểm chứng | Nạp adapter trong process mới; resume từ checkpoint trung gian; so sánh thăm dò với base | Chỉ thấy file xuất hiện trong thư mục Output |

Pilot có thể chạy từ phần W5 đã được kiểm đúng phiên bản trước khi 500 mẫu bổ sung hoàn thành. Khi báo cáo phải ghi **pilot đã dùng 128 mẫu**, không ghi model đã học 1.000 mẫu. W7 dành cho huấn luyện chính và hoàn thiện adapter; W8 mới là mốc so sánh đầy đủ Base/RAG/QLoRA+RAG.

Nếu chỉ hoàn thành pilot trên bộ 500 mẫu, nhóm đạt mốc thử huấn luyện nhỏ nhưng **chưa đủ quy mô dataset của đề cương W6**. Ghi trạng thái hoàn thành một phần; không tự đổi chỉ tiêu xuống 500. Nếu có điều chỉnh được chấp nhận, lưu căn cứ thật trong quyết định phạm vi W6.

## 2 Milestone và hai Issue công việc

**Milestone đề xuất:** `Tuan6`.

**Mô tả milestone:** Hoàn thiện dataset instruction tối thiểu 1.000 mẫu; thực hiện QLoRA pilot tái lập được; có cấu hình, checkpoint/adapter, log và kiểm chứng nạp lại/tiếp tục huấn luyện.

**Mốc kết thúc kế hoạch:** 07/11/2026, theo múi giờ Việt Nam. Giờ nộp LMS lấy theo thông báo của giảng viên, tài liệu này không đặt thay hạn nộp chính thức.

| Mã trong kế hoạch | Tiêu đề Issue để tạo sau | Người phụ trách | Người review | Kết quả chính |
|---|---|---|---|---|
| W6-01 | W6-01 – Vũ Nam Dương – Huấn luyện QLoRA thử nghiệm và bàn giao config checkpoint log | Vũ Nam Dương, B22DCVT119 | Trần Tuấn Cường | Trainer chạy thật, 250 mẫu mới, GPU smoke, pilot 50 step, checkpoint tiếp tục train được và adapter nạp lại được |
| W6-02 | W6-02 – Trần Tuấn Cường – Chuẩn hóa đầu vào kiểm chứng adapter và đóng gói evidence W6 | Trần Tuấn Cường, B22DCVT073 | Vũ Nam Dương | Hợp đồng dữ liệu, 250 mẫu mới, bộ chung 1.000 mẫu, pilot đúng format, kiểm chứng độc lập, đánh giá thăm dò và evidence |

Khi tạo Issue thật, bổ sung số và link GitHub vào bảng này. Commit/PR dùng `Refs #<số thực tế>`; không dùng `Refs #W6-01` hoặc tự dự đoán số Issue tiếp theo. Mỗi người mở PR phần mình và yêu cầu người còn lại review. Có thể tạo tag `w06` sau khi tích hợp và nghiệm thu bằng chứng; viết kế hoạch chưa tạo tag.

## 3 Đầu vào cần kiểm trước khi thực hiện

| Đầu vào | Nơi tìm hoặc cách nhận | Cần kiểm gì | Người chịu trách nhiệm |
|---|---|---|---|
| Kết quả W5 mới nhất | `Evidence/W05/manifest.json`, `docs/instruction-input-review.md` mục 12–13 | 500 mẫu; split 385/57/58; manifest package được tham chiếu là `843b450ead5bc43958f60c146352f4f1b2f93b863eb46fc7f162ee2531b89bc5` | Cường tiếp nhận, Dương cung cấp gói tương ứng |
| Package W5 đầy đủ | Gói riêng `group-reviewed-handoff.zip` và receipt từ Dương; hướng dẫn trong mục 12 nói trên | SHA-256 ZIP theo receipt riêng; manifest package đúng hash; có candidate, sidecar, split, review/revision, auditor và nguồn kiểm được | Cường |
| ZIP W5 gọn nếu dùng | Theo manifest: `.private/instruction/ohayo-instruction.zip`, SHA-256 `8bcc3af65024f2d90d8a921da58dbc8f31909c52b66da943d1e4c488fb6f0036` | Có thể dùng để vận chuyển SFT cũ; không thay package đầy đủ khi cần ánh xạ target sang đoạn nguồn | Cường |
| Gói cục bộ cũ | `.private/w5/group-v0.2/package/manifest.json` | Trên máy đối chiếu, hash còn là `f7dd3b74b8622d53f0fb47093a3460a661af4141bed70bcfec2e22691fd76044`; không tự coi là bản mới `843b…bc5` | Cường |
| Contract và công cụ W5 | `data/instruction/w5/contract/`, `scripts/instruction/`, `scripts/w5/` | Đọc schema, nguồn, split, tokenizer, EOS, loss mask và benchmark exclusion; chạy auditor đúng snapshot của gói | Cả hai |
| Model/tokenizer | `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28` | Tokenizer cùng revision; kiểm identity/hash nếu dùng checkpoint NF4 đã lưu trong Kaggle Input | Dương |
| Giao thức hội thoại hiện tại | `backend/apps/ai/rag/conversation.py`, `pipeline.py`, `context_builder.py`, `citations.py` | Chụp hash các file dùng để xuất/đọc pilot; hiểu khác biệt giữa mã đoạn, nhãn citation hiển thị và số trang | Cường |
| Tài nguyên chạy | Kaggle GPU T4; phiên training riêng với CUDA torch của Kaggle | GPU trống, dung lượng đĩa, phiên bản Python/CUDA/torch và quota thực tế; không để các replica inference chiếm GPU training | Dương |

**Tình trạng khi lập kế hoạch:** chưa thấy hai ZIP mới ở các đường dẫn `.private/instruction/` nêu trên trong checkout của Cường. Hash W5 mới lấy từ evidence Git, chưa phải xác nhận đã nhận và kiểm ZIP trên máy này. Task đầu tiên của Cường là tiếp nhận đúng gói; Dương có thể chuẩn bị trainer với fixture trong lúc chờ.

Giữ nguyên gói W5 gốc. W5 có hash code/prompt đóng băng; code chatbot hiện tại đã thay đổi. Nếu auditor W5 báo code không khớp, dùng bản auditor/snapshot đã đi kèm gói để xác minh, rồi tạo contract W6 riêng. Không sửa hash W5 hoặc bỏ kiểm tra để ép gói cũ đạt.

Các trạng thái review từng mẫu và quyền nguồn còn thiếu phải ghi đúng trong `intake-report.json`. Quyết định chọn baseline nghiên cứu nội bộ không tự trở thành review chéo trên hash mới hoặc quyền phát hành dữ liệu công khai. Ghi riêng phạm vi được hai người chốt cho pilot; không tự điền chữ ký/điểm nghiệm thu thay người khác.

Để khóa dataset 1.000 mẫu, Cường còn phải đối chiếu và hoàn tất những review W5 chưa có trên bản mới: phần 250 mẫu A và các chỉnh sửa B cần xác nhận theo hướng dẫn gói trả lại. Dương đối chiếu review phần B và SELF_REVIEW các bản sửa của mình. Nếu đã có xác nhận ở nơi khác, nhập bằng chứng đúng ID/hash; không làm lại hoặc tạo xác nhận giả. Chỉ review 500 mẫu bổ sung mà bỏ qua trạng thái của 500 mẫu gốc thì chưa đủ để ghi cả bộ đã nghiệm thu. Pilot được kiểm và chốt riêng trên 160 mẫu được chọn.

## 4 Những việc phải chốt chung trước lần chạy GPU

### 4.1 Hợp đồng định dạng W6

W5 đã xuất QA/summary thành văn bản tiếng Việt có `[n]`, hint thành `READ/OUTLINE/COMPARE`, thiếu căn cứ thành sentinel. Chat QA hiện tại lại yêu cầu JSON `items` với `text` và `evidence_id`. Không đưa nguyên SFT cũ vào train rồi tuyên bố đã tương thích chatbot mới.

Cường tạo `data/w6/training-contract.json`; Dương review và trainer phải đọc đúng phiên bản này. Đây là **file cần làm ở W6, chưa có chỉ vì tài liệu này nêu tên**. Contract phải chứa:

| Nhóm trường | Nội dung bắt buộc |
|---|---|
| Danh tính | `schema_version`, `contract_id`, người phụ trách, ngày chốt, commit code, hash file contract |
| Nguồn dữ liệu | Hash manifest W5 đã nhận; hash dataset W6; ID và hash bản ghi gốc; source PDF/page/component; trạng thái sử dụng/review |
| Model | Model ID, revision của weights/tokenizer, chat-template hash, hash các file exporter/parser dùng trong pilot |
| Split | Bản đồ ID → split; quy tắc khóa source component; seed; ID train/validation của pilot; đường dẫn holdout bị loại khỏi job training |
| Format | Prompt/completion theo task, giao thức `evidence_citations_v2`, quy tắc tạo mã đoạn, quy tắc refusal và hint |
| Token và mask | Giới hạn sau chat template; vị trí EOS; prompt/padding label `-100`; completion được giám sát; cấm cắt ngầm |
| Phạm vi chạy | Pilot kỹ thuật nội bộ; chưa thay model chatbot đang phục vụ; các mục còn chờ xác nhận được ghi riêng |

Format pilot mặc định:

- `qa` và `summary`: prompt có evidence được cấp mã; completion là `{"items":[{"text":"...","evidence_id":"..."}]}`. Mỗi ý chọn đoạn hỗ trợ thực sự. Backend tạo `[1]`, `[2]` khi hiển thị.
- `insufficient_evidence` trong QA: completion `{"items":[]}`; parser chuyển thành phản hồi thiếu căn cứ. Không đồng thời xuất nội dung trả lời và sentinel.
- `hint`: giữ giao thức hạn chế `READ [n]`, `OUTLINE [n]`, `COMPARE [n] [m]` và prompt hint phù hợp. Không ép hint đi qua prompt chat QA hoặc đổi thành đáp án bài kiểm tra.
- Nếu phạm vi hint được sửa, cần contract phiên bản mới và audit lại trước training; không tự dùng JSON QA cho cả bốn task.

Mẫu chuyển đổi phải có sidecar ghi ID/hash W5, ID/hash bản W6, task, split, các mã đoạn được chọn, người kiểm tra và phiên bản exporter. Việc bóc câu thành từng ý rồi gắn mã đoạn cần kiểm nội dung; không suy ra mã đúng chỉ từ `[1]` cũ hoặc tự gắn tất cả nguồn vào mọi ý.

### 4.2 Quy mô dữ liệu

**Pilot GPU:** chọn bằng seed 42 từ các split hiện có sau khi tiếp nhận đúng W5: 128 mẫu từ 385 train; 32 mẫu từ 57 validation. Có đủ ba môn và bốn task nếu nguồn thực tế đáp ứng; ghi số lượng thật theo task/môn/độ dài. Không lấy từ 58 holdout. Dữ liệu pilot đã chuyển sang format W6 và được kiểm lại trước khi Dương chạy GPU.

**Dataset để đáp ứng đề cương:** bổ sung 500 mẫu mới, mỗi người 250, để đạt ít nhất 1.000 bản ghi sau lọc/review. Với mỗi người, mục tiêu 150 QA, 50 summary, 25 hint, 25 thiếu căn cứ; phân bố 100 THMLN, 75 KTCTMLN, 75 CNXHKH. Bộ chung dự kiến 600/200/100/100 theo task và 400/300/300 theo môn. Nếu phát hiện mẫu không đạt, tạo/sửa và kiểm lại để đủ số hợp lệ; không tính draft bị loại.

Mẫu mới của Dương dùng ID `W6_A_00001` đến `W6_A_00250`, của Cường dùng `W6_B_00001` đến `W6_B_00250`; nếu phải tạo thay mẫu bị loại, cấp ID mới và giữ lịch sử ID bị loại. Schema W6 chấp nhận cả ID W5 kế thừa và ID W6 mới; không sửa schema W5 đóng băng. Bản xuất pilot từ một mẫu W5 phải giữ `source_record_id` và `source_content_sha256`, có `training_payload_sha256` riêng; chuyển format không được đếm như một mẫu bổ sung.

Giữ nguyên split của 500 ID W5. Mẫu mới phải theo split của source component đã khóa; không chuyển một tài liệu từ holdout/validation sang train. Mục tiêu thêm 385 train, 57 validation, 58 holdout, thành **770/114/116**. Cường phân nguồn và quota theo split trước khi sinh; Dương review khả năng thực hiện. Nếu grouping khiến tỷ lệ này không thực hiện được hợp lý, giữ ranh giới nguồn và ghi số thật cùng quyết định, không phá ranh giới để làm đẹp tỷ lệ.

Pilot 160 mẫu và bộ mở rộng 1.000 mẫu là hai artifact có manifest riêng. Pilot có thể dựa trên snapshot W5 trước khi bộ mở rộng hoàn thành. Toàn bộ bộ mở rộng vẫn phải giữ contract nội dung/split và được audit; việc chuyển hết 1.000 mẫu sang giao thức QA mới có thể tiếp tục ở W7. W6 không được ghi cả 1.000 mẫu đã ở format mới nếu mới chuyển 160 mẫu pilot.

Holdout được lưu/kiểm integrity riêng, không mount vào job train, không dùng để chọn learning rate, rank, checkpoint hoặc sửa prompt. Benchmark QA phát triển trước đây cũng không được đưa vào train hay coi thành test độc lập mới.

### 4.3 Cấu hình QLoRA khởi đầu

Đây là cấu hình đề xuất để thực nghiệm, chưa phải cấu hình đã chạy thành công. Dương ghi cấu hình thực chạy vào từng run; mọi lần đổi tạo run ID/config hash mới.

| Tham số | Giá trị khởi đầu |
|---|---|
| Base model | Qwen2.5-7B-Instruct, revision như mục 3 |
| Training | QLoRA, base NF4 4-bit, double quantization; base weights đóng băng |
| LoRA | `r=8`, `lora_alpha=16`, `lora_dropout=0.05`, `bias=none`, `task_type=CAUSAL_LM`, `target_modules=all-linear` |
| Thiết bị | Một GPU T4, `device_map={"":0}`; chưa dùng DDP hoặc `device_map=auto` để huấn luyện |
| Precision | FP16; BF16 tắt với profile T4 |
| Batch | Per-device batch 1; gradient accumulation 4; batch hiệu dụng 4 ở một GPU |
| Bộ nhớ | Gradient checkpointing bật; `use_cache=False` lúc training |
| Độ dài pilot | Tổng sequence tối đa 2.048 token; prompt tối đa 1.536, completion tối đa 512; đếm sau template và tính EOS |
| Optimizer | `paged_adamw_8bit`, learning rate `2e-4`, max grad norm 1.0, warmup ratio 0.1; scheduler linear |
| Số step | Smoke 2; pilot 50 **optimizer step**, không đếm nhầm microbatch |
| Lưu và đo | Log mỗi optimizer step; validation loss và checkpoint ở step 25, 50; giữ tối đa hai checkpoint trung gian và final adapter |
| Lặp lại | Seed 42 và data seed 42; lưu giới hạn tính xác định của GPU, không hứa loss giống từng bit |
| Báo cáo ngoài | `report_to=none`; không cần ngrok hoặc token inference để train offline |

Dùng `prepare_model_for_kbit_training()` trước khi gắn LoRA. Trainer/collator phải sử dụng đúng labels đã kiểm: prompt và padding là `-100`, completion và EOS được giám sát. Không mặc định một cờ `assistant_only_loss` sẽ tự đúng với mọi phiên bản thư viện. Chọn `transformers.Trainer` với collator kiểm được; chỉ dùng trainer khác nếu có test chứng minh giữ đúng mask.

Đặt `save_only_model=False` để checkpoint có training state; pilot không tự chọn và nạp checkpoint tốt nhất ở cuối (`load_best_model_at_end=False`). Final adapter là kết quả run được ghi rõ, chưa mang tên “best”. Với FP16, ghi số optimizer update bị bỏ qua bởi GradScaler và số update thực áp dụng; không suy số update thành công chỉ từ `global_step`. Report phải phân biệt 50 bước Trainer đã đi qua với update thực tế nếu có bước bị bỏ qua. GPU smoke phải chứng minh có cập nhật thật, không chỉ tăng bộ đếm.

Giữ CUDA torch do Kaggle cung cấp. Mốc tokenizer hiện có là Transformers 4.57.6; Dương thử tương thích PEFT/Accelerate/bitsandbytes, rồi xuất dependency lock và environment thực tế trước pilot. Không ghi một bộ version là đã tương thích chỉ vì import được một thư viện. Không cài đổi dependencies của backend hoặc notebook đang phục vụ Ayo.

Runner nên dùng môi trường training riêng và gọi một process Python mới từ notebook để tránh kernel giữ bản Transformers cũ sau `pip install`. Một notebook training riêng không có nghĩa được bảo đảm thêm quota GPU đồng thời; ghi nhận quota thật và thống nhất thời gian dừng/chạy inference nếu cần.

Nếu thiếu VRAM: kiểm GPU không còn model inference; giữ batch 1 và checkpointing; thử profile mới với sequence 1.536 rồi chọn lại mẫu đáp ứng giới hạn, không truncate ngầm. Mọi thay đổi rank/target module/model đều có config/run mới và được kiểm lại. Nếu phải chuyển sang model nhỏ hơn theo đề cương, ghi rõ model/revision/tokenizer mới, xuất lại dữ liệu và so sánh base cùng model đó; không ghi adapter 3B là adapter của 7B. Không đổi model đang phục vụ LMS trong tuần này.

## 5 Thứ tự làm việc và những chỗ phải bàn giao

| Mốc | Ngày mục tiêu | Chủ trì | Điều kiện xong | Người nhận và việc được mở khóa |
|---|---|---|---|---|
| G0 Khóa đầu vào | 01/11 | Cường, Dương cùng chốt | Gói W5 đúng hash; contract W6 và phạm vi thí nghiệm được ghi; rõ source/split/format | Dương viết trainer theo hợp đồng; Cường xuất pilot |
| G1 Pilot sẵn sàng | 02/11 | Cường | 128 train + 32 validation đã chuyển format, review, audit token/mask, có manifest và ID list | Dương chạy GPU smoke; Cường chuẩn bị harness từ fixture và 20 ca validation |
| G2 GPU smoke | 03/11 | Dương | Hai optimizer step thật, loss hữu hạn, có gradient và adapter tensor thay đổi, không OOM | Dương chạy pilot 50 step; Cường kiểm log và artifact schema |
| G3 Bàn giao pilot | 04/11 | Dương | Run manifest, checkpoint 25/50, final adapter, config/lock/log/hash và receipt đầy đủ | Cường reload/resume và đánh giá thăm dò |
| G4 Kiểm độc lập | 05/11 | Cường | Reload process mới đạt; resume tiếp được; có kết quả base/adapter cùng input và giới hạn | Dương xử lý finding; Cường hoàn thiện evidence |
| G5 Dataset và đóng tuần | 06–07/11 | Cường tích hợp, cả hai review | 1.000 mẫu hợp lệ; artifact và bằng chứng khớp; review PR thật; checklist cuối tuần | Chốt trạng thái W6, bàn giao W7 |

Không cần đợi nhau cho mọi việc: Dương chuẩn bị môi trường, trainer/collator và test fixture trước G1; Cường chuẩn bị intake, converter, schema artifact, evaluator và validator trước G3. Chỉ chạy train thật sau G1; chỉ kiểm adapter thật sau G3. Hai người bổ sung dữ liệu mới và review chéo song song trong 01–06/11, không để việc tăng lên 1.000 mẫu chặn GPU smoke của pilot đã khóa.

## 6 W6-01 công việc của Vũ Nam Dương

### 6.1 Các task và đầu ra

| Task | Công việc cần làm | Đầu vào | Đầu ra chi tiết và điều kiện nhận |
|---|---|---|---|
| 01.1 Môi trường và recipe | Kiểm GPU/đĩa; tạo runtime training riêng; khóa version và cấu hình; kiểm load base NF4 | Model/revision, profile mục 4.3, fixture | `configs/w6/qlora-pilot.json`, `scripts/w6/requirements-training.lock.txt`, environment report với Python/torch/CUDA/HF/GPU; load có identity đúng, không chạy chung hai replica inference |
| 01.2 Trainer và collator | Viết nạp dữ liệu/manifest, train QLoRA, logging, save và resume; chuẩn bị CLI/runner Kaggle | Contract W6, fixture, masked token rows do Cường xuất | `train_qlora.py`, `collator.py`, `training_runtime.py`, test; chặn nhầm split/hash, không train base, không đổi labels/padding; có hướng dẫn chạy lại |
| 01.3 Dữ liệu phần Dương | Tạo 250 mẫu mới theo nguồn/quota được phân; tự kiểm; review 250 mẫu mới của Cường; phối hợp kiểm ánh xạ pilot | Source allocation W6, schema/rubric W5 kế thừa, component split | Candidate A riêng và SELF_REVIEW đúng hash; PEER_REVIEW phần Cường theo thực tế; sửa finding và tính hash lại, không sửa file của Cường trực tiếp |
| 01.4 GPU smoke | Chạy hai optimizer step và kiểm tensor/mask/loss/VRAM | Pilot G1 và cấu hình smoke | Run thư mục riêng có stdout/stderr, step metrics, trainable parameter report, loss hữu hạn; ít nhất một tensor adapter đổi; không chỉ export adapter ngẫu nhiên |
| 01.5 GPU pilot | Chạy 50 optimizer step, đo validation loss, lưu checkpoint và final adapter | Smoke đạt, pilot hash giữ nguyên, profile pilot | Checkpoint 25/50 và `final-adapter/`; config thực, trạng thái optimizer/scheduler/RNG và scaler nếu có; metrics theo step, thời gian, peak VRAM, dữ liệu đã dùng, exit status |
| 01.6 Đóng gói và giải thích | Xuất gói chuyển riêng; viết phần phương pháp/kết quả training; xử lý finding của Cường; review PR W6-02 | Run G3, kết quả smoke/pilot | Receipt ZIP và SHA-256; public training summary không có raw học liệu; model card pilot; lệnh/runner tái lập, giới hạn và các lỗi đã gặp |

### 6.2 Tiêu chí hoàn thành Issue W6-01

- Có code trainer/collator và test, không chỉ notebook với output cũ.
- Pilot kết thúc ở `global_step=50`; log chứng minh optimizer update thật; base bị freeze và adapter thực sự thay đổi theo giá trị tensor.
- Lưu adapter inference được và checkpoint resume được; phân biệt rõ hai loại.
- Có 250 mẫu mới đạt yêu cầu sau review, phần review dữ liệu Cường được ghi theo hash thật.
- Cường nhận được gói/hash, mở được và ghi kết quả kiểm độc lập; finding nghiêm trọng đã sửa hoặc Issue còn mở.
- Có phần báo cáo training của Dương và review chéo thực tế. Chưa tốt hơn base vẫn có thể đạt mốc kỹ thuật nếu thực nghiệm đúng và báo cáo trung thực.

## 7 W6-02 công việc của Trần Tuấn Cường

### 7.1 Các task và đầu ra

| Task | Công việc cần làm | Đầu vào | Đầu ra chi tiết và điều kiện nhận |
|---|---|---|---|
| 02.1 Tiếp nhận và contract | Nhận W5 mới; kiểm receipt/hash; đối chiếu review và provenance; khóa hợp đồng W6, phân nguồn và file ownership | Mục 3 và hai loại format hiện có | `intake-report.json`, `data/w6/training-contract.json`, schema/định nghĩa artifact; chỉ rõ gói nào được dùng, nguồn còn chờ gì, không nhầm gói cũ |
| 02.2 Pilot đúng format | Chọn 128 train/32 validation; ánh xạ target vào evidence ID; audit tokenizer/EOS/mask, code snapshot và leakage | W5 đã nhận và contract W6 | Pilot `train.jsonl`, `validation.jsonl`, sidecar, tokenized rows, ID list và manifest; report 160/160 đạt; 58 holdout W5 không vào training export; Dương review trước GPU |
| 02.3 Dữ liệu phần Cường và bộ chung | Tạo 250 mẫu mới; tự kiểm; review 250 mẫu mới của Dương; tích hợp thêm 500 vào W5 | Quota và component split, candidate A/B mới | Candidate B riêng; review đúng hash; dataset tối thiểu 1.000 mẫu có counts/split/sources thật, dataset card W6, manifest; giữ mọi ID/split W5 bất biến |
| 02.4 Kiểm công cụ | Viết validator dữ liệu/manifest, checker checkpoint, harness đánh giá; dùng fixture trước khi có adapter | Contract và schema artifact đã chốt, code trainer giao diện từ Dương | `prepare_pilot.py`, `validate_dataset.py`, `verify_checkpoint.py`, `evaluate_pilot.py`, test; có test âm khi tráo split, sai hash, sửa mask, thiếu checkpoint hoặc sai base revision |
| 02.5 Kiểm model thật | Tính lại checksum; nạp adapter trong process mới; resume checkpoint 25 ít nhất tới step 26 ở run riêng; chạy thăm dò base/adapter | Gói G3, base cùng revision, 20 ca validation đã khóa | `reload-report.json`, `resume-report.json`, log và kết quả theo từng ca; kiểm adapter active/tensor đúng, gradient tiếp tục cập nhật; không chỉ kiểm file tồn tại |
| 02.6 Evidence và bàn giao | Tổng hợp kết quả, biểu đồ loss, phân tích lỗi, số lượng thực; đóng gói và cập nhật kế hoạch tuần sau; review PR W6-01 | Kết quả hai người và verification G4 | `Evidence/W06/`, báo cáo tuần 1–2 trang PDF/DOCX, link PR/commit/demo khi có, metrics CSV/JSON, manifest/hash, README tái lập và trạng thái từng tiêu chí |

### 7.2 Tiêu chí hoàn thành Issue W6-02

- Người khác biết chính xác package/hash, split, format và các lệnh/runner phải dùng; không phải hỏi lại file nào là đầu vào.
- Pilot và bộ 1.000 mẫu được ghi riêng; dữ liệu chuyển định dạng không bị tính thành mẫu mới.
- Test công cụ có ca sai dữ liệu và fail thật trước khi sửa, không chỉ test đường thành công.
- Có kiểm chứng adapter bằng process mới và resume thật; báo cáo ghi đúng model/base/adapter/config/dataset của từng lần chạy.
- Có so sánh thăm dò và kiểm nội dung citation, không chỉ đếm mã nguồn hợp lệ.
- Dương review PR và các điểm cần sửa; evidence khớp với bản tích hợp cuối, không dùng kết quả test cũ gắn cho code mới.

## 8 Ranh giới file để hai người và AI không làm trùng

Các đường dẫn dưới đây là **đầu ra dự kiến cần tạo trong W6**, chưa phải file có sẵn để chạy ngay.

| Người sở hữu | Đường dẫn được tạo/sửa |
|---|---|
| Dương | `scripts/w6/train_qlora.py`, `collator.py`, `training_runtime.py`, `requirements-training.lock.txt`, `tests/test_training_runtime.py`, `tests/test_collator.py`; `configs/w6/qlora-pilot.json`; `docs/model-card-w6-pilot.md`; `Evidence/W06/training/` |
| Cường | `scripts/w6/contracts.py`, `prepare_pilot.py`, `validate_dataset.py`, `verify_checkpoint.py`, `evaluate_pilot.py`, các test dữ liệu/kiểm chứng; `data/w6/training-contract.json` và schema; `docs/dataset-card-w6.md`; `Evidence/W06/verification/`, `metrics.csv`, `manifest.json`, `README.md`, báo cáo tuần |
| Cả hai theo thời điểm bàn giao | `scripts/w6/README.md`: Cường tạo khung hợp đồng/lệnh, Dương bổ sung phần train qua PR, Cường tổng hợp cuối; không cùng sửa trực tiếp một bản |
| Dương tạo riêng | `.private/w6/candidates/member_a.jsonl`, self review A và peer review B, run training và gói model bàn giao |
| Cường tạo riêng | `.private/w6/candidates/member_b.jsonl`, self review B và peer review A, dữ liệu tích hợp, pilot, evaluation và verification run |

Không thay code/model đang phục vụ Ayo, `.env`, cấu hình inference đang dùng, benchmark đã khóa, hồ sơ W5, gói W5 gốc hoặc nguồn PDF để làm các kiểm tra vượt qua. Nếu cần sửa công cụ W5 do lỗi thật, tạo thay đổi riêng có test và ghi rõ ảnh hưởng; không sửa thầm snapshot của gói.

Hai nhánh gợi ý là `codex/w6-01-qlora-training` và `codex/w6-02-data-verification`. Chốt cùng base trước khi làm; không triển khai trực tiếp trên `main` được bảo vệ. Khi cần thay đổi file thuộc người kia, gửi đề nghị theo đường dẫn, field, lý do và test; người sở hữu sửa hoặc chuyển ownership rõ ràng.

## 9 Hợp đồng bàn giao dữ liệu và model

### 9.1 G1 Cường giao dữ liệu cho Dương

Package pilot tối thiểu gồm:

```text
pilot-v2/
  train.jsonl
  validation.jsonl
  train.metadata.jsonl
  validation.metadata.jsonl
  tokenized-train.jsonl
  tokenized-validation.jsonl
  selection.json
  training-contract.json
  tokenization-report.json
  review-records.csv
  manifest.json
  SHA256SUMS.txt
```

`manifest.json` ghi hash/kích thước từng file, số dòng, split, ID set, source dataset manifest hash, training export version, tokenizer/template hash và commit exporter. Sidecar phải khớp từng dòng/ID/hash của payload. Training job chỉ nhận train và validation; holdout không có trong package này.

Không đưa review, đáp án benchmark, tên người review hay cờ ACCEPT vào prompt. Các trường audit chỉ nằm ở sidecar/manifest. Dương kiểm lại số dòng, hash, ranh giới label và batch thật trước optimizer step đầu tiên.

### 9.2 G3 Dương giao model cho Cường

```text
runs/<run_id>/
  resolved-config.json
  environment.json
  data-reference.json
  trainable-parameters.json
  adapter-update-report.json
  train-metrics.jsonl
  eval-metrics.json
  stdout.txt
  stderr.txt
  checkpoint-25/
  checkpoint-50/
  final-adapter/
    adapter_config.json
    adapter_model.safetensors
  tokenizer-reference.json
  run-manifest.json
  SHA256SUMS.txt
```

`run_id` duy nhất theo UTC timestamp và config hash; ghi múi giờ trong log. Run bị lỗi/OOM có thư mục riêng với exit status và nguyên nhân, không ghi đè bằng lần thành công.

Final adapter dùng để inference cùng đúng base model, không phải full model 7B. Checkpoint để resume còn cần `trainer_state.json`, trạng thái optimizer, scheduler, RNG và scaler khi runtime sử dụng; manifest liệt kê tên file thật do phiên bản Trainer sinh ra. Chỉ có `adapter_model.safetensors` và `adapter_config.json` thì chưa đủ để tuyên bố resume toàn bộ training state.

Checkpoint `ohayo-model` đang dùng làm base NF4 cho inference không tự trở thành checkpoint đã fine-tune. Chép lại base weights hoặc xuất adapter trước optimizer update không đáp ứng W6; phải có bằng chứng cập nhật tensor và log của run training mới.

`adapter-update-report.json` phải so giá trị tensor adapter trước/sau optimizer update, ví dụ norm của hiệu tensor lớn hơn 0, kèm số trainable parameters và trạng thái freeze base. Chênh checksum hai ZIP do metadata/thời gian không phải bằng chứng trọng số đã học.

Đóng ZIP riêng, gửi receipt có SHA-256 ZIP, size, run ID, base revision, dataset hash, config hash, global step và đường dẫn lưu. Cường tính lại checksum trước giải nén, rồi kiểm từng file trong manifest. Không sửa artifact A đã audit; report của Cường lưu trong thư mục verification riêng.

### 9.3 G4 Cường trả kết quả kiểm cho Dương

Mỗi finding phải có `finding_id`, mức độ, run ID, artifact/file, hash liên quan, lệnh hoặc bước tái hiện, kết quả mong đợi, kết quả thực tế và đề nghị sửa. Các report phân biệt rõ:

- Kiểm file/manifest trên CPU: đủ cấu trúc, đúng hash và base reference.
- Reload trên GPU: process sạch nạp đúng base + adapter, adapter active; tensor nạp khớp và sinh được phản hồi.
- Resume trên GPU: nạp checkpoint 25 và trạng thái liên quan, tiếp tục ít nhất tới global step 26; adapter còn cập nhật, loss hữu hạn.

Resume smoke ghi output vào run mới. Giữ cấu hình lịch học 50 step; runner có thể dừng sớm bằng callback ở step 26. Không ghi đè checkpoint 25/50 gốc, không lấy lệnh load adapter inference để thay việc kiểm resume.

## 10 Lệnh chạy cần được triển khai thành giao diện chung

Những lệnh dưới đây là **giao diện đầu ra yêu cầu**, chưa phải hướng dẫn rằng script đã tồn tại. Người sở hữu script phải triển khai tham số, help, exit code và README tương ứng. Trên Kaggle dùng Python của runtime training riêng và đường dẫn mount thực tế.

```text
python scripts/w6/prepare_pilot.py --contract <contract> --source-package <W5-package> --output <pilot-v2>
python scripts/w6/validate_dataset.py --manifest <pilot-manifest> --report <audit-report>
python scripts/w6/train_qlora.py --config <config> --profile smoke --data-manifest <pilot-manifest> --output <smoke-run>
python scripts/w6/train_qlora.py --config <config> --profile pilot --data-manifest <pilot-manifest> --output <pilot-run>
python scripts/w6/train_qlora.py --config <config> --profile pilot --data-manifest <pilot-manifest> --resume-from-checkpoint <checkpoint-25> --stop-after-step 26 --output <resume-verification-run>
python scripts/w6/verify_checkpoint.py --run-manifest <run-manifest> --mode manifest --report <report>
python scripts/w6/verify_checkpoint.py --run-manifest <run-manifest> --mode reload --report <report>
python scripts/w6/evaluate_pilot.py --run-manifest <run-manifest> --cases <validation-cases> --output <evaluation-folder>
```

Exit code 0 chỉ khi đúng các kiểm tra của lệnh đó; report phải nói rõ `mode` và không được biến manifest pass thành reload/resume pass. Nếu nhiều Kaggle Input có cùng tên, yêu cầu đường dẫn hoặc chọn theo manifest/hash đã chốt; không lấy thư mục đầu tiên tìm thấy.

Dương chuẩn bị một launcher/cell Kaggle gọi code đã version hóa, nhận package/config/output rõ ràng và xuất log ra file. Cần lưu source launcher hoặc bản notebook export trong gói tái lập; không bắt buộc đưa một bản notebook dài trùng code vào repo. Không chạy lại các cell inference/ngrok để bắt đầu training.

## 11 Đánh giá nhỏ và tiêu chí không được kết luận quá mức

Cường khóa 20 ca từ validation của pilot trước khi nhìn output adapter, có đại diện ba môn/bốn task nếu đủ. Cố định question, evidence, thứ tự đoạn, prompt, seed, decoding, token limit và phần cứng giữa hai nhánh **base NF4 + evidence** và **cùng base NF4 + adapter + cùng evidence**. Đây là phép thử development quy mô nhỏ, không phải benchmark held-out cuối đồ án.

Lưu đầu ra gốc trước parser/repair và đầu ra sau kiểm tra nếu có. Nếu dùng constrained decoding hoặc tự retry, bật giống nhau cho hai nhánh và ghi riêng; không lấy tỉ lệ JSON hợp lệ do code cưỡng chế làm bằng chứng model đã học tốt hơn.

| Nhóm đo | Đầu ra phải lưu |
|---|---|
| Huấn luyện | Step, train loss, validation loss ở các mốc, gradient/update check, thời gian, peak allocated/reserved VRAM, supervised tokens |
| Định dạng | Số output parse được trước sửa; output bị chặn; số lần retry; đúng sentinel/hint/JSON theo từng task |
| Nội dung | Đúng trọng tâm, đủ nội dung được hỏi, không thêm ý không có nguồn; ghi rubric và mẫu số thật |
| Citation | Tách mã đoạn hợp lệ với việc đoạn thực sự hỗ trợ ý. Có câu trả lời đúng nhưng chọn sai trang vẫn là citation sai |
| Hiệu năng | Thời gian load riêng và thời gian generation; số input/output token; median hoặc p95 với số ca nêu rõ, không so khác phần cứng |

Hai người đọc chéo output có thể chọn nguồn gần chủ đề nhưng không hỗ trợ nội dung. Ví dụ kiểm tra phép toán với đoạn chỉ nói về cổng ALU là một **mẫu lỗi ứng dụng cần nhớ**, không tự thêm tài liệu CPU vào tập huấn luyện ba môn hiện có. Ghi finding theo case ID, claim và source/page; không mặc định mỗi mã hợp lệ là một citation đúng.

Không đặt điều kiện “loss cuối phải nhỏ hơn mọi loss trước” hoặc “adapter phải tốt hơn base” để công nhận đã chạy pilot. Điều kiện kỹ thuật là cập nhật thật, số liệu hữu hạn, lưu/nạp/resume được và bằng chứng khớp. Nếu chất lượng không tăng hoặc giảm, ghi đúng và đề xuất W7; không chọn lại 20 ca sau khi thấy kết quả.

## 12 Evidence công khai và artifact chuyển riêng

```text
Evidence/W06/
  README.md
  metrics.csv
  test-results.txt
  manifest.json
  weekly-report.pdf hoặc weekly-report.docx
  figures/loss-curve.svg hoặc loss-curve.png
  training/
  verification/

.private/w6/
  inputs/w5-reviewed/
  candidates/
  datasets/pilot-v2/
  datasets/expanded-v1/
  runs/<run_id>/
  evaluation/<evaluation_id>/
  verification/<verification_id>/
  handoff/
```

Trong repo lưu code/config không có secret, counts, kết quả kiểm, model/dataset card, checksum và hướng dẫn. Log cần commit dùng `.txt` hoặc `.jsonl`; repo đang ignore `*.log`, nên không để manifest trỏ tới log không được commit. Log công khai chỉ có số đo/trạng thái, không in prompt, target, token IDs, secret hoặc nội dung PDF. Raw output/candidate/tokenized data/weights/optimizer state/ZIP riêng không đưa lên PR công khai.

`metrics.csv` có tối thiểu `run_id, arm, subset, metric, value, n, unit, config_sha256, dataset_sha256, status`. Chưa chạy thì ghi `NOT_RUN`, không dùng 0 thay số đo thiếu. `manifest.json` liệt kê file evidence thật, size/hash, commit, private artifact reference/hash, trạng thái từng gate và những mục còn mở. Kiểm lại hash/kích thước sau lần sửa cuối, không sao chép manifest W5 rồi đổi tên tuần.

README và báo cáo tuần 1–2 trang phải có **Planned – Done – Evidence – Problems – Next week**, phần đóng góp riêng của mỗi người, link PR/commit và demo/video khi có. Biểu đồ loss phải sinh từ log thực của run được ghi trong manifest. Lưu output Kaggle/checkpoint vào version có Output hoặc kho riêng được nhóm dùng, rồi kiểm checksum/nạp lại sau tải; file chỉ còn trong session tạm chưa phải bàn giao bền vững.

## 13 Checklist đóng milestone Tuan6

- [ ] Đầu vào W5 đúng phiên bản/hash, mọi chênh lệch và trạng thái còn thiếu được ghi rõ.
- [ ] Contract W6 được hai người đối chiếu; format pilot tương thích đúng luồng đang thử.
- [ ] Ít nhất 1.000 mẫu hợp lệ, có đóng góp 250 mẫu mới của mỗi người; counts/split/nguồn/review và dataset card truy vết được.
- [ ] Pilot 128 train/32 validation được audit; dữ liệu không bị cắt ngầm; không lấy holdout/benchmark vào train hoặc chỉnh cấu hình.
- [ ] GPU smoke và pilot 50 optimizer step thật; loss hữu hạn; adapter tensor thay đổi và base được freeze.
- [ ] Có config thực, dependency/environment, log, checkpoint 25/50 và final adapter với checksum.
- [ ] Cường nạp adapter trong process mới và resume checkpoint trung gian được, có report/log riêng.
- [ ] Có so sánh development nhỏ trên 20 ca đã khóa, gồm kiểm citation hỗ trợ ý; ghi kết quả dù adapter không tốt hơn base.
- [ ] Hai PR/commit gắn số Issue GitHub thật sau khi được tạo, có review chéo thực tế; không ghi review thay người khác.
- [ ] Evidence W06 khớp code/artifact cuối, có báo cáo tuần, đồ thị từ log, CSV/JSON, manifest và hướng dẫn tái lập.
- [ ] Báo cáo tách rõ pilot kỹ thuật, dataset 1.000 mẫu, việc chưa làm và kế hoạch W7. Không ghi đã triển khai adapter vào Ayo nếu chưa có kiểm thử/tích hợp riêng.

Thiếu optimizer update, không nạp được checkpoint, thiếu log/hash, rò split hoặc lấy nhầm dataset là chưa đạt mốc huấn luyện. Chạy được pilot nhưng thiếu 1.000 mẫu là đạt phần thử nghiệm, chưa hoàn thành toàn bộ W6 theo đề cương. Tất cả trạng thái hoàn thành chỉ được cập nhật bằng kết quả thực hiện sau này.

## 14 Cách giao tài liệu này cho một AI tiếp nhận

Người nhận cần được giao rõ một trong hai mã W6-01/W6-02 và tên thành viên phụ trách. AI đọc tài liệu này cùng các file đầu vào được dẫn, kiểm `git status` và commit thực tế, rồi thực hiện task theo ownership; không thực hiện thay cả hai Issue nếu chưa được giao.

Trình tự bắt đầu:

1. Đọc mục 3 và xác minh package/hash thực có. Nếu thiếu gói riêng, ghi `BLOCKED_INPUT` cho phần phụ thuộc và tiếp tục công cụ/fixture không cần dữ liệu; không tự tạo dữ liệu thay Dương rồi gán tác giả.
2. Đọc contract/format W5, code hội thoại hiện tại và mục 4; chốt contract W6 trước khi tạo batch dữ liệu hoặc chạy GPU.
3. Dương làm 01.1/01.2 song song với Cường làm 02.1/02.2/02.4; cả hai triển khai phần dữ liệu riêng theo quota và phân nguồn.
4. Đi qua G1 → G2 → G3 → G4; ghi run ID, config/data hash và lệnh thực chạy. Mô phỏng/mocks chỉ dùng cho unit test; không thay bằng chứng huấn luyện hoặc reload GPU thật.
5. Handoff bằng package + receipt + checksum + report, ghi rõ việc đã làm/chưa làm, file nào người tiếp theo được sửa. Không đóng Issue/milestone, push, phát hành model hoặc nộp LMS chỉ vì đã đọc kế hoạch này.

Điểm phải báo lại bằng finding: hash sai; thiếu source/metadata; task/format chưa thống nhất; không đủ dữ liệu hợp lệ; prompt/padding được tính loss; base vô tình train; model/tokenizer sai revision; loss NaN/Inf; checkpoint thiếu state; adapter không nạp/resume được; public manifest thiếu file/log. Không bỏ kiểm tra để tiếp tục.

## 15 Tài liệu kỹ thuật tham chiếu

- [PEFT hướng dẫn quantization và QLoRA](https://huggingface.co/docs/peft/v0.17.0/developer_guides/quantization): NF4, chuẩn bị model để train low-bit, LoRA và target module. Các con số pilot trong kế hoạch là lựa chọn thực nghiệm của nhóm, không phải bảo đảm tài nguyên từ tài liệu này.
- [PEFT checkpoint format](https://huggingface.co/docs/peft/en/developer_guides/checkpoint): adapter weights/config và yêu cầu có base model tương ứng khi nạp. Khác với bộ trạng thái Trainer cần cho resume.
- [Transformers PEFT ở nhánh 4.57](https://huggingface.co/docs/transformers/v4.57.1/peft): tham chiếu tích hợp theo họ version đang dùng; bộ dependency thực chạy phải được kiểm và khóa trong W6.
- Trong repo: `docs/instruction-input-review.md`, `docs/weekly/W5/quyet-dinh-chot-ky-thuat.md`, `data/instruction/w5/contract/training-format.json`, `Evidence/W05/manifest.json`, `scripts/instruction/` và `scripts/w5/`.

## 16 Cập nhật chuẩn bị đầu vào 03/11/2026

Đã tìm thấy `D:/ohayo-instruction.zip` đúng SHA-256 công bố trong Evidence W05: `8bcc3af65024f2d90d8a921da58dbc8f31909c52b66da943d1e4c488fb6f0036`. Những nhận định thiếu ZIP ở phần khảo sát ban đầu là trạng thái tại thời điểm khảo sát, không còn là blocker kỹ thuật. Cường cho phép tiếp tục bàn giao kỹ thuật từ ZIP gọn, không chờ gói hồ sơ review đầy đủ; giữ nguyên trạng thái peer/rights gốc, không suy ra đã có nghiệm thu của Dương.

Đã chuẩn bị contract `data/w6/training-contract.json`, pilot 128 train/32 validation theo format citation hiện tại, audit bằng tokenizer Qwen thật và kiểm lại nguồn trên 94 trang PDF; không lấy nội dung holdout. Ba mẫu chuyển format mơ hồ/không phù hợp đã bị loại khỏi pool, không sửa hoặc đoán nguồn. `data/w6/record-allocation.csv` có 500 slot kế hoạch (250/người), **chưa phải 500 mẫu được biên soạn**.

Contract được tạo ngày 02/11, trường trạng thái chuẩn bị trong contract là snapshot trước khi chạy. Trạng thái thực hiện mới nhất đọc ở `Evidence/W06/README.md` và các báo cáo/receipt, không sửa contract đã khóa để đổi kết quả lịch sử. Hướng dẫn nhận gói: `docs/weekly/W6/ban-giao-duong.md`.

Phần tiếp theo vẫn thuộc W6-01 của Dương: đối chiếu mapping/contract, trainer/collator, GPU smoke, pilot 50 optimizer steps và checkpoint/log thật. Cường còn phần dữ liệu mới, reload/resume và evaluation sau khi nhận adapter. Chưa đạt toàn bộ checklist đóng Tuan6; chưa có adapter fine-tune, chưa tạo Issue GitHub hoặc nộp milestone trong lần chuẩn bị này.


## 17 Tiếp nhận kết quả ngày 06/11/2026

Các mục chuẩn bị ngày 03/11 phía trên là snapshot lịch sử. Kết quả mới đọc tại `docs/qlora-receiver-report.md`, `docs/dataset-card-w6.md` và `Evidence/W06/`. Evidence đã được tổng hợp theo layout W05; audit chi tiết cũ được lưu ZIP riêng với đường dẫn/checksum trong `Evidence/W06/manifest.json`. Đã nhận artifact pilot 50 update của Dương, kiểm config/checkpoint/log và xuất ứng viên chung 1.000 mẫu. Cập nhật 07/11: Cường đã chạy kiểm chứng GPU riêng; ZIP/receipt/audit tải về đã được kiểm độc lập. Review nội dung/nhóm và quyền nguồn vẫn giữ trạng thái chưa chốt. Không dùng snapshot cũ để kết luận chưa có adapter, cũng không dùng báo cáo tiếp nhận để tự đóng toàn bộ checklist tuần.
