# Báo cáo kết quả thực hiện W9-01 (Trần Tuấn Cường)

- **Ngày thực hiện:** 18–20/11/2026
- **Người phụ trách:** Trần Tuấn Cường (B, B22DCVT073)
- **Nhánh tích hợp:** `codex/w9-integration`, ghép phần LMS tại `818a9c3` với Ayo của Dương tại `77f9259`; nền chung `8b180aa`.
- **Trạng thái:** Đã ghép code LMS và Ayo, nối hoàn thành học liệu và kiểm hợp đồng hint. Kiểm thử tự động trên bản chung đạt. Nghiệm thu model thật và demo xuyên suốt E01–E10 còn chờ kiểm thực tế.

---

## 1. Tóm tắt kết quả theo từng tác vụ (T0–T7)

### T0. Khóa đầu vào và bàn giao Ayo hiện có
- Tạo tài liệu bàn giao tại `docs/weekly/W9/ban-giao-ayo-cho-duong.md`, ghi rõ nhánh/HEAD, danh sách biến môi trường (không sao chép secret), đường dẫn cell Kaggle thực tế (`notebooks/generation_setup.ipynb` cell `ohayo-chat-memory-startup`), luồng gọi UI → API → Retrieval/Runtime → Kaggle, các lỗi ghi nhận ngày 17/11 và ranh giới ownership file.

### T1. Điều tra và sửa kiểm thử LMS (`ClassroomSessionTests`)
- **Nguyên nhân gốc đã xác định:** Trong `tests/common/test_classroom_sessions.py`, `ClassroomAnnouncementImageView` trả về `FileResponse` (`streaming=True`). Django `ClientHandler.__call__` chỉ ngắt `close_old_connections` khỏi signal `request_finished` cho non-streaming response; khi test gọi `image.close()` trên streaming response bên trong transaction `TestCase` (`autocommit=False != settings['AUTOCOMMIT']`), `close_old_connections()` gọi `BaseDatabaseWrapper.close()`, làm đóng socket `psycopg` trong khi `in_atomic_block=True` nên giữ nguyên `self.connection` đã đóng cho toàn bộ các test sau trong class.
- **Sửa tối thiểu:** Thêm helper `close_response(response)` trong `backend/common/testing.py` (tạm ngắt `close_old_connections` quanh `response.close()`, khôi phục ở `finally`), áp dụng tại `backend/tests/common/test_classroom_sessions.py` kèm assertion kiểm tra stream đã đóng và `connection.connection.closed` vẫn `False`.
- **Kiểm chứng:** `tests.common.test_classroom_sessions` đạt `10/10 OK`; nhóm 205 test (`test_classroom_sessions`, `apps.users.tests`, `apps.courses.tests`, `test_assessments`, `test_session_videos`) đạt `205/205 OK`.

### T2. Dữ liệu và phép tính tiến độ học tập
- **File tạo/sửa:** `backend/apps/courses/progress_models.py` (`DocumentCompletion`), `backend/apps/courses/models.py`, migration `backend/apps/courses/migrations/0016_documentcompletion.py`, `backend/apps/courses/progress_services.py`, command `backend/apps/courses/management/commands/rebuild_classroom_progress.py`, và bộ test `backend/apps/courses/tests/test_learning_progress.py`.
- **Chi tiết triển khai:**
  - `DocumentCompletion` gắn unique `(enrollment, document_version)` với `enrollment` (`CASCADE`) và `document_version` (`PROTECT`).
  - `progress_services.py` cung cấp `classroom_progress`, `mark_document_complete`, `refresh_classroom_progress` và `bulk_enrollment_progress` (truy vấn hàng loạt O(1), không query theo N×hoạt động).
  - Gắn hook `refresh_classroom_progress` vào các điểm mutation thuộc phạm vi LMS: `video_services.py` (`update_progress`, `submit_answer`), `assessment_services.py` (`finalize`), `enrollment_services.py` (`activate`), `video_views.py`, `assessment_views.py`, `session_views.py`.
  - Đồng bộ `Enrollment.progress_percent`, `Enrollment.status` (`ACTIVE`/`COMPLETED`), `Enrollment.completed_at` theo đúng hợp đồng mục 2.1; tuyệt đối không tự mở lại `WITHDRAWN`.
- **Kiểm chứng:** `test_learning_progress` đạt `5/5 OK` (bao gồm `TransactionTestCase` kiểm concurrency gửi lặp và race thu hồi ghi danh).

### T3. API tiến độ và giao diện đánh dấu đã học
- **Backend:** `backend/apps/courses/api/progress_serializers.py`, `progress_views.py`, `urls.py` (routes `GET progress/` và `POST progress/documents/{version_id}/complete/`), `backend/apps/courses/tests/test_progress_api.py`.
- **Frontend:** `frontend/src/hooks/useClassroomProgress.js`, `frontend/src/components/learning/LearningProgress.jsx` (`ClassroomProgressBadge`, `SessionProgressBadge`, `DocumentCompletionButton`), `LearningProgress.test.jsx`, cập nhật `course.service.js`, `ClassroomRoster.jsx`, `ClassroomWorkspace.jsx`.
- **Kiểm chứng:** `test_progress_api` passing; `LearningProgress.test.jsx` (`4/4`), `ClassroomRoster.test.jsx` (`7/7`), `ClassroomWorkspace.test.jsx` (`8/8`) đều đạt.

### T4. Kết quả lớp và Teacher Analytics toàn lớp
- **Backend:** `backend/apps/courses/classroom_results.py`, `api/classroom_results_serializers.py`, `api/classroom_results_views.py`, `urls.py` (`GET results/` và `GET results/export/`), `tests/test_classroom_results.py`.
  - Chính sách điểm tách bạch rõ: `PRACTICE` chọn điểm cao nhất trong lượt `SUBMITTED` hợp lệ mà người gọi được phép thấy (học viên không bị rò điểm/lượt chưa công bố); `TEST` chọn lượt duy nhất; tách `submission_status` và `grading_status`; giữ `0` là điểm đã chấm; thống nhất chỉ số "Bài chờ chấm" (`pending_grading_count` đếm mọi ô có `pending_attempts_count > 0`, kể cả bài đã có điểm cao nhất trước đó nhưng vừa nộp thêm lượt chưa chấm) và `pending_attempts_count` (tổng lượt chờ chấm) đồng bộ giữa API summary, bộ lọc `?grading_status=PENDING`, Excel `inlineStr` và giao diện; đánh dấu `is_overdue` và `is_removed`; phân trang ổn định và query count không đổi giữa 3 và 30 học viên.
- **Frontend:** `frontend/src/components/ClassroomResults.jsx`, `ClassroomResults.test.jsx`, tích hợp thay thế placeholder trong `ClassroomWorkspace.jsx`, cập nhật `classrooms.css` và `ClassroomNavigation.test.jsx`.
- **Kiểm chứng:** `test_classroom_results` (`3/3 OK`), `ClassroomResults.test.jsx` (`3/3 OK`).

### T5. Quiz/Submission và thống nhất nút trợ giúp AI
- **Sửa lỗi `question_stats`:** Cập nhật `backend/apps/courses/assessment_questions.py` (`selected_ids`) và `backend/apps/courses/assessment_reports.py` để giá trị `[]`, `""` hoặc thiếu key không bị tính vào `answered`.
- **Thống nhất UI trợ giúp:** Cập nhật `frontend/src/components/assessments/AssessmentRunner.jsx` bỏ nút `"Trợ giúp AI"` cũ luôn báo chưa kết nối, giữ callback `onRequestAssistance({ assessment_id, question_id })` cho `QUIZ` và `{ assessment_id }` cho `TEXT`, giữ hiển thị rõ `"Gợi ý tĩnh của giáo viên"` (khi có) và ẩn hoàn toàn trong chế độ `TEST`. API legacy `AssessmentAssistanceView` vẫn giữ nguyên cho các caller cũ.
- **Kiểm chứng:** `tests.common.test_assessments` (`11/11 OK`), `AssessmentRunner.test.jsx` (`12/12 OK`), `AssessmentDashboard.test.jsx` (`3/3 OK`).

### T6. Dữ liệu demo và bảng kết quả mong đợi
- **Tạo:** `backend/apps/courses/management/commands/seed_w9_demo.py`, `backend/apps/courses/tests/test_w9_demo.py`, `docs/weekly/W9/demo-w9-01.md`.
- Command khóa an toàn kép (`W9_DEMO_ENABLED=1`, tên DB `w9_demo_*`, mật khẩu qua `W9_DEMO_PASSWORD` không in ra stdout); tạo PDF 2 trang thật bằng ReportLab kèm derivative watermark đọc được qua `/api/documents/{id}/view/` (`PdfReader`) và video WebM VP8 phát được dài `12.0s` (checkpoint `5.0s`, kiểm 12 frame qua `cv2.VideoCapture` và `/videos/{id}/file/`); kiểm tra conflict đầy đủ trên toàn bộ trường quyết định kết quả (attempt status/score/answers/grade_published, VideoProgress chưa hoàn thành, DocumentCompletion, enrollment/session/assessment) và không tự ghi đè dữ liệu đã thay đổi.
- **Kiểm chứng:** `test_w9_demo` (`2/2 OK`).

---

## 2. Patch phối hợp bàn giao cho Vũ Nam Dương (`W9-02`)

Do tuân thủ ranh giới ownership file trong `phan-cong-w9.md`, Cường **không sửa trực tiếp** các file thuộc quyền giữ của Dương. Dưới đây là 2 điểm ghép nối sẵn sàng tích hợp khi Dương hoàn tất W9-02:

1. **`backend/apps/documents/services.py` (tại `set_publication` và `remove_document`):**
   Sau khi thay đổi `published_version` / `is_published` / `removed_at` thành công (bên trong transaction hoặc ngay sau khi lưu):
   ```python
   if locked.session_id:
       from apps.courses.progress_services import refresh_classroom_progress
       refresh_classroom_progress(classroom_id=locked.session.classroom_id)
   ```
   *(Lưu ý: `GET progress/` và `GET results/` đã tự tính từ DB hiện tại nên không bao giờ hiển thị số cũ; callback này giúp đồng bộ cột cache `Enrollment.progress_percent` và `Enrollment.completed_at` ngay tại thời điểm giáo viên công bố/thay phiên bản/gỡ tài liệu).*

2. **`frontend/src/components/SessionWorkspace.jsx` & `frontend/src/components/documents/CourseDocuments.jsx`:**
   - Truyền `onDocumentLoaded` (khi `PdfViewer` nạp thành công `blob`) hoặc dùng `useClassroomProgress(course.id, room.id, !canManage)` trong `SessionWorkspace.jsx` và gắn `<DocumentCompletionButton courseId={course.id} classroomId={room.id} versionId={active.published_version_id} documentLoaded={...} completed={...} onCompleted={reloadProgress} />` cho học viên.

---

## 3. Kết quả kiểm chứng LMS trước khi ghép Ayo

Log chi tiết được lưu tại `.private/w9/member-b/`.

| Lệnh kiểm chứng | Phạm vi / Kết quả thực tế |
|---|---|
| `docker compose exec -T backend python manage.py makemigrations --check --dry-run` | `No changes detected` (exit 0) |
| `docker compose exec -T backend python manage.py check` | `System check identified no issues (0 silenced)` (exit 0) |
| `git diff --check` | Không lỗi trailing whitespace / conflict marker (exit 0) |
| `docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test backend python manage.py test apps.courses.tests.test_learning_progress apps.courses.tests.test_progress_api apps.courses.tests.test_classroom_results apps.courses.tests.test_w9_demo --noinput` | **11/11 tests OK** (`4.177s`) |
| `docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test backend python manage.py test apps.users.tests apps.courses.tests tests.common tests.ai tests.documents.test_material_access tests.documents.test_study_annotations --noinput` | Chạy **365 tests**, báo **7 failures + 1 error** đều nằm trong `tests.common.test_schema.OpenAPITests` cho phần `/api/ai/*` của W9-02 (Dương); 100% test LMS (bao gồm 4 endpoint mới của Cường trong `test_schema.py`) đều đạt (`51.816s`). |
| `npm.cmd run lint` (trong `frontend/`) | **0 errors, 0 warnings** (`eslint . --max-warnings 0`) |
| `npm.cmd run build` (trong `frontend/`) | **Thành công** (`vite build` trong `809ms`) |
| `npm.cmd test -- --run --maxWorkers=2` (trong `frontend/`) | **54/54 file test PASS, 346/346 tests PASS** (`85.09s`) |

### Chi tiết các failure còn lại trong `tests.common.test_schema.OpenAPITests` (phụ thuộc W9-02)
- `test_error_responses_include_real_shapes_and_pagination_not_found` (`KeyError: 'additionalProperties'`)
- `test_every_operation_has_concise_vietnamese_documentation` cho 4 endpoints AI (`/api/ai/conversations/` GET/POST, `/api/ai/conversations/{conversation_id}/` GET, `/api/ai/chat/{answer_id}/feedback/` PATCH)
- `test_schema_validates_and_documents_all_business_operations` (thiếu 5 endpoints `/api/ai/*` trong tập expected)
- `test_schema_swagger_and_health_are_public` & `test_write_operations_use_bearer_security_without_csrf_header` (`DatabaseOperationForbidden` trên `SimpleTestCase`)

---

## 4. Tích hợp Ayo ngày 20/11/2026

Đã nhận commit `77f9259` của Dương và đối chiếu 67 file code với `ayo-handoff.zip`. Checksum ZIP đúng biên bản, 111 file manifest đúng kích thước/hash. Notebook gửi riêng có cùng nội dung cell với bản runtime trong ZIP.

- Xử lý xung đột `test_classroom_sessions.py`, giữ kiểm tra PNG, đóng stream và kết nối DB còn mở.
- Gắn `DocumentCompletionButton` vào màn hình đọc học liệu của học viên. Truyền classroom từ `SessionWorkspace`; chỉ bật sau khi PDF tải được. Tính trạng thái theo `kind=PDF` và đúng version; hủy request tiến độ cũ khi áp dụng kết quả ghi hoàn thành.
- Sau công bố, đổi phiên bản công bố, thu hồi công bố hoặc gỡ tài liệu, tính lại tiến độ sau commit giao dịch học liệu để tránh đảo thứ tự khóa enrollment/document. Test kiểm trạng thái enrollment thực tế và thời điểm callback.
- Luồng hint dùng `onRequestAssistance` hiện có qua `SessionAssistant`, gửi scope, `mode=hint`, assessment/question công khai qua `/api/ai/chat/`. Test xác nhận không gửi conversation_id và hủy request cũ khi đổi bài. Bộ policy AI/OpenAPI chạy cùng LMS đã đạt.

| Kiểm chứng trên bản tích hợp | Kết quả |
|---|---|
| Backend chính, settings `config.settings.test` | 429/429 đạt; users, courses, common/schema, AI, material access và annotations |
| Các module tài liệu runtime/index/parser còn lại | 84/84 đạt |
| Upload/worker với `tests.documents_settings` | 27/27 đạt |
| Frontend toàn bộ | 56 file, 366/366 đạt |
| Frontend kiểm lại PDF/progress/hint sau bổ sung assertion | 4 file, 16/16 đạt |
| Lint/build | Đạt; build còn cảnh báo chunk lớn |
| Django check và makemigrations --check --dry-run | Đạt, không thiếu migration |

Log riêng ở `.private/w9/integration-20261120/`. Lượt đầu gọi toàn bộ `tests.documents` bằng settings LMS có hai lỗi import test-support của upload/worker; đã chạy riêng đúng settings theo README và đạt. Các lỗi này không được tính là lượt test đạt. Cấu hình demo đã bổ sung Compose project riêng để frontend và backend cùng dùng DB demo.

## 5. Những mục còn chờ nghiệm thu nhóm

- Địa chỉ Kaggle trong Docker trả HTTP 404 ở `/health` khi kiểm ngày 20/11. Người chạy xác nhận notebook báo thiếu checkpoint nền NF4 trong Input. Cần gắn lại dataset `ohayo-model` đã dùng ở notebook Qwen cũ, khởi động runtime và cung cấp URL hoạt động để kiểm model thật trên bản tích hợp, gồm hint PRACTICE, TEST, nguồn nhiều trang, memory, summary và câu hỏi gợi ý.
- Chạy demo giáo viên–học viên–giáo viên trên dữ liệu demo riêng, kiểm restart giữ dữ liệu và quyền API/media. Kết quả test tự động ở mục 4 chưa thay thế bằng chứng thao tác trên trình duyệt/model thật.
- Chuyển log/ảnh/config đã khử bí mật và SHA bản chạy cuối cho Dương tổng hợp `Evidence/W09/`. Chỉ đóng milestone nhóm sau khi E01–E10 được kiểm đủ.
