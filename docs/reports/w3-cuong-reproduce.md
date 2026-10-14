# Tái lập phần W3 của Cường

Nhánh: `TranTuanCuong_B22DCVT073_W3Tasks`. Đây là chunking/quyền/adapter, không phải toàn bộ RAG. Các lệnh dưới chạy one-off container, không cần khởi động DB/frontend và không gọi migration trên DB demo.

## Môi trường đã kiểm chứng

Python 3.12 trong image backend; Django 5.2.18, Docling 2.135.0, pypdf 6.10.0, transformers 5.19.0, tokenizers 0.23.3. Dùng image đã build theo Dockerfile hiện tại. Tokenizer model revision được khóa trong `backend/config/w3/chunking_config.json`; model weights embedding chưa được cài/kiểm chứng cho W3 B.

## Test phần B

```powershell
docker compose run --rm --no-deps --entrypoint python backend manage.py test tests.documents.test_chunker tests.documents.test_chunking_batch tests.documents.test_chunking_command tests.documents.test_retrieval_scope tests.documents.test_retrieval_adapter --settings=config.settings.test --verbosity=2
```

Các tests upload/worker W2 dùng model course test riêng, phải chạy riêng:

```powershell
docker compose run --rm --no-deps --entrypoint python backend manage.py test tests.documents.test_upload tests.documents.test_worker --settings=tests.documents_settings --verbosity=1
```

Không chạy hai nhóm với cùng settings rồi coi lỗi app fixture là lỗi runtime. Bốn test PostgreSQL concurrency bị skip trên SQLite và chưa được tính đạt.

## Probe corpus và tokenizer thật

Chạy ở thư mục gốc bằng PowerShell; output mặc định dưới `backend/.private/w3`, được Git ignore. Không commit chunk text/index lớn:

```powershell
$w3DataPath = Join-Path (Get-Location) 'data'
docker compose run --rm --no-deps --entrypoint python -v "${w3DataPath}:/w3-input:ro" backend scripts/verify_w3_chunks.py --corpus /w3-input/corpus --output /app/backend/.private/w3 --revision 5617a9f61b028005a4858fdac845db406aefb181
```

Script dùng pypdf cho probe offline, lưu config/corpus manifest và UUID mapping ổn định; kiểm tra token ≤512, offsets, bao phủ ký tự không trắng, checksum catalog và idempotency. Kết quả kiểm chứng hiện có ở `w3-cuong-corpus-chunk-verification.json`: 27 PDF, 1.048 chunk. Không sinh embedding, index hoặc Recall.

## Probe Docling và management command với DB riêng

```powershell
$w3DataPath = Join-Path (Get-Location) 'data'
docker compose run --rm --no-deps --entrypoint python -v "${w3DataPath}:/w3-input:ro" -v smart-lms-rag_docling_cache:/home/app/.cache backend scripts/verify_w3_docling.py --pdf /w3-input/corpus/KTCTMLN/ch01.pdf --output /app/backend/.private/w3 --config /app/backend/config/w3/chunking_config.json
```

Script bắt buộc SQLite `:memory:`, tự migrate trong DB đó, trích xuất Docling thật, tạo DocumentVersion EXTRACTED và gọi `build_document_chunks`. Đã kiểm chứng 29 trang/29 chunk; status vẫn EXTRACTED và indexed_at vẫn null. Không sửa dữ liệu container database của người dùng. UUID runtime proof khác mapping corpus offline, không ghép hai bộ như cùng một index.

## Build trên phiên bản runtime có sẵn

Khi backend chạy, operator lấy version UUID hợp lệ từ database rồi gọi command (không phải input trực tiếp từ frontend):

```powershell
docker compose exec -T backend python manage.py build_document_chunks --version-id <UUID-phien-ban-da-trich-xuat> --config /app/backend/config/w3/chunking_config.json
```

`<UUID-phien-ban-da-trich-xuat>` là tham số vận hành cần thay bằng ID thật, không phải ID probe in-memory đã mất. Command kiểm tra envelope/DB/original hash, output riêng từng generation. Đọc manifest bằng `load_catalog(private_path(manifest_key))`; không dùng đường dẫn hoặc catalog client gửi.

## Interface cho Dương

```python
from apps.documents.retrieval_scope import resolve_scope
from apps.documents.retrieval_adapter import retrieve_authorized
from apps.documents.chunking import load_catalog
from apps.documents.storage import private_path

scope = resolve_scope(user, course_id, session_id=session_id, mode="hint")
catalog = load_catalog(private_path(manifest_key))
hits = retrieve_authorized(user, question, scope, retriever, top_k=5, catalog=catalog)
```

Các tên `user/course_id/session_id/question/manifest_key/retriever` phải lấy từ runtime/trusted artifacts. Retriever implement `search(query, allowed_version_ids, top_k)`, không tự mở rộng scope, trả chunk IDs của catalog đang dùng và score hữu hạn. Nếu nhiều version, operator merge catalogs đã kiểm chứng và cung cấp đủ manifest mapping. Artifact/index/model revision phải khớp; B chưa có kiểm chứng provider A thực tế.

## Dữ liệu và report

`data/qa/qa_w3_cuong_v1.0.csv`: 25 pilot +25 câu mới, 7 mẫu hint. Evidence là toàn trang PDF vật lý với hash/version mapping, chưa là span-level annotation. `qa_w3_review_log.csv` ghi source-check bằng agent và peer review pending; không có chữ ký giảng viên hay review Dương đã hoàn thành.

Chuẩn bị lại dữ liệu với Python có pypdf bằng `scripts/prepare_w3_cuong_qa.py`; kiểm tra git diff trước ghi lại dataset. Dương cần bàn giao 50 mẫu của mình, review phần Cường, embedding/index/notebook/results/metrics để nghiệm thu toàn bộ W3. Cường không tạo số Recall giả thay phần này.
