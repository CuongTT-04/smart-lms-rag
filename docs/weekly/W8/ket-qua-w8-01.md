# Báo cáo hoàn thiện LMS core và AI assistant (Trần Tuấn Cường)

- **Yêu cầu nghiệm thu:** “Hoàn thiện LMS core: course/lesson/quiz/submission + AI assistant”, theo mốc W8 giảng viên giao. Tài liệu được chuyển về W8 ngày 24/11/2026. Các tên nhánh, lệnh, DB và đường log có nhãn `w9` bên dưới ghi đúng định danh kỹ thuật của những lần chạy W8 để tra cứu kết quả.

- **Ngày thực hiện:** 18–21/11/2026
- **Người phụ trách:** Trần Tuấn Cường (B, B22DCVT073)
- **Nhánh tích hợp:** `codex/w9-integration`, ghép phần LMS tại `818a9c3` với Ayo của Dương tại `77f9259`; nền chung `8b180aa`.
- **Trạng thái:** Đã ghép và triển khai LMS + Ayo, kiểm demo LMS trên trình duyệt ngày 20/11, kiểm model thật qua API và Nginx ngày 21/11. Gói bằng chứng phần Cường đã sẵn sàng để Dương tổng hợp Evidence/W08; các giới hạn kiểm tra ghi ở mục 5–6.

---

## 1. Tóm tắt kết quả theo từng tác vụ (T0–T7)

### T0. Khóa đầu vào và bàn giao Ayo hiện có
- Tạo tài liệu bàn giao tại `docs/weekly/W8/ban-giao-ayo-cho-duong.md`, ghi rõ nhánh/HEAD, danh sách biến môi trường (không sao chép secret), đường dẫn cell Kaggle thực tế (`notebooks/generation_setup.ipynb` cell `ohayo-chat-memory-startup`), luồng gọi UI → API → Retrieval/Runtime → Kaggle, các lỗi ghi nhận ngày 17/11 và ranh giới ownership file.

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
- **Tạo:** `backend/apps/courses/management/commands/seed_w9_demo.py`, `backend/apps/courses/tests/test_w9_demo.py`, `docs/weekly/W8/demo-w8-01.md`.
- Command khóa an toàn kép (`W9_DEMO_ENABLED=1`, tên DB `w9_demo_*`, mật khẩu qua `W9_DEMO_PASSWORD` không in ra stdout); tạo PDF 2 trang thật bằng ReportLab kèm derivative watermark đọc được qua `/api/documents/{id}/view/` (`PdfReader`) và video WebM VP8 phát được dài `12.0s` (checkpoint `5.0s`, kiểm 12 frame qua `cv2.VideoCapture` và `/videos/{id}/file/`); kiểm tra conflict đầy đủ trên toàn bộ trường quyết định kết quả (attempt status/score/answers/grade_published, VideoProgress chưa hoàn thành, DocumentCompletion, enrollment/session/assessment) và không tự ghi đè dữ liệu đã thay đổi.
- **Kiểm chứng:** `test_w9_demo` (`2/2 OK`).

---

## 2. Patch phối hợp bàn giao cho Vũ Nam Dương (`W8-02`)

Do tuân thủ ranh giới ownership file trong `phan-cong-w8.md`, Cường **không sửa trực tiếp** các file thuộc quyền giữ của Dương. Dưới đây là 2 điểm ghép nối sẵn sàng tích hợp khi Dương hoàn tất W8-02:

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
| `docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test backend python manage.py test apps.users.tests apps.courses.tests tests.common tests.ai tests.documents.test_material_access tests.documents.test_study_annotations --noinput` | Chạy **365 tests**, báo **7 failures + 1 error** đều nằm trong `tests.common.test_schema.OpenAPITests` cho phần `/api/ai/*` của W8-02 (Dương); 100% test LMS (bao gồm 4 endpoint mới của Cường trong `test_schema.py`) đều đạt (`51.816s`). |
| `npm.cmd run lint` (trong `frontend/`) | **0 errors, 0 warnings** (`eslint . --max-warnings 0`) |
| `npm.cmd run build` (trong `frontend/`) | **Thành công** (`vite build` trong `809ms`) |
| `npm.cmd test -- --run --maxWorkers=2` (trong `frontend/`) | **54/54 file test PASS, 346/346 tests PASS** (`85.09s`) |

### Chi tiết các failure còn lại trong `tests.common.test_schema.OpenAPITests` (phụ thuộc W8-02)
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

### Docker và demo trên trình duyệt

Bản code tích hợp được lưu tại merge commit `1163002`, có hai parent `818a9c3` và `77f9259`. Đã sao lưu DB trước triển khai vào `.private/w9/integration-20261120/database-before.dump`, rebuild Docker và kiểm health qua frontend cổng 5173. Backend/frontend healthy, Nginx `-t` đạt. Các migration `ai.0003_summarytask`, `courses.0016_documentcompletion`, `documents.0004_documentstudynotes` đã áp dụng.

Demo thực tế dùng Compose project `smart-lms-w9-demo`, DB `w9_demo_w9integration`, frontend `http://localhost:5174`, có mạng và volume riêng. Tài khoản/mật khẩu demo nằm trong file riêng `demo.env`, ngoài Git.

| Thao tác đã kiểm qua trình duyệt | Kết quả quan sát |
|---|---|
| S1 mở PDF có watermark, đánh dấu đã học | Hiển thị Đã học; tiến độ từ 25% lên 50% |
| S1 tiếp tục tự luận, lưu nháp và nộp bài | Đã nộp thành công, chờ chấm; tiến độ 3/4 = 75% |
| T1 mở bảng lớp | S1 75%, S2 100%; 2 bài chờ chấm trước khi chấm S1 |
| T1 chấm tự luận S1 8/10 và công bố lượt đó | Bảng lớp hiện 8/10; còn 1 bài chờ chấm của S2 |
| Restart backend demo, đăng nhập lại S1 | Vẫn 75%, quiz 0/10, tự luận 8/10, TB 4; DB kiểm lại SUBMITTED, grade_published=True |

Ảnh trong thư mục log riêng gồm `student-pdf-completed.png`, `student-submitted.png`, `teacher-results-pending.png`, `teacher-results-graded.png`, `student-results-after-restart.png`. Dữ liệu demo đã thay đổi qua thao tác nộp/chấm thật, nên S1 ở 75% và tự luận 8/10 thay cho trạng thái seed ban đầu. Command seed sẽ báo conflict nếu chạy lại vào các bản ghi đã thay đổi; dùng DB demo mới khi cần kịch bản từ đầu.

## 5. Kiểm Ayo với Kaggle thật ngày 21/11/2026

URL người dùng cung cấp khớp cấu hình Docker. Gateway `/health` trả ready, 2 replica, cấu hình Qwen2.5-7B-Instruct đúng revision và đủ capability cho QA, history, citation, summary. Học liệu CPU hiện công bố đúng checksum `602b731153749027a9d62e1b361b369b9cfa932c22994030a355c06be5d85b41`, version `b879fdaf-fa8d-4947-b713-e4ee6cb63939`.

Bộ nghiệm thu chính dùng DB PostgreSQL test riêng, JWT và API/permission/retrieval thực, gọi Kaggle thật. Đối chiếu nội dung với các đoạn CPU đã trích xuất, không chỉ dựa vào citation ID. File kết quả thô và đoạn nguồn nằm riêng ngoài Git tại `.private/w9/live-20261121/`.

| Nhóm kiểm | Kết quả quan sát |
|---|---|
| 10 câu QA | 8 câu có nguồn được trả lời đúng nội dung; 2 câu lịch thi/RTX 5090 thiếu căn cứ và không gán nguồn |
| Chu kỳ lệnh CPU | Đủ 10 bước theo slide, gồm tăng PC và lặp ở trang 9; nguồn trang 8–9, có nhãn trích học liệu |
| Memory | 2 hội thoại độc lập; ALU → đại từ Nó → CU → đại từ Nó. Câu CU độc lập bỏ lịch sử ALU; hội thoại mới bắt đầu turns_used=0 |
| Câu hỏi gợi ý | Chọn một gợi ý tạo đúng lượt trong hội thoại; gửi lại cùng client_message_id không tăng số lượt |
| Hint PRACTICE | Nhận bài tập công khai qua API, hướng dẫn tự đọc, yêu cầu chép đáp án vẫn giữ chế độ hướng dẫn |
| Summary trang 7–9 | COMPLETED, 3/3 trang, 3 chunk và 5/5 phần, có định nghĩa, bước xử lý, tăng PC/lặp và ví dụ; khoảng 31 giây ở lượt test |
| TEST và lifecycle | TEST còn hiệu lực trả 403 AI_NOT_ALLOWED; gỡ TEST thì QA hoạt động lại. Các lỗi timeout/index/busy/thu hồi quyền được kiểm bằng regression cô lập |
| Qua Nginx thật | Hai câu ALU nối tiếp và một summary trang 7–9 đều thành công qua frontend → backend → retrieval → Kaggle |
| Sau thay container backend | Đọc lại đúng 2 lượt hội thoại và bản summary cũ, giữ nguyên answer và coverage, health qua frontend `ok` |

### Sửa lỗi phát hiện trong nghiệm thu

Hint ban đầu tìm nguồn theo câu nhắc chung của học viên, nên dẫn tới trang 27 liệt kê đề bài. Commit `40e9789` bổ sung tiêu đề, prompt và mô tả công khai của bài PRACTICE vào query truy xuất, giới hạn 8000 ký tự. Giữ việc loại đáp án, hint riêng, rubric và explanation riêng khỏi query/model.

Hai regression test xác nhận lỗi trước sửa; sau sửa toàn bộ AI/OpenAPI đạt **147/147 tests**. Kiểm lại hai hint bằng Qwen thật chuyển sang trang 23 nội dung ALU. Lượt hint cũ trong `live-results.json` được đánh dấu đã thay thế bằng `hint-after.json`; `effective-results.json` chứa 23 ca logic cuối, và `content-review.json` ghi kết luận từng ca.

Không có thay đổi frontend trong lần sửa hint. Bộ 366 test frontend và demo LMS ngày 20/11 vẫn là bằng chứng giao diện của bản ghép. Backend đã build/nạp lại với commit `40e9789`, không thiếu migration, các dịch vụ đang healthy.

### Giới hạn đã ghi nhận

- Hint hiện là hướng dẫn đọc có nguồn, còn chung về cách diễn đạt. Một số lượt giải thích thêm lặp lại ý đã được nguồn hỗ trợ.
- Kiểm summary ở phạm vi trang 7–9; chưa coi là kiểm toàn bộ PDF 28 trang. API hiện cho chọn tối đa 20 trang mỗi công việc.
- Thao tác kiểm lại giao diện Edge ngày 21/11 bị công cụ dừng vì không xác định chắc URL đang mở. Không ghi lượt này thành nghiệm thu UI hint với model thật. Đường HTTP/Nginx/model và hợp đồng UI hint đã có bằng chứng riêng.
- Đây là kiểm tích hợp có phạm vi theo học liệu CPU; không phải benchmark mới hoặc xác nhận chất lượng cho mọi câu hỏi/học liệu.

## 6. Bàn giao để tổng hợp Evidence/W08

Phần Cường gồm code tích hợp, test, demo LMS, QA/citation/memory/hint/summary thật và kiểm lưu trữ đã có kết quả. Gói riêng `.private/w9/w9-lms-ayo-integration-final-evidence.zip` gồm bằng chứng LMS ngày 20/11 và kết quả model thật ngày 21/11, kèm manifest/receipt để kiểm lại. Gói có nội dung học liệu và phản hồi, chỉ chuyển riêng.

Dương tổng hợp kết quả hai phần vào `Evidence/W08/` theo phân công, cập nhật số liệu/manifest của bản cuối và ghi các giới hạn ở trên. Khi chuẩn bị nộp, đối chiếu checklist E01–E10 với phạm vi API, test tự động, demo trình duyệt và các trường hợp chưa có ảnh UI model thật; không ghi các phạm vi khác nhau thành cùng một lượt kiểm.
