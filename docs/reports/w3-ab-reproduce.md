# Tái lập W3 tích hợp A/B

Ngày chuẩn bị: 15/10/2026. Source A: `88d5520`; source B: `1ef69c7`, tài liệu B `dae41c6`. Nhánh nhận: `TranTuanCuong_B22DCVT073_W3Tasks`. Xem biên bản `w3-ban-giao-duong.md` để biết phần còn phải nghiệm thu.

## 1. Môi trường và dữ liệu đầu vào

Chạy Python 3.12 tại thư mục gốc repo, ưu tiên venv riêng hoặc Kaggle. Không cần bật backend/DB để chạy corpus offline:

```powershell
python -m pip install -r backend/requirements-w3.txt
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
python -m unittest discover -s backend/apps/ai/tests -v
python scripts/merge_w3_qa.py
```

Lệnh merge cần `data/corpus/{THMLN,KTCTMLN,CNXHKH}/*.pdf` đúng snapshot. Nó không thay file pilot gốc; đầu ra chung gồm `qa_w3_v1.0.csv`, `qa_w3_v1.0.json`, `qa_review_log.csv`, `w3_source_map.json`. Nếu chỉnh nhãn sau review, chỉnh nguồn của người phụ trách rồi merge lại; không chỉ sửa CSV chung rồi để JSON dùng nhãn cũ. Cả hai file phải cùng phiên bản trước khi đo.

Đã kiểm tra gói source đóng bằng `scripts/package_kaggle.ps1` chạy 112 test AI, không cần DB. Dependencies dùng khoảng version; khi nghiệm thu Dương phải lưu `python -m pip freeze` của môi trường thực đo. Môi trường kiểm tra tích hợp hiện tại: FAISS CPU 1.15.1, sentence-transformers 6.1.0, transformers 5.19.0, torch 2.14.1+cpu; đây chưa phải môi trường đã đo embedding corpus.

## 2. Tạo hoặc nhận chunk artifacts

Nếu đã nhận `backend/.private/w3/corpus_manifest.json` cùng thư mục `documents/`, có thể bỏ qua bước tạo lại, nhưng phải giữ nguyên đường dẫn tương đối bên trong và kiểm tra checksum. Chưa có artifacts thì chạy:

```powershell
python backend/scripts/verify_w3_chunks.py --corpus data/corpus --output backend/.private/w3 --revision 5617a9f61b028005a4858fdac845db406aefb181
```

Đây là **probe offline pypdf**, mapping UUID5 theo subject/file/hash, không phải toàn bộ extraction Docling trong DB. Snapshot hiện có: 27 PDF, 1.048 chunk. Không lấy `version_id` probe để gọi API runtime. Với runtime thật, dùng `build_document_chunks` trên DocumentVersion của DB, rồi lập corpus manifest từ đúng các per-version manifest đó; không trộn hai loại ID.

## 3. Kiểm tra trước khi tải weights

```powershell
python scripts/run_w3_baseline.py --corpus-manifest backend/.private/w3/corpus_manifest.json --storage-root backend/.private/w3/documents --output-dir data/processed/w3-integrated --validate-only --check-tokenizer --allow-download
```

Lệnh kiểm tra manifest/hash/cấu hình/nhãn/UUID và tokenizer thật, **không tạo vector hay Recall**. Bỏ `--check-tokenizer` để kiểm tra artifacts hoàn toàn offline, không nạp tokenizer. Bỏ `--allow-download` nếu model/tokenizer đã có cache; mặc định `local_files_only=true`.

Config tích hợp: `backend/config/w3/embedding_config.json`, BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181`, 1.024 chiều, float32, normalize L2, FAISS inner product, batch 2/CPU. **Chunk 512 token nội dung + 2 special = encoder 514**. Config mặc định module A vẫn là 512 cho sample; dùng đúng config tích hợp cho corpus B. Check thực tế trên 1.048 chunk: lớn nhất 514 token gồm special, không truncate.

Hash config chunk: `184dc29844666d63f6948ed4c4e191580cfb686a9d829dc84065cf072ad9f6d6`.
Hash config embedding CPU/offline: `79e14591a23052075da4b5f7df4c10e34e3b5e33634bdcbfe65b6f5ef10a2bb7`.
CPU/cho phép tải: `cb64865324751eb5726329917a349887a33142e51f8114a4500d50e822902466`.
Đổi device/batch/offline flag làm đổi fingerprint của A, vì vậy reload phải dùng đúng cấu hình đã build. Không dùng sample index 512 với config 514.

## 4. Đo bằng model thật — Dương thực hiện

Sau review QA và chốt snapshot:

```powershell
python scripts/run_w3_baseline.py --corpus-manifest backend/.private/w3/corpus_manifest.json --storage-root backend/.private/w3/documents --output-dir data/processed/w3-integrated --allow-download --check-tokenizer
python scripts/run_w3_baseline.py --corpus-manifest backend/.private/w3/corpus_manifest.json --storage-root backend/.private/w3/documents --output-dir data/processed/w3-integrated --allow-download --reuse-index
```

GPU: thêm `--device cuda` ở **cả hai lệnh**, khi môi trường thực sự hỗ trợ. Nếu đổi QA/config/snapshot sau khi build, dùng output directory mới hoặc build generation mới, không coi snapshot cũ là kết quả mới. Runner từ chối reuse khi catalog/config lệch. Model weights lớn chưa tải/chạy trong lượt tích hợp này; lỗi thiếu cache cần bật download lần đầu.

Output dưới `data/processed/w3-integrated/`:

| File | Nội dung cần kiểm tra |
|---|---|
| `preflight.json` | 27 PDF, 1.048 chunk, 100 QA nếu cùng snapshot; config/dataset/corpus hashes; parser và review status |
| `index/current.json` và generation UUID | FAISS binary, chunks và manifest đã checksum; chuyển cả generation, không chỉ pointer |
| `predictions.json` | Top-10 từng QA, mode, scores, trang/UUID, latency/lỗi và provenance |
| `retrieval_results.csv` | Mỗi QA một dòng, gold/retrieved, Page Recall/Hit@1/3/5/10; không bỏ câu lỗi |
| `metrics.json` | Macro Page Recall/Hit, denominator, số lỗi/nhãn sai/missing, runtime và index revision |

`k` đếm chunk; sau lấy top-k mới khử trùng trang `(document_id,version_id,page_number)` để tính recall. Retrieval lỗi/rỗng với gold hợp lệ tính 0; nhãn sai/no-evidence báo riêng, không tự xem đạt. Chạy offline dùng identity resolver đã ghi rõ `authorization_verified=false`; nó chỉ đo ranking theo khóa học. Chất lượng trả lời/hint của LLM chưa nằm trong phép đo này.

Notebook mới: `notebooks/w3_retrieval_baseline.ipynb`, source không có outputs. Chỉnh `OHAYO_ROOT`, `OHAYO_CORPUS`, `OHAYO_DEVICE`, rồi Run All từ kernel sạch. Notebook của Dương đính kèm đã được đối chiếu, không sửa bản `D:/ohayo-retrieval-baseline.ipynb`; sample và cell vá test cũ không được mang thành kết quả corpus.

## 5. Nối quyền Django thực tế

Sau khi operator build/load index và trusted catalog cho **đúng UUID DB**, gọi trong backend:

```python
from apps.documents.retrieval_scope import resolve_scope
from apps.documents.dense_retrieval import retrieve_dense_authorized

scope = resolve_scope(user, course_id, session_id=session_id, mode="hint")
hits = retrieve_dense_authorized(user, question, scope, index, embedding,
                                catalog=catalog, top_k=5)
```

`user` lấy từ xác thực; selectors có kiểm tra quyền server; không nhận `allowed_version_ids`, đường dẫn manifest hoặc catalog từ client. Index phải chứa đúng các record của catalog (text/hash/trang/config). Bridge giữ preview của giáo viên ở scope B, chuyển sang scope A để prefilter trước top-k và kiểm tra lại DB trước/sau encode/search. B dựng response từ trusted catalog. Không thêm endpoint chatbot và không tự đổi trạng thái READY.

Kiểm thử backend có đầy đủ dependencies `backend/requirements.txt` và optional ML dependencies. Trong image Docker hiện có, không cần rebuild Docling; có thể cài optional ML vào container kiểm thử riêng rồi chạy:

```powershell
$w3Modules = @(Get-ChildItem backend/tests/documents/test_*.py | Where-Object { $_.BaseName -notin @('test_upload','test_worker') } | ForEach-Object { 'tests.documents.' + $_.BaseName })
# Chạy từ backend với cùng danh sách module; dùng SQLite test, không DB demo.
Push-Location backend
python manage.py test @w3Modules tests.common apps.users.tests apps.courses.tests --settings=config.settings.test --verbosity=1
python manage.py test tests.documents.test_upload tests.documents.test_worker --settings=tests.documents_settings --verbosity=1
Pop-Location
```

277 test nhóm runtime: 273 đạt, 4 PostgreSQL concurrency skip trên SQLite; 27 test nhóm fixture W2 đạt. Test parser có dùng Docling thật, cần cache model Docling hoặc mạng; lượt đầu thiếu cache đã dừng, lượt cuối dùng cache có sẵn và đạt. Tách settings hai nhóm theo hướng dẫn B; không migrate DB production/demo để chạy kiểm thử.

## 6. Gói bàn giao

```powershell
# Thư mục đích phải tồn tại và chưa có ohayo-smartlms/ohayo-smartlms.zip.
./scripts/package_kaggle.ps1 -Destination .private/w3-handoff-package
```

Script từ chối ghi đè. Gói có source/checksum và notebook/QA, không có DB, secrets, weights, corpus hoặc chunk/index. Gói hiện tại được tạo trước merge commit: `source_commit` chỉ HEAD trước merge, `working_copy_files=true`; **checksum từng file trong package-manifest.json** mới là bằng chứng source thực đóng. Sau commit có thể đóng lại ở một thư mục đích mới để manifest chỉ đúng merge commit.

Để chạy corpus trên máy khác, nhận riêng PDF đúng checksum hoặc `corpus_manifest.json + documents/` qua nơi lưu phù hợp quyền. Dương cần xác nhận nhận đủ artifacts này; một ZIP source nhỏ không chứa dữ liệu để đo toàn corpus.
