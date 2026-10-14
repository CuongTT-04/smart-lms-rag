# Kế hoạch triển khai phần Cường trong W3

> **Dành cho người thực hiện bằng agent:** dùng kỹ năng `executing-plans` để thực hiện từng task sau khi người dùng đã review kế hoạch và yêu cầu triển khai. Chưa triển khai sản phẩm trong bước lập kế hoạch này; không tự dispatch subagent.

**Goal:** Hoàn thành chunking, nguồn/phiên bản/quyền retrieval, dữ liệu QA và bằng chứng phần Cường trước hết 16/10/2026; ngày 17 viết báo cáo W3.

**Architecture:** Chunking nhận extraction JSON hiện tại và tạo JSONL có nguồn theo từng trang. Scope resolver sử dụng quyền course/classroom/session và phiên bản đang công bố trong database. Adapter gọi retriever do Dương bàn giao, rồi kiểm tra lại nguồn trước trả kết quả. Chunk/index lớn lưu trong private storage hoặc gói offline, không đưa lên public MEDIA_ROOT.

**Tech Stack:** Django/DRF hiện tại, Python, BGE-M3 tokenizer đã khóa revision, JSON/JSONL; retriever/index của Dương qua interface, không tự viết thêm hệ embedding.

**Spec:** [Kế hoạch W3 chung, mục 5 và mục 10](2026-10-12-ke-hoach-w3.md). Đây là kế hoạch riêng cho Trần Tuấn Cường, không thay đổi phân công phần Dương.

## Hiện trạng và cách điều chỉnh lịch

Kiểm tra workspace ngày 14/10: `processors/chunker.py`, embedding service và retriever đều trống. Extraction đã có envelope `schema_version=1.0`, UUID course/document/version, `checksum_sha256`, `page_count` và `pages[{page_number,text,status,warnings}]`. Worker hiện chốt EXTRACTED, giữ `indexed_at=None`. Quyền hiện có tại `apps.documents.access` và `apps.courses.permissions`.

Chưa có bằng chứng đủ để đánh dấu công việc 13/10 là hoàn thành. Ngày 14 cần bù schema/chunk mẫu trước rồi mới batch/scope. Nếu Dương đang có mã ở nhánh riêng, nhận interface/config/index manifest thực tế trước tích hợp; không kết luận nhánh riêng chưa làm chỉ từ workspace này.

| Ngày | Thứ tự ưu tiên của Cường | Milestone cá nhân |
|---|---|---|
| **14/10** | Task 1 →2 →3; bắt đầu Task 4 và 6 | **B1:** schema/config và chunk mẫu thật bàn giao sớm. **B2:** batch có manifest, scope resolver và 50 QA phần Cường ở trạng thái nháp |
| **15/10** | Hoàn tất Task 4 →5; Task 6 và 7 | **B3:** scope/tích hợp có test; 50 QA phần Cường được review, review phần Dương; đối chiếu kết quả 100 QA khi nhận được |
| **16/10** | Hồi quy Task 7 →Task 8; sửa blocker | **B4:** tái lập được, test/log/demo/evidence hoàn chỉnh; khóa source/config/data cuối ngày |
| **17/10** | Task 9 | **B5:** báo cáo 1–2 trang khớp evidence ngày 16 |

Ước lượng riêng Cường: khoảng **22–31 giờ công**, chưa tính báo cáo, thời gian đợi model hoặc phát sinh; cần khoảng 7–10 giờ/ngày trong ba ngày còn lại. Ngày 14 tải nặng nhất: phải ưu tiên chunk mẫu cho Dương trước, có thể hoàn tất batch/scope đầu ngày 15 như khung giờ Task 3–4. Nếu công suất ít hơn hoặc giao diện Dương chậm, phải ghi thiếu hụt, ưu tiên nguồn/quyền/dữ liệu và giảm tối ưu thêm. Không chuyển ngày 17 thành ngày phát triển tính năng.

## Global Constraints

- 512 token tối đa mỗi chunk; overlap mục tiêu 64 token trong cùng trang; tokenizer BGE-M3 khóa revision; không âm thầm truncation.
- Trang PDF vật lý bắt đầu từ 1; char offsets `[start,end)` trên văn bản đã chuẩn hóa; baseline không chunk qua trang.
- Ground truth W3 theo `(document_id,version_id,page_number)`; Page Recall@k với k là số chunk; trang lặp không tính nhiều lần.
- 100 QA nhóm: Cường kiểm tra 25 pilot + thêm 25 QA, Dương tương tự; hai người review chéo toàn bộ phần còn lại.
- Không đổi parser/worker W2 chỉ để thêm chunking; không đổi quyền tải sạch, watermark hay công bố.
- Không công bố RAG READY khi chỉ có chunk hoặc embedding fixture. Index thất bại không được làm hỏng bản PDF đã EXTRACTED và đang xem được.
- Tệp model/index/chunk lớn không commit vào Git thường; metadata/checksum và kết quả nhỏ quản lý theo phiên bản.
- Không sửa phần mã Dương không thuộc interface đã thống nhất; không tự tạo PR/issue bên ngoài khi chưa được yêu cầu. Trong thực hiện, commit chỉ các file task có review, không `git add .` khi workspace có thay đổi khác.

## Review Focus

1. Trang trắng, chuỗi dài không dấu cách và Unicode tiếng Việt: không loop vô hạn, không mất văn bản, không sai token/offset (Task 2).
2. Metadata lệch course/document/version/checksum và nguồn bị thay đổi: từ chối tạo artifact gắn sai nguồn (Task 3).
3. Scope rỗng, ID từ khóa khác và client tự cấp quyền: không fallback sang toàn corpus (Task 4).
4. Người dùng mất quyền hoặc tài liệu bị gỡ sau resolve scope: không trả chunk cũ, không dùng cache quyền cũ (Task 5).
5. Retry/build gián đoạn và file output cũ: không tạo trùng, không chốt READY giả, không ghi đè gói đã khóa một phần (Task 3 và 7).

## Bản đồ file

Tên file mới là đích triển khai đề xuất; chưa tồn tại chỉ vì kế hoạch liệt kê.

| File | Vai trò | Thao tác |
|---|---|---|
| `backend/apps/documents/processors/chunker.py` | Normalization, token chunking và nguồn | Điền file hiện trống |
| `backend/apps/documents/retrieval_contracts.py` | Config/Chunk/Scope/Hit và lỗi giao tiếp | Tạo, thống nhất với Dương trước khi viết trùng type |
| `backend/apps/documents/chunking.py` | Kiểm tra extraction với DB, ghi JSONL/manifest nguyên tử | Tạo |
| `backend/apps/documents/retrieval_scope.py` | Resolve/revalidate quyền và phiên bản | Tạo |
| `backend/apps/documents/retrieval_adapter.py` | Gọi interface của Dương, validate output và nguồn | Tạo |
| `backend/apps/documents/management/commands/build_document_chunks.py` | Build chunk batch theo danh sách phiên bản server quản lý | Tạo |
| `backend/tests/documents/test_chunker.py` | Unit test chunking | Tạo |
| `backend/tests/documents/test_chunking_batch.py` | Metadata, artifact, retry | Tạo |
| `backend/tests/documents/test_retrieval_scope.py` | Quyền thật với course/classroom/session | Tạo |
| `backend/tests/documents/test_retrieval_adapter.py` | Output không hợp lệ, race quyền và lỗi index | Tạo |
| `docs/decisions/2026-10-14-w3-retrieval-contract.md` | ADR hợp đồng ngày chốt thực tế | Tạo |
| `docs/reports/w3-cuong-reproduce.md` | Hướng dẫn tái lập và giới hạn | Tạo |
| `docs/reports/w3-cuong-error-analysis.md` | Lỗi dữ liệu/nguồn/quyền | Tạo |
| `data/qa/qa_w3_cuong_v1.0.csv`, `data/qa/qa_w3_review_log.csv` | 50 QA phụ trách và review log | Tạo; không sửa đè pilot gốc |

Giữ chunk/index/fixture thật ở private output. Với corpus offline, có manifest ánh xạ mã môn/tên PDF sang UUID tài liệu/phiên bản; không dùng `THMLN` thay UUID course của ứng dụng. QA offline có thể giữ mã môn và khóa nguồn corpus, nhưng phải có bảng mapping để chạy cùng runtime.

## Task 1 — Chốt hợp đồng và cấu hình (1–2 giờ, 14/10)

**Output:** ADR, schema, config và bản interface gửi bàn giao cho Dương bằng tệp/link nội bộ; chưa gửi tin nhắn cho người khác thay người dùng.

**Interfaces đề xuất:**

```python
chunk_extraction(envelope, document_title, config, tokenizer) -> list[Chunk]
resolve_scope(user, course_id, classroom_id=None, session_id=None,
              document_ids=None, mode="qa") -> RetrievalScope
retrieve_authorized(user, query, scope, retriever, top_k=5) -> list[RetrievalHit]
# retriever của Dương: search(query, allowed_version_ids, top_k)
```

`RetrievalScope` bất biến, có user/course/classroom/session/mode, requested document IDs và allowed version IDs. `Chunk` dùng đủ trường mục 5.1 kế hoạch chung. `RetrievalHit` dùng rank/chunk ID/score/text/source mục 5.4. Không tạo hai type không tương thích giữa module A/B; nếu Dương có hợp đồng thực thì đối chiếu và ghi thay đổi vào ADR.

- [ ] Đối chiếu output `metadata.py`; chốt normalization NFC + newline LF, không xóa nội dung/header/footer khi chưa có quy tắc kiểm chứng.
- [ ] Chốt source hash là hash PDF; config hash phải bao gồm normalization/tokenizer revision/max tokens/overlap/schema.
- [ ] Token count là độ dài `tokenizer.encode(text, add_special_tokens=False)`; ghi riêng budget special tokens khi encode model để không cắt mất text.
- [ ] Chốt FAISS baseline, output của scope và hợp đồng callback indexing receipt; không nhận một bool `success=True` không có manifest/hash.
- [ ] ADR ghi ngày 14/10 và phần chưa nhận từ Dương; schema/config dùng giá trị thật khi resolve model revision, không tự bịa commit model.

**Gate B1:** hai bên có cùng tên trường/signature; Cường có thể làm Task 2 với tokenizer dependency, Dương có thể đọc chunk mẫu.

## Task 2 — Chunking theo trang và nguồn ổn định (5–7 giờ, 14/10)

**Files:** chunker, contracts, `test_chunker.py`. Không thay parser extraction hiện có.

**Test cycle:**

- [ ] Viết test trước với extraction hai trang, một trang trắng, Unicode và đoạn dài; chạy để xác nhận lỗi do module chưa triển khai.
- [ ] Implement normalization theo config, chia paragraph/câu, fallback tách theo offset khi câu dài; mỗi đoạn luôn tiến vị trí; overlap không vượt chunk và không làm loop.
- [ ] Tạo chunk ID bằng UUID5/hash từ version/page/offset/config hash; section không có đặt null; chunk_order xác định theo thứ tự.
- [ ] Verify `text == normalized_page[char_start:char_end]`; đếm token thực không vượt 512; mọi vùng text có nghĩa được bao phủ; page không thay đổi.
- [ ] Chạy lại test; sau đó tokenizer thật trên một PDF đã EXTRACTED và xuất `chunks_sample.jsonl` cho Dương.

Test cốt lõi đặt trong Django SimpleTestCase, dùng tokenizer giả nhỏ chỉ cho unit test, còn acceptance sử dụng tokenizer BGE-M3 thật:

```python
first = chunk_extraction(envelope, "Chương 1", config, tokenizer)
again = chunk_extraction(envelope, "Chương 1", config, tokenizer)
assert [c.chunk_id for c in first] == [c.chunk_id for c in again]
assert len({c.chunk_id for c in first}) == len(first)
for c in first:
    page = normalized_pages[c.page_number]
    assert c.text == page[c.char_start:c.char_end]
    assert 0 < c.token_count <= config.max_tokens
```

`envelope/config/tokenizer/normalized_pages` là fixture xác định trong test: hai trang có nội dung tiếng Việt, token budget nhỏ để tạo nhiều chunk; test không tải GPU/model qua mạng. Bổ sung fixture page trắng và văn bản không dấu cách để bắt non-progress.

Run trong container hiện có:

```powershell
docker compose exec -T backend python manage.py test tests.documents.test_chunker --settings=config.settings.test --verbosity=2
```

**Gate B1:** đối chiếu ít nhất 5 chunk với PDF, đủ trang đầu/cuối; không cross-page; text, offset, token và ID đúng. Đây là bàn giao ưu tiên trước batch, không chờ hoàn thành mọi test quyền.

## Task 3 — Batch chunking và manifest có thể tái lập (3–4 giờ, 14–15/10)

**Files:** chunking service, build command, `test_chunking_batch.py`; tái sử dụng `private_path` và cách atomic write trong `metadata.py`.

**Consumes:** `DocumentVersion` và extraction path server xác định. **Produces:** JSONL/manifest theo version và config hash; summary số trang/chunk và danh sách nguồn lỗi.

- [ ] Viết test mismatch UUID/version/course, checksum khác DB, page thiếu/trùng, extraction schema không hỗ trợ, source removed và output path không thuộc private root.
- [ ] Đọc extraction qua `private_path(version.extracted_storage_key)`; đối chiếu UUIDs, hash và page_count với DB trước chunking. Chỉ dùng trạng thái đã trích xuất hợp lệ.
- [ ] Ghi file tạm + flush/fsync + `os.replace`; manifest có hash JSONL, normalization/config, số trang/chunk, input snapshot và lỗi theo document/version.
- [ ] Với cùng version/config/output hash, retry dùng lại hoặc rebuild cùng kết quả; không append trùng. Build mới tạo generation riêng; manifest chỉ trỏ artifact đã ghi đủ.
- [ ] Build command nhận `--version-id` có thể lặp và `--output-key` tương đối trong private storage; không nhận đường dẫn arbitrary từ frontend. Lệnh batch chỉ chạy do người vận hành được cấp quyền, không là API public.
- [ ] Chạy unit test rồi batch nguồn đủ điều kiện; ghi rõ scope thực, không tính 27 PDF nếu chưa xử lý đủ.

Run test:

```powershell
docker compose exec -T backend python manage.py test tests.documents.test_chunking_batch --settings=config.settings.test --verbosity=2
```

**Gate B2:** `chunks.jsonl` + `corpus_manifest.json`, model-independent mapping nguồn sẵn sàng cho Dương. Chunking không cập nhật RAG READY, không đổi EXTRACTED thành FAILED chỉ vì tạo chunk lỗi.

## Task 4 — Scope resolver theo quyền hiện hành (3–4 giờ, 14–15/10)

**Files:** retrieval_scope, scope tests; gọi lại `require_access`, `require_session_access`, `can_view_classroom`; không thêm bản sao quy tắc quyền.

- [ ] Tạo test với User/Course/CourseMember/Classroom/Enrollment/ClassroomSession thật theo fixture `tests.documents.test_integration`; không dùng Course giả cho toàn bộ quyền runtime.
- [ ] Bắt các case: thiếu auth, account inactive, course không PUBLISHED cho học viên, pending/thu hồi, khác khóa, classroom enrollment không hợp lệ, session draft/removed, document_ids không thuộc requested scope.
- [ ] Học viên lấy phiên bản đang công bố, chưa removed và indexing generation hợp lệ. Giáo viên preview draft chỉ có mode explicit được quyền owner cho phép; default không mở rộng nguồn.
- [ ] `document_ids=[]` nghĩa là chọn không nguồn, không biến thành “tất cả”; `None` nghĩa là không có lựa chọn thu hẹp. Session/classroom invalid bị chặn thay vì fallback scope course.
- [ ] Nguồn course-level chưa gắn session không tự thêm vào câu hỏi session; muốn tìm cả course cần lựa chọn scope explicit theo ADR.
- [ ] Return frozen scope từ server, không dùng user/allowed versions do client tự gửi; không để phần tìm kiếm tự suy đoán quyền.

Test bắt rỗng phải có trước implementation:

```python
scope = resolve_scope(student, course.id, document_ids=[])
assert scope.allowed_version_ids == ()
```

Run:

```powershell
docker compose exec -T backend python manage.py test tests.documents.test_retrieval_scope --settings=config.settings.test --verbosity=2
```

**Gate B2:** scope đúng cho student/owner và closed khi không hợp lệ. Mapping phiên bản/index readiness phải nhận manifest của Dương; unit fixture có thể kiểm tra interface nhưng không là bằng chứng real index đã hoạt động.

## Task 5 — Adapter retrieval và kiểm tra quyền lần hai (2–3 giờ, 15/10)

**Files:** retrieval_adapter, adapter tests. **Dependency:** Dương bàn giao `search(query, allowed_version_ids, top_k)` hoặc interface tương đương được ADR ghi nhận.

- [ ] Fake retriever chỉ trong test để kiểm tra query/scope/response, không dùng fake cho demo nghiệm thu.
- [ ] Validate query non-empty và top_k integer trong 1–10 cho baseline; phân biệt index unavailable với scope không nguồn. Scope bị cấm không gọi retriever.
- [ ] Kiểm tra output không trùng chunk ID, score hữu hạn, đúng allowed versions/course, metadata page tồn tại và provenance khớp manifest. Không trả storage path; nếu provider trả source sai scope, chặn response và ghi lỗi tích hợp.
- [ ] Re-resolve quyền/document publication trước trả. Nếu quyền/version đổi trong lúc search, bỏ kết quả cũ và báo yêu cầu chạy lại; không trả draft/removed để giữ đủ top-k.
- [ ] Nhận indexing receipt có artifact/checksum/config/model/version mapping đầy đủ; không chốt READY khi chưa validate artifact. Không thêm hook worker tự index chưa được test. Nếu chưa chốt readiness contract với Dương, giữ manual build + validated manifest và ghi giới hạn tích hợp.

Test quyền thay đổi trong callback:

```python
def search_and_revoke(query, allowed_version_ids, top_k):
    membership.status = "REMOVED"
    membership.save(update_fields=["status"])
    return fixture_hits
# Gọi adapter phải bị chặn sau revalidation; không trả fixture_hits.
```

`CourseMember` hiện dùng `REMOVED` để thu hồi; fixture phải là membership học viên có quyền trước callback. Kiểm chứng thêm gỡ tài liệu, thay published_version và provider score NaN; tất cả là fail-closed.

Run:

```powershell
docker compose exec -T backend python manage.py test tests.documents.test_retrieval_adapter --settings=config.settings.test --verbosity=2
```

**Gate B3:** gọi retriever thật từ service/script, đúng nguồn và quyền; không cần thêm giao diện chat hoặc endpoint public trong W3.

## Task 6 — 50 QA của Cường và review chéo (4–5 giờ, bắt đầu 14/10, chốt 15/10)

- [ ] Lấy 25 pilot được phân công theo QA ID, đánh dấu owner; không để hai người rà soát cùng 25 và bỏ sót phần khác.
- [ ] Đối chiếu mỗi ground truth với PDF thật và trang vật lý; thêm evidence_text, source version/snapshot mapping và mode qa/hint. Chỉnh nhãn trong bản W3, giữ pilot gốc.
- [ ] Thêm 25 câu mới có nguồn trong corpus snapshot. Tách câu hỏi nội dung với gợi ý cách trả lời; không thêm dữ liệu trả lời riêng của giáo viên vào corpus student.
- [ ] Kiểm tra trùng câu hỏi/ý nghĩa, câu thiếu evidence, câu không thể trả theo source. Câu hỏi nhiều trang có tập nguồn chuẩn; nguồn tương đương không bị coi là bắt buộc đồng thời.
- [ ] Bàn giao CSV 50 mẫu và review 50 mẫu của Dương, ghi QA ID/reviewer/status/correction/reason; merge nhóm thành 100 QA sau xử lý bất đồng.

**Output:** `qa_w3_cuong_v1.0.csv`, review log; không tạo một bộ test kín mới. QA W3 dùng development. Cường không tự tạo 50 câu của Dương hoặc tự ghi là đã có review của Dương.

**Gate B3:** 50 mẫu của Cường có evidence đúng và đủ trường; không đạt thì ghi số hợp lệ thực. Chỉ chốt đủ 100 khi nhận và review cả phần Dương.

## Task 7 — Hồi quy và đối chiếu phép đo (2–3 giờ, 15–16/10)

- [ ] Nhận từ Dương notebook, retrieval_results, metrics và index manifest cùng revision; không chỉ nhận ảnh bảng Recall.
- [ ] Kiểm tra 5 QA mẫu hit/miss và case nhiều trang; tính Page Recall từ top-k chunks sau dedup trang; kiểm tra macro average và mẫu lỗi có Recall 0 theo protocol.
- [ ] Lưu `w3-cuong-error-analysis.md`: QA/chunk/source cụ thể, lỗi nhãn/chunk/truy xuất/quyền, đã sửa hoặc còn mở. Không tự gọi Page Recall là chất lượng gợi ý.
- [ ] Chạy test phần mới và hồi quy auth/material access/publication/worker; ghi pass/fail/skipped và môi trường. Test SQLite không chứng minh concurrency PostgreSQL.
- [ ] Chạy case quyền với DB riêng trên PostgreSQL nếu cần concurrency; không mutate dữ liệu demo thật để làm test.

Run phần mới sau khi triển khai:

```powershell
docker compose exec -T backend python manage.py test tests.documents.test_chunker tests.documents.test_chunking_batch tests.documents.test_retrieval_scope tests.documents.test_retrieval_adapter --settings=config.settings.test --verbosity=2
docker compose exec -T backend python manage.py test tests.documents.test_material_access tests.documents.test_worker tests.documents.test_integration --settings=config.settings.test --verbosity=2
```

**Gate B4:** không lỗi quyền/version/trùng artifact nghiêm trọng. Nếu notebook/index Dương chưa bàn giao, ghi blocked phần real integration, vẫn hoàn tất tests scope/chunk; không báo milestone full retrieval đã đạt.

## Task 8 — Gói tái lập và demo (2–3 giờ, 16/10)

- [ ] `w3-cuong-reproduce.md` ghi runtime/dependencies, input/version/config, lệnh build chunks, build/load index theo interface thật Dương đã bàn giao, chạy notebook và xuất metrics; kiểm tra đường dẫn trong container/private output.
- [ ] `evidence_manifest.json` trỏ source commit/PR, SHA256 QA/corpus/chunks/index/config/metrics, test log và demo. Không ghi revision chưa tồn tại.
- [ ] Demo ngắn: query thật →top-5 →đối chiếu PDF trang; reload index; nguồn sai quyền bị chặn. Đoạn demo nhận từ Dương phải cùng snapshot, không ghép hai cấu hình khác nhau như một lần chạy.
- [ ] Bảng Planned–Done–Evidence–Problems–Next week chia rõ đóng góp Cường và Dương; list output còn thiếu.
- [ ] Review chéo và khóa version cuối ngày 16. Không commit model/index lớn hoặc secret. Không reset/revert các file docs đang có thay đổi từ trước.

**Gate B4:** ngày 17 viết báo cáo từ gói đã chốt, không phải chạy lại thí nghiệm để tìm số liệu.

## Task 9 — Báo cáo (17/10)

- [ ] Viết 1–2 trang: mục tiêu W3, công việc cá nhân/nhóm, corpus/QA thực, baseline/config, Page Recall và giới hạn, lỗi và kế hoạch W4.
- [ ] Mỗi số liệu gắn với results/metrics có revision; chấm đúng phần đã làm, không đếm mocked tests thành embedding thật.
- [ ] Dương xác nhận phần embedding/index/metric; Cường xác nhận nguồn/quyền/test.
- [ ] Xuất báo cáo theo định dạng nộp và kiểm tra bố cục; link source/demo/gói evidence đúng quyền truy cập.

## Thứ tự làm ngay và phụ thuộc

1. **Ngay 14/10:** Task 1–2 và bàn giao chunk mẫu; làm Task 6 xen kẽ thời gian chờ model.
2. **Sau mẫu:** Task 3–4; Dương không phải đợi quyền/API mới bắt đầu offline index, nhưng nghiệm thu runtime cần Task 5.
3. **15/10:** Task 5 khi nhận interface; hoàn tất review QA và Task 7 khi nhận số liệu.
4. **16/10:** chỉ sửa blocker, tái lập và Task 8; không thêm hybrid, chat UI, QLoRA hoặc migration không cần thiết.

Kế hoạch chưa đánh dấu bất kỳ task nào Done. Lần triển khai tiếp theo bắt đầu bằng kiểm tra lại nhánh/code Dương và tình trạng workspace; không giả định kế hoạch ngày 12 phản ánh tiến độ ngày 14.
