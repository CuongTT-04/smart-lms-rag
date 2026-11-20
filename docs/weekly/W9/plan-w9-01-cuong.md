# W9-01 – Kế hoạch triển khai phần LMS của Cường

> Dành cho agent thực thi: đọc bản phân công và SRS trước, dùng skill `executing-plans` nếu có. Làm tuần tự theo các tác vụ bên dưới; mỗi tác vụ có kiểm chứng trước khi chuyển bước. Chỉ dùng subagent nếu phiên thực thi cho phép. Chưa được tự commit, push, merge, gửi tin cho Dương hoặc triển khai lên môi trường dùng thật.

**Ngày lập:** 18/11/2026. **Người phụ trách:** Trần Tuấn Cường. **Mã việc:** W9-01 (chưa phải số Issue GitHub).

**Goal:** Hoàn thiện tiến độ, kết quả lớp, quiz/submission và ghép Ayo để demo LMS xuyên suốt; có code, migration, tests, dữ liệu giả lập và bằng chứng tái lập.

**Căn cứ nghiệm thu:** “Hoàn thiện LMS core: course/lesson/quiz/submission + AI assistant” theo mốc W8 giảng viên giao. Tiêu đề và nội dung yêu cầu là căn cứ khi lịch đề cương bị lệch; các mã W9 trong kế hoạch là định danh hồ sơ đã sử dụng.

**Architecture:** Tái sử dụng courses/assessments/video/documents hiện có; đặt phép tính tiến độ và kết quả lớp trong các service/selectors riêng của `apps.courses`. Chỉ lưu mới dấu xác nhận hoàn thành PDF; video và bài nộp lấy từ dữ liệu nghiệp vụ sẵn có. Frontend gọi API có kiểm quyền, không tự suy ra điểm hoặc phần trăm.

**Tech Stack:** Django/DRF, PostgreSQL, React/Vite/Vitest, Docker Compose. Không thêm thư viện nếu stack hiện tại đáp ứng.

**Spec:** `docs/weekly/W9/phan-cong-w9.md`, `docs/SRS.md`. Kế hoạch này chi tiết hóa phần L1–L4; Dương giữ W9-02 (AI/học liệu).

## 1. Giới hạn và nguyên tắc chạy

- Làm trong checkout phù hợp đang có; kiểm `git status`, nhánh và hướng dẫn repo trước khi sửa. Giữ mọi thay đổi của người dùng; không reset/clean.
- API scope theo course/classroom/session và quyền server. UUID do client gửi không phải bằng chứng có quyền.
- Enrollment liên kết `StudentProfile`; AssessmentAttempt liên kết `User`. Khi join dùng `enrollment.student.user_id`, không so ID profile với ID user.
- PDF dùng phiên bản đang công bố; nháp/gỡ/khác lớp không tính vào tiến độ. Không thay quyền preview của giáo viên bằng quyền học viên.
- PDF đánh dấu đã học là tự xác nhận, không chứng minh hiểu bài. Điểm số tách khỏi hoàn thành hoạt động.
- Dữ liệu tồn tại từ trước phải tương thích; không ghi đè trạng thái WITHDRAWN hoặc mở lại quyền khi tính tiến độ.
- Không sửa AI/gateway, memory, citation, câu hỏi gợi ý, summary hoặc lưu ghi chú PDF của Dương trong tác vụ này. Thay đổi file chung bàn giao dưới dạng hợp đồng/patch rồi tích hợp tuần tự.
- Test dùng database `test_*` riêng. Seed chỉ dùng DB demo riêng. Không flush DB đang chạy, không seed vào tài khoản/học liệu thật.
- Không thay kết quả nghiên cứu W7, không tự train lại. Không xuất secrets, PDF riêng hoặc nội dung chat thật vào log công khai.
- Không gọi thử model mới nếu không có quyền gửi đúng dữ liệu/đích dịch vụ. Có thể hoàn thành test LMS và adapter giao diện bằng mock, nhưng ghi rõ tích hợp AI thật còn chờ nếu chưa kiểm.

## 2. Quy tắc nghiệp vụ và hợp đồng agent phải tuân theo

### 2.1. Tiến độ

Một hoạt động là một PDF đang công bố (theo published version), một video đang công bố hoặc một assessment đang công bố trong buổi học không nháp/không gỡ của lớp.

- PDF hoàn thành khi học viên gửi xác nhận cho đúng published version được phép đọc. Unique `(enrollment, document_version)`; gửi lặp trả cùng trạng thái, không tăng đếm.
- Video hoàn thành theo `VideoProgress.completed_at` và quy tắc checkpoint server hiện có.
- Assessment hoàn thành khi có ít nhất một attempt `SUBMITTED`, kể cả auto-submit hợp lệ hoặc chờ chấm; `DRAFT` không tính. Nhiều lượt cùng bài vẫn là một hoạt động.
- Tổng = số hoàn thành / số hoạt động ×100, làm tròn 2 chữ số để hiển thị; hoàn thành dựa trên count bằng nhau, không dựa trên số đã làm tròn.
- Tổng bằng 0: `percent=0`, `has_activities=false`, `completed_at=null`, UI “Chưa có hoạt động”.
- Lần đầu đạt đủ: ghi completed_at; tính lại vẫn đủ thì giữ mốc cũ. Thêm hoạt động hoặc đổi PDF chưa học: hạ tiến độ, xóa completed_at; học đủ lại tạo mốc mới.
- Với enrollment hợp lệ ACTIVE/COMPLETED: đồng bộ status theo mức hoàn thành hiện tại. WITHDRAWN không tự chuyển trạng thái; API học viên bị chặn. Dữ liệu hoạt động cũ giữ nguyên để đối chiếu.
- Gỡ bài/video/PDF loại khỏi mẫu số và tử số. Đổi phiên bản PDF không kế thừa dấu hoàn thành bản trước.

### 2.2. Điểm và trạng thái bài

Ôn tập chọn điểm cao nhất trong các lượt SUBMITTED đã chấm; bằng điểm chọn lượt nộp mới hơn, thêm ID làm tiêu chí ổn định. Kiểm tra chọn lượt hợp lệ duy nhất. Lượt nháp không tham gia tính điểm.

Tách `submission_status` (NOT_SUBMITTED/DRAFT/SUBMITTED) và `grading_status` (NOT_APPLICABLE/PENDING/GRADED); quá hạn là cờ riêng theo thời gian server. Điểm 0 là điểm đã chấm, không phải thiếu điểm. Có lượt mới chờ chấm nhưng lượt cũ đã chấm: giữ selected score theo chính sách, báo riêng số lượt chờ chấm.

Giáo viên sở hữu thấy điểm nội bộ; học viên chỉ thấy điểm/feedback của lượt được phép công bố theo `assessment_services.attempt_output`. Chọn điểm cao nhất cho học viên trong các lượt đã được phép công bố, không chọn trước rồi vô tình lộ điểm/lượt còn kín. Không trả đáp án đúng/rubric trong API tổng hợp. Nếu tính trung bình: bỏ giá trị null, giữ 0, trả null khi chưa có điểm; ghi rõ trung bình theo tập điểm nhìn thấy của người gọi.

### 2.3. Giao diện service và API mới

Các tên dưới đây là tên triển khai dự kiến, kiểm route hiện có để tránh trùng; nếu đổi phải cập nhật đồng thời tests, frontend và tài liệu hợp đồng.

| File/hàm | Đầu vào và đầu ra |
|---|---|
| `progress_services.py`: `classroom_progress(*, actor, classroom_id)` | Kiểm quyền; trả dict tiến độ của actor theo JSON bên dưới. |
| `progress_services.py`: `mark_document_complete(*, actor, classroom_id, version_id)` | Kiểm quyền/phiên bản trong transaction; upsert idempotent; trả dict progress mới. |
| `progress_services.py`: `refresh_classroom_progress(*, classroom_id)` | Tính từ dữ liệu có thẩm quyền, đồng bộ Enrollment hợp lệ; trả số enrollment đã cập nhật. |
| `classroom_results.py`: `classroom_results(*, actor, classroom_id, filters)` | Kiểm quyền và validate filters; trả dữ liệu report cho view phân trang/serialize theo hợp đồng dưới. |

Route dưới prefix hiện có `/api/courses/{course_id}/classrooms/{classroom_id}/`:

| Method/path | Kết quả |
|---|---|
| GET `progress/` | Tiến độ cá nhân và từng buổi/hoạt động; giáo viên dùng results thay vì giả làm học viên |
| POST `progress/documents/{version_id}/complete/` | Chỉ nhận body rỗng; server xác định actor, phiên bản và trạng thái; trả progress mới |
| GET `results/` | Teacher: học viên thuộc lớp, có phân trang; student: duy nhất dòng của mình |

```json
{
  "classroom_id": "uuid",
  "total_activities": 4,
  "completed_activities": 2,
  "percent": 50.0,
  "has_activities": true,
  "completed_at": null,
  "sessions": []
}
```

Mỗi session trả `session_id`, counts và `activities`; mỗi activity có `kind` (PDF/VIDEO/ASSESSMENT), `id`, `version_id` chỉ cho PDF, `completed`. API results dùng pagination chuẩn repo, mỗi row gồm `student_id` (User ID), tên, progress, counts nộp/chờ chấm và assessment cells với trạng thái/điểm đúng quyền. Không trả User model thô. Filter `q`, `submission_status`, `grading_status` phải validate; UI và số tổng hiển thị cùng scope/filter. Học viên không được dùng query student_id để xem người khác.

## 3. Các tác vụ triển khai

### T0. Khóa đầu vào và bàn giao Ayo đang có

**Đọc:** bản phân công, `backend/apps/ai/{services,runtime,remote,policy,conversations}.py`, UI `components/ai/`, `docker-compose.yml`; log kiểm ngày 17/11.
**Tạo:** `docs/weekly/W9/ban-giao-ayo-cho-duong.md`.

- [ ] Ghi nhánh/HEAD, dirty files liên quan, đường dẫn cell thực tế (kiểm file tồn tại, không dùng tên nhớ từ hội thoại nếu chưa xác minh).
- [ ] Mô tả UI → conversations/chat API → retrieval/runtime → Kaggle; liệt kê tên env cần có, không sao chép giá trị bí mật.
- [ ] Ghi lỗi ALU citation, test backend chưa sạch, quyền nháp/thu hồi và phụ thuộc hint; dẫn log riêng có thật.
- [ ] Ghi rõ baseline chỉ có QA/hint và câu hỏi tiếp theo do Dương triển khai; không ghi đã hoàn thành summary/memory review khi chưa chạy.
- [ ] Bàn giao hợp đồng trạng thái bài/lớp và danh sách file ownership theo bản phân công. Kết quả là tài liệu cho người dùng gửi, không tự nhắn cho Dương.

**Xong khi:** agent của Dương biết bắt đầu từ đâu, chạy bằng cấu hình nào và tái hiện lỗi nào mà không cần đọc lịch sử chat.

### T1. Điều tra và sửa kiểm thử LMS hiện tại

**Đọc/sửa:** `backend/tests/common/test_classroom_sessions.py`, test fixtures/response cleanup liên quan; `backend/config/settings/test.py` chỉ đổi nếu xác định đúng nguyên nhân. Phần schema chat thuộc Dương.

- [ ] Chạy riêng `tests.common.test_classroom_sessions`, rồi chạy cùng `apps.users.tests apps.courses.tests tests.common.test_assessments tests.common.test_session_videos` trên DB test trong Docker; lưu log `.txt`.
- [ ] Tái hiện test đầu tiên làm connection đóng; kiểm lifecycle streaming response, `response.close()`, transaction/TestCase, signal request_finished và test order. Ghi nguyên nhân trước khi sửa.
- [ ] Thêm regression cho nguyên nhân tìm được; sửa tối thiểu tại fixture/harness hoặc production nếu lỗi xuất hiện ngoài test. Không bỏ test, không tắt kiểm quyền, không chuyển hết test sang transaction chỉ để né lỗi.
- [ ] Chạy lại riêng và nhóm để xác nhận không làm nhiễm DB connection của test sau. Ghi phần schema failure giao Dương, không báo toàn suite xanh nếu còn failure.

**Xong khi:** lỗi LMS đã xác định và có regression; lỗi ngoài ownership được nêu bằng tên test và log.

### T2. Dữ liệu và phép tính tiến độ

**Tạo:** `backend/apps/courses/progress_models.py`, `progress_services.py`, migration mới bằng makemigrations; `backend/apps/courses/tests/test_learning_progress.py`.
**Sửa:** `backend/apps/courses/models.py` để đăng ký model theo pattern assessment/video hiện tại.

- [ ] Viết fixtures với Enrollment ACTIVE, StudentProfile/User đúng quan hệ, một buổi công bố và PDF/version/video/assessment thật trong DB test.
- [ ] Viết test trước cho unique completion, count/mẫu số, thay PDF, gỡ hoạt động, lớp rỗng, WITHDRAWN, gửi trùng và hai tài khoản. Chạy để thấy failure do chức năng chưa có.
- [ ] Tạo `DocumentCompletion`: enrollment FK, document_version FK, completed_at, unique hai FK; dùng PROTECT/CASCADE có chủ đích theo chính sách lưu giữ hiện hành. Không sao chép VideoProgress/AssessmentAttempt sang bảng completion mới.
- [ ] Triển khai ba hàm progress tại mục 2.3. Transaction khóa enrollment và xác thực lại version đang công bố trước upsert; bảo đảm race không ghi hoàn thành tài liệu sai scope.
- [ ] Gọi refresh sau mark PDF, completion video, submit/expire assessment và mutation công bố/gỡ buổi/bài/video/enrollment. Các điểm publish/replace/remove document do Dương giữ: gửi patch callback `refresh_classroom_progress(classroom_id=...)` để tích hợp tuần tự, test đủ trước chốt.
- [ ] GET progress/results tính từ dữ liệu hiện tại để không hiển thị cache cũ; không ghi DB từ GET. Bổ sung command rebuild progress cho dữ liệu cũ; command không tự chạy vào DB thật khi làm kế hoạch/test.
- [ ] Đọc lại roster/serializers đang lấy Enrollment.progress_percent: bảo đảm refresh ở mutation và backfill không để nơi này hiển thị số cũ. Khi ảnh hưởng nhiều học viên dùng bulk queries, không một truy vấn mỗi cell.
- [ ] Kiểm concurrency PDF gửi hai lần và thu hồi/công bố thay đổi đồng thời bằng TransactionTestCase; kết quả không trùng và không vượt quyền.

Ví dụ assertions bắt buộc trong fixture 4 hoạt động (PDF, video, quiz, tự luận):

```python
self.assertEqual(progress['total_activities'], 4)
self.assertEqual(progress['completed_activities'], 2)  # PDF + quiz đã nộp
self.assertEqual(progress['percent'], 50.0)
self.assertIsNone(progress['completed_at'])
# Gửi lại cùng PDF: count vẫn 2; đổi published version: count còn 1.
# Quiz có điểm 0 hoặc tự luận chờ chấm vẫn là hoạt động đã nộp.
```

**Xong khi:** phép tính, mutation hooks, cache Enrollment và backfill thống nhất; migration không xóa dữ liệu cũ.

### T3. API progress và giao diện đánh dấu đã học

**Tạo:** `backend/apps/courses/api/progress_views.py`, `progress_serializers.py`; `frontend/src/components/learning/LearningProgress.jsx` và `.test.jsx`.
**Sửa:** `backend/apps/courses/api/urls.py`, `frontend/src/services/course.service.js`, `ClassroomRoster.jsx`; patch phối hợp cho `SessionWorkspace.jsx` và `documents/CourseDocuments.jsx` do Dương giữ.
**Test:** `backend/apps/courses/tests/test_progress_api.py`, frontend tests liên quan.

- [ ] Viết API tests: own active student →200; anonymous →401; foreign/missing/withdrawn resource →404 theo pattern repo; actor teacher không được ghi completion giả; body có student_id/percent bị từ chối.
- [ ] Triển khai route/serializer mục 2.3; khai báo OpenAPI và response/error shapes. Không trả dữ liệu của học viên khác.
- [ ] Thêm badge tiến độ ở lớp/buổi và nút “Đánh dấu đã học” trong PDF đang xem đúng version; chỉ enable sau mở tài liệu thành công. Gửi một request, khóa nút khi pending; lỗi không hiển thị completed giả.
- [ ] Sau thành công re-fetch progress, sau chuyển lớp/version reset đúng state; chống response lớp trước ghi đè lớp sau bằng abort/request scope.
- [ ] Test click double, network fail, version thay đổi, reload; accessible label và trạng thái loading/empty/error.

**Xong khi:** giáo viên và học viên nhìn đúng tiến độ thực, gọi trực tiếp API cũng được bảo vệ; không cần Kaggle cho thao tác này.

### T4. Kết quả lớp và số liệu giáo viên

**Tạo:** `backend/apps/courses/classroom_results.py`, `api/classroom_results_views.py`, serializers tương ứng; `backend/apps/courses/tests/test_classroom_results.py`.
**Tạo frontend:** `frontend/src/components/ClassroomResults.jsx`, `.test.jsx`; **sửa** `ClassroomWorkspace.jsx`, `course.service.js`, CSS lớp hiện có.

- [ ] Viết fixtures nhiều lượt ôn tập (4, 8, 0, pending, draft), bài kiểm tra một lượt, điểm chưa công bố và thành viên khác lớp.
- [ ] Test giáo viên thấy best=8; học viên chỉ thấy best trong lượt đã công bố; không có grade hợp lệ trả null; điểm 0 giữ 0; draft không tăng submitted; same user nhiều lượt vẫn đếm một bài.
- [ ] Implement service/API theo mục 2.2–2.3, quyền kiểm trước aggregate. Pagination ổn định theo tên + ID; filter đã validate và tổng không lệch danh sách.
- [ ] Tái sử dụng helper attempt_output để giữ chính sách feedback/đáp án; không gọi dashboard hiện tại như nguồn duy nhất vì dashboard đang dùng lượt nộp mới nhất, khác chính sách điểm cao nhất của bảng lớp. Ghi nhãn rõ “điểm cao nhất” so với “lượt mới nhất”, không tự đổi ý nghĩa dashboard cũ.
- [ ] Thay placeholder bằng bảng + trạng thái rỗng/loading/error, tên/tiến độ/nộp/chờ chấm/điểm, lọc và phân trang. Student view chỉ dòng cá nhân; không dựa vào ẩn cột để bảo vệ dữ liệu.
- [ ] Nếu thêm export toàn lớp: dùng đúng dataset/filter/quyền của API; test workbook với giá trị null/0/tên bắt đầu `=` để không thành công thức ngoài ý muốn. Không bắt buộc thêm exporter mới nếu dashboard từng bài đã đáp ứng phần xuất hiện hành.
- [ ] Query-count regression so 3 và 30 học viên, tránh N×bài queries; không cần benchmark tải lớn ngoài phạm vi.

**Xong khi:** bảng lớp khớp expected data, quyền đúng và có test cả backend/frontend.

### T5. Quiz/submission và nối trợ giúp AI

**Sửa:** `backend/apps/courses/assessment_reports.py`, `api/assessment_views.py` nếu cần; `frontend/src/components/assessments/AssessmentRunner.jsx`.
**Test:** `backend/tests/common/test_assessments.py`, `AssessmentRunner.test.jsx`, `AssessmentDashboard.test.jsx`.

- [ ] Regression question_stats: đáp án `[]`, chuỗi rỗng, thiếu key không tính answered; có lựa chọn hợp lệ thì tính. Dùng `assessment_questions.selected_ids` theo shape hiện hành thay vì chỉ kiểm key tồn tại.
- [ ] Kiểm tạo/công bố, lưu nháp/revision conflict, double submit, deadline/auto-submit, ôn tập nộp lại, TEST một lượt, file hợp lệ/không hợp lệ, giáo viên khác lớp, chấm lại và công bố. Sửa lỗi phát hiện trong phạm vi này với regression.
- [ ] Dùng callback `onRequestAssistance({assessment_id, question_id})` hiện có; quiz gửi đúng câu, TEXT chỉ assessment_id. Loại entry AI cũ luôn báo disconnected hoặc đổi đúng thành gợi ý tĩnh có nhãn rõ. Không sửa thuật toán AI của Dương.
- [ ] Test callback quiz/TEXT, không render AI cho TEST, unavailable/error không mất draft. API legacy nếu đổi phải kiểm callers trước; không xóa endpoint còn được dùng.
- [ ] Gửi Dương acceptance cho policy: bài kiểm tra hiệu lực chặn AI; gỡ/mất quyền không giữ khóa sai; người ngoài không nhận answer key. Agent Cường giữ trạng thái phụ thuộc cho đến khi code Dương tới, không mock rồi tuyên bố policy thật đạt.

**Xong khi:** quiz/submission ổn định và entry AI thống nhất; phần phụ thuộc có trạng thái kiểm thật riêng.

### T6. Dữ liệu demo và bảng kết quả mong đợi

**Tạo:** `backend/apps/courses/management/commands/seed_w9_demo.py`, `backend/apps/courses/tests/test_w9_demo.py`, `docs/weekly/W9/demo-w9-01.md`.

- [ ] Command chỉ chạy khi `W9_DEMO_ENABLED=1` và tên DB bắt đầu `w9_demo_`; từ chối mặc định kể cả người dùng quên tham số. Không in mật khẩu; nhận mật khẩu demo qua env riêng và truyền cho người chạy ngoài Git.
- [ ] Dùng prefix và khóa ổn định để get_or_create, không xóa dữ liệu. Nếu bản ghi cùng khóa khác cấu hình seed, báo conflict thay vì ghi đè. Test gọi hai lần không tăng count.
- [ ] Seed 2 giáo viên, 3 học viên, 2 lớp, buổi nháp/công bố; tài liệu PDF tự tạo không nhạy cảm, video fixture local có checkpoint, quiz practice/TEST và TEXT. Chưa cấu hình index/model không được báo AI READY giả.
- [ ] Dữ liệu kỳ vọng: lớp chính 4 hoạt động áp dụng; S1 PDF+quiz=2/4=50%, quiz graded=0; S2 đủ 4/4=100%, TEXT submitted/pending; S3 không có quyền. Có thêm attempt draft, nhiều lượt practice và kết quả chưa công bố để test UI. Due dates theo anchor timestamp được ghi trong receipt, không hardcode ngày sớm khiến demo lập tức quá hạn.
- [ ] Viết bảng expected counts/điểm theo từng vai trò bằng tay theo seed, test so với API. Demo AI thật dùng học liệu CPU được cấp quyền riêng; seed synthetic không giả làm dữ liệu CPU.

**Xong khi:** máy khác tạo được dữ liệu demo và đối chiếu số liệu mà không dựa vào DB của tác giả.

### T7. Tích hợp Dương, chạy cuối và bàn giao

**Tạo:** `docs/weekly/W9/ket-qua-w9-01.md`; log/raw riêng tại `.private/w9/member-b/`. Dương tổng hợp Evidence/W09 cuối.

- [ ] Ghi commit/patch Dương bàn giao, diff các file chung, kiểm migration dependency và tên API. Không ghi đè SessionWorkspace/CourseDocuments đang được Dương sửa.
- [ ] Chạy test mới từng nhóm, rồi toàn bộ frontend test/build/lint và bộ backend liên quan. Kiểm schema cả endpoint mới và của Dương; remaining failure ghi đúng tên, không đếm thành PASS.
- [ ] Chạy demo trong môi trường riêng: teacher tạo/công bố → student mở PDF/hoàn thành video/nộp quiz+TEXT → teacher chấm/công bố → student reload thấy điểm/progress → restart giữ dữ liệu → thu hồi quyền chặn API/media. Quay/chụp các mốc thực tế.
- [ ] Kiểm AI sau tích hợp theo E05–E07 bản phân công: nguồn nhiều trang, ALU, memory/chuyển chủ đề, hint, summary, gợi ý tiếp theo, indexing chờ và Kaggle ngắt. Nếu chưa nhận code/model thì chỉ phần này chờ, tiếp tục hoàn thiện T0–T6.
- [ ] Gói bàn giao Cường: code/migration/test, hướng dẫn seed/demo, expected table, lệnh chạy và exit/count thực, ảnh/log đã lọc, commit/config hash khi có thật, danh sách findings đã đóng/còn mở. Gửi cho người dùng để chuyển Dương; không tự gửi ra ngoài.
- [ ] Đánh dấu checklist theo bằng chứng, chỉ ghi W9-01 hoàn tất khi phần LMS đạt và tích hợp phụ thuộc đã kiểm; milestone nhóm cần E01–E10 đều đạt.

## 4. Lệnh kiểm chứng

Chạy tại root repo; Docker đang dùng DB thật được bảo vệ bằng settings test của Django, DB tạo ra phải có tiền tố `test_`. Trước khi chạy kiểm tên DB đích và không sử dụng flush. Log mỗi lần vào file mới dưới `.private/w9/member-b/`.

```powershell
docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test backend python manage.py test apps.courses.tests.test_learning_progress apps.courses.tests.test_progress_api apps.courses.tests.test_classroom_results apps.courses.tests.test_w9_demo --noinput
docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test backend python manage.py test apps.users.tests apps.courses.tests tests.common tests.ai tests.documents.test_material_access tests.documents.test_study_annotations --noinput
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py check
git diff --check
```

Trong `frontend/`:

```powershell
npm.cmd test -- --maxWorkers=2
npm.cmd run build
npm.cmd run lint
```

Migration mới: tạo từ models, kiểm SQL và chạy trên DB test/demo trước. Không áp dụng migration vào DB thật hoặc rebuild/restart dịch vụ người dùng chỉ để thử mà chưa chuẩn bị rõ tác động. Nếu môi trường chặn Docker/network, dùng cơ chế cấp quyền công cụ; không coi test không chạy là đạt.

## 5. Trọng điểm review và tiêu chí đóng

| Rủi ro | Tác vụ kiểm |
|---|---|
| Cộng trùng tiến độ, nhầm User/Profile | T2 unique/concurrency/fixtures, T3 API |
| Thay published version vẫn giữ hoàn thành cũ | T2 version mutation + T3 stale UI |
| Thu hồi quyền/gỡ buổi nhưng vẫn đọc/ghi | T2/T3 API regression + T7 demo |
| Điểm chưa công bố hoặc đáp án lọt qua aggregate/export | T4 response/excel + T5 hint callback |
| Test chạy riêng đạt nhưng chạy chung hỏng DB | T1 và T7 full suite |
| File chung hoặc migration bị ghi đè khi ghép | T0 ownership + T7 diff/dependency |

Thứ tự: T0 → T1 → T2 → T3 → T4 → T5 → T6 → T7. T1/T5 có thể do agent độc lập xử lý nếu được phép và không sửa chung file. T2–T4 phụ thuộc nhau, không giao song song khi hợp đồng chưa ổn định.

Mọi tác vụ hiện là kế hoạch, chưa xác nhận triển khai. Kết quả cần có là luồng chạy thật và số liệu đối chiếu được, không chỉ file code hoặc test mock xanh. Việc Dương chưa bàn giao phải được ghi là phụ thuộc chờ, không biến thành yêu cầu Cường tự làm toàn bộ AI.
