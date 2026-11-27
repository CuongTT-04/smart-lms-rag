# Bàn giao W9-GR-01 — Ma trận quyền, Fixture dùng chung và Hợp đồng phạm vi nguồn

**Người phụ trách:** Trần Tuấn Cường (`B22DCVT073`)  
**Người tiếp nhận (`W9-GR-02`):** Vũ Nam Dương (`B22DCVT119`)  
**Tham chiếu phân công:** [phan-cong-w9-guardrails.md](phan-cong-w9-guardrails.md)

---

## 1. Ma trận quyền học liệu xuyên suốt LMS

| Kênh / Endpoint | Hàm kiểm quyền chính | Chủ khóa (`teacher_main`) | HV đúng lớp (`student_a`) | HV lớp bên cạnh (`student_b`) | GV khóa khác (`teacher_other`) | Admin tổng hợp (`admin_summary`) | Cache header |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /api/courses/{id}/documents/` | `require_access` + lọc `Enrollment(ACTIVE/COMPLETED)` & `is_published` & `is_draft=False` | `200` (tất cả bản chưa gỡ) | `200` (chỉ bản công bố thuộc lớp mình & học liệu cấp khóa) | `200` (chỉ lớp B, **0** tài liệu lớp A) | `404` | `404` | `private, no-store` |
| `GET /api/documents/{id}/status/` | `DocumentAPIView.document()` + `version()` | `200` | `200` (chỉ `published_version`) | `404` | `404` | `404` | `private, no-store` |
| `GET /api/documents/{id}/view/` | `DocumentViewView.get()` (`select_for_update`, watermark email khi `PROTECTED`, re-check sau I/O) | `200` (watermark email hoặc bản sạch khi `PUBLIC_DOWNLOAD`) | `200` (watermark email khi `PROTECTED`, chỉ `published_version`) | `404` | `404` | `404` | `private, no-store` |
| `GET /api/documents/{id}/view/?expected_version_id=...` (mở citation) | `DocumentViewView.get()` + so khớp `expected_version_id` | `200` nếu khớp, `409 SCOPE_CHANGED` nếu lệch | `200` nếu khớp `published_version`, `409 SCOPE_CHANGED` nếu đổi phiên bản | `404` | `404` | `404` | `private, no-store` |
| `GET /api/documents/{id}/download/` (tải bản sạch) | `DocumentDownloadView` (`material_policy == PUBLIC_DOWNLOAD` cho HV, re-check sau I/O) | `200` (luôn tải được bản gốc) | `200` khi `PUBLIC_DOWNLOAD`, **`403 DOWNLOAD_DISABLED`** khi `PROTECTED` | `404` | `404` | `404` | `private, no-store` |
| `GET /api/documents/{id}/extraction/` | `DocumentExtractionView.get(manage=True)` | `200` | `404` | `404` | `404` | `404` | `private, no-store` |
| `GET/PUT /api/documents/{id}/study-notes/?version_id=...` | `StudyNotesView` + `study_scope` HMAC `(user, doc, version)` + `recheck_version` | `200` (dữ liệu riêng của actor) | `200` (chỉ `published_version` hiện hành) | `404` | `404` | `404` | `private, no-store` |
| `resolve_scope()` / `POST /api/ai/chat/` | `retrieval_scope.resolve_scope()` + `ai.policy.enforce_chat_policy()` | Cho phép (hỗ trợ `preview=True` cho nháp/chưa công bố) | Chỉ `published_version` lớp mình (`preview=True` → `404`; đang làm `TEST` → `403 AI_NOT_ALLOWED`) | Chỉ lớp B | `404` | `404` | N/A |
| `GET /api/ai/conversations/{id}/` & `GET /api/ai/summaries/{id}/` | `owned_conversation()` / `owned_task()` gọi lại `resolve_scope()` + đối chiếu `published_version_id` | `200` (chủ hội thoại) | `200` khi còn quyền & đúng phiên bản; `404`/`409` ngay khi mất quyền hoặc đổi phiên bản | `404` | `404` | `404` | N/A |

### Các điểm đã rà và siết chặt trong `W9-GR-01`
1. **Chống cache metadata/extraction cũ:** [views.py](../../../backend/apps/documents/api/views.py) (`DocumentAPIView.finalize_response`) gắn `Cache-Control: private, no-store` cho mọi phản hồi `GET` (bao gồm danh sách tài liệu, trạng thái, extraction, preview, download và study-notes).
2. **Làm mới trạng thái tài khoản trực tiếp từ DB (`refresh_live_user`):** [access.py](../../../backend/apps/documents/access.py) và [permissions.py](../../../backend/apps/courses/permissions.py) kiểm đồng thời `is_active` và `status == ACTIVE` sau khi `refresh_from_db`, nên nếu tài khoản bị khóa/đổi vai trò giữa lượt (kể cả qua `.update()` trực tiếp), `resolve_scope`, `live_scope` và mọi endpoint đều chặn ngay (`401`/`404`).
3. **Đóng khe TOCTOU sau file I/O:** [views.py](../../../backend/apps/documents/api/views.py) (`DocumentViewView.get`) kiểm lại `version.removed_at`, `published_version_id`, `expected_version_id` và `material_policy` ngay sau khi đọc file PDF, tránh trả bản sạch khi chính sách vừa chuyển từ `PUBLIC_DOWNLOAD` về `PROTECTED`.
4. **Hàm kiểm citation dùng chung:** bổ sung `verify_citation_access()` trong [retrieval_scope.py](../../../backend/apps/documents/retrieval_scope.py) và `assert_scope_and_citations_live()` trong [retrieval_adapter.py](../../../backend/apps/documents/retrieval_adapter.py) để `W9-GR-02` gọi trực tiếp khi kiểm tra citation và sau bước gọi model.

---

## 2. Bộ fixture kiểm thử dùng chung và cách reset

**Đường dẫn code:** `backend/tests/documents/w9_guardrails_fixture.py`  
**Hàm khởi tạo:** `build_w9_guardrails_fixture(prefix='w9gr')` (dùng trong `TestCase` kèm `override_settings(DOCUMENTS_STORAGE_ROOT=tmp_dir)` — mỗi test case có DB transaction rollback và thư mục PDF tạm riêng nên tự reset sạch sau mỗi lần chạy, không ảnh hưởng dữ liệu đang dùng).

### Tài khoản và phạm vi trong fixture
| Biến fixture | Username | Vai trò | Phạm vi được phép |
| --- | --- | --- | --- |
| `teacher_main` | `w9gr-teacher-1` | `TEACHER` | Chủ `course_main` (`classroom_a`, `classroom_b`) |
| `teacher_other` | `w9gr-teacher-2` | `TEACHER` | Chủ `course_other` (`classroom_other`) |
| `student_a` | `w9gr-student-a` | `STUDENT` | Thành viên `course_main`, chỉ ghi danh `classroom_a` |
| `student_b` | `w9gr-student-b` | `STUDENT` | Thành viên `course_main`, chỉ ghi danh `classroom_b` |
| `admin_summary` | `w9gr-admin-summary` | `ADMIN` | Không có quyền đọc tài liệu/file/citation/chat của lớp |

### Học liệu giả lập, trang chuẩn và cụm từ nhận biết (`SENTINELS`)
| Biến fixture | Vị trí | Trạng thái mặc định | Số trang & Sentinel nhận biết | Mục đích kiểm chứng |
| --- | --- | --- | --- | --- |
| `doc_allowed` (`doc_allowed_v1`) | `session_a` (Lớp A) | `is_published=True`, `PROTECTED`, `READY` | 3 trang: Trang 1 `W9_SCOPE_A_P1_CPU_CYCLE` (chu kỳ lệnh CPU); Trang 2 `W9_SCOPE_A_P2_ALU_GATES` (cổng ALU — không hỗ trợ ý chu kỳ CPU); Trang 3 `W9_SCOPE_A_P3_REGISTERS` + chỉ dẫn giả lập `W9_PROMPT_INJECTION_MARKER` | Kiểm trả lời đúng trang, phân biệt trang không hỗ trợ nhận định, prompt injection vô hại |
| `doc_versioned` (`v1`, `v2`) | `session_a` (Lớp A) | `v1` công bố (2 trang), `v2` sẵn sàng chưa công bố (3 trang) | `v1`: `W9_VER1_ONLY_PAGE1_ALPHA`, `W9_VER1_ONLY_PAGE2_ALPHA`; `v2`: `W9_VER2_ONLY_PAGE1_BETA`..`PAGE3_BETA` | Kiểm `v2` chưa công bố không lộ, công bố `v2` làm hết hiệu lực URL/citation/lịch sử của `v1` |
| `doc_classroom_b` | `session_b` (Lớp B) | `is_published=True`, `PROTECTED`, `READY` | 2 trang: `W9_SCOPE_B_SECRET_CLASSROOM_B` | Kiểm chặn rò chéo lớp trong cùng khóa |
| `doc_other_course` | `session_other` (Khóa khác) | `is_published=True`, `PROTECTED`, `READY` | 1 trang: `W9_SCOPE_OTHER_COURSE_SECRET` | Kiểm chặn rò chéo khóa |
| `doc_removed` | `session_a` (Lớp A) | Đã gỡ (`remove_document`) | 1 trang: `W9_REMOVED_DOC_SECRET` | Kiểm chặn nguồn đã gỡ |
| `doc_draft_session` | `session_a_draft` (Buổi nháp) | `is_published=True`, buổi `is_draft=True` | 1 trang: `W9_DRAFT_SESSION_SECRET` | Kiểm buổi nháp chỉ mở cho chủ khóa khi `preview=True` |
| `practice_quiz` / `active_test` | `session_a` (Lớp A) | `PRACTICE` / `TEST` đều công bố | `active_test` chứa đáp án bí mật `W9_PRIVATE_TEST_KEY_DELTA`; gọi `fx.start_active_test_attempt(fx.student_a)` để tạo lượt `DRAFT` đang làm | Kiểm gợi ý ôn tập không lộ đáp án và chặn AI `403 AI_NOT_ALLOWED` khi đang làm `TEST` |

Catalog chunk khớp sẵn checksum và số trang được cấp trực tiếp qua `fx.catalog`; danh sách mã ca kiểm cố định (`W9-C01`..`W9-C07`) nằm tại `W9_GUARDRAIL_CASES`.

---

## 3. Hợp đồng phạm vi nguồn cho `W9-GR-02` (Dương gọi chung)

1. **Xác định phạm vi đầu lượt:** gọi `scope = resolve_scope(user, course_id, classroom_id, session_id, document_ids, mode, preview=False)`. Client chỉ đề nghị ID; server quyết định `scope.allowed_version_ids`.
2. **Truy xuất có kiểm quyền hai đầu:** gọi `retrieve_authorized(...)` / `retrieve_dense_authorized(...)`. Hệ thống gọi `live_scope(user, scope)` trước khi search, sau khi search và sau khi đối chiếu provenance (`chunk.course_id`, `document_id`, `source_checksum`, `1 <= page_number <= page_count`).
3. **Kiểm lại trước khi trả UI & lưu lịch sử:** gọi `assert_scope_and_citations_live(user, scope, citations=citations)` (tự gọi `live_scope` + `verify_citation_access` cho từng citation).
4. **Mở citation từ UI:** `CitationViewer` luôn gọi `GET /api/documents/{document_id}/view/?expected_version_id={version_id}` (kèm `#page={page_number}` phía viewer).
5. **Mã lỗi chuẩn theo trạng thái:**
   - Thiếu căn cứ trong nguồn được phép: `200` với `status="INSUFFICIENT_EVIDENCE"`, `citations=[]`.
   - Đang làm bài `TEST` (còn hạn, chưa nộp): `403 AI_NOT_ALLOWED` trước khi gọi model.
   - Đổi phiên bản công bố / trang không hợp lệ / thay đổi tập nguồn giữa lượt: `409 SCOPE_CHANGED`.
   - Tài liệu bị gỡ / hủy công bố / mất quyền lớp-khóa / buổi nháp / Admin truy cập nguồn riêng: `404 NOT_FOUND`.
   - Tài khoản bị khóa / vô hiệu hóa giữa lượt: `401 AUTH_REQUIRED`.

---

## 4. Kết quả kiểm thử thực chạy (`W9-GR-01`)

Chạy ngày `25/11/2026` trong container `backend` Docker (`DJANGO_SETTINGS_MODULE=config.settings.test`):

- **Lệnh kiểm thử:**
  ```powershell
  docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test backend python manage.py test tests.documents.test_w9_guardrails_access tests.documents.test_material_access tests.documents.test_retrieval_scope tests.documents.test_session_access tests.documents.test_retrieval_adapter tests.documents.test_study_annotations apps.courses.tests tests.ai --noinput
  ```
  - **Kết quả:** `Ran 305 tests in 57.460s — OK` (**305/305 PASS**, gồm **7/7** ca mới trong `test_w9_guardrails_access.py`, toàn bộ `test_material_access`, `test_retrieval_scope`, `test_session_access`, `test_retrieval_adapter`, `test_study_annotations`, `apps.courses.tests` và `tests.ai`).
- **Kiểm tra migration & hệ thống:**
  - `python manage.py makemigrations --check --dry-run` → `No changes detected`.
  - `python manage.py check` → `System check identified no issues (0 silenced)`.
- **Trạng thái còn chờ ghép với Dương (`W9-GR-02`):**
  - Chạy model thật (Kaggle/gateway) với bộ fixture `w9_guardrails_fixture.py`, chấm `accuracy`/`coverage` citation theo nhận định (`NFR-29`), kiểm chéo mở citation trên UI rồi thu hồi quyền, và tổng hợp `Evidence/W09/`.
