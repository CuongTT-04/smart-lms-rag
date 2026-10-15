# W3 - Tổng hợp quy trình và kết quả của thành viên A

**Thành viên:** Vũ Nam Dương (A).  
**Ngày tạo:** 14/10/2026. **Cập nhật gần nhất:** 16/10/2026.  
**Mục đích:** Báo cáo tổng hợp duy nhất cần đọc để theo dõi phần việc A, quy trình, kết quả đo và bằng chứng bàn giao. Các mục đầu giữ lịch sử phát triển; mục 9-10 chốt kết quả tích hợp hiện hành. Không thay thế phê duyệt nghiệm thu của nhóm.

**Tóm tắt hiện tại:** Đã hoàn thành phần triển khai và chạy baseline retrieval của A trên 27 PDF/1.048 chunk/100 QA development. Page Recall@1/3/5/10 đạt 0,73/0,94/0,97/0,98; không có prediction thiếu hoặc lỗi truy xuất. Reuse sau session reset giữ nguyên 100/100 danh sách top-k và toàn bộ score, cùng index/chunk bytes. Đã lưu notebook có outputs, hai ZIP kết quả và môi trường thực thi. Còn xác nhận human peer review, chốt source commit tương ứng, xác nhận B nhận bàn giao và, nếu nhóm yêu cầu, một lượt notebook sạch chạy tuần tự hoàn toàn. Không ghi toàn bộ W3 đã nghiệm thu khi các mục này chưa có minh chứng.

Nguồn phân công: `D:\Downloads\2026-10-12-ke-hoach-w3.md` và danh sách tám công việc A có thể làm trước khi nhận bàn giao từ B đã thống nhất trong chat. Số thứ tự dưới đây theo danh sách đó, không phải mã milestone M1-M5.

## 1. Bảng theo dõi công việc

| STT | Công việc | Trạng thái | Phạm vi kết quả hiện tại |
|---|---|---|---|
| 1 | Chuẩn bị môi trường embedding | Hoàn thành bước chuẩn bị ban đầu | Nạp BGE-M3 thật, cấu hình cache, tạo vector và đo thử trên ba đoạn tiếng Việt. Chưa chốt batch tối ưu cho corpus. |
| 2 | Xây dựng embedding service | Hoàn thành | Service nhận chunk, sinh vector gắn đúng ID, xử lý ngoại lệ; 19 kiểm thử tự động và chạy thử model thật đạt. |
| 3 | Xây dựng index FAISS | Hoàn thành từ mẫu đến corpus tích hợp | Mẫu 12 vector; baseline thật 1.048 vector với mapping nguồn và checksum. |
| 4 | Viết chức năng lưu/tải lại index | Hoàn thành, đã kiểm chứng corpus | Hai ZIP giữ cùng index/chunk bytes; 100/100 top-k và score giống nhau sau reuse; mỗi runner có 3 reload checks. |
| 5 | Viết hàm truy xuất top-k | Hoàn thành phần A và nhận code tích hợp B | Truy xuất trong scope trước top-k, revalidate; baseline offline chạy đủ 100 QA. Bridge DB do B tích hợp, phép đo này không xác minh quyền DB. |
| 6 | Rà soát và bổ sung QA | Hoàn thành kiểm tra hỗ trợ; chờ human peer | A sửa 24 QA Triết học cũ và thêm 25 câu; tích hợp 100 QA với B, kiểm tra nguồn 100/100, xử lý KTCTMLN_QA_001 và hai chỉnh sửa; không tự gán peer approval. |
| 7 | Viết công cụ tính metric | Hoàn thành, đã dùng cho baseline thật | Đối chiếu trực tiếp CSV/JSON và tính độc lập Recall/Hit cả hai lượt đều khớp; 100 mẫu có gold hợp lệ, 0 lỗi. |
| 8 | Notebook và gói minh chứng | Hoàn thành notebook có outputs và reuse; còn điều kiện chốt nhóm | File tải về có 15 tiêu đề/15 code cell, 14 cell code có outputs, 118 test OK; baseline/reuse đầy đủ và pip freeze. Không tự xác nhận một lượt Run All sạch từ outputs ghép nhiều session. |

Corpus thật, tích hợp source A/B, baseline và artifacts kết quả đã có; phần còn chờ được liệt kê riêng ở mục 10. Các phát biểu "chưa đo corpus" trong mục 2-8 là trạng thái lịch sử lúc hoàn thành từng công cụ, không phải kết luận hiện tại.

## 2. Công việc 1 - Chuẩn bị môi trường embedding

**Ngày kiểm chứng:** 13/10/2026.  
**Trạng thái:** Hoàn thành bước chuẩn bị và chạy thử ban đầu.

### Mục tiêu

Chuẩn bị môi trường Python có thể chạy BGE-M3 thật để chuyển văn bản tiếng Việt thành vector, đồng thời xác định cách lưu model và ghi nhận cấu hình, thời gian, bộ nhớ ban đầu.

### Quy trình đã thực hiện

1. Xác định môi trường Python thực tế của dự án là `backend\.venv`.
2. Xác nhận các thư viện embedding đã cài: PyTorch, Sentence Transformers, Hugging Face Hub, NumPy và psutil.
3. Nạp model `BAAI/bge-m3`; ghi lại revision cụ thể thay vì chỉ dùng tên model.
4. Kiểm tra cache đã có ở ổ D, lưu biến môi trường `HF_HOME=D:\AIModels\huggingface` ở mức tài khoản Windows và bổ sung tham chiếu `main` còn thiếu.
5. Nạp model offline từ cache mới, tạo một vector `(1, 1024)` thành công. Cache cũ ở ổ C được giữ lại.
6. Chạy ba đoạn tiếng Việt trên CPU với batch size 1, 2 và 4; kiểm tra giới hạn token, kích thước vector, giá trị hữu hạn và chuẩn hóa L2.

### Cấu hình và môi trường đã ghi nhận

| Thuộc tính | Giá trị |
|---|---|
| Model | `BAAI/bge-m3` |
| Revision | `5617a9f61b028005a4858fdac845db406aefb181` |
| Python | `3.13.7` |
| PyTorch | `2.14.1+cpu` |
| Sentence Transformers | `6.1.0` |
| Transformers | `5.19.0` |
| Hugging Face Hub | `1.33.0` |
| NumPy | `2.5.4` |
| psutil | `7.2.2` |
| Thiết bị thực hiện phép đo | CPU |
| Cache | `D:\AIModels\huggingface` |
| Giới hạn đầu vào trong phép thử | 512 token, gồm token đặc biệt |
| Chiều vector | 1.024 |
| Chuẩn hóa | L2 |

### Kết quả

Thời gian nạp model trong phép thử ban đầu: **5,67 giây**. Thời gian này tính từ bước khởi tạo model, không tính lần tải weights đầu tiên.

| Batch size cấu hình | Thời gian xử lý ba đoạn | Kích thước đầu ra | RAM tiến trình |
|---|---:|---|---:|
| 1 | 0,598 giây | `(3, 1024)` | 1,84 GiB |
| 2 | 0,277 giây | `(3, 1024)` | 1,84 GiB |
| 4 | 0,237 giây | `(3, 1024)` | 1,84 GiB |

Tất cả assertion đạt: đầu vào không vượt giới hạn token; đầu ra đúng số lượng và chiều vector; không có NaN/vô cực; độ dài L2 của từng vector xấp xỉ 1.

### Minh chứng và giới hạn

- Bảng trên ghi lại output thực tế đã chạy trong chat, chưa có artifact riêng của phép đo ban đầu.
- Cấu hình được lưu thành file trong công việc 2 tại [config.json](backend/apps/ai/embeddings/config.json).
- Ba đoạn ngắn chỉ kiểm chứng khả năng chạy model. Batch 4 thực tế xử lý ba đoạn; lượt đầu có thể chịu chi phí khởi động.
- RAM là RSS của tiến trình tại thời điểm lấy mẫu, không phải mức đỉnh và không phải VRAM.
- Chưa chọn batch tối ưu. Cần đo thêm trên nhiều chunk gần độ dài thực tế trước khi xử lý corpus.

## 3. Công việc 2 - Xây dựng embedding service

**Ngày kiểm chứng:** 13/10/2026.  
**Trạng thái:** Hoàn thành service và kiểm chứng trên mẫu.

### Mục tiêu

Tạo thành phần tái sử dụng nhận danh sách chunk có ID và văn bản, trả vector gắn đúng ID để phục vụ lập chỉ mục và tìm kiếm ở các công việc tiếp theo.

### Quy trình đã thực hiện

1. Đọc cấu trúc module AI và xác nhận các file embedding chưa có triển khai.
2. Định nghĩa cấu hình model, kiểu kết quả và mã lỗi trong `base.py`; lưu cấu hình JSON và mã hash để đối chiếu các lượt chạy.
3. Xây dựng `EmbeddingService`, nạp model khi có dữ liệu cần xử lý và tái sử dụng model trong cùng service instance.
4. Kiểm tra đầu vào: mỗi chunk phải có ID hợp lệ, ID không trùng trong một lần gọi và văn bản không rỗng. Không sửa metadata nguồn của bên gọi.
5. Đếm token bằng tokenizer của model, gồm token đặc biệt và không truncation; từ chối đoạn vượt giới hạn thay vì cắt nội dung ngầm.
6. Sinh dense embedding theo batch, không thêm prompt; chuyển đầu ra thành mảng float32 liên tục và kiểm tra số hàng, chiều vector, giá trị hữu hạn, chuẩn hóa L2.
7. Trả ID theo thứ tự hàng vector, số token và hash cấu hình. Bổ sung `embed_query()` dùng cùng thiết lập để embedding câu hỏi.
8. Viết kiểm thử chuẩn/ngoại lệ, script kiểm chứng model thật và tài liệu hướng dẫn sử dụng, bàn giao.

### Đầu ra đã tạo

| File | Nội dung |
|---|---|
| [base.py](backend/apps/ai/embeddings/base.py) | `EmbeddingConfig`, `EmbeddedChunks` và `EmbeddingError`. |
| [service.py](backend/apps/ai/embeddings/service.py) | Service embedding chunk và câu hỏi, nạp model một lần, kiểm tra token/vector. |
| [config.json](backend/apps/ai/embeddings/config.json) | Model/revision, CPU, batch 2, 512 token, float32, 1.024 chiều, L2 và chế độ dùng cache offline. |
| [requirements-embedding.txt](backend/requirements-embedding.txt) | Dependencies tùy chọn cho phần embedding; chưa tự thêm vào image Docker hiện tại. |
| [test_embeddings.py](backend/apps/ai/tests/test_embeddings.py) | Kiểm thử hợp đồng, lỗi đầu vào, model và vector. |
| [check_embeddings.py](scripts/check_embeddings.py) | Script chạy BGE-M3 thật và xuất minh chứng cấu hình, kết quả. |
| `docs/embedding-service.md` (tài liệu lịch sử, hiện không còn tại đường dẫn này) | Hướng dẫn cài đặt, sử dụng, kiểm tra và giới hạn. |
| [w3-embedding-smoke.json](data/processed/w3-embedding-smoke.json) | Kết quả chạy thực tế gần nhất; file sinh cục bộ, được Git bỏ qua. |

### Kết quả kiểm chứng

**Kiểm thử tự động:** 19/19 đạt. Bao gồm mapping ID/vector, đầu vào rỗng, ID trùng/sai, văn bản rỗng, biên token, đoạn vượt giới hạn, lỗi inference, sai kích thước/dtype, vector NaN/vô cực hoặc chưa chuẩn hóa, nạp model một lần và thử lại khi nạp thất bại. Đây là kiểm thử bằng model giả lập để kiểm tra các nhánh xử lý; phép chạy model thật được ghi riêng dưới đây.

**Kiểm chứng model thật:** chạy offline trên CPU với cache ổ D, status `PASSED`.

| Nội dung | Kết quả thực tế |
|---|---|
| Đầu vào | Ba đoạn tiếng Việt mẫu, không phải corpus/benchmark W3 |
| Số token từng đoạn | 15, 17, 15 |
| Batch size | 2, cấu hình khởi đầu |
| Kích thước vector | `(3, 1024)` |
| Dtype | `float32` |
| Độ dài L2 | `1.0`, `1.0`, `1.0` |
| Mapping khi đảo thứ tự chunk | Đúng; vector vẫn gắn với đúng ID |
| Embedding câu hỏi | Vector `(1024,)`, giá trị hữu hạn |
| Đoạn quá giới hạn | Bị từ chối với `TOKEN_LIMIT_EXCEEDED` |
| Lượt đầu, gồm nạp model | 27,585 giây |
| Lượt gọi lại với model đã nạp | 0,302 giây |
| RSS tiến trình lấy mẫu, không phải mức đỉnh | 1,836 GiB |
| Hash cấu hình | `2918526ee7d27db8c48d7ff6508c311e1fad4add7c0b877cb90c98c689436140` |

Số liệu lượt đầu của công việc 2 có phạm vi đo khác thời gian nạp model ở công việc 1, vì bao gồm cả luồng service và sinh vector. Không dùng hai số liệu để suy ra model chạy nhanh/chậm hơn giữa các lần thử.

Kiểm tra biên dịch Python và `git diff --check` cũng đạt. Chưa commit hoặc push các đầu ra này.

### Cách chạy lại

Từ thư mục gốc dự án:

```powershell
$env:HF_HOME = "D:\AIModels\huggingface"
$env:PYTHONPATH = "$PWD\backend"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
.\backend\.venv\Scripts\python.exe -X utf8 -m unittest discover -s backend/apps/ai/tests -v
.\backend\.venv\Scripts\python.exe -X utf8 scripts/check_embeddings.py
```

Script ghi đè file kết quả chạy thử cục bộ; cần lưu bản riêng nếu muốn giữ lịch sử nhiều lượt đo.

### Giới hạn và công việc tiếp theo

Service đã được kiểm chứng bằng mẫu, chưa lập index corpus, chưa đo Recall và chưa xác nhận quyền truy xuất tích hợp. Thông tin course/document/version/page vẫn thuộc metadata chunk của bên gọi; dùng ID để nối vector về nguồn. B phụ trách nguồn, quyền và phiên bản hiện hành.

Bước tiếp theo theo danh sách công việc là xây dựng index FAISS mẫu và kiểm tra lưu/tải lại index. Batch 2 chưa được coi là tối ưu cho dữ liệu thực tế.

## 4. Công việc 3 - Xây dựng index FAISS mẫu

**Ngày kiểm chứng:** 14/10/2026.  
**Trạng thái:** Hoàn thành index mẫu; chưa phải index corpus hoặc nghiệm thu retrieval theo quyền.

### Mục tiêu

Đưa vector sinh bởi embedding service vào FAISS, giữ mapping hàng vector về chunk và nguồn, rồi kiểm tra tìm kiếm tương đồng trên một tập mẫu nhỏ.

### Quy trình đã thực hiện

1. Cài `faiss-cpu` vào `backend\.venv`, phiên bản kiểm chứng `1.15.1`; bổ sung dependency vào `requirements-embedding.txt`.
2. Tạo 12 chunk tiếng Việt mẫu thuộc ba nhóm nội dung. Ghi rõ UUID, tài liệu và trang là nhãn mô phỏng, không tham chiếu database hoặc PDF thật.
3. Dùng embedding service chạy BGE-M3 thật, cùng revision/cấu hình của công việc 2, trên CPU và cache offline ở ổ D.
4. Xây `DenseIndex` dùng FAISS `IndexFlatIP` với 1.024 chiều, float32 và vector chuẩn hóa L2. Kiểm tra số vector, thứ tự ID, cấu hình, metadata nguồn và giá trị vector trước khi thêm vào index.
5. Lưu mapping hàng vector -> chunk ID -> course/document/version/page trong manifest. Metadata được sao chép để thay đổi từ bên gọi không làm sai mapping trong index.
6. Truy vấn bằng vector của từng chunk để kiểm tra self-search, sau đó embedding ba câu hỏi và tìm top-5, trả rank, score, text và thông tin nguồn.
7. Xuất index nhị phân, chunk mẫu, manifest và kết quả. Mỗi lần build tạo một index mới, không append vào index cũ.
8. Kiểm thử FAISS thật bằng vector kiểm soát được, đối chiếu ranking/score với NumPy; chạy luồng hoàn chỉnh với BGE-M3 thật và kiểm tra artifact.

### Đầu ra đã tạo

| File | Nội dung |
|---|---|
| [index.py](backend/apps/ai/retrieval/index.py) | `DenseIndex`, kiểm tra dữ liệu/mapping và tìm kiếm IndexFlatIP nội bộ trên snapshot offline. |
| [w3-sample-chunks.json](data/fixtures/w3-sample-chunks.json) | Fixture gồm 12 chunk và ba câu hỏi; nguồn được ghi rõ là mô phỏng. |
| [build_sample_index.py](scripts/build_sample_index.py) | Sinh embedding, tạo index, truy vấn và xuất các artifact mẫu. |
| [test_index.py](backend/apps/ai/tests/test_index.py) | 17 kiểm thử index chuẩn/ngoại lệ, sử dụng FAISS thật. |
| `docs/sample-faiss-index.md` (tài liệu lịch sử, hiện không còn tại đường dẫn này) | Hướng dẫn chạy, hợp đồng và giới hạn index mẫu. |
| [sample.index](data/processed/w3-sample-index/sample.index) | Index FAISS nhị phân chứa 12 vector. |
| [chunks_sample.jsonl](data/processed/w3-sample-index/chunks_sample.jsonl) | Chunk mẫu đã gắn thông tin nguồn mô phỏng. |
| [sample_index_manifest.json](data/processed/w3-sample-index/sample_index_manifest.json) | Model/config/runtime, mapping từng hàng, số lượng và checksum. |
| [sample_query_results.json](data/processed/w3-sample-index/sample_query_results.json) | Kết quả top-5 từng câu hỏi, thời gian và các kiểm tra thực tế. |

Artifact trong `data/processed/` là dữ liệu sinh cục bộ được Git bỏ qua. Fixture, mã nguồn và tài liệu là các file có thể quản lý bằng Git; chưa commit/push ở bước này.

### Kết quả kiểm chứng

**Kiểm thử tự động:** 17/17 kiểm thử index đạt; chạy hồi quy cùng 19 kiểm thử embedding, tổng cộng **36/36 đạt**. Bao gồm ranking/score so với NumPy, mapping nguồn, k vượt số chunk, metadata không bị sửa từ bên ngoài, build lại không cộng dồn, ID trùng, nguồn sai, lệch cấu hình/thứ tự, vector sai và query không hợp lệ.

**Chạy BGE-M3 và FAISS thật:** status `PASSED`.

| Nội dung | Kết quả thực tế |
|---|---|
| Số chunk/vector | 12/12 |
| Kiểu index | `IndexFlatIP` |
| Chiều vector và dtype | 1.024, `float32`, chuẩn hóa L2 |
| Self-search trả đúng chunk ID | 12/12 |
| Câu hỏi mẫu có top-1 đúng kỳ vọng fixture | 3/3 |
| Top-k truy vấn mẫu | 5 |
| Sinh embedding, gồm nạp model | 32,706 giây |
| Xây index từ vector đã có | 0,00115 giây |

| Câu hỏi mẫu | Top-1 | Score tương đồng |
|---|---|---:|
| Vật chất tác động như thế nào đến ý thức và ý thức tác động trở lại ra sao? | `fixture-philosophy-2` | 0,770988 |
| Hai thuộc tính của hàng hóa là gì? | `fixture-economics-1` | 0,698090 |
| Gia đình có những chức năng cơ bản nào? | `fixture-socialism-3` | 0,825125 |

Score là inner product trên vector chuẩn hóa, không phải xác suất câu trả lời đúng. Tỷ lệ 3/3 trên fixture không phải Page Recall hay kết quả benchmark 100 QA. Kiểm tra biên dịch Python và `git diff --check` đạt.

### Cách chạy lại

Từ thư mục gốc dự án:

```powershell
$env:HF_HOME = "D:\AIModels\huggingface"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
.\backend\.venv\Scripts\python.exe -X utf8 scripts/build_sample_index.py
```

Script xuất artifact vào `data/processed/w3-sample-index/`. Thời gian chạy có thể thay đổi theo tải máy; model/revision/config và nội dung fixture được ghi để đối chiếu.

### Giới hạn và công việc tiếp theo

Chưa lập chỉ mục 27 PDF, chưa nhận chunk thật của B, chưa kiểm chứng reload và chưa kiểm soát quyền người dùng trên index. Hàm tìm kiếm ở đây chỉ phục vụ index offline, không có endpoint công khai. Không dùng nó trực tiếp để phục vụ học viên khi chưa có scope/quyền hiện hành.

Index nhị phân đã được xuất để làm artifact mẫu. Công việc 4 sẽ bổ sung chức năng lưu/tải lại có kiểm tra checksum, cấu hình và mapping, rồi xác nhận truy vấn sau load nhất quán. Công việc 5 sẽ bổ sung truy xuất trong tập nguồn hợp lệ.

## 5. Công việc 4 - Lưu và tải lại index

**Ngày kiểm chứng:** 14/10/2026.  
**Trạng thái:** Hoàn thành chức năng lưu/load và kiểm chứng trên index mẫu.

### Mục tiêu

Giữ lại index sau khi tắt tiến trình để lần chạy sau sử dụng ngay, đồng thời bảo đảm vector, cấu hình embedding và metadata nguồn thuộc cùng một bộ dữ liệu. Load index không cần nạp BGE-M3 hoặc sinh lại embedding.

### Quy trình đã thực hiện

1. Bổ sung `save_index()` và `load_index()` trong module `storage.py`.
2. Mỗi lần lưu tạo một snapshot mới gồm index nhị phân, chunk JSONL và manifest. Manifest ghi model/revision/config, số lượng, mapping, checksum và phiên bản FAISS.
3. Ghi và flush các file trước, rồi thay thế `current.json` nguyên tử để chọn snapshot hoàn chỉnh. Nếu ghi hoặc đổi pointer thất bại, snapshot đang dùng vẫn được giữ nguyên; không append vector vào bản cũ.
4. Khi load, kiểm tra pointer, đường dẫn, checksum manifest/index/chunks và cấu hình mong đợi trước khi deserialize FAISS.
5. Kiểm tra kiểu index, metric, chiều/số vector, giá trị hữu hạn, chuẩn hóa và metadata nguồn; đối chiếu mapping với manifest để phát hiện lệch thứ tự hoặc sai nguồn.
6. Chạy lại script build với BGE-M3 thật, lưu/load index và so sánh đầy đủ top-5 trước/sau load cho ba câu hỏi.
7. Lưu vector câu hỏi dùng kiểm chứng và chạy `check_index_reload.py` trong một tiến trình Python mới. Tiến trình chỉ đọc index/vector đã lưu, không import Sentence Transformers hoặc nạp model.
8. Kiểm thử các tình huống chuẩn/ngoại lệ và ghi kết quả vào file minh chứng, tài liệu hướng dẫn và nhật ký này.

### Đầu ra đã tạo hoặc cập nhật

| File | Nội dung |
|---|---|
| [storage.py](backend/apps/ai/retrieval/storage.py) | Hàm lưu/load snapshot và kiểm tra tính nhất quán. |
| [index.py](backend/apps/ai/retrieval/index.py) | Bổ sung xuất bản sao chunk để lưu đầy đủ text/metadata. |
| [test_index_storage.py](backend/apps/ai/tests/test_index_storage.py) | 22 kiểm thử lưu/load và lỗi dữ liệu/ghi file. |
| [build_sample_index.py](scripts/build_sample_index.py) | Bổ sung lưu/load và so sánh kết quả trước/sau; xuất vector câu hỏi. |
| [check_index_reload.py](scripts/check_index_reload.py) | Kiểm tra reload trong tiến trình riêng, không cần model. |
| `docs/sample-faiss-index.md` (tài liệu lịch sử, hiện không còn tại đường dẫn này) | Cách sử dụng và giới hạn snapshot. |
| [bundle/current.json](data/processed/w3-sample-index/bundle/current.json) | Pointer chọn snapshot đã ghi hoàn chỉnh, kèm checksum manifest. |
| `bundle/snapshot-<id>/index.faiss` | Index của generation được chọn. |
| `bundle/snapshot-<id>/chunks.jsonl` | Text và metadata chunk cùng generation. |
| `bundle/snapshot-<id>/manifest.json` | Cấu hình, mapping và checksum cùng generation. |
| [sample_query_vectors.npy](data/processed/w3-sample-index/sample_query_vectors.npy) | Ba vector câu hỏi để kiểm tra kết quả mà không chạy lại model. |
| [reload_verification.json](data/processed/w3-sample-index/reload_verification.json) | Kết quả kiểm chứng trong tiến trình riêng. |

Các artifact sinh trong `data/processed/` được Git bỏ qua. Script build đã cập nhật `sample_query_results.json` với `reload_verified=true`; số liệu công việc 3 trong nhật ký là lượt đo trước, không phải thời gian của lượt build mới này.

### Kết quả kiểm chứng

**Kiểm thử tự động:** 22/22 kiểm thử lưu/load đạt; tổng hồi quy embedding + index + storage **58/58 đạt**.

| Tình huống | Kết quả |
|---|---|
| Lưu/load bình thường | Giữ đúng manifest, vector, metadata và kết quả tìm kiếm |
| Lưu nhiều lần | Mỗi lần có generation mới, vẫn 3 vector trong fixture kiểm thử, không cộng dồn |
| Lỗi ghi file hoặc đổi pointer | Từ chối lưu; pointer cũ và index đang dùng còn hoạt động |
| Thiếu file, index/chunk/manifest bị sửa | Từ chối load với mã lỗi rõ ràng |
| Sai revision hoặc cấu hình embedding | Từ chối load |
| Sai thứ tự chunk, mapping trang, số lượng hoặc kiểu index | Từ chối load |
| Vector không hữu hạn | Từ chối load |
| Pointer vượt thư mục hoặc lưu vào corpus gốc | Bị chặn |

**Chạy BGE-M3 thật và kiểm chứng tiến trình riêng:** đều có status `PASSED`.

| Nội dung | Kết quả thực tế |
|---|---|
| Snapshot chứa vector | 12 |
| Câu hỏi kiểm chứng | 3 |
| Top-5 trước/sau load | 3/3 giống hoàn toàn về ID, rank, score, text và source |
| Tiến trình load có nạp model không? | Không (`model_loaded=false`) |
| Thời gian load trong tiến trình riêng, gồm kiểm tra snapshot | 0,020888 giây |
| Hash cấu hình | `2918526ee7d27db8c48d7ff6508c311e1fad4add7c0b877cb90c98c689436140` |

Thời gian load trên chỉ đo index mẫu 12 vector, không gồm khởi động Python/import thư viện hoặc sinh vector câu hỏi. Không dùng làm cam kết hiệu năng cho corpus lớn. Biên dịch Python và `git diff --check` đạt.

### Cách chạy lại

Sau khi đã có artifact của lượt build mới nhất, từ thư mục gốc:

```powershell
.\backend\.venv\Scripts\python.exe -X utf8 scripts/check_index_reload.py
```

Nếu cần xây mới cả embedding/index/snapshot, chạy `scripts/build_sample_index.py` với cache/model đã chuẩn bị như công việc 3. API nội bộ sử dụng `save_index(index, directory)` và `load_index(directory, expected_config)`; cấu hình mong đợi phải khớp đầy đủ với bản đã lưu.

### Giới hạn và công việc tiếp theo

Snapshot chỉ là lưu trữ nội bộ; checksum phát hiện hỏng hoặc lệch bộ artifact, không xác thực tác giả. Chỉ deserialize index từ nơi tin cậy. Các snapshot cũ và snapshot chưa được chọn do lỗi ghi được giữ lại, chưa có chức năng tự dọn hoặc bảo đảm khôi phục khi mất điện hệ điều hành.

Chưa nghiệm thu corpus/100 QA, quyền người dùng hoặc tác vụ indexing đồng thời trong hệ thống web. Công việc 5 tiếp theo phát triển truy xuất top-k theo tập nguồn hợp lệ do B xác định.

## 6. Công việc 5 - Truy xuất top-k theo tập nguồn hợp lệ

**Ngày kiểm chứng:** 14/10/2026.  
**Trạng thái:** Hoàn thành phần tìm kiếm và hợp đồng service của A; chưa nghiệm thu quyền từ database thật.

### Mục tiêu

Nhận câu hỏi, scope và top-k; chuyển câu hỏi thành vector rồi trả các chunk liên quan nhất trong đúng tập nguồn hợp lệ. Không để các nguồn ngoài scope chiếm hết global top-k và làm mất nguồn được phép đọc.

### Quy trình đã thực hiện

1. Định nghĩa `RetrievalScope` gồm user/course, tập phiên bản được phép, mode qa/hint và các selector lớp/buổi/tài liệu khi có. Chuẩn hóa UUID và dùng tập bất biến.
2. Xây `RetrievalService` yêu cầu callback resolver phía server; resolver phải tính quyền hiện hành, giữ nguyên các selector và không tin allowlist từ frontend.
3. Kiểm tra cấu hình embedding câu hỏi khớp index đã load, đồng thời tạo revision truy vết index từ manifest và checksum.
4. Resolve nguồn trước khi nạp model; lọc các hàng theo course/version và tài liệu được chọn. Scope rỗng không tự mở rộng sang toàn khóa.
5. Embed câu hỏi bằng BGE-M3, resolve lại nguồn rồi lấy giao của tập hợp lệ ban đầu và hiện hành. Quyền mới phát sinh giữa lượt query không tự mở rộng phạm vi tìm kiếm.
6. Tạo FAISS index tạm từ đúng các hàng hợp lệ trước khi search. Kết quả chỉ gồm nguồn trong tập này; khi không đủ k nguồn, trả ít hơn k.
7. Resolve thêm lần nữa trước khi trả. Khi nguồn bị thu hồi sau search, trả lỗi `SCOPE_CHANGED` thay vì trả nội dung từ scope cũ. Không cache quyền giữa các lượt gọi.
8. Trả rank, chunk ID, score, text và source được whitelist, không trả private storage key. Phân biệt lỗi cấm quyền, resolver/model/index với scope rỗng hoặc chưa có nguồn indexed.
9. Kiểm thử trên FAISS thật với vector kiểm soát được; chạy ba câu hỏi bằng BGE-M3 thật trên snapshot 12 chunk và resolver nguồn mô phỏng.

### Đầu ra đã tạo hoặc cập nhật

| File | Nội dung |
|---|---|
| [retriever.py](backend/apps/ai/retrieval/retriever.py) | `RetrievalScope`, `RetrievalService`, `RetrievalError` và các bước revalidation. |
| [index.py](backend/apps/ai/retrieval/index.py) | Tìm kiếm trực tiếp trong tập hàng được phép, không chỉ lọc global top-k. |
| [test_retriever.py](backend/apps/ai/tests/test_retriever.py) | 22 kiểm thử truy xuất/scope và lỗi đầu vào, không sử dụng quyền database thật. |
| [check_scoped_retrieval.py](scripts/check_scoped_retrieval.py) | Kiểm chứng query embedding thật, ba khóa mẫu và thay đổi nguồn trong resolver mô phỏng. |
| `docs/scoped-retrieval.md` (tài liệu lịch sử, hiện không còn tại đường dẫn này) | Hợp đồng bàn giao cho B, cách sử dụng và giới hạn. |
| [scoped_retrieval_verification.json](data/processed/w3-sample-index/scoped_retrieval_verification.json) | Kết quả model/index thật và scope mô phỏng; được Git bỏ qua. |

### Kết quả kiểm chứng

**Kiểm thử tự động:** 22/22 kiểm thử mới đạt; tổng hồi quy **80/80 đạt**.

| Tình huống | Kết quả |
|---|---|
| Global top-2 đều ngoài scope | Vẫn tìm đủ hai chunk hợp lệ ở vị trí thấp hơn trong global ranking |
| Phiên bản không được duyệt nhưng cùng khóa | Không được đưa vào kết quả |
| Phiên bản thuộc khóa khác | Không vượt qua bộ lọc course |
| Tập nguồn/tài liệu rỗng | Trả `EMPTY_SCOPE`, không embedding query hoặc mở rộng nguồn |
| Nguồn có quyền nhưng chưa trong index | Trả `NO_INDEXED_SOURCES` |
| Người dùng bị resolver từ chối | Lỗi `SCOPE_FORBIDDEN`, không trả nguồn |
| Thu hồi trong lúc embedding | Kết quả rỗng theo scope hiện hành |
| Thu hồi sau khi search | Lỗi `SCOPE_CHANGED`, yêu cầu thử lại |
| Thay đổi quyền giữa các lần gọi | Resolver chạy lại, không dùng quyền cached |
| Sai config/query/top-k hoặc resolver lỗi | Mã lỗi riêng, không che thành kết quả rỗng |
| Metadata có private storage key | Không xuất trường đó trong response |
| Mode hint | Dùng cùng cơ chế giới hạn nguồn |

**Kiểm chứng model thật:** status `PASSED`. BGE-M3 và FAISS chạy thật, resolver là dữ liệu mô phỏng trong bộ nhớ, không phải database Django.

| Câu hỏi mẫu | Top-1 | Số kết quả khi yêu cầu top-5 |
|---|---|---:|
| Vật chất tác động như thế nào đến ý thức và ý thức tác động trở lại ra sao? | `fixture-philosophy-2` | 4 |
| Hai thuộc tính của hàng hóa là gì? | `fixture-economics-1` | 4 |
| Gia đình có những chức năng cơ bản nào? | `fixture-socialism-3` | 4 |

Ba khóa mẫu có bốn chunk mỗi khóa. Service trả bốn nguồn hợp lệ thay vì lấy nguồn khóa khác để đủ năm. Ba câu có top-1 đúng kỳ vọng, toàn bộ nguồn thuộc scope resolver cho phép. Thu hồi scope trả `EMPTY_SCOPE`; phiên bản chưa indexed trả `NO_INDEXED_SOURCES`; user bị cấm bị từ chối.

Revision index: `fc8d6f3d072c371657b871aa5ec44ad26619502bb3bdc2d73662e5c4920f6f8b`. Đây là revision của snapshot mẫu, không phải release của corpus. Biên dịch Python và `git diff --check` đạt.

### Cách chạy lại

Từ thư mục gốc, với snapshot của công việc 4 đã có:

```powershell
$env:HF_HOME = "D:\AIModels\huggingface"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
.\backend\.venv\Scripts\python.exe -X utf8 scripts/check_scoped_retrieval.py
```

### Giới hạn và bàn giao cho B

Phần A đã có hàm `retrieve(query, scope, top_k)` và hợp đồng resolver, chưa có endpoint công khai hoặc chức năng xác định quyền database. B cần nối resolver với user xác thực, course/classroom/session, enrollment hiện hành, tài liệu chưa gỡ và phiên bản được công bố. Resolver chỉ thu hẹp nguồn theo selector, không dùng `active_version` nháp thay `published_version` dành học viên và không đưa đáp án riêng vào nguồn.

Sau tích hợp phải kiểm thử lại với model và database thật. Tỷ lệ 3/3 trên fixture không phải Page Recall trên 100 QA hoặc nghiệm thu bảo mật LMS. W4 còn phải kiểm tra quyền trước trả phản hồi AI. Cách dựng index tạm cần được đo trên corpus thật trước khi tối ưu tài nguyên.

Công việc tiếp theo trong danh sách là rà soát 25 QA pilot, bổ sung 25 QA mới và chuẩn bị review chéo dữ liệu của B.

## 7. Công việc 6 - Rà soát pilot và bổ sung 25 QA Triết học Mác-Lênin

**Lịch sử:** Phần tạo lần đầu dưới đây ghi nhận trạng thái trước khi được yêu cầu sửa 24 QA cũ. Trạng thái hiện hành nằm ở mục "Cập nhật khắc phục 24 QA cũ" cuối phần này; v2.0 hiện không còn giữ nguyên 24 dòng lỗi.

**Ngày thực hiện và kiểm chứng:** 14/10/2026.  
**Trạng thái:** Hoàn thành tạo v2.0 và đối chiếu nguồn phần A hiện có; chưa chốt benchmark nhóm hoặc hoàn thành review chéo dữ liệu của B.

### Mục tiêu và yêu cầu cụ thể

Theo yêu cầu mới, tạo `data/qa/qa_pilot_v2.0.csv`, sao chép toàn bộ nội dung `qa_pilot_v1.0.csv` và thêm 25 QA chỉ thuộc môn Triết học Mác-Lênin. Giữ nguyên dữ liệu cũ, đồng thời ghi riêng các vấn đề phát hiện khi rà soát để không dùng nhãn chưa đúng làm benchmark.

### Quy trình đã thực hiện

1. Đọc schema CSV v1.0, kiểm kê 50 dòng: 24 THMLN, 13 KTCTMLN và 13 CNXHKH. Xác nhận khác biệt giữa kế hoạch 25 pilot của A và thực tế 24 QA Triết học.
2. Đọc 14 PDF Triết học trong corpus, lấy số trang vật lý và trích xuất nội dung theo từng trang để tìm bằng chứng. Kiểm tra trực quan trang nguồn đại diện, gồm ch08 trang PDF 5 và ch14 trang PDF 6, để đối chiếu số trang vật lý với số trang in.
3. Rà soát 24 QA Triết học cũ: xác nhận 12 nhãn trang vượt độ dài file; 12 nhãn trang trong phạm vi vẫn cần kiểm tra/gán lại nguồn. Không sửa các dòng gốc.
4. Biên soạn 25 câu mới với ID liên tiếp 025-049, đáp án, loại câu, độ khó, tài liệu/trang/mục và anchor bằng chứng. Tránh lặp nguyên văn câu hỏi hiện có và chọn các nội dung cụ thể có nguồn.
5. Đối chiếu đáp án với nguồn đã đọc; script kiểm tra anchor và các thuật ngữ hỗ trợ tồn tại trong đoạn trích trang được gán nhãn. Lưu excerpt và checksum PDF trong review log.
6. Dùng parser/writer CSV để nối 25 dòng vào nội dung v1.0, giữ nguyên từng byte của file cũ làm prefix v2.0; giữ nguyên 10 cột và file v1.0.
7. Kiểm tra parse lại CSV, số lượng, ID duy nhất, không trùng chính xác câu hỏi mới và tính hợp lệ của trang nguồn. Ghi trạng thái self-check/peer-review tách biệt, không công bố đủ 100 QA hợp lệ khi mới có 75 dòng.

### Đầu ra

| File | Nội dung |
|---|---|
| [qa_pilot_v2.0.csv](data/qa/qa_pilot_v2.0.csv) | 50 QA cũ nguyên vẹn và 25 QA Triết học bổ sung. |
| [qa_pilot_v2.0_additions.json](data/qa/qa_pilot_v2.0_additions.json) | Nội dung và anchor/thuật ngữ bằng chứng của 25 QA mới. |
| [qa_pilot_v2.0_review.csv](data/qa/qa_pilot_v2.0_review.csv) | Rà soát 24 QA Triết học cũ và bằng chứng nguồn cho 25 QA mới. |
| [w3-a-qa-verification.json](docs/reports/w3-a-qa-verification.json) | Thống kê, checksum và kết quả kiểm tra giữ nguyên dữ liệu v1.0. |
| [build_qa_pilot_v2.py](scripts/build_qa_pilot_v2.py) | Tái tạo CSV và kiểm chứng nguồn, số lượng, schema, ID/câu hỏi. |
| `docs/qa-pilot-v2.md` (tài liệu lịch sử, hiện không còn tại đường dẫn này) | Giải thích phiên bản, quy ước trang và vấn đề cần review. |

### Kết quả

| Nội dung kiểm tra | Kết quả |
|---|---|
| File v1.0 có bị sửa không? | Không |
| 50 dòng/header cũ giữ nguyên byte trong v2.0 | Đạt |
| Số dòng mới | 25, toàn bộ THMLN |
| Tổng v2.0 | 75 |
| Phân bố môn trong v2.0 | THMLN 49; KTCTMLN 13; CNXHKH 13 |
| ID bổ sung | `THMLN_QA_025`-`THMLN_QA_049` |
| Loại câu mới | 24 short_answer, 1 true_false |
| Độ khó mới | 15 easy, 10 medium |
| Nguồn 25 QA mới | Trang PDF hợp lệ, anchor và thuật ngữ bằng chứng được kiểm tra trong 12 PDF |
| Trùng ID hoặc trùng chính xác câu hỏi mới | Không |
| Số cột và parse CSV | Giữ 10 cột, parse thành công |
| Rà soát pilot Triết học cũ | 24: 12 PAGE_OUT_OF_RANGE, 12 NEEDS_SOURCE_REVIEW |
| Peer review | Chưa hoàn tất |

Các QA mới bao phủ khái niệm triết học, tiền đề triết học Mác, vận động/đứng im, ý thức, nguyên lý/phạm trù/quy luật biện chứng, nhận thức/thực tiễn/chân lý, quan hệ và lực lượng sản xuất, thượng tầng, dân tộc, nhà nước, ý thức xã hội và nhân cách.

### Giới hạn và việc còn lại

Chưa coi toàn bộ 75 dòng là benchmark đạt: dữ liệu cũ được giữ nguyên dù đã phát hiện lỗi nguồn, các QA mới mới có đối chiếu nguồn và chờ B review. Cần thống nhất xử lý chênh lệch 24/25 pilot của A, sửa/gán lại nhãn cũ trong đợt cập nhật được nhóm chấp nhận, nhận phần QA của B và review chéo để chốt 100 mẫu development hợp lệ. Không đưa dữ liệu này thành tập test độc lập cuối đồ án.

### Cập nhật khắc phục 24 QA cũ - 14/10/2026

Theo yêu cầu bổ sung của người dùng, sửa `THMLN_QA_001` đến `THMLN_QA_024` trong v2.0; giữ file v1.0 làm bản gốc để đối chiếu.

**Quy trình:**

1. Đọc lại trang PDF cho từng chủ đề, dùng số trang vật lý bắt đầu từ 1 thay cho nhãn trang sai hoặc vượt độ dài file.
2. Gán lại nguồn của cả 24 QA; làm rõ câu hỏi/đáp án mơ hồ, quá rộng hoặc không được giáo trình hỗ trợ. Ví dụ: QA_005 chuyển sang định nghĩa tự ý thức; QA_012 bỏ ví dụ nhầm lực lượng sản xuất với cơ sở hạ tầng; QA_013 chuyển sang chức năng phán đoán.
3. Lưu nội dung đã sửa và lý do vào [qa_pilot_v2.0_corrections.json](data/qa/qa_pilot_v2.0_corrections.json), kèm anchor và thuật ngữ để kiểm tra bằng chứng.
4. Cập nhật script tái tạo v2 từ các bản sửa và phần bổ sung; ghi nguồn cũ/mới, trường thay đổi, lý do sửa, đoạn trích và checksum PDF trong review log.
5. Kiểm tra 75 ID duy nhất, 10 cột, thứ tự ID cũ, 49 câu Triết học không trùng chính xác, các trang/anchor/thuật ngữ; kiểm tra dữ liệu không thuộc phạm vi sửa và chạy lại để xác nhận kết quả ổn định.

**Kết quả hiện hành:**

| Kiểm tra | Kết quả |
|---|---|
| QA cũ đã sửa | 24/24, giữ ID và vị trí |
| QA Triết học được đối chiếu nguồn | 49/49; `SOURCE_CHECKED_PENDING_PEER` |
| Lỗi trang vượt phạm vi trong phần Triết học v2 | 0 |
| Dữ liệu 26 QA hai môn khác và 25 QA bổ sung | Giữ nguyên |
| File gốc v1.0 | Không thay đổi; SHA-256 `30efc4826b64d4a5cfac663f4c78b89696a30fa5d60181ac911566d7aaf96ca6` |
| Tổng/schema/ID | 75 dòng, 10 cột, không trùng ID |
| Review chéo và nghiệm thu benchmark | Chưa hoàn tất |

Minh chứng hiện hành: [v2 CSV](data/qa/qa_pilot_v2.0.csv), [review log](data/qa/qa_pilot_v2.0_review.csv), [verification JSON](docs/reports/w3-a-qa-verification.json). Việc kiểm tra anchor/thuật ngữ hỗ trợ không tự chứng minh đáp án đúng; nội dung đã được đọc đối chiếu và vẫn cần B review độc lập. Chưa chứng nhận 26 QA môn khác, chưa đủ 100 mẫu đã review và chưa đo Recall trên corpus thật. Các phát hiện lỗi ở lần tạo đầu đã được xử lý trong v2, không phải sửa ngầm v1.

## 8. Công việc 7 - Xây dựng công cụ tính metric truy xuất

**Ngày thực hiện và kiểm chứng:** 14/10/2026.  
**Trạng thái:** Hoàn thành module/CLI, kiểm thử và demo phép tính. Chưa hoàn thành phép đo baseline trên corpus thật hoặc 100 QA đã review.

### Mục tiêu

Đánh giá xem các chunk tìm được có trỏ tới đúng trang bằng chứng của câu hỏi hay không, theo protocol mục 5.5 trong kế hoạch W3. Tách công cụ tính điểm khỏi model và resolver quyền để dùng lại trong notebook công việc 8.

### Quy trình đã thực hiện

1. Đọc protocol: khóa đơn vị nguồn `(document_id, version_id, page_number)`, k là số chunk, tính Macro Page Recall và Hit@1/3/5/10.
2. Xây module nhận dataset chuẩn hóa và kết quả top-k theo QA ID. Cắt top-k chunk trước rồi bỏ trang trùng; các trang gold trùng cũng chỉ tính một lần. Sai document/version là miss.
3. Phân biệt QA có nhãn hợp lệ, no-evidence và sai/thiếu nhãn. QA hợp lệ nhưng retrieval lỗi/rỗng/thiếu kết quả giữ trong mẫu số với điểm 0; ghi rõ status/error, không âm thầm bỏ mẫu thất bại.
4. Kiểm tra rank, chunk ID, score hữu hạn, trang, course và latency. Response hỏng hoặc sai course bị chấm lỗi toàn lượt, không xuất nguồn đó. Chỉ ghi metadata nguồn công khai, không ghi text/private storage key.
5. Thêm adapter đọc pilot CSV; ánh xạ mã môn/tên PDF sang UUID document/version từ source map rõ ràng. Không tự đoán phiên bản, không sửa nhãn theo top-k và không tự xem nguồn thay thế là các trang bắt buộc.
6. Xây CLI chấm predictions đã lưu; xuất `retrieval_results.csv` cho từng QA và `metrics.json` tổng hợp, provenance và checksum. Giới hạn output trong thư mục con `data/processed`, không ghi đè input.
7. Tạo fixture 5 QA với phép tính kiểm tra độc lập: một QA hit đầy đủ, một QA nhiều trang với chunk lặp, một timeout, một no-evidence, một sai nhãn. Kiểm thử chuẩn/ngoại lệ và chạy lại CLI để kiểm tra kết quả ổn định.

### Đầu ra

| File | Nội dung |
|---|---|
| [metrics.py](backend/apps/ai/evaluation/metrics.py) | Hàm tính Recall/Hit, đọc pilot qua source map và xuất báo cáo. |
| [evaluate_retrieval.py](scripts/evaluate_retrieval.py) | CLI chấm JSON/CSV và predictions top-k đã thu thập. |
| [test_evaluation.py](backend/apps/ai/tests/test_evaluation.py) | 28 test về phép tính, nhãn, response, mapping và xuất file. |
| [w3-evaluation-qa.json](data/fixtures/w3-evaluation-qa.json) | Năm QA giả lập để kiểm chứng công cụ. |
| [w3-evaluation-predictions.json](data/fixtures/w3-evaluation-predictions.json) | Kết quả giả lập có rank/source/score và timeout. |
| `docs/retrieval-evaluation.md` (tài liệu lịch sử, hiện không còn tại đường dẫn này) | Protocol, schema, source map, cách chạy và giới hạn. |
| [w3-a-evaluation-verification.json](docs/reports/w3-a-evaluation-verification.json) | Minh chứng kiểm thử công cụ và số liệu demo, không phải Recall corpus thật. |
| [metrics.json](data/processed/w3-evaluation-smoke/metrics.json) | Kết quả aggregate demo; file cục bộ được Git bỏ qua. |
| [retrieval_results.csv](data/processed/w3-evaluation-smoke/retrieval_results.csv) | Đủ năm dòng QA và điểm/lỗi từng mẫu; file cục bộ được Git bỏ qua. |

### Kết quả kiểm chứng

**28/28 kiểm thử mới đạt; toàn bộ hồi quy AI 108/108 đạt, không fail hoặc skip trong lượt chạy cuối.** Lần chạy trong sandbox gặp lỗi quyền tạo/dọn file tạm Windows ở hai test; chạy lại ngoài sandbox đã đạt, không coi lượt lỗi đó là pass.

| Kiểm tra | Kết quả |
|---|---|
| Tổng QA demo | 5, giữ đủ trong CSV |
| QA có nhãn để chấm | 3, gồm 1 timeout vẫn tính 0 |
| QA no-evidence / sai nhãn | 1 / 1, ghi riêng, không chia cho 0 |
| Macro Page Recall@1 / @3 | 0,5 / 0,5 |
| Macro Page Recall@5 / @10 | 2/3 / 2/3 |
| Hit@1 / @3 / @5 / @10 | Đều 2/3 |
| Chunk cùng trang, gold trùng, nhiều trang | Phép tính đúng, không tăng điểm do lặp nguồn |
| Sai document/version | Miss, không chấm nhầm theo số trang |
| Rỗng, thiếu prediction, timeout, response hỏng | Giữ trong mẫu số và tính 0 |
| Rank/ID/score/trang/latency sai, sai course | Bị ghi lỗi, không xuất nguồn sai course |
| Mapping CSV thiếu hoặc trang ngoài PDF | Ghi `INVALID_LABEL`, không tự đoán nguồn |
| Chạy lại CLI / checksum kết quả | Cùng bytes; SHA-256 khớp JSON |
| Output ngoài vùng cho phép / chồng input | CLI từ chối |
| CSV thiếu source map | CLI từ chối |

Demo dùng kết quả được viết sẵn để chứng minh phép tính, không phải query BGE-M3 mới hoặc corpus thật. Latency trong fixture cũng là số giả lập. `git diff --check` đạt; chưa commit/push.

### Cách chạy lại

Từ thư mục gốc:

```powershell
.\backend\.venv\Scripts\python.exe -X utf8 scripts/evaluate_retrieval.py `
  --qa data/fixtures/w3-evaluation-qa.json `
  --predictions data/fixtures/w3-evaluation-predictions.json `
  --output-dir data/processed/w3-evaluation-smoke

$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -X utf8 -m unittest discover -s backend/apps/ai/tests -v
```

### Giới hạn và công việc tiếp theo

Chưa có source map corpus thật và top-10 của 75 pilot/100 QA được peer review; công cụ không tự nạp model hoặc xác nhận quyền database. Các revision model/index/corpus/chunking trong fixture là null có chủ đích; khi đo thật phải khóa và lưu chúng cùng dataset/source commit. Kết quả đúng trang không chứng minh chunk chứa đoạn hỗ trợ hoặc phản hồi AI đúng. QA no-evidence cần kiểm thử hành vi riêng; chưa có protocol chấm nhóm nguồn thay thế hoặc nDCG.

Công việc tiếp theo là dựng khung notebook (công việc 8), tái sử dụng module để đọc input/config, load index, thu thập top-10 và xuất kết quả. Khi B bàn giao corpus/scope/source map và nhóm review QA xong, mới chạy phép đo baseline và phân tích miss để nghiệm thu W3.

## 9. Công việc 8 - Notebook tích hợp, baseline corpus và kiểm chứng reuse

**Thời gian thực hiện:** 15-16/10/2026. **Kiểm tra trực tiếp ba artifact cuối:** 16/10/2026.  
**Phạm vi hoàn thành:** Notebook có code/outputs; baseline BGE-M3 thật; kiểm tra index đã lưu sau session reset; kết quả từng QA, metric, môi trường và phân tích lỗi. Đây là kết quả kỹ thuật trên tập development, không phải xác nhận human peer review hay nghiệm thu toàn bộ hệ thống.

### 9.1. Phân biệt phần đóng góp của A và B

- A chuẩn bị embedding service, FAISS, storage/reload, scoped retrieval, metric và phần QA của mình; sau tích hợp vận hành notebook Kaggle, chạy full baseline/reuse và lưu kết quả.
- B bàn giao chunking, catalog nguồn, bridge quyền và runner/notebook tích hợp. Không ghi toàn bộ module tích hợp là sản phẩm riêng của A.
- Nhóm dùng source tích hợp có commit bàn giao `9117d19865226c35f0f67c185f5da106e1576995`; đã kiểm tra commit này nằm trong lịch sử nhánh A. Đây là mốc nhận bàn giao, không tự chứng minh chính xác source commit của mọi file làm việc lúc chạy Kaggle; source audit sau đó có chỉnh sửa chưa được gắn mã commit cuối trong artifacts.

### 9.2. Quy trình hoàn thành trên Kaggle

1. Nhận source tích hợp và 27 PDF. Đưa source và corpus vào hai Dataset riêng tư; không upload database, `.env`, model weights hoặc tài khoản người dùng. Kiểm tra 27/27 PDF khớp checksum source map.
2. Copy source từ `/kaggle/input` sang vùng ghi được; khai báo ROOT/CORPUS/OUT/ARTIFACTS/COMMON; dùng CPU và cache model `/tmp/ohayo-huggingface`. Kernel reset làm mất biến nên phải chạy lại cell khai báo, không chỉ chạy cell cuối.
3. Cài `backend/requirements-w3.txt` và chạy hồi quy. Mốc trước chỉnh audit là 112 test; sau bổ sung kiểm tra nguồn là 118 test. Notebook cuối lưu trực tiếp output `Ran 118 tests in 2.446s / OK`, không ghi 112 là kết quả cuối.
4. Tạo chunk bằng probe pypdf với tokenizer BGE-M3 khóa revision. Không gọi đây là extraction Docling từ DB. Preflight kiểm tra manifest, checksum, UUID, QA và token; không tạo embedding hoặc Recall ở bước `--validate-only`.
5. Chốt đầu vào kỹ thuật 27 PDF/1.048 chunk/100 QA. Dùng config tích hợp encoder 514 token, khác sample 512: 512 nội dung + 2 token đặc biệt; không truncate và không lấy index mẫu thay cho index corpus.
6. Chạy `run(*COMMON)` để nạp BGE-M3, sinh vector corpus, xây/lưu/load FAISS, truy xuất top-10 cho mọi QA và xuất metric. Lượt này tốn gần 40 phút trên CPU; kết quả có đủ 100 prediction và không có truy xuất lỗi.
7. Lưu kết quả đầu ra về máy trước khi session kết thúc. Sau khi Kaggle reset, upload bản kết quả đã lưu dưới dạng Dataset riêng tư, dựng lại môi trường/chunk artifacts và copy đầy đủ index vào thư mục kiểm chứng riêng.
8. Chạy `--reuse-index` với cùng dataset/config/device/offline flag; runner đối chiếu index/catalog, không embedding lại corpus. Đối chiếu metric và danh sách chunk/source từng QA; lưu kết quả reuse riêng, không ghi đè baseline đầu.
9. Ghi `pip freeze` và thông tin Python/platform; nén kết quả reuse, tải notebook có outputs. Bổ sung 15 tiêu đề Markdown tiếng Việt, không thay code hoặc output. Kiểm tra lại ba file bàn giao thực tế ở mục 9.7.

### 9.3. Rà soát và đồng bộ QA sau bàn giao

Tập tích hợp = 75 QA phía A + 50 phía B - 25 ID pilot chung = **100 QA**. Phân bố: THMLN 49, KTCTMLN 31, CNXHKH 20; gồm 93 `qa`, 7 `hint`. Không trùng ID hoặc câu hỏi nguyên văn sau chuẩn hóa; không vì vậy mà gọi các câu độc lập ngữ nghĩa hoặc held-out test.

| Xử lý | Kết quả |
|---|---|
| 49 QA Triết học phía A | Kiểm lại minh chứng anchor/thuật ngữ và trang nguồn |
| 51 QA còn lại | Đọc câu hỏi/đáp án và nguồn PDF, lưu bằng chứng riêng cho từng câu |
| KTCTMLN_QA_001 | Đối chiếu trang PDF 19-21, kiểm tra trực quan trang 20 của ch01.pdf: câu hỏi/đáp án và gold trang 20 đúng; giữ nguyên, bổ sung minh chứng nguồn |
| KTCTMLN_QA_005 | Chuyển gold từ trang PDF 9 sang 10 của ch02.pdf để trỏ trực tiếp quan hệ tỷ lệ nghịch hỗ trợ bài tính; giữ câu hỏi/đáp án |
| CUONG_W3_QA_023 | Làm rõ đáp án nói về tư hữu tư bản chủ nghĩa đối với tư liệu sản xuất, không đồng nhất với mọi sở hữu cá nhân |
| Đồng bộ và tái tạo | CSV/JSON cùng câu hỏi, đáp án, mode, document/version/page; output tái tạo ổn định; input pilot A/B giữ nguyên |
| Kiểm tra và phân quyền review | Source-check 100/100, không còn source_review_required; agent reviewer ghi Codex, human peer vẫn pending, không ký thay thành viên |

Đặc tả và lịch sử chỉnh sửa có trong [qa_w3_source_checks.json](data/qa/qa_w3_source_checks.json), [qa_w3_source_audit.csv](data/qa/qa_w3_source_audit.csv), [qa_review_log.csv](data/qa/qa_review_log.csv). Runner đọc [qa_w3_v1.0.json](data/qa/qa_w3_v1.0.json); không chỉ sửa CSV rồi dùng JSON cũ. Các thay đổi được kiểm tra trước khi đo, không sửa gold theo top-k.

### 9.4. Cấu hình và môi trường thực đo

| Thành phần | Giá trị |
|---|---|
| Embedding | BAAI/bge-m3, dense |
| Revision model/tokenizer | `5617a9f61b028005a4858fdac845db406aefb181` |
| Thiết bị / batch | CPU / 2, chưa tuyên bố tối ưu tốc độ |
| Token encoder | Tối đa 514 gồm special; preflight xác nhận mức lớn nhất thực tế là 514 |
| Vector | 1.024 chiều, float32, L2-normalized |
| Index | FAISS IndexFlatIP, inner product |
| Tập đầu vào | 27 PDF, 1.048 chunk, 100 QA development |
| Parser | pypdf, không phải kết quả runtime Docling |
| Query và đơn vị đánh giá | Top-10 chunk; Page Recall/Hit@1/3/5/10 theo document/version/page |
| Python / OS | 3.13.15 / Linux x86_64, glibc 2.39 |
| Các dependency chính | torch 2.11.0+cpu; sentence-transformers 5.7.0; transformers 5.16.1; FAISS CPU 1.15.1; NumPy 2.1.3; pypdf 6.10.0 |
| Dependency phục vụ runner | Django 5.2.18; requests 2.34.2; không chạy Django server hoặc migrate database khi đo |
| Môi trường lưu kèm | `pip-freeze.txt` và `environment.json` trong ZIP reuse |

`pip freeze` là bản ghi gói đang cài, không phải image/container lock hoàn chỉnh; cần giữ Dataset version, code và revision model cùng kết quả. Session reset có thể làm mất cache, vì vậy reuse vẫn phải nạp/tải model và embedding câu hỏi.

### 9.5. Kết quả baseline và reuse

Đã kiểm tra trực tiếp cả hai ZIP, parse CSV/JSON và tính lại metric độc lập; không chỉ chép aggregate từ chat.

| k (số chunk) | Page Recall baseline | Page Recall reuse | Hit baseline / reuse |
|---|---:|---:|---:|
| 1 | 0,73 | 0,73 | 0,73 / 0,73 |
| 3 | 0,94 | 0,94 | 0,94 / 0,94 |
| 5 | 0,97 | 0,97 | 0,97 / 0,97 |
| 10 | 0,98 | 0,98 | 0,98 / 0,98 |

| Nội dung kiểm chứng | Baseline | Reuse |
|---|---:|---:|
| QA tổng / có gold hợp lệ / prediction | 100 / 100 / 100 | 100 / 100 / 100 |
| Thiếu prediction / nhãn lỗi / retrieval lỗi | 0 / 0 / 0 | 0 / 0 / 0 |
| Status OK | 100 | 100 |
| Nạp model, build hoặc load/reload index | 2.330,135 giây (~38 phút 50 giây) | 47,519 giây |
| Query latency trung bình | 0,323999 giây/QA | 0,341467 giây/QA |
| Reload checks nội bộ runner | 3 | 3 |
| Notebook kiểm tra top-k hai lượt | Kết quả đối chiếu: `QA có top-k khác nhau: []` | 100/100 giống nhau |

Hai cột thời gian nạp/build/reload không phải toàn bộ thời gian notebook; lượt reuse không build vector corpus. Không suy ra benchmark phục vụ đồng thời nhiều người hoặc cam kết latency production từ 100 lượt offline này.

**Kiểm tra bổ sung trực tiếp trên files:**

- Hai archive qua kiểm tra integrity, không có entry lỗi; CSV SHA-256 khớp metrics tương ứng.
- Mỗi ZIP có đủ pointer + generation + binary index + chunks + manifest; checksum manifest, index và chunks khớp; số vector/chunk là 1.048.
- Có đúng 100 QA/prediction, IDs khớp; danh sách chunk/source trong predictions tương ứng CSV và mapping index; Recall/Hit từng dòng và aggregate đều tính lại đúng.
- Thứ tự chunk/source top-10 của **100/100 QA giống nhau**, mức chênh score lớn nhất **0,0**. Binary index và chunks JSONL của hai ZIP **giống nhau từng byte**.
- Không deserialize FAISS hoặc tải model để thực hiện các phép kiểm tra artifact trên máy; lượt kiểm chứng model thật là các lần chạy Kaggle đã lưu.

Recall@5=0,97 vượt mục tiêu 0,80 **trên tập development này**. Mỗi QA hiện có một trang gold nên Recall và Hit bằng nhau. Không diễn giải thành 97% câu trả lời LLM đúng, cũng không xem source-check bằng công cụ là peer approval của con người.

### 9.6. Phân tích ba câu miss@5

| QA | Gold PDF | Kết quả thực tế | Kết luận dùng cho báo cáo |
|---|---|---|---|
| THMLN_QA_004 | THMLN/ch05.pdf, trang 16 | Top-1 cùng tài liệu trang 5; gold không có trong top-10 | Chunk gold vẫn trong index; top đầu nói về vật chất/ý thức nhưng không phải trang gold. Khả năng ranking chưa phân biệt tốt câu đúng-sai/đảo quan hệ và chunk có ngữ cảnh lẫn; đây là giả thuyết, chưa có ablation chứng minh. |
| THMLN_QA_010 | THMLN/ch12.pdf, trang 2 | Ưu tiên trang 1 và 3; gold không có trong top-10 | Nguồn gốc/chức năng nhà nước có nội dung gần với bản chất giai cấp; trang 2 hỗ trợ trực tiếp hơn. Không phát hiện thiếu chunk gold hoặc mapping sai. |
| CNXHKH_QA_006 | CNXHKH/ch03.pdf, trang 14 | Top-1 trang 13; gold ở hạng 7 | Miss@5 nhưng hit@10. Trang lân cận có một phần luận điểm, trang gold có đủ khoa học/công nghệ/quản lý. Không phải hoàn toàn lạc chủ đề. |

Giữ nguyên baseline và gold; không đổi nhãn theo ranking để làm đẹp Recall. Nếu nhóm muốn chấp nhận nguồn thay thế, cần protocol và dataset phiên bản mới, review độc lập rồi đánh giá lại. Các cặp như THMLN_QA_011/020 và KTCTMLN_QA_004/005 cùng kiểm tra kiến thức gần nhau; đây là hạn chế của tập development, không phải dữ liệu test độc lập cuối đồ án. Cải tiến query/chunk/hybrid/reranker đưa sang thử nghiệm riêng theo kế hoạch, không bắt buộc build lại corpus để khép báo cáo W3 hiện tại.

### 9.7. Ba artifact cuối đã nhận và kiểm tra trên máy

Cùng nằm tại `D:\Lap trinh\Đồ án tốt nghiệp\Ứng dụng`. Liên kết dưới đây tính từ vị trí worklog hiện tại ở thư mục gốc repository:

| Artifact | Nội dung xác nhận trực tiếp |
|---|---|
| [ohayo-baseline-v1.0.zip](../ohayo-baseline-v1.0.zip) | 5.164.747 byte; thư mục trong ZIP là `ohayo-baseline-v1.0/`; đủ index/current.json, snapshot generation, predictions, CSV, metrics và preflight |
| [reuse-verification-v1.0.zip](../reuse-verification-v1.0.zip) | 5.172.588 byte; thư mục trong ZIP là `reuse-verification-v1.0/`; đủ index/kết quả reuse và pip-freeze.txt/environment.json |
| [ohayo-retrieval-baseline-v1-0.ipynb](../ohayo-retrieval-baseline-v1-0.ipynb) | 57.944 byte; 30 cell gồm 15 tiêu đề Markdown và 15 cell code; 14 cell code có outputs; không có error output; lưu 118 tests OK và top-k khác nhau [] |

**SHA-256 toàn file:**

```text
ohayo-baseline-v1.0.zip
ce0e1018c7ebbf804d5fda761faee629aa7cf79643132932b163d152dfeaa7f7

reuse-verification-v1.0.zip
3e01eeba039245891a90f51bd08ebc5516ea177d17adcb4fcd058243eae87670

ohayo-retrieval-baseline-v1-0.ipynb
62b605f01000974aab4afaa9cea05f3b47930f827f22b02e4c275a669899f073
```

Notebook giữ outputs từ quá trình baseline và session reuse: execution_count là `1,2,3,4,5,6,7,8,9,None,9,10,11,12,13`. Cell đóng gói baseline không có execution_count/output, nhưng ZIP baseline đã được nhận và kiểm tra riêng; không mặc định cell đó đã chạy. Vì vậy, bằng chứng hiện tại chứng minh notebook có outputs và reuse sau reset thành công, **không tự chứng minh cả 15 cell đã Run All trong một session sạch duy nhất**. Cần trình bày đúng phạm vi này khi nộp.

### 9.8. Hash cấu hình/dataset/index để đối chiếu

| Đối tượng | Giá trị |
|---|---|
| Dataset JSON | `2f7f9e0880630e39eb18e5ba30f2fde391be8deed87321a16402b3eb2044a45b` |
| Chunking config | `184dc29844666d63f6948ed4c4e191580cfb686a9d829dc84065cf072ad9f6d6` |
| Embedding config thực dùng | `cb64865324751eb5726329917a349887a33142e51f8114a4500d50e822902466` |
| Index revision cả hai lượt | `5d1f070cda659dfe8fb9a3dc8945ee69badea453aaa02a44cf65f104e43afd1b` |
| CSV baseline | `2bfcc0f995f733820bfb2ce8f254d926fe1e2a9ce9fc30bf55a2a6c071b87995` |
| CSV reuse | `2cb9550700de4741afc7334ce11051dee8bb34b8042413550fb64e3540818dd2` |
| Corpus manifest baseline | `0ce8cd4aff3b35c4515c4a3eac59006f81dd875dcec1e5012cb1aa09dab3351f` |
| Corpus manifest reuse | `a50711b0d43d2652c24c20b983eac4995980ab44987564f760b89b8431bf856d` |

CSV chứa latency nên khác bytes giữa lượt chạy dù ranking/score giống nhau. Generator corpus manifest có elapsed_seconds, nên hash cả manifest không phải hash thuần nội dung PDF. Hai manifest gốc không nằm trong ba artifact kết quả để diff trực tiếp toàn nội dung; không khẳng định chỉ có một trường thay đổi. Runner reuse đã kiểm tra catalog/index; index/chunk bytes được kiểm tra bằng nhau trực tiếp. Không bỏ qua checksum lệch nói chung chỉ vì lý do metadata.

## 10. Kết luận bàn giao và phần còn lại

| Hạng mục | Trạng thái hiện tại |
|---|---|
| Phần code embedding/index/storage/retrieval/metric của A | Đã triển khai và kiểm thử |
| Corpus/chunk tích hợp của B | Đã sử dụng để chạy baseline, có đúng 27 PDF/1.048 chunk |
| Full baseline + reuse | Đã có số liệu thật và artifacts kiểm tra được, ranking/score không đổi |
| Phân tích lỗi | Đã hoàn thành ba miss@5 và hai miss@10; không sửa gold để tăng điểm |
| Notebook có outputs / environment / index backup | Đã nhận đủ ba artifact trên máy, pip freeze và environment trong ZIP reuse |
| Human peer review QA | Còn chờ xác nhận A/B; các artifacts hiện ghi pending_human_peer, không có bằng chứng 100 phê duyệt người |
| Một lượt Restart Kernel -> Run All hoàn toàn | Chưa có bằng chứng trong notebook hiện tại; reuse sau reset đã có. Cần bổ sung nếu tiêu chí nhóm yêu cầu Run All sạch |
| Phiên bản source cuối, Dataset versions và xác nhận B đã nhận | Cần ghi mã commit/link/version tương ứng và xác nhận bàn giao; không tự tạo thông tin chưa được cung cấp |
| Nghiệm thu quyền database / RAG READY / chatbot | Không nằm trong kết quả offline này; authorization_verified=false, rag_ready=false; chatbot sinh phản hồi thuộc phần sau |

**Cách hoàn thiện còn lại, không lặp lại vô ích lượt embedding:**

1. A/B đọc và xác nhận review log; ghi rõ người, thời điểm, kết quả và thay đổi. Nếu gold thay đổi, chấm lại trên nhãn mới và giữ phiên bản cũ; không đổi nhãn chỉ vì đã thấy retrieval miss.
2. Nếu cần chứng minh notebook sạch, dùng luồng reuse với index đã kiểm tra, cùng input/config và Dataset được gắn sẵn, chạy tuần tự từ đầu. Không nhấn Run All bản hiện tại một cách máy móc vì cell baseline vẫn gọi run(*COMMON) và cell restore có assert thư mục chưa tồn tại; cần chọn rõ luồng build hoặc reuse trước khi chạy.
3. Ghi source commit chính xác của gói chạy và Dataset versions/notebook version URL nếu còn truy xuất được; ghi thiếu nếu không thể khôi phục, không lấy HEAD hiện tại thay cho provenance cũ.
4. Gửi B ba artifact cuối và worklog này. Để tái chạy từ đầu, nhóm còn cần source tích hợp, 27 PDF đúng checksum hoặc bộ chunk artifacts đầy đủ và quyền tải model; ba file kết quả không phải bản đóng gói toàn bộ ứng dụng.

Kết luận ngắn cho báo cáo: **A đã hoàn thành phần kỹ thuật baseline retrieval và kiểm chứng reuse; mục tiêu Recall@5 đạt trên tập development đang chờ peer review. Chưa tuyên bố toàn bộ milestone nhóm đã nghiệm thu.**

## 11. Quy ước cập nhật và trình bày từ đây

Theo yêu cầu ngày 16/10/2026:

- File/module mới đặt theo chức năng, không tự thêm tiền tố/hậu tố tuần như w2/w3 nếu không có yêu cầu cụ thể. Phiên bản chỉ dùng khi cần phân biệt artifacts/dataset hoặc người dùng yêu cầu.
- Mỗi đợt công việc chỉ duy trì 1-2 file Markdown tổng hợp đủ quy trình, kết quả, bằng chứng và phần còn thiếu; không tạo một báo cáo Markdown mới cho từng lần test hoặc trao đổi.
- Bổ sung vào báo cáo chính; kết quả chi tiết máy đọc giữ trong artifact phù hợp (JSON/CSV/log/ZIP), không lặp lại thành nhiều bản Markdown.
- Không tự đổi tên file cũ hoặc xóa báo cáo cũ đang được tham chiếu; việc hợp nhất/dọn lịch sử cần yêu cầu riêng. Worklog này giữ nguyên tên do người dùng chuyển lại và dùng làm bản tổng hợp hiện tại.
- Các ghi chép Kaggle cũ dưới đây là lịch sử trước khi có baseline/reuse; mục 9-10 phía trên là trạng thái hiện hành.

**Kaggle chạy lại sau sửa test - 15/10/2026:** Theo output mới người dùng cung cấp, toàn bộ 108 test đạt trong 0,764 giây, không fail/skip, subprocess returncode=0. Kết quả này thay thế trạng thái chờ xác nhận hồi quy Kaggle trong ghi chép lần đầu dưới đây. Luồng mẫu đã đạt phần kiểm chứng chạy notebook; chưa xác nhận lưu phiên bản hoặc chạy tuần tự từ kernel mới. Cần giữ cell sửa test trước cell kiểm thử, vì cell copy package từ Dataset có thể khôi phục test cũ. Dataset/ZIP vẫn chưa cập nhật bản sửa. Kết quả fixture không phải Recall corpus thật hoặc nghiệm thu quyền database.

**Kết quả Kaggle do người dùng cung cấp - 15/10/2026:** Dựng index mẫu 12 vector đạt, self-search 12/12, ba câu hỏi top-1 đúng 3/3, embedding gồm nạp model 74,194 giây. Reload tiến trình riêng đạt, ba truy vấn giữ nguyên top-5, không nạp model, load 0,004303 giây. Scoped retrieval đạt trên resolver mô phỏng, thu hồi trả EMPTY_SCOPE, phiên bản chưa indexed trả NO_INDEXED_SOURCES và user bị cấm bị từ chối. Metric fixture đạt phép tính kỳ vọng. Hồi quy Kaggle lần đầu: 107/108 đạt, một fail do test_config_roundtrip_and_fingerprint giả định config.json luôn bằng mặc định offline, trong khi notebook đã bật local_files_only=False theo hướng dẫn. Đã sửa test trong repo để dùng file tạm độc lập, kiểm tra cả online/offline và hash khác nhau; hồi quy local bản sửa đạt 108/108. Cần người dùng áp dụng bản sửa trong notebook rồi chạy lại; chưa xác nhận Kaggle 108/108, chưa lưu/tái chạy notebook từ kernel mới, chưa nghiệm thu corpus thật. Gói ZIP/Dataset đã upload vẫn là bản trước khi sửa test.

**Cập nhật chuẩn bị công việc 8 - 15/10/2026:** Đã tạo thư mục `D:\Lap trinh\Đồ án tốt nghiệp\Ứng dụng\ohayo-smartlms` và ZIP cùng tên bên cạnh, theo yêu cầu người dùng. Gói có 33 file, gồm module AI, test, script chạy mẫu, fixture, QA v2/review/bản bổ sung/bản sửa, README và manifest checksum. Không đóng gói database, môi trường cài đặt, cache model, corpus PDF hoặc index đã sinh. ZIP có 91.631 byte; kiểm tra tính toàn vẹn, checksum các file, cú pháp Python và 75 QA có ID duy nhất đều đạt. SHA-256 ZIP: `ec2a5527d728f5561b8d2f7116969eee5acf1b80ae69e1e5dc5c58fdbe4206e8`. Script tái đóng gói: `scripts/package_kaggle.ps1`, từ chối ghi đè gói đã tồn tại. Chưa kiểm chứng cài dependencies hoặc chạy notebook trong môi trường Kaggle; công việc 8 chưa được đánh dấu hoàn thành.

Sau mỗi công việc được hoàn thành và kiểm chứng trong chat này:

1. Cập nhật trạng thái trong bảng theo dõi.
2. Bổ sung mục riêng gồm mục tiêu, quy trình, file đầu ra, kết quả kiểm tra, minh chứng, giới hạn và bước tiếp theo.
3. Ghi đúng ngày, cấu hình, phiên bản và phạm vi phép đo; phân biệt mẫu giả lập với dữ liệu/model thật, test bị bỏ qua với test đạt.
4. Tóm tắt quy trình và kết quả dưới chat, kèm đường dẫn file tổng hợp.

Không đánh dấu một công việc hoàn thành chỉ vì đã tạo file. Nếu mới hoàn thành một phần hoặc còn phụ thuộc bàn giao của B, ghi rõ phần đã đạt và phần còn thiếu. Việc cập nhật diễn ra khi thực hiện công việc trong chat, không phải tác vụ theo dõi tự chạy nền.
