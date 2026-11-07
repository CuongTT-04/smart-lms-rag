# Bàn giao kết quả QLoRA và dữ liệu instruction

Cập nhật 05/11/2026. Dương bàn giao; Cường tiếp nhận, kiểm tra và yêu cầu sửa nếu cần. Mục 2 dùng đường dẫn bên trong ZIP sau giải nén; đường dẫn code ở các mục khác tính từ thư mục gốc dự án. Không mặc định Cường đã duyệt kết quả được bàn giao.

## 1. Công việc Dương đã hoàn thành

| Hạng mục | Kết quả |
|---|---|
| Tiếp nhận đầu vào | Kiểm checksum, contract, nguồn và tokenizer của pilot **128 train + 32 validation**, không dùng holdout |
| Môi trường và công cụ | Môi trường training riêng; trainer/collator, kiểm dữ liệu, CLI/notebook Kaggle, audit và phân tích; không thay chatbot đang phục vụ |
| GPU smoke | **2 optimizer steps thật**, adapter thay đổi, base frozen, kiểm mask/loss/VRAM đạt |
| GPU pilot | **50 optimizer steps**; checkpoint **25/50**, final adapter, state phục vụ resume, config thực, dependency/environment và log |
| Phân tích học | Validation loss step 25 → 50 giảm khoảng **6,99%**; chỉ hai mốc trên 32 mẫu, chưa đủ kết luận không overfit hoặc tốt hơn base |
| Reload/resume | Process GPU mới nạp adapter khớp tensor; resume **25 → 26** ở run riêng, giữ lịch 50 bước, không ghi đè pilot |
| So sánh development | Cùng 20 ca: format **20/20**, đủ ý **17/20** mỗi nhánh. Adapter tốt hơn 2, kém hơn 2; trung bình **5,175 giây** so base **4,617 giây**. Chưa chứng minh ưu thế chất lượng/tốc độ |
| 250 mẫu mới của Dương | **100 Triết học / 75 Kinh tế chính trị / 75 CNXH khoa học**; **150 QA / 50 summary / 25 hint / 25 thiếu căn cứ**; ID `W6_A_00001`–`W6_A_00250` |
| Kiểm và xuất dữ liệu mới | Tự rà nguồn/ý trả lời; kiểm schema, ID/hash, citation, trùng/gần trùng, split, tokenizer/EOS/mask. **199 train / 18 validation / 33 holdout**, tối đa **1.158 token**; **118/118 test CPU đạt**; đọc lại gói và kiểm ZIP đạt |

**Chưa làm/chưa kết luận:** 250 mẫu mới chưa dùng để train; pilot chỉ dùng 128 mẫu train cũ. Chưa nhận/kiểm 250 mẫu mới của Cường, chưa nghiệm thu bộ chung 1.000 mẫu, chưa đánh giá holdout hoặc deploy adapter. Tự review không thay peer review; kiểm gần trùng không chứng minh tuyệt đối không trùng ngữ nghĩa. Quyền nguồn vẫn khai báo chưa xác minh, chỉ chuyển nội bộ, không công khai học liệu/đáp án.

## 2. Gói bàn giao và cách tiếp nhận

Cường nhận **3 file đặt cạnh nhau**: `qlora-handoff.zip`, `qlora-handoff-receipt.json` và `qlora.md`. Tài liệu này không nằm trong ZIP. Sao lưu ba file ngoài checkout; không cần có cây thư mục riêng trên máy Dương để đọc gói.

### Bố cục sau giải nén

Các đường dẫn dưới đây tính từ **thư mục vừa giải nén `qlora-handoff.zip`**. Gói có 30 file nội dung và một `manifest.json` chung.

| Đường dẫn trong gói | Nội dung và cách dùng |
|---|---|
| `manifest.json` | Danh mục 30 file với kích thước/SHA-256. Dùng khóa đường dẫn trong `files` để tìm file; trường `source` chỉ ghi xuất xứ trên máy tạo gói, không phải đường dẫn phải tồn tại ở máy Cường |
| `additions/` | `instruction-additions.zip` và `instruction-additions-receipt.json`: bộ 250 mẫu mới của Dương |
| `smoke/` | `smoke-20261104T172418236960Z.zip` và receipt cùng tiền tố: bằng chứng 2 optimizer steps |
| `pilot/` | `pilot-20261104T180615021055Z.zip`, receipt và audit cùng tiền tố: training 50 steps, checkpoint 25/50, final adapter, config/state/log |
| `verification/` | `verification-20261104T190518815654Z.zip`, receipt và audit cùng tiền tố: reload, resume 25→26 và 40 đầu ra base/adapter |
| `analysis/pilot/` | `analysis.json`, `training-metrics.csv`, `loss-curve.png`, `training-diagnostics.png`, `manifest.json`: phân tích và biểu đồ training |
| `analysis/verification/` | `content-review.csv`, `content-review.json`, `comparison.png`, `manifest.json`: đối chiếu nội dung và so sánh hai nhánh |
| `checks/additions/` | `readback-audit.json`, `tests.json`, `test-results.txt`, `final-check.json`: kiểm đọc lại 250 mẫu, 118 test CPU và kiểm gói cuối |
| `checks/smoke/`, `checks/pilot/` | Mỗi thư mục có `audit.json`, `receiver-verification.json`: kết quả Dương kiểm sau khi nhận artifact từ Kaggle |
| `checks/verification/` | `audit.json`, `receiver-verification.json`, `content-review-decisions.json`: kiểm artifact và rubric/quyết định đối chiếu nội dung từng ca |

### Thứ tự kiểm và đọc

1. **Kiểm ZIP chung** theo `sha256` và `size_bytes` trong `qlora-handoff-receipt.json`, rồi giải nén vào thư mục riêng. Đối chiếu các file bên trong với `manifest.json` chung; không sửa checksum để bỏ qua lỗi.
2. **Đọc kết quả tổng hợp** tại `checks/additions/`, `analysis/pilot/`, `analysis/verification/` và `checks/verification/content-review-decisions.json`. Đây là kết quả Dương bàn giao, chưa phải xác nhận độc lập của Cường.
3. **Review 250 mẫu:** kiểm receipt tại `additions/`, giải nén `instruction-additions.zip` riêng; đọc `dataset-config.json`, `audit.json`, `candidates.jsonl`, `self-review.jsonl` và các tệp SFT/metadata. Giữ 33 holdout riêng, không ghép vào train.
4. **Kiểm model:** kiểm các ZIP con theo receipt gốc rồi giải nén smoke, pilot, verification vào **ba thư mục khác nhau**. Dùng pilot cho checkpoint 25/50 và final adapter; verification chỉ chứa bằng chứng kiểm bổ sung, không thay bộ pilot. Phân tích sau nhận đã nằm trong `analysis/` và `checks/` của ZIP chung, không cần xin riêng từng file nữa.

**Không kèm trong ZIP chung:** bộ 500 mẫu W5, gói đầu vào ban đầu của Cường, base weights/cache, venv và source hiện tại đầy đủ. Cường dùng đầu vào đã giữ đúng phiên bản/hash; thiếu thì yêu cầu đúng gói, không lấy một bản W5 bất kỳ. Code/config/notebook tiếp nhận qua nhánh dự án: `scripts/qlora/`, `scripts/instruction/expand.py`, `scripts/instruction/tests/test_expand.py`, `configs/qlora-pilot.json`, cùng ba notebook `qlora_training.ipynb`, `qlora_pilot.ipynb`, `qlora_verification.ipynb`. Snapshot trong artifact chỉ dùng tái lập run cũ, không thay bằng source mới rồi giữ hash cũ.

## 3. Công việc Cường làm nối tiếp

Đối chiếu mục 7.1 kế hoạch W6 gốc, W6-02 gồm: **02.1 đầu vào/contract; 02.2 pilot; 02.3 dữ liệu và bộ chung; 02.4 công cụ kiểm; 02.5 kiểm model thật; 02.6 evidence/bàn giao**. Thứ tự tiếp nhận:

- [ ] **02.1–02.2: xác nhận đầu vào và pilot đã dùng.** Kiểm receipt/hash, contract, model/tokenizer revision và 128/32 ID. Đã có đầu ra, không cần tạo lại pilot; xác nhận đúng trạng thái review/quyền nguồn và finding còn mở của 500 mẫu W5.
- [ ] **02.3: review 250 mẫu Dương.** Đọc `dataset-config.json`, `audit.json`, candidate và `self-review.jsonl` trong ZIP; review đúng ID/hash. Báo mẫu cần sửa và lý do, không sửa âm thầm gói đã khóa.
- [ ] **02.3: hoàn thiện 250 mẫu Cường.** Theo nguồn/quota đã chốt, tự review; gửi candidate và hồ sơ cho Dương review. Không tính 250 mẫu Dương thành phần Cường.
- [ ] **02.3: tích hợp ít nhất 1.000 mẫu hợp lệ.** 500 cũ + 250 Dương + 250 Cường; kiểm trùng giữa hai phần mới và với dữ liệu/benchmark cũ, xử lý review còn thiếu. Giữ ID/split W5 và nhóm nguồn; mục tiêu chung **770 train / 114 validation / 116 holdout** nếu phân bổ không đổi. Audit tokenizer/mask/metadata/hash, xuất gói mới và cập nhật dataset card; không đưa holdout vào train.
- [ ] **02.4: tiếp nhận công cụ, bổ sung kiểm tra thiếu.** Tái dùng validator, trainer/collator, checker/harness và test hiện tại; kiểm tương thích bộ chung, thêm test hồi quy khi sửa. Không dựng bộ công cụ song song chỉ vì đường dẫn dự kiến trong kế hoạch cũ khác thực tế.
- [ ] **02.5: kiểm độc lập pilot.** Xác thực artifact/log/tensor và kết quả reload/resume, đối chiếu 20 ca cùng nguồn. Đã có bằng chứng thực chạy, không mặc định train lại 50 bước. Nếu cần chứng minh reload/resume trên môi trường Cường, chạy kiểm riêng, lưu report riêng. Chỉ ghi Cường đã kiểm sau khi làm thật; không đổi ca/config để làm đẹp kết quả.
- [ ] **02.6: bàn giao kết quả kiểm và nội dung báo cáo.** Gửi Dương kết quả/finding, số liệu, biểu đồ và phần đạt/chưa đạt, gắn đúng run/hash; review PR W6-01. Phần dữ liệu/PR Cường chuyển lại Dương review. **Không cập nhật `Evidence/W06/`: Dương sẽ tổng hợp thư mục này sau cùng.**
- [ ] **Chốt hướng W7:** training chính sau khi bộ chung được nghiệm thu; xác định dữ liệu thực dùng, config và tiêu chí so sánh. Ưu tiên đủ ý/bám nguồn, kiểm overfitting; không tăng steps chỉ để giảm loss, không coi pilot là đã train 1.000 mẫu hoặc đã nâng cấp chatbot.

Không tự đóng nghiệm thu, review chéo hoặc tag chỉ vì file đã tồn tại; không dựng approval hay kết quả chưa chạy.

**Phân công cập nhật:** Cường chỉ bàn giao kết quả kiểm và nội dung báo cáo; **Dương phụ trách tổng hợp/cập nhật `Evidence/W06/` sau cùng**, không nằm trong checklist thực hiện của Cường.

## 4. Giữ skeleton hiện tại khi nâng cấp

**Lấy cấu trúc thực tế của Dương làm nền**, không dựng lại `scripts/w6/`, `configs/w6/` hay `.private/w6/` theo đường dẫn dự kiến trong kế hoạch cũ:

```text
scripts/qlora/                  # training, collator, kiểm chứng, phân tích và tests/
scripts/instruction/            # công cụ dữ liệu, expand.py và tests/
configs/qlora-pilot.json         # recipe pilot đã dùng
notebooks/qlora_*.ipynb          # notebook gọi công cụ tương ứng
.private/qlora/                 # inputs/, runs/, verification/, delivery/...
.private/instruction/additions/ # gói 250 mẫu, receipt và kết quả kiểm
Evidence/W06/                   # Dương tổng hợp sau cùng; không thuộc checklist Cường
```

- Sửa file dùng chung: đọc contract/code/test trước; mở rộng đúng module, tránh nhân bản logic hoặc thêm tiền tố/hậu tố tuần không cần thiết.
- Đổi contract/schema/format: tạo phiên bản mới có migration rõ, giữ tương thích artifact cũ hoặc ghi rõ điểm không tương thích. Không sửa PDF, benchmark, hash hoặc gói khóa để ép test đạt.
- Launcher pilot khóa 128/32: **không nạp thẳng bộ 1.000 mẫu** khi chưa mở rộng cấu hình và kiểm lại.
- Sửa code nguồn rồi đồng bộ notebook qua công cụ build tương ứng; cập nhật test/tài liệu, tái xuất/audit phần bị ảnh hưởng và tính lại manifest/receipt. Run cũ bất biến, chạy lại vào output mới.
- Không tự đổi `.env`, model serving hoặc deploy adapter. Gom bàn giao vào 1–2 tài liệu cần thiết; raw dữ liệu, weights và log có học liệu giữ riêng, không đưa lên Git công khai.
