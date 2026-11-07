# W6 — tiếp nhận QLoRA và phần việc của Cường

Kiểm ban đầu: 06/11/2026; cập nhật artifact GPU của Cường: 07/11/2026. Dương phụ trách W6-01; Cường phụ trách W6-02. Báo cáo này ghi kết quả tiếp nhận thực tế, không thay đổi artifact gốc của Dương.

Issue thực của phần Cường: [#12 — Chuẩn bị dữ liệu và kiểm định pilot QLoRA](https://github.com/CuongTT-04/smart-lms-rag/issues/12). Các thay đổi hiện tại chưa được commit; khi commit có thể dùng `Refs #12`, chưa đóng Issue khi bước GPU/review còn mở.

## Kết luận theo tiêu chí tuần

**Đã có bằng chứng đạt mốc chuyên môn “Fine-tune/QLoRA thử nghiệm nhỏ; lưu config/checkpoint/log”.** Pilot của Dương có 50 optimizer update thật, adapter thay đổi, base được đóng băng, loss hữu hạn và checkpoint kèm trạng thái optimizer/scheduler. Cường đã kiểm lại các artifact trên CPU và tái tính kết quả so sánh.

**Chưa đóng toàn bộ checklist W6.** Cường đã tự chạy GPU reload/resume trên Kaggle và gói tải về đã được kiểm độc lập; bộ chung 1.000 mẫu là bản ứng viên kỹ thuật, còn cần review nội dung và xác nhận của hai thành viên. Không ghi đã huấn luyện trên 1.000 mẫu hoặc đã đưa adapter vào Ayo.

## Đầu vào và cách kết hợp code

- Checkout Cường tại `a8afe15`; nhập 34 file được thêm trên nhánh Dương tại `3c3b803`. Không ghi đè code serving của Cường; không commit/push/merge trong lần tiếp nhận.
- Gói `qlora-handoff.zip`: 664.778.900 byte, SHA-256 `15360e8fa39f62551db321126e525d61a999d12119f16a4127eecdcd8558a647`. Đã đối chiếu receipt, manifest, kích thước/hash từng file và các ZIP bên trong trước khi đọc payload.
- Pilot manifest: `b228645e1df2d4370715539399f388208d1c7aa04745ce85ca7ccb94425a2a1d`.
- Pilot data manifest: `3be5d5f9d70e9bda9b2d0285ffdb78e3186287359ec70f35052b4e1ac3947448`. Dữ liệu khóa gồm 128 train/32 validation, tách riêng bộ mở rộng.
- W5 kế thừa từ ZIP đúng hash `8bcc3af65024f2d90d8a921da58dbc8f31909c52b66da943d1e4c488fb6f0036`. Không dùng một bản candidate cũ trên máy có 9 content hash khác ZIP đã bàn giao. Giữ nguyên payload và split của 500 mẫu trong ZIP xác thực.

Code mới của Cường gồm bộ tiếp nhận ZIP, kiểm artifact huấn luyện trên CPU, hỗ trợ export 250 mẫu B, hợp nhất bộ 1.000 mẫu và chuẩn bị notebook/cell kiểm chứng riêng. Công cụ trainer/collator cốt lõi và code resume đóng băng trong notebook của Dương được giữ nguyên.

## Bằng chứng huấn luyện

| Hạng mục | Kết quả đã kiểm |
|---|---|
| Model | Qwen2.5-7B-Instruct, revision `a09a35458c702b33eeacc393d103063234e8bc28` |
| Cấu hình | NF4 double quant, FP16; LoRA r=8, alpha=16, dropout=0,05, all-linear; seed=42 |
| Tối ưu | Batch 1, tích lũy gradient 4, learning rate 0,0002, paged_adamw_8bit |
| Smoke / pilot | 2 / 50 update, không có update bị scaler bỏ qua |
| Tham số trainable | 20.185.088; base frozen |
| Adapter delta L2 | 4,9554480940 sau pilot |
| Validation loss | Step 25: 0,3279542923; step 50: 0,3050376475 |
| Checkpoint | 25, 50; adapter/config, optimizer, scheduler, RNG, scaler và Trainer state |
| Final adapter | SHA-256 `b56082699bafadede84f3afc96da2e72084cae3f988464644aec4f392eb9e823`; tensor khớp checkpoint 50 và hữu hạn |
| VRAM pilot | Peak allocated 11,348 GiB; reserved 13,086 GiB |
| Artifact GPU reload của Dương | Process mới, tensor nạp lại khớp, adapter frozen khi đánh giá |
| Artifact GPU resume của Dương | 25 → 26; optimizer/scheduler bước 25 → 26; giữ lịch max_steps=50; đúng 1 update |
| Cường kiểm lại | Hash/inventory, tensor safetensors trên CPU; optimizer/scheduler đọc với `weights_only=True`; tái tính 40 output |
| Cường tự chạy GPU | **VERIFIED** trên Kaggle, run `verification-20261106T194045367524Z`; kiểm độc lập file tải về trên CPU |

Không dùng việc loss giảm giữa hai điểm để kết luận không overfit hoặc adapter trả lời tốt hơn base.

## So sánh development và review

Bảng dưới dùng lần chạy độc lập của Cường. Hai nhánh dùng cùng 20 case validation đã khóa trước khi thấy output, cùng input và generation config. Đã so byte: 40/40 raw output và prompt trùng lần Dương; kết quả review hỗ trợ được chuyển kèm hash, không tạo human approval mới. Đây không phải phép đánh giá holdout. Tái tính 40 output từ file gốc cho kết quả:

| Chỉ số | Base | Adapter |
|---|---:|---:|
| Output đúng định dạng | 20/20 | 20/20 |
| Mã nguồn hợp lệ, trên các case đủ điều kiện | 18/18 | 18/18 |
| Reference token F1 trung bình | 0,7455 | 0,7854 |
| Thời gian generation trung bình | 4,474 giây | 5,066 giây |
| Review nội dung của Dương: đủ yêu cầu | 17/20 | 17/20 |
| Review hỗ trợ khi tiếp nhận: đủ yêu cầu | 16/20 | 16/20 |

Khác biệt rubric được giữ rõ: review tiếp nhận đánh dấu cả hai output `W5_B_00120` chưa bao quát ý phân phối/tiêu dùng dễ dàng, nhanh chóng. Không sửa review của Dương. Các output thiếu vế khác được ghi theo ID/hash trong gói riêng; `W5_A_00240` của base cần người đọc chốt cách diễn giải quan hệ nhân quả ở ý đầu.

Việc đọc đối chiếu có hỗ trợ được ghi `ASSISTED_CONTENT_REVIEW`, không giả thành chữ ký peer review của Cường/Dương. Không lấy F1 hoặc mã citation hợp lệ để thay kiểm nội dung và nguồn hỗ trợ từng ý. **Chưa chứng minh cải thiện chất lượng tổng thể.**

## Bộ dữ liệu mở rộng

Đã xuất và kiểm kỹ thuật 250 mẫu bổ sung của Cường: 150 QA, 50 summary, 25 hint, 25 insufficient-evidence; phân môn 100 THMLN/75 KTCTMLN/75 CNXHKH. Đối chiếu 146 trang vật lý; kiểm tokenizer Qwen thật, EOS, prompt/padding mask, không cắt ngầm. Mẫu B dài nhất 925 token.

Đã kiểm lại 250 mẫu Dương từ spec và PDF gốc, trên 60 trang vật lý; không ghi đè SELF_REVIEW gốc. Bộ ứng viên chung gồm 500 mẫu W5 + 250 A + 250 B, split **770 train / 114 validation / 116 instruction holdout**. Giữ nguồn và variant family trong cùng split, kiểm trùng exact/5-gram và benchmark, tokenize lại 1.000 mẫu; dài nhất 1.602 token.

Đọc [dataset card W6](dataset-card-w6.md) để biết định dạng hỗn hợp, giới hạn của mẫu B, trạng thái review và yêu cầu chuyển format trước W7. Kết quả kiểm kỹ thuật không thay nghiệm thu nội dung. Quyền nguồn giữ `DECLARED_NOT_VERIFIED`; không phát hành dữ liệu/ZIP công khai.

## Chạy lại và bàn giao

Evidence công khai được tổng hợp tại [Evidence/W06](../Evidence/W06/README.md) theo layout W05: README, metrics, log kiểm tra, manifest và figures. Các audit chi tiết/PDF trước đây trong `receiver/` đã được lưu nguyên trạng trong ZIP ngoài thư mục evidence; xem `previous_evidence_archive` trong `Evidence/W06/manifest.json` để biết đường dẫn và checksum. Raw output, dữ liệu và trọng số chỉ trong gói `.private` có checksum.

## Review code cuối và sửa sau review

Đã có một lượt review code độc lập, chỉ đọc. Ba finding quan trọng đã được xử lý, có kiểm hồi quy RED → GREEN:

1. Audit resume nay so cấu hình, training arguments (chỉ cho khác output/log path), data reference, binding checkpoint và cấu hình adapter với pilot. Tự so tensor 25 → 26: **392 tensor thay đổi**, delta L2 tính bằng float64 là **0,14360502710160428**, khớp số báo cáo trong sai số làm tròn. Test từ chối tensor không đổi dù report ghi delta dương, hoặc cấu hình/learning rate/binding bị đổi.
2. Audit bộ bổ sung luôn đối chiếu payload với kết quả dựng lại từ spec/PDF, kể cả đường chạy standalone. Metadata owner/task/môn/family/source phải khớp candidate. Đã thử tráo hai payload cùng split rồi cập nhật hash, sidecar, tokenization và manifest trên một bản sao riêng: bị từ chối `AUTHORED_PAYLOAD_RECOMPUTATION`.
3. Ba tóm tắt B thiếu tiền ngữ đã thay bằng nguồn và tóm tắt hoàn chỉnh: `W6_B_00025`, `W6_B_00145`, `W6_B_00194`. Xuất **member-b-v2** và **group-1000-v2**; giữ v1 để truy vết. Hash cũ/mới và lý do nằm trong revision log riêng. Quota, ID và split không đổi.

Sau sửa: **103 test QLoRA/receiver và 105 test instruction đạt**, cùng kiểm artifact thực và readback 1.000 dòng; không dùng kết quả unit test để thay bằng chứng GPU. Lượt Kaggle đầu của Cường dừng ở `TOKENIZER_LIBRARY_VERSION:huggingface-hub` do hai bước chọn khác môi trường Python; đã sửa routing `--environment` và thêm test hồi quy. Lần chạy mới đã thành công; gói verification tải về được kiểm checksum, tensor, optimizer/scheduler và tái tính 40 output. Log lỗi cũ được giữ.

Hai điểm nhỏ được review ghi nhận, chưa sửa trong lượt này: chuỗi mô tả `semantic_novelty` kế thừa trong audit B vẫn nhắc owner review, trong khi các trường trạng thái thực tế là self=0, automated=250, peer=0; không dùng chuỗi này làm xác nhận của owner. Bộ đọc ZIP cũng chưa đối chiếu lại nội dung file `SHA256SUMS.txt` không được manifest liệt kê khi thư mục đã giải nén tồn tại; các payload và ZIP gốc vẫn được kiểm hash. Có thể bổ sung kiểm hai chi tiết này trước khi tái sử dụng công cụ cho nhiều đợt bàn giao.

Các quyết định kỹ thuật được giữ: tái sử dụng checkout hiện tại; dùng ZIP W5 đúng checksum làm bản gốc; bảo toàn format cũ với cờ chưa sẵn sàng train; giữ cả hai rubric review; tách evidence bổ sung để không ghi đè artifact nhóm. Chi phí tương ứng là cần chuẩn hóa format/review trước W7 và tổng hợp evidence khi đóng tuần, thay vì thay đổi ngầm dữ liệu đã khóa.

Các mục còn mở để đóng toàn bộ W6: hai người chốt review nội dung theo đúng hash; tổng hợp Evidence/PR/Issue và xác nhận quyền nguồn theo phạm vi sử dụng. Chưa tạo review, commit hay Issue thay thành viên.


## Artifact GPU độc lập của Cường — đã tiếp nhận

- Run: `verification-20261106T194045367524Z`; ZIP 190.438.481 byte, SHA-256 `85760688ed358d1b8dc4ff6dc7f26ce3dad96f7558bac4e9a3d88ad4c2f0f38b`.
- Manifest SHA-256 `de247e3df5d02a0e81bfce368490a0ef0f4c7360d0f8cea76626c4458d834777`; kiểm đủ 90 file và audit ngoài ZIP khớp receipt/summary bên trong.
- GPU Tesla T4; process reload mới PID 195, forward loss 0,0018717271; adapter SHA khớp pilot, tensor nạp lại đúng, không bật train khi đánh giá.
- Resume 25 → 26: đúng 1 update, optimizer/scheduler khôi phục và tăng đúng bước, giữ max_steps=50. Tự tính lại trên tensor thấy 392 tensor thay đổi, L2 **0,14359974930396277**, khớp report trong sai số số học.
- Đường dẫn pilot trên Kaggle được mount tại gốc Dataset, không bắt buộc mang tên thư mục run. Công cụ kiểm đã được sửa để đối chiếu đường dẫn với `context.pilot` và manifest đúng checksum; test vẫn từ chối parent/checkpoint/manifest sai. Không sửa artifact gốc để vượt kiểm.
- 40/40 raw output và prompt trùng bản đã đọc đối chiếu; latency được lấy riêng từ lần Cường, không sao chép latency của Dương.

Như vậy phần chạy GPU riêng của Cường đã có artifact kiểm chứng, không chỉ dựa trên ảnh/log console. Mốc chuyên môn và config/checkpoint/log đã đủ bằng chứng. Review nội dung/nhóm, quyền nguồn và chuẩn hóa bộ 1.000 cho W7 vẫn giữ trạng thái thực tế trong dataset card.
