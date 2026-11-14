# Thí nghiệm so sánh mô hình

> Cập nhật 14/11/2026: đã hoàn thành kiểm độc lập và phần Cường, đủ 900 primary + 90 secondary, đã phân xử bất đồng và có báo cáo nhóm cuối ở mục 10. Các mục 1–7 ghi quá trình triển khai; mục 8–9 ghi kết quả tiếp nhận và tái lập, mục 10 bổ sung báo cáo của Cường. Evidence/W07 do Dương hoàn thiện sau cùng từ gói kết quả nhóm. Đánh giá nội dung bằng agent theo rubric tự động, exact judge revision không được nền tảng cung cấp.

## Mục tiêu và quyết định

So sánh Base LLM, RAG và tuned+RAG trên cùng benchmark 300 câu. Theo quyết định mới nhất ngày 12/11/2026, dùng **bộ 1.000 mẫu đã nhận qua `package.zip`**: **770 train / 114 validation / 116 holdout**. Khởi tạo adapter mới, train một epoch, dự kiến khoảng **193 optimizer updates** với batch 1, tích lũy gradient 4 trên một GPU; số bước thực phải xác nhận trong trainer/log. Quyết định này thay thế phương án tạm dùng 500 mẫu; không chạy thêm một lượt train 500 mẫu riêng.

Lượt huấn luyện mở rộng là phần bổ sung do Dương quyết định, không có trong contract v3 Cường bàn giao. Khởi tạo adapter mới từ cùng base Qwen, không ghi đè adapter pilot. Chạy dev bằng adapter cũ làm mốc, sau đó train mở rộng và đối chiếu trên dev. Chốt adapter bằng train/validation/dev trước main; khi thay adapter phải tạo contract mới và kiểm leakage lại. Main dự kiến giữ ba nhánh; so adapter cũ–mới trên dev không được mô tả là so sánh trực tiếp trên toàn bộ main.

## 1. Tiếp nhận đầu vào — đã hoàn thành kiểm kỹ thuật

Ngày kiểm: 12/11/2026. Nhánh tiếp nhận: `VuNamDuong_B22DCVT119_W7Tasks`.

Đã đọc hai tài liệu phân công/hướng dẫn và kiểm các ZIP bên trong `v3.rar`; không thực thi code nhận được. Bỏ qua các bản giải nén dư và `__pycache__` nằm ngoài bốn ZIP có receipt. Giữ nguyên nội dung gốc, tách thư mục generator khỏi evaluator.

| Đầu vào | Kết quả đã kiểm |
| --- | --- |
| Bốn ZIP | SHA-256, kích thước, CRC, tên/path an toàn và manifest của **116 file nội dung** đều đạt; receipt riêng khớp receipt tổng |
| ZIP instruction 1.000 mẫu | Đã nhận `D:/Downloads/package.zip`, **999.246 byte**, kiểm **12 file** và **11 mục manifest**; SHA-256 `7cd57224a56d1f4265535ae27523913933726adeaf85b570e75187ce1e50475b`. Không giải nén hoặc chạy code từ ZIP |
| Nguồn gốc 1.000 mẫu | **500 mẫu kế thừa khớp gói cũ**, thêm **250 A + 250 B**; kiểm ID, schema/content hash, slot phân công, nguồn và ràng buộc prompt/đáp án của 500 mẫu mới. Đếm thực **770/114/116**, không cộng file candidate/tokenized thành mẫu mới |
| Dev | **30 câu, 30 cache, 90 đầu vào ba nhánh**, 30 reference; đủ ID, lịch chạy khớp seed 42 |
| Main | **300 câu, 300 cache, 900 đầu vào ba nhánh**, 300 reference; ID không giao dev |
| Quota main | Mỗi môn 40 factual, 30 explanation, 10 multi-page, 20 insufficient; ở lượt tiếp nhận mới kiểm nhãn khai báo. Kết quả review nội dung nằm ở mục 2 |
| Corpus | **27 PDF, 621 trang vật lý**; checksum và số trang từng tài liệu khớp registry |
| Ranh giới dữ liệu | Tái dựng prompt từ câu hỏi và cache; không đưa reference/gold fields vào model input; base không có evidence |
| Tokenizer | Kiểm bytes tokenizer cũ và chat template; tính lại **990 chuỗi token IDs** trên CPU, khớp hash và số token. Đầu vào dài nhất dev/main: **3.043/3.095 token** |
| Hai nhánh RAG | Messages, context hash, token IDs hash và độ dài đầu vào khớp từng câu |
| Adapter cũ | Kiểm **63 file** theo manifest pilot; final adapter đúng SHA đã khóa và khớp bytes checkpoint 50; bằng chứng đầu vào 128/32 khớp gói mới |
| Bộ kiểm tiếp nhận | **5/5 kiểm tra đạt**: gói hợp lệ, sai hash, sai kích thước, path traversal và bản giải nén bị sửa |

Đây là kiểm bytes, cấu trúc, quota và liên kết dữ liệu, không phải review nội dung 300 câu. Chưa nạp trọng số Qwen lên GPU, chưa train, chưa sinh output dev/main. Cache đã được đối chiếu với input và nguồn khai báo; chưa tái dựng độc lập FAISS hoặc chạy lại BGE. Receipt đi cùng ZIP không phải chữ ký xác thực độc lập.

### Hồ sơ và cách kiểm lại

- [Kết quả tiếp nhận](../.private/comparison/intake-report.json).
- [Kết quả kiểm bộ tiếp nhận](../.private/comparison/intake-tests.json).
- [Công cụ kiểm lại](../.private/comparison/intake.py).
- [Tiếp nhận ZIP 1.000 mẫu](../.private/comparison/group-intake-report.json), [quyết định lựa chọn dữ liệu hiện tại](../.private/comparison/dataset-selection.json).
- [Lịch sử tìm bộ 1.000 mẫu](../.private/comparison/dataset-location.json); đây là hồ sơ cũ trước khi nhận được ZIP, không còn phản ánh tình trạng thiếu gói.
- Dữ liệu đã chọn: `.private/comparison/inputs/instruction/package.zip`; công cụ xác thực [select_training_dataset.py](../.private/comparison/select_training_dataset.py). ZIP 500 mẫu `.private/instruction/ohayo-instruction.zip` vẫn là mốc nguồn gốc, không phải lựa chọn train hiện tại.
- Đầu vào đã xác thực: `.private/comparison/inputs/v3/archives/`; bản giải nén tách tại `generator/dev`, `generator/main`, `evaluator/dev`, `evaluator/main`.
- Adapter cũ: `.private/qlora/runs/pilot-20261104T180615021055Z/final-adapter/`.

```powershell
.\.private\qlora\trainer-env\Scripts\python.exe -B .private/comparison/intake.py
.\.private\qlora\trainer-env\Scripts\python.exe -B .private/comparison/intake.py --self-test
.\.private\qlora\trainer-env\Scripts\python.exe -B .private/comparison/select_training_dataset.py
```

Các đường dẫn `.private` là hồ sơ nội bộ trên máy làm việc, không phải file được đưa lên Git. Công cụ dùng Python/UnRAR và tokenizer có sẵn, không tải model hoặc cài thư viện; chạy lại đối chiếu bản đã giải nén, không ghi đè đầu vào khác bytes.

## 2. Review benchmark và chuẩn hóa dữ liệu — đã hoàn thành phần chuẩn bị

Ngày kiểm: 12/11/2026. Không sửa ZIP/PDF gốc, không tải trọng số Qwen, không dùng GPU, chưa huấn luyện mở rộng hoặc sinh câu trả lời main.

Gói nhận vào ghi `training_ready=false`, `group_release_ready=false`, quyền nguồn chưa xác minh và format cũ/mới đang trộn. Không đổi các khai báo trong ZIP thành đã duyệt. Chuẩn hóa thành bản dẫn xuất riêng, kiểm kỹ thuật lại; không tạo xác nhận review chéo hoặc quyền sử dụng chưa có bằng chứng.

### Dữ liệu huấn luyện

| Nội dung | Kết quả |
| --- | --- |
| Nguồn | ZIP 1.000 mẫu ở mục 1, giữ nguyên bytes gốc và checksum; đối chiếu phần kế thừa với ZIP cũ SHA-256 `8bcc3af65024f2d90d8a921da58dbc8f31909c52b66da943d1e4c488fb6f0036` |
| Split | **770 train / 114 validation / 116 holdout**, giữ ID, nguồn, vị trí và variant family; không chuyển mẫu giữa các tập |
| Format | Thống nhất QA/summary/refusal sang evidence IDs và JSON items; hint giữ mã thao tác đọc. 500 payload đã chuẩn hóa trước vẫn khớp; 500 payload mới đã ở đúng giao thức nên giữ nguyên, không chuyển đổi lần hai |
| Ba trường hợp cần sửa | `W5_A_00139`: dùng đoạn công thức `p=G-k` trên cùng trang 26 để dẫn kết luận không lợi nhuận. `W5_A_00146`: gắn lại citation của ý đó vào nguồn công thức đã có. `W5_B_00008`: tách ba ý tóm tắt thành các item có citation riêng. Lưu target/hash trước và sau |
| Nguồn thực tế | Kiểm checksum PDF, đối chiếu đoạn trích và **306 trang nguồn khác nhau**. Đây là kiểm nguồn của dữ liệu, không phải bằng chứng quyền sử dụng |
| Token và loss mask | Tính lại cả bản nhận và bản chuẩn hóa của đủ **1.000 mẫu** bằng tokenizer thật; dài nhất đầu vào gốc **1.602 token**, sau chuẩn hóa **1.405 token**. Chênh lệch do thay format phần cũ, không phải cắt nội dung. Prompt/padding không tính loss, EOS được giám sát đúng; không cắt ngầm |
| Đọc lại gói | Hash/count, ID, payload, token IDs, split theo nhóm nguồn và family đều đạt |

Đầu ra dùng tiếp: **[training-v2](../.private/comparison/prepared/training-v2/)**, gồm SFT từng split, tokenized rows, metadata, mapping, corrections và manifest. Manifest chuẩn hóa có SHA-256 `95a678d4cfdaa02ff1f10b4278056e0eb72ea44f9991911fde52105e8645f3e3`. [training-v1](../.private/comparison/prepared/training-v1/) là bản 500 mẫu được giữ nguyên để đối chiếu, không dùng cho lượt train đã chọn.

Manifest này ghi trạng thái **tại thời điểm xuất**: `benchmark_leakage=PENDING_SEPARATE_AUDIT`, `training_ready=false`. Không sửa manifest đã khóa để nâng trạng thái; đọc kết hợp [báo cáo sau xuất 1.000 mẫu](../.private/comparison/data-review-report.json), leakage audit và [ràng buộc thí nghiệm hiện tại](../.private/comparison/experiment-readiness.json). Quyền nguồn vẫn kế thừa trạng thái chưa xác minh; không coi gói này là dữ liệu đã được cấp phép phát hành công khai. Kiểm kỹ thuật đạt không tự cấp phép chạy training hoặc main khi runner/config chưa được kiểm.

### Benchmark và chống leakage

| Nội dung | Kết quả |
| --- | --- |
| Review nội dung | **300 câu**, gồm 240 có căn cứ và 60 thiếu thông tin; có review gắn hash cho từng câu. Giữ quota mỗi môn 40 factual / 30 explanation / 10 multi-page / 20 insufficient |
| Đối chiếu nguồn | Bản cuối kiểm lại **352 liên kết trang nguồn** với văn bản trích xuất từ PDF thật; đọc ý đáp án, đoạn hỗ trợ và các trang biên khi nội dung bị ngắt trang |
| Nhãn thiếu căn cứ | Kiểm toàn phạm vi môn: CNXHKH **142 trang**, KTCTMLN **264 trang**, THMLN **215 trang**. Quét văn bản toàn môn kết hợp lý do thiếu thông tin riêng cho từng câu; không coi top-k trống hoặc tìm từ không thấy là đủ chứng minh không có căn cứ |
| Trùng/ngữ nghĩa | Thay **8 câu** trùng hoặc quá gần yêu cầu cũ; giữ ID để truy vết và đổi content hash. Tách các mệnh đề phân cách rõ bằng dấu chấm phẩy; giữ phủ định cùng phần giải thích. Tổng **120 content hash** thay đổi |
| Tách nguồn train/main | Kiểm lại trên **1.000 mẫu**: ba chương nguồn của main có căn cứ là `CNXHKH:ch03.pdf`, `KTCTMLN:ch02.pdf`, `THMLN:ch13.pdf`, không nằm trong 770 train/114 validation; chúng thuộc nhóm nguồn của holdout |
| Trùng và rò rỉ từ vựng | Không có câu main khớp sau chuẩn hóa với câu hỏi của bộ 1.000. Quét exact và Jaccard 5-gram ký tự ở ngưỡng **0,85** không phát hiện cặp trùng nội bộ hoặc cặp question/target gần benchmark vượt ngưỡng; target ngắn dưới 80 ký tự không dùng làm tín hiệu trùng đáp án. Đây không phải chứng minh tuyệt đối không trùng ngữ nghĩa |
| Phạm vi quét lịch sử | Cả **1.000/1.000 câu hỏi** của gói nhận khớp thành viên trong thư viện 1.175 câu của lượt semantic screen đã bàn giao. Xác nhận được phạm vi câu hỏi của quét cũ, không thay cho việc tính BGE mới hoặc kiểm tương đương ngữ nghĩa của đáp án |
| Bộ kiểm | **183/183 test đạt**, gồm **43 test** cho chuẩn bị dữ liệu/thí nghiệm và 140 test hồi quy hiện có; kiểm đọc lại candidate và acceptance gate gắn hash được kế thừa sau khi đối chiếu manifest/review. Không tạo lại kết quả sinh hay nghiệm thu mới cho benchmark |

Bản dùng tiếp là **[benchmark-v3](../.private/comparison/prepared/benchmark-v3/)**. `benchmark-v1` lưu findings ban đầu; `benchmark-v2` là trung gian, không dùng cho chạy thí nghiệm. Các tên phiên bản này chỉ nằm trong hồ sơ nội bộ, không phải prefix tuần cho file dự án.

Không sửa benchmark đã khóa chỉ để thay thông tin training. `readiness.json` bên trong benchmark là snapshot khi review với bộ 500; **ràng buộc dữ liệu hiện tại phải đọc `experiment-readiness.json` ở trên**, đã liên kết đúng manifest bộ 1.000 và benchmark-v3. Quét BGE cho tám câu thay thế còn chờ khi kết thúc bước 2; đã tính mới và kiểm ở bước 3, không dùng điểm của câu cũ thay cho câu mới.

Minh chứng chính:

- [Tổng hợp kết quả hiện tại](../.private/comparison/data-review-report.json), [kiểm đọc lại 1.000 mẫu](../.private/comparison/training-readback-1000.json), [183 test](../.private/comparison/preparation-tests-1000.json).
- [Benchmark bản cuối](../.private/comparison/prepared/benchmark-v3/main.references.jsonl), [review từng câu](../.private/comparison/prepared/benchmark-v3/reviews.csv), [lịch sử thay đổi](../.private/comparison/prepared/benchmark-v3/changes.json).
- [Leakage audit với bộ 1.000](../.private/comparison/review-workbench/group-leakage-audit.json), [kiểm 60 nhãn thiếu căn cứ](../.private/comparison/review-workbench/absence-review.json).
- [Ranh giới dev với bộ 1.000](../.private/comparison/review-workbench/group-dev-boundary.json): kiểm lại 30 câu dev; không suy từ kiểm khớp nguyên văn rằng dev hoàn toàn độc lập về ngữ nghĩa.
- [Kiểm candidate và các cặp gần của câu thay thế](../.private/comparison/review-workbench/final-review-verification.json), [acceptance gate](../.private/comparison/review-workbench/acceptance-gate.json).
- Công cụ dự án: [kiểm ZIP/lineage và native payload](../scripts/comparison/instruction_source.py), [chuẩn hóa training](../scripts/comparison/prepare_data.py), [quản lý revision/review, split và duplicate audit](../scripts/comparison/benchmark.py), [test chuẩn bị đầu vào](../scripts/comparison/tests/test_inputs.py), [test gói nhóm](../scripts/comparison/tests/test_group_source.py).

### Điều kiện trước khi chạy

1. **Không dùng câu hỏi mới với cache cũ.** Bước 3 đã tính mới BGE, cache và input/hash cho toàn bộ dev/main. Trước freeze vẫn phải đối chiếu đúng manifest bản mới và xử lý cách diễn giải những câu giao kiến thức với dữ liệu cũ; quét từ vựng không thay thế semantic review.
2. **Chưa bật main.** Review nội dung hoàn tất nhưng gói chưa phải phiên bản thí nghiệm đã freeze; `main_authorized=false`. Câu cùng chủ đề vẫn có tương quan; không trình bày 300 câu là 300 khái niệm độc lập. Dev cũ là tập hiệu chỉnh, không phải tập đánh giá hoàn toàn mới.
3. **Contract v3 gốc vẫn khóa adapter pilot cũ**, SHA-256 `b56082699bafadede84f3afc96da2e72084cae3f988464644aec4f392eb9e823`. Runner/config mới phải ràng buộc đúng dữ liệu, reference, cache, tokenizer và adapter thực dùng; giữ nguyên đầu vào gốc.
4. **Train trên 770 mẫu, không phải cả 1.000.** 114 validation chỉ đánh giá; 116 holdout không cập nhật trọng số hay chọn cấu hình. Không train tiếp chồng lên adapter pilot; tạo adapter mới từ cùng base. Chưa thay adapter phục vụ chatbot. Không gắn reference/review/evaluator vào Input notebook sinh câu trả lời.

Kiểm lại bộ test comparison trên Windows với Python môi trường dữ liệu đã có:

```powershell
.\.private\qlora\trainer-env\Scripts\python.exe -X utf8 -B -c "import sys,unittest; sys.path.insert(0,'.private/qlora/data-deps'); r=unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('scripts/comparison/tests')); sys.exit(not r.wasSuccessful())"
```

Các số liệu ở mục 2 là kết quả chuẩn bị đầu vào; kết quả runner và cache mới được tổng hợp riêng bên dưới.

## 3. Runner, test và xác minh đầu vào — đã hoàn thành phần chuẩn bị

Ba nhánh dùng cùng base Qwen2.5-7B-Instruct, revision `a09a35458c702b33eeacc393d103063234e8bc28`. Base không nhận evidence và tắt adapter; RAG nhận evidence nhưng tắt adapter; tuned+RAG nhận **đúng cùng messages, context và token IDs với RAG**, bật adapter pilot. Chạy tuần tự trên một T4, không dùng hai bản model song song.

| Hạng mục | Kết quả |
| --- | --- |
| Runner | Greedy, seed 42, một beam, tối đa 512 output token, 4.096 input token, một lần sinh/câu/nhánh. Không lịch sử, response cache, sửa đầu ra hoặc retry ngầm; hai warmup mỗi nhánh không nằm trong mẫu số chính |
| Ghi nhận lỗi | Giữ nguyên raw output, timeout/model error/output limit, thời gian, thời điểm token đầu và VRAM; không bỏ câu lỗi khỏi kết quả. Timeout 90 giây được kiểm tại ranh giới token, không phải cơ chế cưỡng chế dừng kernel GPU |
| Model và adapter | Tokenizer/template/ID đặc biệt khớp checksum; adapter khớp checkpoint 50, đủ **392 tensor, 20.185.088 tham số LoRA**, đúng shape 28 lớp Qwen, rank 8. Đây là kiểm bytes/config/shape trên CPU, **reload Qwen thật còn chờ GPU smoke** |
| BGE và FAISS thật | Đọc lại **27 PDF / 621 trang**, tạo **1.131 chunk**, vector float32 1.024 chiều chuẩn hóa; BGE-M3 đúng revision, lọc môn trước tìm top-5. Index riêng cho thí nghiệm, không thay index backend đang phục vụ |
| Khác bản nhận | Gói cũ báo 1.129 chunk nhưng không có index/vector để phục hồi. Snapshot mới có 1.131 chunk với phiên bản thư viện và provenance riêng; không tuyên bố hai index giống bytes. Sau lỗi API tokenizer lúc xuất prompt, tái sử dụng snapshot vector đã xác thực, không tính lại embedding corpus; cache câu hỏi được xuất mới |
| Fresh semantic screen | Tính **1.475 vector câu hỏi**: 300 main + 1.175 câu lịch sử. Đọc cặp gần của tám câu thay thế và mọi cặp được trả về có cosine ≥ 0,8; điểm tương đồng chỉ dùng để tìm trường hợp cần đọc, không tự coi là duyệt |
| Cache và input | Xuất lại **330 cache / 990 đầu vào**; kiểm toàn bộ bằng Transformers **4.57.6**, tokenizers **0.22.2**, hub **0.36.2**. Dev dài nhất **3.045 token**, main **3.051 token**; evidence dài nhất **2.740/2.769 token**; không cần cắt context. Kiểm text là đoạn nguồn thật, đúng môn/trang/checksum, thứ tự rank và input hash |
| Test | **184/184 test đạt**, gồm 81 comparison và 103 hồi quy QLoRA. Có test PEFT thật trên model CPU rất nhỏ để kiểm adapter bật/tắt làm thay đổi output; fixture/test double không phải kết quả Qwen |
| Gói Kaggle | ZIP **28 file, 78.594.341 byte**, chỉ có runner, config, tokenizer, adapter pilot và dev 30 câu/90 đầu vào. Không đóng main, gold/reference, reviews hoặc dữ liệu train/validation/holdout |

**Giới hạn benchmark:** đã ghi các cặp giao một phần kiến thức/ý đáp án, kể cả khi không trùng cách hỏi. Ví dụ câu áp dụng về Mặt trận/đoàn thể vẫn giao ý với câu cũ; câu tổng hợp về tồn tại xã hội chứa một ý đã hỏi trước. Giữ chúng để so ba nhánh trên cùng miền kiến thức thì phải công bố giới hạn này, không gọi đó là đánh giá tổng quát hóa trên 300 khái niệm hoàn toàn mới. Trước main freeze phải chốt cách xử lý/diễn giải; nếu thay câu phải refresh và audit lại. Không đổi thành đã nghiệm thu chéo.

Môi trường BGE chạy CPU riêng, ghi thực tế torch 2.14.1+cpu, Transformers 5.19.0, sentence-transformers 6.1.0 và FAISS 1.15.1. Đầu vào sau đó được đọc lại bằng tokenizer của môi trường Qwen đã khóa, không suy từ khác phiên bản rằng token IDs chắc chắn giống nhau.

### File dùng tiếp

- [Notebook comparison.ipynb](../notebooks/comparison.ipynb): bốn code cell, lần lượt xác thực Input, chuẩn bị môi trường riêng, smoke ba nhánh, rồi dev. Không có cell train hoặc main.
- [runner-dev.zip](../.private/comparison/prepared/runner-dev-v1/runner-dev.zip), [receipt](../.private/comparison/prepared/runner-dev-v1/runner-dev.receipt.json), [preflight](../.private/comparison/prepared/runner-dev-v1/preflight.json). SHA-256 ZIP: `20c11d7069127e26492d4e46f4bc488fd8bacdafab889bbb21793d39ca6f5c54`.
- [Cache mới và provenance](../.private/comparison/prepared/retrieval-v2/), [audit 990 input](../.private/comparison/prepared/input-readback.json), [review fresh semantic screen](../.private/comparison/prepared/semantic-review.json), [kết quả test](../.private/comparison/runner-tests.json).
- Mã chính: [runner](../scripts/comparison/runner.py), [retrieval](../scripts/comparison/retrieval.py), [packing](../scripts/comparison/packing.py), [audit đầu vào](../scripts/comparison/audit_preparation.py), [đóng gói/notebook](../scripts/comparison/package_runner.py); test tại [scripts/comparison/tests](../scripts/comparison/tests/).

**Bước vận hành tiếp theo trên Kaggle:** import notebook trên, thêm ZIP đúng checksum vào Input (Kaggle tự giải nén cũng được), bật Internet và T4, chạy bốn code cell theo thứ tự. Cell dev chỉ đi tiếp khi smoke đủ ba dòng và không lỗi; cả hai lượt tự xuất ZIP, receipt và audit. Gửi các file đó để kiểm trước khi sang train mở rộng. Không chạy lại notebook QLoRA để thực hiện bước này; chưa thay adapter chatbot và chưa được chạy main.

## 4. Smoke và dev với adapter pilot — đã nhận đủ kết quả

Đã đối chiếu độc lập ZIP/receipt, CRC, manifest/config, lịch chạy, hash đầu vào và trạng thái adapter. Smoke có **3/3 output + 6 warmup** hoàn tất; dev có **90/90 output + 6 warmup** hoàn tất, không model error/timeout/output limit. Hai lượt dùng cùng package/config đã khóa. Bằng chứng được lưu nguyên bytes tại [baseline](../.private/comparison/prepared/training-runner-v2/baseline/), kèm [readback.json](../.private/comparison/prepared/training-runner-v2/baseline/readback.json).

Dev sinh trong tổng **942,93 giây** (chỉ cộng thời gian generation, không phải toàn bộ wall time). Trung bình base **6,09 giây**, RAG **13,68 giây**, tuned+RAG **11,67 giây** mỗi câu. VRAM cấp phát đỉnh **7,900 GiB**, reserved đỉnh **9,082 GiB**. Đây là kiểm vận hành và số đo, **chưa phải điểm factuality hoặc bằng chứng adapter tốt hơn**.

## 5. Train mở rộng — đã train, kiểm kỹ thuật và chấm dev

[202/202 test đạt sau sửa lỗi ghi môi trường](../.private/comparison/training-recovery-tests.json), gồm 99 comparison và 103 hồi quy QLoRA. Test trainer dùng model CPU rất nhỏ, kiểm một epoch bao gồm cả nhóm tích lũy gradient cuối không đủ bốn mẫu; không coi loss/ảnh từ fixture là kết quả Qwen. Đã tính lại token IDs/mask của **884 mẫu được đưa vào notebook**, khớp bản chuẩn hóa đã khóa. 116 holdout vẫn giữ ngoài gói.

| Cấu hình | Quyết định |
| --- | --- |
| Khởi tạo | Cùng base Qwen/revision, **LoRA mới**, không nạp hoặc train tiếp adapter pilot. Không thay chatbot |
| Dữ liệu | **770 train / 114 validation**; không đưa payload holdout, main hoặc gold/reference dev vào notebook |
| Quy mô | Một epoch, batch 1, gradient accumulation 4, dự kiến **193 optimizer updates**; kiểm lại global step và epoch thực, không bỏ hai mẫu cuối |
| LoRA/optimizer | Rank 8, alpha 16, dropout 0,05, all-linear; NF4/double quant, FP16, gradient checkpointing; paged AdamW 8-bit, LR 0,0002, warmup ratio 0,1, clip norm 1, seed 42 |
| Validation | Đánh giá **step 0**, các bước **25, 50, 75, 100, 125, 150, 175**, rồi **193**. Chỉ dùng cùng 114 mẫu validation; không dùng holdout để chọn model |
| Lưu model | Giữ hai checkpoint gần nhất (**150 và 193** sau lượt full thành công), đủ adapter/optimizer/scheduler/scaler/RNG/trainer state/binding; lưu riêng final adapter của cuối epoch. Không tự gọi final là best adapter |
| Biểu đồ | `figures/loss-curve.png`, `optimizer.png`, `memory.png`, `runtime.png`; có CSV/JSON/log gốc. **Không chèn nhận xét, kết luận, lời cảnh báo hoặc đoạn phân tích vào ảnh**; giải thích nằm riêng trong `summary.json`/báo cáo |
| Audit và dev | Audit updates thật, gradient hữu hạn, không skipped update, delta adapter, checkpoint/hash, log/eval schedule và biểu đồ. Sau đó reload adapter mới, smoke trước, chạy lại cùng 30 dev × ba nhánh để đối chiếu với mốc cũ |

Gói dùng hiện tại: **[training-runner.zip](../.private/comparison/prepared/training-runner-v3/training-runner.zip)**, **4.599.451 byte**, SHA-256 `8546d96bb335fa9697838a7ff3481152a69be2c4faef92af795d335e4e51101e`; [receipt](../.private/comparison/prepared/training-runner-v3/training-runner.receipt.json), [preflight](../.private/comparison/prepared/training-runner-v3/preflight.json). Bản v1 là bản chuẩn bị trung gian; v2 là đầu vào của lượt smoke đã chạy, giữ nguyên để truy vết, không dùng cho lượt full tiếp theo. Gói nhỏ vì không kèm base weights, adapter cũ hay PDF; Qwen được lấy từ cache hoặc tải đúng revision.

**Sửa lỗi audit môi trường ngày 13/11/2026:** `distributions()` liệt kê cả metadata trong venv và hệ thống; chuyển thẳng thành dict làm sáu phiên bản hệ thống ghi đè phiên bản được phân giải. Đã sửa riêng luồng train mở rộng để ghi bằng `version(name)`, cùng cách kiểm của model loader; giữ listing hỗn hợp dưới trường chẩn đoán riêng. Không sửa trainer pilot dùng chung.

Lượt `smoke-20261112T184520250008Z` thực tế hoàn tất hai updates, không skipped update, delta adapter **0,5169502284**; validation 114 mẫu **0,4485598207 → 0,3828130066**. [Audit khôi phục](../.private/comparison/runs/smoke-20261112T184520250008Z-audit.json) kiểm hash/count, nguồn mã thực thi, checkpoint/final adapter, log và bốn PNG đạt mà không train lại. Giữ nguyên `environment.json` và manifest gốc: pin guard được suy ra từ đúng mã/package và run bất biến đã xác thực, **không coi listing cũ là snapshot phiên bản hiệu lực trực tiếp**. Ngoại lệ phục hồi chỉ nhận đúng cặp hash package/run này; run khác thiếu snapshot đúng vẫn bị từ chối. Kết quả full/dev nhận sau khôi phục được ghi ở mục kết quả bên dưới.

### Thao tác trên Kaggle

1. Giữ nguyên phiên Kaggle và `/kaggle/working` đang có smoke. Import lại **[comparison_training.ipynb](../notebooks/comparison_training.ipynb)** mới nhất vào notebook Training 2 hiện tại; không Factory Reset hoặc tạo phiên mới trong lúc phục hồi.
2. Upload ZIP trên thành dataset **Private**, tên `OHAYO QLoRA Training`, thêm vào Input. Bật Internet và T4; code chỉ cho một GPU nhìn thấy. Không cần thêm riêng dataset cũ hoặc checkpoint `ohayo-model`.
3. Chạy lần lượt **năm code cell**: cell 1 xác thực/gắn Input mới; cell 2 chuẩn bị môi trường riêng và kiểm dữ liệu; cell 3 **audit/xuất lại đúng smoke cũ, không train lại**; cell 4 train **mới từ base** đủ một epoch, audit/xuất log/model/biểu đồ; cell 5 reload adapter mới, smoke ba nhánh rồi dev. `REQUIRE_EXISTING_SMOKE=True` mặc định cho lượt khôi phục này: thiếu thư mục cũ thì dừng để phục hồi từ gói đã lưu, không tự chạy smoke mới.
4. Các cell sau có gate kiểm lượt trước. Có lỗi thì gửi gói `*-failed.zip`, không chạy lại training chỉ để sửa audit/biểu đồ. Khi thành công, tải ZIP, audit JSON và receipt của training smoke/full, cùng ZIP/receipt của candidate smoke/dev. Biểu đồ đã nằm trong ZIP full, không bắt buộc tải từng ảnh.
5. Gửi các gói để kiểm thực nghiệm và đối chiếu old/new dev trước khi chốt adapter. Hướng dẫn trên là quy trình vận hành; kết quả đã nhận được cập nhật ngay dưới đây, không chạy lại notebook chỉ để bổ sung hồ sơ.

Train loss là loss của batch/update, không phải một lượt đánh giá toàn bộ train; không lấy chênh lệch tức thời với validation làm kết luận chắc chắn về overfitting. Timeline VRAM chỉ lấy tại cuối update và đỉnh tích lũy. Thời gian/throughput có tính phần validation/checkpoint trước đó trong lượt train, nhưng không gồm tải base và validation step 0. Log gốc đủ để vẽ lại bên ngoài run đã khóa bằng `python -B -m scripts.comparison.training_report --run <run> --output <thu-muc-moi>` mà không train lại.

Adapter cũ học 128 train, validation 32; lượt mới là 770/114. **Không so trực tiếp loss validation giữa hai tập khác nhau** để kết luận hơn/kém. So old/new trên cùng dev; chênh lệch phản ánh cả dữ liệu và ngân sách cập nhật khác nhau, không phải thí nghiệm cô lập duy nhất biến số số lượng mẫu. Factuality/citation vẫn cần chấm riêng, không suy từ `completed` hoặc loss giảm.

### Kết quả đã nhận và kiểm ngày 13/11/2026

Lượt **`full-20261112T192034516377Z`** được kiểm độc lập từ ZIP, không chạy lại Qwen hoặc thực thi optimizer/RNG pickle. CRC, danh mục file an toàn, size/SHA-256 theo receipt/manifest, config và mã thực thi đều khớp gói v3. [Kết quả xác thực](../.private/comparison/runs/full-20261112T192034516377Z-verification.json), [đánh giá log/CSV/ảnh](../.private/comparison/runs/full-20261112T192034516377Z-assessment.json).

| Nội dung | Kết quả thực |
| --- | --- |
| Quy mô | **770 train / 114 validation**, một epoch; không có holdout |
| Updates | **193/193** cập nhật áp dụng, 0 skipped; gradient hữu hạn; delta LoRA L2 **9,3010854648** |
| Validation | Chín điểm đo: **0,448560 → 0,306518 → 0,223373 → 0,213458 → 0,207547 → 0,201834 → 0,200283 → 0,191018 → 0,189976**; giảm **57,65%** so step 0 trên cùng 114 mẫu; tốt nhất tại step 193 |
| Train loss | Trung bình 25 updates đầu **0,538132**, 25 updates cuối **0,294892**; loss từng update dao động theo batch, không phải lỗi chỉ vì đường train không mượt |
| Tài nguyên | Trainer runtime **3.822,7633 giây**, khoảng **63 phút 43 giây**, đã gồm periodic validation/checkpoint; không gồm tải base và validation step 0. Đỉnh allocated **11,348 GiB**, reserved **13,168 GiB** |
| Lưu trữ | Checkpoint **150/193**, đủ trạng thái tiếp tục; final adapter khớp bytes checkpoint 193. Việc có đủ state không thay cho thử resume độc lập |
| Môi trường | Snapshot phiên bản hiệu lực trực tiếp đạt; lỗi listing venv/system đã được sửa, không dùng ngoại lệ khôi phục của lượt smoke cho lượt full |
| Dev mới | `dev-20261112T203002043135Z`: **90/90 completed**, 0 lỗi; cùng inputs/lịch chạy; adapter SHA khớp final full **`51713be1e630135099f95ed08c89b5be8669b75c9e1908a1346c5c9cc4942ae7`**. Base/RAG giữ 30/30 output giống bytes, tuned+RAG đổi 27/30, chưa suy từ thay đổi rằng tốt hơn |
| Biểu đồ | Đủ **bốn PNG**, đọc được/không trắng; **194 dòng CSV** (step 0 + 193 updates) khớp số đo raw, đủ chín validation points. Giữ nguyên ảnh, không chèn nhận xét |

Đã tái dựng gói dev từ final adapter và input v3, dùng đúng serialization LF của Linux cho hai JSON được sinh tại runtime: config/hash manifest khớp hoàn toàn run plan của dev. Không đổi bytes các ZIP/run gốc để làm khớp checksum.

**Nhận xét training:** có bằng chứng mô hình học trên tập validation cố định; validation loss giảm tại mọi điểm đo nên **chưa thấy tín hiệu overfitting rõ trong lượt này**, không phải chứng minh không overfit. Learning rate/gradient hữu hạn và không có skipped update hỗ trợ kết luận train vận hành ổn định. Kết quả chấm dev được tách ở mục sau, không suy từ loss ra độ đúng câu trả lời.

Ảnh thực: [loss](../.private/comparison/runs/full-20261112T192034516377Z/figures/loss-curve.png), [optimizer](../.private/comparison/runs/full-20261112T192034516377Z/figures/optimizer.png), [VRAM](../.private/comparison/runs/full-20261112T192034516377Z/figures/memory.png), [runtime](../.private/comparison/runs/full-20261112T192034516377Z/figures/runtime.png). Adapter ở [final-adapter](../.private/comparison/runs/full-20261112T192034516377Z/final-adapter/); chưa cần train lại.

### Chấm old/new trên cùng dev

Đã chấm **60 output tuned+RAG**, gồm hai adapter trên cùng **30 câu dev** và cùng context; không tính lại các output Base/RAG vốn đã giống bytes giữa hai lượt. Giữ rubric gốc, xáo trộn seed 42 và che old/new bằng ID `J001`–`J060`; khóa điểm/lý do trước khi tổng hợp nhãn. Chấm nội dung raw riêng với format và renderer, không sửa output để tăng điểm. Không dùng khớp từ khóa hoặc ID citation hợp lệ thay cho đánh giá ý nghĩa.

Đối chiếu nguồn thực: **30 gold-page bindings + 150 context bindings**, **23 PDF / 120 trang vật lý**. Ghi rõ mệnh đề, đoạn nguồn, doc/version/page/offset và lý do cho từng đánh giá. Cùng mã renderer backend được chạy trên cả 60 output. [Báo cáo nguồn](../.private/comparison/assessment/dev-v2/source-verification.json), [review từng claim](../.private/comparison/assessment/dev-v2/judgments.jsonl), [kết quả renderer](../.private/comparison/assessment/dev-v2/renderer.jsonl).

| Chỉ số | Adapter pilot cũ | Adapter mới 770 train |
| --- | --- | --- |
| Điểm đúng/đủ, tổng trên 60 điểm | **47/60 (78,33%)** | **50/60 (83,33%)** |
| Đủ điểm 2/2 | **20/30** | **22/30** |
| Đúng một phần / 0 điểm | 7 / 3 | 6 / 2 |
| Faithfulness theo claim | **61/62 (98,39%)** | **71/73 (97,26%)** |
| Citation precision | **46/62 (74,19%)** | **62/73 (84,93%)** |
| Citation coverage | **46/62 (74,19%)** | **62/73 (84,93%)** |
| JSON parse / ID nguồn hợp lệ | 30/30 / 30/30 | 30/30 / 30/30 |
| Renderer hiển thị được | **29/30** | **30/30** |
| Từ chối nhầm câu có đáp án | 0/30 | 0/30 |
| Generation trung bình | 11,67 giây | 12,28 giây |

Tỷ lệ điểm rubric là **tổng điểm / 60**, không phải tỷ lệ câu đúng hoàn toàn. Citation precision và coverage tình cờ bằng nhau ở tập này vì mỗi claim có đúng một nguồn được chỉ định và không có claim thiếu ID; chúng vẫn là hai định nghĩa riêng. Faithfulness dùng toàn bộ context đã cấp; citation phải được chính đoạn đã dẫn hỗ trợ. Vì vậy vẫn có câu đúng nội dung nhưng sai citation. Output cũ cho câu điều kiện sức lao động có xuống dòng thật trong một item: nội dung đạt 2/2 nhưng renderer chặn, không biến thành sai nội dung hoặc âm thầm sửa lại. Điểm quy đổi sau renderer tương ứng **75,00% / 83,33%**, tách khỏi điểm raw.

So từng câu, adapter mới **thắng 5, thua 4, hòa 21** theo correctness. Điểm theo môn (mỗi môn tối đa 20): **CNXHKH 14→16; KTCTMLN 13→18; THMLN 20→16**. Ví dụ mới sửa đúng lựa chọn tư bản khả biến và nhận định độc quyền/cạnh tranh; ngược lại, câu cơ chế nhận thức qua lao động kém đầy đủ hơn bản cũ và câu nội dung kinh tế của liên minh bị hiểu nhầm thành chính trị. Không che các trường hợp thoái lui.

**Quyết định lựa chọn:** chọn adapter mới `51713be1e630135099f95ed08c89b5be8669b75c9e1908a1346c5c9cc4942ae7` vì điểm tổng, citation và khả năng hiển thị tốt hơn; ghi nhận giảm điểm Triết và faithfulness giảm nhẹ. Đây là lựa chọn thực dụng trên dev, không phải chứng minh adapter mới tốt hơn ở mọi môn hoặc khác biệt có ý nghĩa thống kê. Bản khóa thí nghiệm được ghi tại mục 6; chưa chạy main hoặc đổi chatbot.

**Giới hạn chấm:** cả 30 câu đều answerable nên **không đo được từ chối đúng trên câu thiếu căn cứ**; không trình bày 0 từ chối nhầm thành 100% đúng từ chối. Đây là một lượt chấm rubric trong phiên hiện tại, không phải hai reviewer độc lập hoặc API judge đã khóa model/revision/decoding; thông tin không được nền tảng cung cấp ghi `null` ở judge config, không bịa thông số. Quyết định từng câu được lưu và hash, validation/aggregation tái chạy xác định; điểm semantic vẫn có độ chủ quan. Dev đã dùng để chọn adapter, không thay main test và không tính 60 review này vào 900/990 lượt chấm main.

Đầu ra chính: [summary.json](../.private/comparison/assessment/dev-v2/summary.json), [scores.csv](../.private/comparison/assessment/dev-v2/scores.csv), [paired.jsonl](../.private/comparison/assessment/dev-v2/paired.jsonl), [judge-config.json](../.private/comparison/assessment/dev-v2/judge-config.json), [manifest.json](../.private/comparison/assessment/dev-v2/manifest.json). `dev-v1` giữ review ban đầu; `dev-v2` bổ sung xác minh renderer, chỉnh mô tả newline và tách rõ hai compound claims trước tổng hợp nhãn, không đổi điểm correctness. Công cụ [dev_scoring.py](../scripts/comparison/dev_scoring.py), [9 test mới](../scripts/comparison/tests/test_dev_scoring.py) đạt; không train lại và không gọi Qwen/GPU để chấm.

Mã dùng tiếp: [trainer mở rộng](../scripts/comparison/training.py), [audit/xuất](../scripts/comparison/training_audit.py), [biểu đồ](../scripts/comparison/training_report.py), [đóng gói/notebook](../scripts/comparison/package_training.py), [test mới](../scripts/comparison/tests/test_training.py). Giữ nguyên trainer và artifact pilot cũ, không tự commit/push/PR.

## 6. Chọn adapter và khóa thí nghiệm

Chọn **final adapter step 193**, học từ 770 mẫu train, dựa trên validation và đối chiếu cùng dev; không dùng instruction holdout hoặc điểm main để chọn model. Giữ nguyên adapter pilot làm mốc so sánh, không sửa các ZIP/run gốc.

| Thành phần | Nội dung đã chốt |
| --- | --- |
| Model | Qwen2.5-7B-Instruct, revision `a09a35458c702b33eeacc393d103063234e8bc28`; tokenizer/template/adapter được ràng buộc checksum |
| Ba nhánh | Base; Base + RAG; adapter mới + RAG. Hai nhánh RAG nhận cùng prompt/context/token IDs; Base không nhận context |
| Sinh đáp án | Greedy, seed 42, một beam, tối đa 512 output token / 4.096 input token; timeout hợp tác 90 giây, một lần sinh; không retry, sửa đầu ra, lịch sử hoặc response cache |
| Retrieval | Snapshot BGE-M3/FAISS đã kiểm; lọc môn trước top-5, cache context bất biến. Đây là so sánh generation trên retrieval cố định, không đo latency end-to-end của hệ thống online |
| Main | Giữ nguyên **300 câu: 240 có đáp án / 60 thiếu căn cứ**, chạy ba nhánh thành **900 output**. Dev 30 câu/90 output được tách riêng, không cộng vào mẫu số main |
| Diễn giải | Đánh giá trong cùng miền kiến thức, có giao một phần khái niệm/ý đáp án với dữ liệu lịch sử; không tuyên bố 300 khái niệm hoàn toàn mới |
| Đánh giá | Giữ raw output, tính cả lỗi trong mẫu số; chấm correctness, faithfulness, citation, format/renderer và từ chối theo rubric đã có. Điểm semantic phải lưu lý do/căn cứ và provenance reviewer; chưa coi là đã chạy API judge độc lập |
| Vận hành | Gói generator không chứa gold/reference, review, train hoặc holdout. Smoke ba nhánh trên **chính gói cuối đã khóa** phải đạt trước khi bắt đầu main; không cần train lại |

Bản khóa tại [frozen-experiment](../.private/comparison/prepared/frozen-experiment/): `freeze.json` ghi quyết định và hash đầu vào main/dev; `run-config.json` ghi cấu hình chạy; `source-lock.json` đối chiếu nguồn, dữ liệu và kết quả dev; `preflight.json` ghi kiểm CPU; `manifest.json` kiểm tính toàn vẹn bản khóa. Công cụ [freeze.py](../scripts/comparison/freeze.py) từ chối ghi đè và kiểm lại 330 câu / 990 đầu vào bằng tokenizer thật. Bản khóa là hợp đồng nguồn để đóng gói chạy, **chưa phải ZIP Kaggle**. Không đưa `source-lock.json` cùng tài liệu đánh giá riêng vào Input generator.

**115/115 test comparison đạt**, gồm bảy test mới về chọn adapter, giữ cấu hình, checksum và chống đường dẫn thoát thư mục. Không gọi Qwen, không train, không sửa chatbot trong bước này. Khi đổi model, prompt, benchmark, context hoặc generation policy phải tạo bản khóa mới và smoke lại; không sửa trực tiếp bản đã khóa.

**Thao tác tay:** bước 6 không cần chạy cell trên Kaggle. Bước 7 tiếp theo sẽ đóng ZIP và notebook theo bản khóa này, chạy smoke rồi main; session Kaggle mới chỉ cần nạp lại model để suy luận, không huấn luyện lại.

## 7. Chạy main — đã nhận và kiểm đủ 900 output

Gói [runner-main.zip](../.private/comparison/prepared/main-runner-fixed/runner-main.zip) và [receipt](../.private/comparison/prepared/main-runner-fixed/runner-main.receipt.json) ràng buộc đúng bản khóa mục 6. Gồm final adapter, tokenizer, runner, prompt/schema, dev phục vụ smoke và **300 câu main / 900 đầu vào model**. Không kèm base weights, gold/reference, review, train/validation/holdout hoặc tài liệu bàn giao riêng. Không cần thêm dataset training hoặc checkpoint `ohayo-model`; base được tải đúng revision hoặc dùng cache.

**125/125 test comparison đạt**, gồm smoke gate, notebook main và gọi entry point trực tiếp từ gói độc lập. Kiểm CPU xác thực tokenizer/adapter và toàn bộ 990 đầu vào; test double không phải kết quả Qwen. [Test](../.private/comparison/main-package-fix-tests.json), [preflight](../.private/comparison/prepared/main-runner-fixed/preflight.json), [mã đóng gói](../scripts/comparison/package_main.py), [gate main](../scripts/comparison/main_entry.py).

**Sửa gói trước khi chạy GPU:** bản ZIP đầu tiên thiếu `scripts/comparison/kaggle.py`, làm cell 2 dừng với `No module named scripts.comparison.kaggle`. Đã sửa allowlist để có đủ entry point inference, loại mã training không cần thiết và kiểm `--help` của kaggle/runner/main_entry ngay trong working directory của gói xuất. Giữ bản ZIP cũ để đối chiếu; dùng ZIP sửa và import lại notebook mới cùng nhau. Model, adapter, freeze, prompt và dữ liệu main/dev không thay đổi; chưa có main run cần phục hồi.

### Thao tác trên Kaggle

1. Mở notebook **OHAYO - Main Evaluation**; import lại [comparison_main.ipynb](../notebooks/comparison_main.ipynb) đã cập nhật. Upload ZIP sửa thành dataset **Private**, đặt tên **ohayo-main-evaluation-input-v2**, rồi thêm vào Input và bỏ Input main cũ để tránh nhầm. Có thể giữ phiên hiện tại; chạy lại code cell 1 để chọn đúng checksum và working directory mới, rồi cell 2. Không dùng ZIP training cho lượt này.
2. Chọn GPU **T4** (T4 x2 cũng được, code chỉ nhìn một GPU), bật Internet. Không cần ngrok hoặc inference token vì không mở chatbot/tunnel.
3. Chạy bốn **code cell** theo thứ tự trong cùng phiên:

| Cell | Công việc | Đầu ra cần kiểm |
| --- | --- | --- |
| 1 | Tìm ZIP hoặc dataset đã giải nén, kiểm SHA-256 từng file, tạo working copy riêng | Package authenticated, chưa nạp Qwen |
| 2 | Tạo môi trường inference riêng, giữ CUDA torch Kaggle, kiểm model/tokenizer/input | Environment/assets checked, chưa sinh đáp án |
| 3 | Nạp model và adapter, sáu warmup rồi smoke một câu × ba nhánh | **3 output, failure_rows = 0**, ZIP + receipt; không chấm chất lượng |
| 4 | Đối chiếu smoke đúng package/config, đủ warmup và 196 lớp LoRA bật/tắt đúng; chạy 300 câu × ba nhánh | **900 output**, audit trạng thái/hash/count, ZIP + receipt; semantic scoring chưa chạy |

Smoke và main chạy bằng subprocess riêng để giải phóng GPU sau mỗi lượt. Main có sáu warmup riêng, không tính vào 900 output. Ghi nhận thời gian, raw output, token, trạng thái dừng và VRAM; không sửa câu trả lời, không tự bỏ câu lỗi, không retry ngầm. Gate chặn chạy lại main cùng package khi thư mục kết quả trong phiên đã có run plan. Nếu phiên reset, phải giữ gói đã tải để đối chiếu, không tự coi là chưa chạy rồi chạy lại.

Ước lượng từ dev: 300 × tổng latency ba nhánh khoảng **2 giờ 45 phút**, cộng tải model, warmup, kiểm input và đóng gói; nên dự trù **3–4 giờ**, không phải thời gian cam kết. Độ dài đáp án và máy Kaggle có thể làm thời gian thay đổi.

4. Khi chạy xong, tải **ZIP + receipt + audit JSON của cả smoke và main**. Notebook in đường dẫn ở cuối cell; tất cả ở `/kaggle/working/comparison-main-runs/`. Audit nằm trong thư mục run và cũng có trong ZIP. ZIP main chứa outputs/measurements/warmup/runtime/run-plan/audit và console log; không chứa thêm adapter/base weights nên nhỏ hơn gói Input.
5. Gửi các file trên để kiểm 900 output rồi chuyển sang chấm/phân tích ở bước 8. Có exception hoặc số dòng thiếu thì giữ ZIP/log và gửi nguyên trạng; không chạy lại cell 4 để lấy kết quả đẹp hơn. Câu timeout/model error/output limit vẫn giữ trong mẫu số đánh giá.

### Kết quả đã nhận và xác thực

Đã nhận `smoke-20261113T010750639983Z.zip` và `main-20261113T011502419787Z.zip`, cùng receipt và audit JSON. Kiểm độc lập SHA-256/size/CRC, đủ bộ file, ba bản audit khớp nhau, package/config/freeze, lịch câu/nhánh, hash prompt/context/token IDs, model revision, dependency, sáu warmup mỗi lượt và trạng thái 196 lớp LoRA. Đúng adapter mới đã chọn; không retry và không có timeout/model error. Giữ nguyên bytes ZIP và raw output.

| Nội dung | Kết quả thực |
| --- | --- |
| Smoke | **3/3 completed**, sáu warmup đạt; đúng gói main sửa |
| Main | **900/900 output** của 300 câu × ba nhánh; **897 completed / 3 output_limit** |
| Base | 300 output: **299 completed / 1 output_limit**; generation trung bình **5,37 giây/câu** |
| RAG | 300 output: **298 completed / 2 output_limit**; generation trung bình **12,41 giây/câu** |
| Tuned + RAG | 300 output: **300 completed**, generation trung bình **9,73 giây/câu** |
| Tổng thời gian generation | **8.252,51 giây**, khoảng **2 giờ 17 phút 33 giây**; đây là tổng generation, không phải toàn bộ wall time gồm setup/load/warmup/audit |
| VRAM | Đỉnh allocated **7,909 GiB**, reserved **12,006 GiB**; reserved không đồng nghĩa bộ nhớ tensor đang dùng |
| Kiểm công cụ | **131/131 test comparison đạt**, gồm sáu test mới về receipt, file thiếu/thừa, audit và process lỗi; không chạy lại Qwen |

Ba output bị cắt ở **512 token**: Base `Q9adc337668772c04dbc7`; RAG `Qfc5f4409e51a7e8f56ee` và `Qd4a7c993e27bf136e316`. Giữ nguyên và đưa vào mẫu số 900; không chạy lại, sửa nối hoặc loại bỏ để cải thiện điểm. Đây là trạng thái kỹ thuật output limit, chưa tự suy thành điểm đúng/sai nội dung trước khi áp dụng rubric.

Minh chứng lưu riêng tại [main-intake](../.private/comparison/runs/main-intake/): [readback.json](../.private/comparison/runs/main-intake/readback.json) tổng hợp kiểm độc lập và latency/VRAM; [manifest.json](../.private/comparison/runs/main-intake/manifest.json) kiểm toàn bộ file; hai ZIP/receipt/audit giữ tên gốc; thư mục mỗi run chứa `outputs.jsonl`, `measurements.jsonl`, `warmup.jsonl`, `run-plan.json`, `runtime.json`, `progress.json`, `audit.json` và log. Mã [intake_main.py](../scripts/comparison/intake_main.py); [test](../.private/comparison/main-intake-tests.json).

**Bước 7 hoàn tất phần chạy và kiểm kết quả kỹ thuật.** Chưa chấm factuality/correctness/citation/từ chối hoặc kết luận mô hình mới tốt hơn trên main. Bước 8 sẽ dùng chính 900 output này để đánh giá; không cần train hoặc sinh đáp án lại. Không tự commit/push/PR, không thay model chatbot.

## 8. Chấm và phân tích — kết quả của hai thành viên

Đã tiếp nhận gói kết quả Cường ngày **14/11/2026**, kiểm SHA-256/kích thước/CRC và đủ 60 file theo manifest, sau đó tái chạy aggregate trên dữ liệu cuối của dự án. Review A ban đầu được giữ nguyên: **450 primary + 45 secondary**; review B có **450 primary + 45 secondary**. Ghép thành **900 primary trên 300 câu × ba nhánh**, dùng 90 secondary để đối chiếu riêng, không cộng trùng vào mẫu số. Bản mở rộng một reviewer vừa tạo đã được gỡ, không dùng bất kỳ điểm nào từ bản đó.

Cùng rubric, đơn vị item, raw/reference hash và failure policy; mỗi review gắn ID/hash, điểm, lý do và căn cứ nguồn. Kết quả gồm **14 output bất đồng đã có quyết định phân xử**, giữ nguyên review gốc A/B, bảng trước phân xử và decision log. Ba output_limit vẫn giữ trong 900 và nhận 0 correctness chính; không chạy lại Qwen, không train hoặc sửa raw/gold.

### Kết quả sau phân xử trên 300 câu mỗi nhánh

| Chỉ số | Base | RAG | Tuned + RAG |
| --- | --- | --- | --- |
| Tổng điểm / tối đa | **335/600** | **454/600** | **457/600** |
| Điểm đúng/đủ quy đổi | **55,83%** | **75,67%** | **76,17%** |
| Đạt 2/2 | 118/300 | 193/300 | 191/300 |
| Từ chối đúng trên 60 câu thiếu căn cứ | 47/60 | 58/60 | 59/60 |
| Từ chối rỗng nhầm trên 240 câu có đáp án | 3/240 | 3/240 | 10/240 |
| Bám nguồn theo item | N/A | 251/263 (95,44%) | 242/273 (88,64%) |
| Citation precision/coverage theo item | N/A | 207/263 (78,71%) | 177/273 (64,84%) |
| Generation trung bình | 5,37 giây | 12,41 giây | 9,73 giây |
| Renderer hoặc protocol riêng của Base hợp lệ | 222/300 | 269/300 | 299/300 |

Điểm quy đổi là tổng rubric 0/1/2 chia tối đa, **không phải tỷ lệ câu đúng hoàn toàn**. Support/citation tính trên item có mệnh đề kiểm chứng được; item nhiều ý cần được hỗ trợ toàn bộ. Output rỗng, không parse được và item không có assertion được đếm riêng, không mặc định 100% support; đây không phải atomic-claim faithfulness. Base không nhận context nên source support/citation N/A. Precision và coverage tình cờ bằng nhau do mỗi item đủ điều kiện có một citation; định nghĩa hai chỉ số vẫn khác.

**Nhận xét:** RAG cao hơn Base **19,83 điểm phần trăm**. Tuned + RAG nhỉnh RAG **0,50 điểm phần trăm**, nhưng CI 95% **[-3,17; +4,33]** còn chứa 0; có **36 thắng / 39 thua / 225 hòa** theo cặp 300 câu. Chưa đủ cơ sở kết luận tuning cải thiện correctness chắc chắn hoặc thắng toàn diện. Tuned có lợi về format/hiển thị, từ chối khi thiếu căn cứ và thời gian generation, nhưng bám nguồn/citation thấp hơn và từ chối nhầm nhiều hơn. Tuned sinh ít token hơn, không diễn giải latency thấp hơn thành tốc độ mỗi token cao hơn.

A/B trùng điểm correctness **81/90 (90,00%)**, Cohen kappa **0,8289**. Có 14 output bất đồng về điểm hoặc support/citation; không hiểu 14 là số câu khác điểm correctness. Đây là đồng thuận giữa các lượt **đánh giá rubric tự động có đối chiếu nguồn**, không phải độ tin cậy chấm tay. Provenance B ghi ba batch mù; exact judge revision/decoding không được nền tảng cung cấp, không khẳng định cùng phiên bản judge cố định. Bootstrap 10.000 lần seed 42 chỉ phản ánh biến thiên chọn câu, không bao gồm sai số judge hay biến thiên giữa các lượt train.

Retrieval dùng chung trên 240 câu answerable: page Recall@5 **79,38%**, MRR@5 **0,7081**, nDCG@5 **0,6982**, truy đủ trang gold ở multi-page **30,00%**. Không dùng 60 insufficient để tính recall; không tìm thêm để bù top-5 chunk trùng trang. Adapter không làm đổi retrieval cache. Benchmark có giao kiến thức đã công bố; kết luận chỉ trong phạm vi bộ kiểm ba môn đã khóa, không phải 300 khái niệm hoàn toàn mới hay độ trễ chatbot online end-to-end.

### Minh chứng và tái lập

- [Review A gốc](../.private/comparison/assessment/main/reviews-a.jsonl), [review B](../.private/comparison/assessment/member-b-v1/reviews-b.jsonl), [quyết định phân xử](../.private/comparison/assessment/adjudication-v1/decisions-notes.jsonl).
- Kết quả nhận từ Cường tại [group-v2](../.private/comparison/assessment/group-v2/): [900 scored rows](../.private/comparison/assessment/group-v2/scored-group.jsonl), [metrics.csv](../.private/comparison/assessment/group-v2/metrics.csv), [summary.json](../.private/comparison/assessment/group-v2/summary.json), paired/errors, bảng trước phân xử, decision log, bốn PNG và báo cáo MD/PDF.
- Kết quả tái tính riêng tại [group-reproduced](../.private/comparison/assessment/group-reproduced/). Summary/paired JSON khớp về nội dung; bốn file JSONL scored/primary-before/adjudication/adjudicated-reviews **khớp từng byte** với gói nhận. [Biên bản tái lập](../.private/comparison/inputs/member-b-handoff/reproduction.json).
- [group_scoring.py](../scripts/comparison/group_scoring.py) kiểm A/B locks, rubric, raw/reference/context, mapping/assignment và renderer trước khi ghép. [group_report.py](../scripts/comparison/group_report.py) vẽ biểu đồ từ số liệu thật, không chèn nhận xét vào ảnh. **156/156 test comparison đạt tại máy tiếp nhận**: [kết quả test](../.private/comparison/group-scoring-tests.json).

Không ghi đè bản đã khóa. Để tái lập, dùng thư mục output mới:

```text
python -m scripts.comparison.group_scoring aggregate --b-folder .private/comparison/assessment/member-b-v1 --adjudication .private/comparison/assessment/adjudication-v1/decisions-notes.jsonl --output .private/comparison/assessment/group-check
python -m scripts.comparison.group_report --output .private/comparison/assessment/group-check
```

Các lệnh cần môi trường CPU có numpy/jsonschema, vẽ ảnh cần matplotlib; không cần GPU. Các trạng thái pending trong snapshot `assessment/main/` được giữ nguyên theo manifest lịch sử, không phải trạng thái nhóm hiện hành.

## 9. Tiếp nhận và hoàn thiện bàn giao

Gói Dương [comparison-handoff.zip](../.private/comparison/handoff/comparison-handoff.zip) giữ nguyên đầu vào/run/review A đã khóa. Gói Cường [member-b-w7-handoff.zip](../.private/comparison/inputs/member-b-handoff/member-b-w7-handoff.zip) và [receipt](../.private/comparison/inputs/member-b-handoff/member-b-w7-handoff.receipt.json) chứa phần B/phân xử/kết quả nhóm; SHA-256 ZIP **6d67a86ac01c7336dfab19de53ed13eb8bce41bd2216c1a381afff54fe89eed2**. Hai gói bổ sung cho nhau, không tự hiểu ZIP Dương cũ đã chứa kết quả nhóm mới.

Đã kiểm manifest, tích hợp công cụ theo skeleton hiện có và tái lập kết quả. Sửa kiểm entrypoint để gói không mượn module từ PYTHONPATH của checkout; không đổi runner ZIP đã khóa, model, adapter, input hoặc kết quả main. Giữ provenance và log do Cường gửi riêng; không biến việc tiếp nhận thành khẳng định đã tự chạy lại các phép kiểm GPU/tokenizer/PDF của Cường.

Phần tiếp theo là Dương hoàn thiện **Evidence/W07** theo layout README.md, metrics.csv, test-results.txt, manifest.json, figures/ từ kết quả nhóm sau phân xử. Lưu review/raw/gold/weights/ZIP riêng; không đưa dữ liệu nhạy cảm vào Evidence công khai. Khi cần sửa điểm, đối chiếu ID/hash/tiêu chí và tạo bản dẫn xuất mới thay vì sửa review gốc. Việc cập nhật Evidence, commit/push/PR hoặc đổi model chatbot không được tự thực hiện trong lượt tiếp nhận này.

## Lộ trình tiếp theo

| Bước | Công việc | Trạng thái |
| --- | --- | --- |
| 1 | Tiếp nhận và kiểm đầu vào | Đã nhận và kiểm gói 1.000 mẫu; nguồn gốc 500 cũ + 250 A + 250 B khớp |
| 2 | Kiểm benchmark, tiếp nhận và chuẩn hóa dữ liệu train, chống leakage | Đã chuẩn hóa 1.000 mẫu, giữ 770/114/116; benchmark-v3 giữ review; fresh screen và giới hạn giao kiến thức được bổ sung ở bước 3 |
| 3 | Xây runner, test và xác minh model/adapter | Đã hoàn thành runner/test, BGE/cache mới, kiểm 990 input và gói dev; xác minh reload Qwen thật chuyển sang GPU smoke ở bước 4 |
| 4 | Smoke và chạy dev với adapter cũ | Đã kiểm smoke 3/3, dev 90/90; phần tuned+RAG được chấm đối chiếu ở mục 5 |
| 5 | Train mở rộng 770 mẫu một epoch, audit và đối chiếu trên dev | Full đạt 193 updates/1 epoch; đã chấm 60 old/new outputs và ghi regressions |
| 6 | Chọn adapter và khóa phiên bản thí nghiệm | Đã chọn adapter mới, khóa model/config/benchmark/retrieval và kiểm 990 đầu vào; chưa chạy main |
| 7 | Chạy main 300 câu × ba nhánh | Đã xác thực đủ 900 output: 897 completed, 3 output_limit; giữ nguyên toàn bộ để chấm |
| 8 | Ghép chấm A/B và phân tích nhóm | Đủ 900 primary + 90 secondary, 14 output đã phân xử; đã tái lập kết quả nhóm khớp gói Cường |
| 9 | Kiểm gói và hoàn thiện bàn giao | Đã tiếp nhận gói B, kiểm checksum và tái lập aggregate/report; Evidence/W07 do Dương hoàn thiện sau cùng |

Giữ nguyên artifact cũ, không tự commit/push/PR hoặc triển khai adapter vào chatbot. Các đầu ra sinh sau phải có run/hash thực; không dùng 990 đầu vào đã chuẩn bị để thay cho kết quả model.


## 10. Kết quả nhóm và phần Cường — hoàn thành 14/11/2026

## Thiết kế và phạm vi

Đánh giá 300 câu trên THMLN, KTCTMLN, CNXHKH, mỗi môn 100 câu. Toàn bộ gồm 120 factual, 90 explanation, 30 multi-page và 60 insufficient. Cùng Qwen2.5-7B-Instruct revision a09a35458c702b33eeacc393d103063234e8bc28, NF4 double quant FP16. Adapter mới được huấn luyện một epoch, 193 updates trên 770 train và 114 validation; 116 holdout tách riêng. Adapter được chọn bằng dev trước khi khóa main. Hai nhánh RAG dùng cùng cache, messages và token IDs; Base không nhận học liệu. Greedy, seed 42, tối đa 512 token, một lượt sinh/câu/nhánh, một GPU T4.

Có 900 output thực, 897 completed và 3 output_limit. Giữ cả ba lỗi trong mẫu số và chấm 0 correctness chính. Đã có 900 primary, 90 secondary và phân xử mọi bất đồng được phát hiện. Điểm nội dung được tạo bằng agent theo rubric có đối chiếu nguồn; exact judge revision và decoding không được nền tảng cung cấp.

## Kết quả trên toàn bộ 300 câu mỗi phương pháp

| Chỉ số | Base LLM | RAG | Tuned + RAG |
|---|---:|---:|---:|
| Tổng điểm rubric / 600 | 335/600 | 454/600 | 457/600 |
| Điểm đúng/đủ quy đổi (%) | 55,83 | 75,67 | 76,17 |
| Câu đạt 2/2 | 118/300 | 193/300 | 191/300 |
| Từ chối đúng trên 60 câu thiếu căn cứ | 47/60 | 58/60 | 59/60 |
| Từ chối rỗng nhầm trên 240 câu có đáp án | 3/240 | 3/240 | 10/240 |
| Bám nguồn theo item (%) | N/A | 95,44 | 88,64 |
| Citation precision theo item (%) | N/A | 78,71 | 64,84 |
| Citation coverage theo item (%) | N/A | 78,71 | 64,84 |
| Generation trung bình (giây) | 5,37 | 12,41 | 9,73 |
| Generation p95 (giây) | 11,22 | 29,90 | 17,73 |
| Output token | 21801 | 26547 | 13282 |

Điểm phần trăm là tổng điểm rubric chia điểm tối đa. Tỷ lệ đạt 2/2 được ghi riêng. Faithfulness/citation dùng item có mệnh đề kiểm chứng được; một item nhiều ý phải được hỗ trợ đầy đủ. Output rỗng, không parse được và item không có assertion được đếm riêng, không tự nhận 100% hỗ trợ. Base có các chỉ số nguồn/citation N/A. Xem metrics.csv để đối chiếu tử số, mẫu số và từng môn/loại.

## So sánh theo cặp

| So sánh | Chênh lệch điểm % | CI 95% | Thắng / thua / hòa |
|---|---:|---|---|
| rag so với base | 19,83 | [14,50; 25,33] | 112 / 39 / 149 |
| tuned_rag so với rag | 0,50 | [-3,17; 4,33] | 36 / 39 / 225 |
| tuned_rag so với base | 20,33 | [14,83; 25,67] | 109 / 33 / 158 |

RAG tăng điểm đúng/đủ so với Base trong phạm vi benchmark này. Tuned+RAG chênh 0,50 điểm phần trăm so với RAG. CI còn chứa 0, nên chưa đủ cơ sở khẳng định tuning làm tăng correctness chắc chắn. Các chỉ số nguồn/citation cần đọc cùng correctness và khả năng hiển thị; kết quả không cho thấy tuned thắng toàn diện.

Bootstrap 10.000 lần, seed 42, resample theo câu hỏi để giữ ba nhánh cùng nhau. CI phản ánh biến thiên chọn câu, chưa bao gồm sai số judge hoặc độ biến thiên giữa các lần train.

## Kiểm độc lập, đồng thuận và giới hạn

Đã tái kiểm đủ 900 ID/arm, config/input/context hash, lịch chạy và log trạng thái LoRA; kiểm bytes/config/392 tensor của adapter, tái tính token IDs của 990 đầu vào dev/main. Đã đối chiếu 1.500 context bindings và 352 gold-page bindings trên 354 trang vật lý thuộc 27 PDF. Nguồn main không nằm trong train/validation thực 770/114. Báo cáo leakage 385/57/58 trong gói gốc là bản lịch sử; kết quả kiểm độc lập 770/114/116 được lưu riêng, giữ nguyên artifact gốc.

A và B cùng điểm correctness ở 90,00% của 90 lượt đối chiếu; Cohen kappa 0,8289. Đã phân xử 14 output có bất đồng về điểm hoặc support/citation. Các review gốc A/B và quyết định mới được giữ riêng. Đây là đồng thuận giữa các lượt đánh giá tự động, có thể có sai số hoặc thiên lệch chung của model.

Retrieval dùng chung trên 240 câu answerable: page Recall@5 79,38%, MRR@5 0,7081, nDCG@5 0,6982; truy đủ trang của câu multi-page đạt 30,00%. Adapter không làm đổi cache retrieval đã khóa.

Tổng generation 8252,51 giây. Số đo này tách khỏi setup/load/warmup và retrieval offline, chưa phải độ trễ API end-to-end. Tuned sinh ít token hơn RAG; thời gian thấp hơn không tự chứng minh tốc độ mỗi token cao hơn.

Benchmark chỉ phủ ba chương và có giao kiến thức đã công bố. Chấm nguồn theo item bảo thủ; exact judge revision không xác minh được. Các khác biệt theo môn/loại và lỗi nằm trong metrics.csv/errors.csv. Kết quả là bằng chứng so sánh trên bộ test đã khóa, phạm vi suy rộng cần giữ đúng giới hạn này.

## Đầu ra gửi Dương

Gửi review B đã khóa, 90 lượt đối chiếu, 14 quyết định phân xử, summary/metrics/paired/errors, bốn biểu đồ và log kiểm/test cùng manifest/checksum. Dương hoàn thiện Evidence/W07 sau cùng từ các artifact cuối này. Raw, benchmark, adapter và review A gốc được giữ nguyên.


### Tái lập phần chấm/tổng hợp

Giữ nguyên snapshot/raw/review gốc. Code mới `scripts/comparison/group_scoring.py` dùng lại `assignment`, `semantic_metrics`, `paired`, parser và kiểm input/output có sẵn. `group_report.py` dựng báo cáo/biểu đồ từ summary thực. `package_main.py` đã sửa kiểm entrypoint để gói thiếu module không mượn module từ PYTHONPATH của máy nhận.

Kết quả cuối riêng tư tại `.private/comparison/assessment/group-v2/`, review Cường `.private/comparison/assessment/member-b-v1/`, phân xử `.private/comparison/assessment/adjudication-v1/`. Bản group-v1 là bản dẫn xuất trước khi hoàn thiện phần provenance/kỹ thuật, dùng group-v2 để bàn giao. Nhật ký kiểm đầu vào độc lập tại `.private/comparison/work/cuong-20261114/`.

```text
python -m unittest discover -s scripts/comparison/tests
python -m scripts.comparison.group_scoring aggregate --b-folder .private/comparison/assessment/member-b-v1 --adjudication .private/comparison/assessment/adjudication-v1/decisions-notes.jsonl --output .private/comparison/assessment/group-reproduced-v1
python -m scripts.comparison.group_report --output .private/comparison/assessment/group-reproduced-v1
```

Các lệnh aggregate/report cần các dữ liệu cuối được phục hồi bằng restore-map gói Dương và kết quả B/phân xử trong gói Cường. Dùng thư mục output mới, giữ nguyên bản đã đóng. Vẽ biểu đồ dùng matplotlib đã khai báo trong training-requirements; tổng hợp dùng numpy và jsonschema. PDF báo cáo hai trang có trong gói riêng cùng nguồn dựng PDF; phần PDF cần reportlab. Các phép kiểm/tokenizer CPU tái sử dụng môi trường W6.

Sau nhận `member-b-w7-handoff.zip` và receipt, Dương kiểm checksum/manifest, chạy lại test và aggregate sang thư mục mới, đối chiếu 900/90 và số liệu nhóm. Hoàn thiện Evidence/W07 gồm README, metrics.csv, test-results.txt, manifest.json, figures theo layout đã thống nhất; ghi đúng artifact/run/hash cuối. Các gói dữ liệu/raw/weights/review chỉ gửi riêng. PR/commit/merge và thay model chatbot là thao tác riêng theo quyết định của nhóm.
