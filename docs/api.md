# Hợp đồng API học liệu W2 — phần B

### Quản lý khóa học và xóa lớp (10/10/2026)

- Tạo khóa học chỉ tạo khóa, thành viên chủ sở hữu và chính sách; không tự sinh lớp. Các lớp đã có được giữ nguyên.
- Trang quản lý khóa học đổi trạng thái qua trường Trạng thái và nút Lưu thay đổi, gửi `PATCH /api/courses/{course_id}/`; không có nút xuất bản riêng ở đầu trang. Tab Học liệu được bỏ khỏi trang giáo viên; học liệu theo buổi được quản lý trong chi tiết buổi học.
- `DELETE /api/courses/{course_id}/classrooms/{classroom_id}/`: chỉ chủ khóa được xóa, trả `204`. Dialog chỉnh sửa lớp có nút Xóa lớp học và bước xác nhận.
- Migration `courses.0010_classroom_removed_at` thêm xóa mềm lớp. Trong cùng giao dịch, xóa lớp gỡ các buổi học và học liệu của lớp, hủy job đang chờ, chuyển ghi danh sang WITHDRAWN và hủy yêu cầu tham gia PENDING. Mã lớp, bảng tin, buổi học và tài liệu của lớp không còn truy cập được. Lớp khác và học liệu chung khóa không bị gỡ; dữ liệu lịch sử và file được giữ.

Cập nhật 09/10/2026. Hợp đồng phục vụ tích hợp A/B. Upload/list/status/retry/thay phiên bản/gỡ/extraction đã có triển khai phần B và kiểm thử với model khóa học riêng cho test; đã tích hợp trong cấu hình config.settings.w2 với model Course và đăng nhập nguyên bản của A. Nhóm đã thống nhất Django/DRF + JWT Bearer. Phần B sử dụng SimpleJWT để kiểm tra access token; User UUID, Course/CourseMember và JWT dùng nguyên bản nhánh A 0a0d63e. Quyền được kiểm tra bằng apps.courses.permissions.can_manage_course/can_view_course.

## Quy ước chung

- Runtime IDs là UUID. Nhãn KTCTMLN/CNXHKH là subject_code, không thay course_id.
- API dùng `Authorization: Bearer <access_token>`; không xác thực bằng session cookie hoặc Basic. A quản lý đăng nhập, cấp/refresh token và đăng xuất; B kiểm tra JWT và quyền khóa học hiện hành.
- `apps.courses.permissions.can_manage_course(user, course)` kiểm tra giáo viên với membership OWNER/ACTIVE; `can_view_course(user, course)` kiểm tra quyền đọc hiện hành. Học viên cần STUDENT/ACTIVE và khóa học PUBLISHED. Admin không mặc định được đọc mọi nội dung riêng.
- Dữ liệu trả không có original_storage_key, đường dẫn máy, stack trace hoặc URL clean file public.
- Timestamp UTC ISO-8601; UI hiển thị UTC+7. Chuẩn hóa lỗi thành `{error: {code, message}, request_id}`.
- Idempotency-Key gửi cho upload/retry/thay bản; lưu theo chủ thể/endpoint/phạm vi và hash payload. Lặp cùng thao tác trả kết quả đã có; khóa cũ payload khác trả 409. Backend phải chống trùng document/version/job bằng transaction và ràng buộc.

## Hợp đồng JWT với A

Dùng `rest_framework_simplejwt.authentication.JWTAuthentication`. Frontend gửi access token bằng header `Authorization: Bearer <access_token>` cho mỗi request API, kể cả upload multipart. Không gửi refresh token thay access token; không đưa token vào URL, log hoặc tài liệu bàn giao.

A đã có `POST /api/users/login/`, `POST /api/users/token/refresh/`, `GET /api/users/session/` và `POST /api/users/logout/`. Login trả access token và đặt refresh token trong cookie HttpOnly; frontend A giữ access token trong bộ nhớ, gửi Bearer cho API và tự refresh một lần khi nhận 401. B dùng lại API client này, không tự lưu refresh token hay tạo endpoint auth khác.

Cookie refresh thuộc đường dẫn `/api/users/`; riêng cookie đó không xác thực API tài liệu. API tài liệu không yêu cầu X-CSRFToken. Giữ nguyên cookie/refresh/session và CSRF middleware của A. Login/refresh/logout, thời hạn và blacklist giữ nguyên nhánh A; không thay cơ chế của A bằng đề xuất token trước đó.

Cấu hình tích hợp B tại `config.settings.w2` và `config.urls`, dùng URL chung sau khi gộp theo yêu cầu. User/Course, permissions, JWT, API client và trang chính giữ nguyên; route học liệu nằm trong config/urls.py và apps/documents/api/urls.py.


Kiểm thử phần B dùng JWT thật qua HTTP: token hợp lệ, thiếu/sai/hết hạn token, refresh token gửi nhầm, user bị khóa, session-only/Basic bị từ chối, upload multipart và quyền khóa học bị thu hồi. Không dùng force_authenticate để bỏ qua JWT. Đối chiếu [SimpleJWT — Getting started](https://django-rest-framework-simplejwt.readthedocs.io/en/stable/getting_started.html).

## Endpoint

| Method/path | Quyền | Input | Output |
|---|---|---|---|
| POST /api/courses/{course_id}/documents/ | Giáo viên phụ trách | multipart file/title; Idempotency-Key | 202 document_id/version_id/job_id/extraction_status=QUEUED/rag_ready=false sau lưu bền vững; không chờ parser |
| GET /api/courses/{course_id}/documents/ | Người có quyền đọc | pagination | Metadata học liệu được công bố; giáo viên phụ trách thấy draft/phần quản lý theo quyền |
| GET /api/documents/{document_id}/status/ | Người có quyền xem | version_id tùy chọn, phải thuộc document | extraction_status, pipeline_status, job status, extracted_at/indexed_at, error_code an toàn; không source text |
| POST /api/documents/{document_id}/retry/ | Giáo viên phụ trách | version_id, Idempotency-Key | 202 job_id; retry phiên bản FAILED hoặc EXTRACTED/READY thiếu bản xem bảo vệ; không tạo version mới |
| POST /api/documents/{document_id}/versions/ | Giáo viên phụ trách | multipart file; Idempotency-Key | 202 phiên bản mới; giữ policy, không ghi đè bản cũ |
| DELETE /api/documents/{document_id}/ | Giáo viên phụ trách | none | 204 soft remove; nguồn/job muộn không phục hồi |
| GET /api/documents/{document_id}/extraction/ | Giáo viên phụ trách | version_id | 200 schema extraction 1.0 khi đã xong; không dùng làm API học viên tải sạch |
| PATCH /api/documents/{document_id}/publication/ | Giáo viên phụ trách | is_published (boolean), version_id khi công bố | 200 metadata; chỉ công bố version cùng học liệu đã EXTRACTED/READY và có watermark READY; thu hồi công bố xóa published_version |
| GET /api/documents/{document_id}/view/ | Người có quyền đọc | none | PDF inline: derivative có watermark khi PROTECTED; bản gốc sạch khi PUBLIC_DOWNLOAD; học viên chỉ đọc phiên bản đang công bố |
| PATCH /api/documents/{document_id}/policy/ | Giáo viên phụ trách | material_policy=PROTECTED/PUBLIC_DOWNLOAD, policy_revision (integer) hiện hành | 200 metadata; tăng revision khi đổi policy; revision cũ trả 409 |
| GET /api/documents/{document_id}/download/ | Giáo viên phụ trách; học viên có quyền đọc khi PUBLIC_DOWNLOAD | version_id tùy chọn cho giáo viên | Giáo viên tải bản gốc ngay sau upload, mặc định phiên bản mới nhất; học viên chỉ tải bản đang công bố khi được cho phép |

## Trạng thái và lỗi

extraction_status: NOT_STARTED/QUEUED/PROCESSING/EXTRACTED/FAILED; pipeline_status của version: QUEUED/PROCESSING/EXTRACTED/READY/FAILED/REMOVED. EXTRACTED không đủ để đặt rag_ready=true. Bản gỡ/mất quyền không trả nội dung extraction/source qua link cũ.

| HTTP | Tình huống |
|---|---|
| 400 | PDF hỏng/mã hóa, đầu vào thiếu hoặc vượt giới hạn trang. PDF quét bị worker từ chối với OCR_REQUIRED sau khi nhận job; W2 không OCR |
| 401 | Thiếu, sai hoặc hết hạn access token; tài khoản bị khóa; API yêu cầu Bearer JWT. |
| 403/404 | Sai quyền/phạm vi theo quy ước chống lộ sự tồn tại do A/B chốt |
| 409 | Idempotency conflict, version/state không cho retry hoặc kết quả chưa sẵn sàng |
| 413 | File vượt 20 MiB |
| 415 | File thực không thuộc định dạng W2 hỗ trợ |

Lỗi trước lưu/queue từ chối request; lỗi extraction sau 202 cập nhật job/status, không đổi response trước đó thành thành công xử lý. Mã pipeline gồm INVALID_PDF, ENCRYPTED_PDF, OCR_REQUIRED, TEXT_LAYER_REQUIRED, PAGE_LIMIT, SIZE_LIMIT, INCOMPLETE_CONVERSION, PAGE_MAPPING_ERROR, CONVERSION_FAILED, SOURCE_CHANGED, WATERMARK_FAILED, TIMEOUT, WORKER_INTERRUPTED. Thông điệp lỗi không chứa nội dung/file path nhạy cảm.

## Schema extraction 1.0

- course_id/document_id/version_id: UUID runtime hoặc UUID fixture offline ghi rõ mục đích; không là nhãn môn.
- subject_code: nhãn dataset tùy chọn; checksum_sha256: hash file gốc.
- parser: name=docling, version đã cài, ocr_enabled=false, table_structure_enabled=false trong B1.
- pages: đủ số trang vật lý, page_number 1-based; text/status/warnings. Trang trống được giữ. Ảnh không được OCR có cảnh báo; không tuyên bố đã hiểu mọi hình/bảng.
- extraction_status=EXTRACTED, rag_ready=false, indexed_at=null trong W2 standalone.

Kiểm tra lại quyền/policy/version trước trả nội dung. Source/license corpus là khai báo, chưa thay thế bằng chứng cho phép công bố. Không đưa PDF hoặc extraction nội bộ lên dịch vụ ngoài để xử lý.

## Tích hợp tham gia lớp ngày 09/10/2026

Theo nhánh A 0a0d63e, giáo viên tạo lớp và chọn yêu cầu duyệt; học viên tham gia qua POST `/api/courses/join/` với `class_code`. POST `/members/` không còn được hỗ trợ. Enrollment hợp lệ đồng bộ CourseMember ACTIVE; chỉ đọc học liệu khi quyền khóa hiện hành cho phép và học liệu đã công bố. Rút một lớp không mất quyền khóa nếu còn enrollment hiệu lực ở lớp khác; rút lớp cuối hoặc thu hồi cả khóa chặn metadata/status. Học liệu của B vẫn thuộc Course, chưa có phân quyền học liệu riêng từng Classroom.

## Quy tắc bản xem và công bố đã triển khai

`published_version` dành bản xem, tách `active_version` dành RAG. Thay PDF giữ phiên bản đang công bố; giáo viên chủ động công bố bản mới khi xử lý xong. PDF mới mặc định draft/PROTECTED. Worker tạo derivative có watermark trên từng trang, giữ nguyên gốc sạch và extraction; không tự công bố. Bản EXTRACTED cũ thiếu watermark có thể gửi retry để tạo lại bản xem.

PUBLIC_DOWNLOAD chỉ mở tải sạch cho người có quyền khóa, không tạo link truy cập vô danh. View/download kiểm tra quyền, trạng thái, policy và checksum trước trả bytes; thiếu/hỏng bản xem bảo vệ trả lỗi 503, không fallback gốc sạch. Header `Cache-Control: private, no-store`, `X-Document-Version`, `X-Policy-Revision`; không có URL storage công khai. PROTECTED download trả 403 cho học viên. Giáo viên phụ trách luôn tải được nguồn sạch, kể cả đang xử lý; quyền truy cập và checksum vẫn được kiểm tra. Đổi lại bảo vệ chặn yêu cầu tải sạch mới của học viên.

Frontend nhận PDF qua client JWT thành Blob, kiểm tra trạng thái trước hiển thị, kiểm tra lại mỗi 2 giây khi viewer mở và thu hồi URL Blob khi đóng/rời trang. Bản xem PROTECTED được tạo trong bộ nhớ từ nguồn đã kiểm tra checksum, với watermark là email của người đang xem, mã học liệu, phiên bản và trang PDF. Tài khoản cũ chưa có email dùng tên tài khoản. Không lưu bản cá nhân lên ổ đĩa; bản gốc và extraction giữ nguyên. Đây là biện pháp hạn chế chia sẻ: không ngăn tuyệt đối chụp màn hình, lưu derivative hoặc thu hồi bytes đã tải hợp lệ.


### Cập nhật chính sách riêng từng lớp (09/10/2026)

`PATCH /api/courses/{course_id}/classrooms/{classroom_id}/` nhận `name`, `visibility` (`PUBLIC` hoặc `PRIVATE`), `require_approval` và `is_join_enabled`. Các trường được kiểm tra và lưu trong cùng giao dịch, chỉ tác động lớp được chỉ định. Chỉ giáo viên sở hữu khóa học được sửa. `require_approval` của lớp quyết định lượt tham gia mới có cần xét duyệt; đóng đăng ký không thu hồi học viên đã tham gia. Mức hiển thị không tự cấp quyền đọc học liệu; luồng tham gia hiện tại vẫn sử dụng mã lớp.

Lớp mới mặc định riêng tư, không yêu cầu xét duyệt và mở đăng ký. Migration `courses.0004_classroom_policy` sao chép mức hiển thị và xét duyệt của khóa học sang từng lớp hiện có để giữ hành vi trước khi cập nhật. Các lần sửa sau đó độc lập giữa các lớp. Endpoint `access-policy` được giữ để tương thích, nhưng không còn quyết định xét duyệt của lớp.


### Không gian lớp học và học liệu theo buổi (09/10/2026)

- `GET /api/courses/{course_id}/classrooms/{classroom_id}/sessions/`: danh sách buổi học có phân trang; chỉ chủ khóa học hoặc học viên ghi danh còn hiệu lực trong đúng lớp được đọc.
- `POST` cùng đường dẫn nhận `title` tùy chọn (mặc định chuỗi trống), tạo một `ClassroomSession` có thứ tự trong lớp. Nút Thêm mới trong tab Buổi học tạo ngay một thẻ trống; giao diện hiển thị Buổi học chưa đặt tên và cho phép mở thẻ.
- Học liệu có `session_id` tùy chọn. Upload gửi `session_id` trong multipart; danh sách lọc bằng `?session_id=...`. Cả API đọc trực tiếp và danh sách đều kiểm tra quyền của lớp. Không thể gắn tài liệu vào buổi học thuộc khóa khác.
- `?scope=course` chỉ trả học liệu chung (`session_id=null`). Dữ liệu cũ được giữ nguyên ở cấp khóa học. `enrolled_count` trong Classroom đếm ghi danh ACTIVE/COMPLETED.

Giao diện giáo viên có mục Lớp học trên sidebar, tìm kiếm, lọc khóa học và tên khóa học trên mỗi thẻ. Tên lớp ở tab lớp học của khóa cũng mở cùng không gian lớp. Navbar dưới banner theo thứ tự Bảng tin, Buổi học, Học viên, Kết quả; mặc định Bảng tin. Banner có nút Chỉnh sửa lớp học. Bảng tin có nút Thêm mới, ô nhập và đăng thông báo; Kết quả mới có khung giao diện. Trợ lý AI chỉ xuất hiện trong buổi học đã mở và báo chưa kết nối; không có kết quả hay câu trả lời AI giả lập.

### Bảng tin theo lớp (09/10/2026)

- `GET /api/courses/{course_id}/classrooms/{classroom_id}/announcements/`: phân trang, thông báo mới nhất trước; chỉ chủ khóa học hoặc học viên ghi danh còn hiệu lực trong đúng lớp.
- `POST` cùng đường dẫn: chủ khóa học gửi `content` (1–5000 ký tự sau khi loại khoảng trắng đầu/cuối). Lưu người đăng và thời điểm đăng; trả `201` với `id`, `classroom_id`, `author_name`, `content`, `created_at`.
- Không chia sẻ bảng tin giữa các lớp. UI giữ bản nháp khi lỗi, khóa thao tác đăng/tạo buổi học đang xử lý. Không gửi HTML để hiển thị nội dung thông báo.
- Migration `courses.0006_alter_classroomsession_title_classroomannouncement` bổ sung bảng thông báo và cho phép tên buổi học trống; giữ nguyên các buổi học và học liệu hiện có.

### Ảnh và link trong thông báo (09/10/2026)

- POST thông báo nhận `link` tùy chọn (HTTP/HTTPS, tối đa 2000 ký tự), `image` tùy chọn qua multipart. Nội dung thông báo vẫn bắt buộc.
- Mỗi thông báo hỗ trợ một ảnh và một link. Ảnh JPG/PNG/WebP tối đa 5 MiB, 20 triệu pixel; máy chủ kiểm tra nội dung, chuẩn hóa thành PNG và lưu ở `.private/announcements` (có thể cấu hình `ANNOUNCEMENTS_STORAGE_ROOT`).
- Kết quả GET/POST có `link` và `has_image`. `GET /api/courses/{course_id}/classrooms/{classroom_id}/announcements/{announcement_id}/image/` trả ảnh PNG với quyền đúng lớp, JWT và `private, no-store`. Endpoint ảnh chỉ hỗ trợ đọc.
- Migration `courses.0007_classroomannouncement_image_and_more` bổ sung các trường ảnh/link, giữ nguyên thông báo cũ. UI có xem trước và bỏ ảnh/link, giữ bản nháp khi đăng thất bại.

### Chi tiết buổi học (09/10/2026)

- `PATCH /api/courses/{course_id}/classrooms/{classroom_id}/sessions/{session_id}/` nhận `title`, tối đa 255 ký tự, chủ khóa học được sửa tên đúng buổi học trong lớp.
- Bản xem PDF của giáo viên hỗ trợ `GET /api/documents/{document_id}/view/?version_id={version_id}` để xem chính xác phiên bản đang chuẩn bị công bố. Học viên vẫn chỉ xem bản đã công bố; tham số không mở quyền đọc bản nháp và tải xuống giữ nguyên chính sách cũ.
- Trang buổi học là không gian riêng: sidebar xanh lá, chọn học liệu, xem PDF, đổi tên, AI và công bố học liệu đang chọn. Video/Bài tập hiện là khu vực chờ triển khai.
- Kết quả trích xuất có khung cuộn cao 360 px, gắn đúng học liệu đang chọn; trạng thái và nút kiểm tra cách nhau 24 px.

### Bộ xem PDF vừa trang và thu phóng (09/10/2026)

Trình xem dùng PDF.js với worker đóng gói cùng frontend để hiển thị một trang mỗi lần. Mặc định tự khớp theo cả chiều rộng và chiều cao khung; nút Mặc định khôi phục cách khớp này. Hai nút thu nhỏ/phóng to có thanh trượt ở giữa, hỗ trợ điều khiển bằng bàn phím; có nút trang trước/sau. Khi phóng lớn, khung cuộn riêng. Nguồn vẫn là blob PDF từ API JWT và watermark/chính sách hiện có, kiểm tra quyền định kỳ giữ nguyên.


### Đổi tên học liệu (10/10/2026)

`PATCH /api/documents/{document_id}/` với JSON `{"title":"Tên học liệu"}`. Chỉ người có quyền quản lý khóa/buổi học được phép; giữ nguyên PDF, phiên bản, chính sách và công bố. Trả 200 gồm document_id/title; tiêu đề được trim, dài 1–255 ký tự; trường khác hoặc dữ liệu không hợp lệ trả 400. Không có quyền hoặc tài liệu đã gỡ trả 404.


### Hoàn tất tạo buổi học (10/10/2026)

Session trả thêm `is_draft` (mặc định true). POST tạo buổi học mới vẫn nhận title tùy chọn và luôn tạo bản nháp. Chủ khóa gửi `PATCH /api/courses/{course_id}/classrooms/{classroom_id}/sessions/{session_id}/` với `{"is_draft":false}` để hoàn tất. Có thể gửi lại an toàn; không hỗ trợ chuyển ngược thành bản nháp. Không tự công bố PDF hay thay đổi quyền đọc PDF; các thao tác publication vẫn riêng. Migration0008 bổ sung trường lưu trạng thái; các buổi học cũ chưa có trạng thái cũng bắt đầu là bản nháp.

### Xóa buổi học (10/10/2026)

`DELETE /api/courses/{course_id}/classrooms/{classroom_id}/sessions/{session_id}/` dành cho chủ khóa học, đúng lớp và buổi học; thành công trả 204. Xóa mềm bằng `removed_at`, gỡ toàn bộ học liệu bên trong, thu hồi công bố và hủy tác vụ trích xuất đang chờ/chạy. Bản ghi và tệp gốc được giữ nội bộ. Buổi học đã xóa không còn trong GET danh sách; sửa buổi học hoặc truy cập học liệu đã gỡ trả 404. Migration `courses.0009_classroomsession_removed_at` bổ sung trường xóa mềm.

### Thành viên lớp dành cho học viên (10/10/2026)

`GET /api/courses/{course_id}/classrooms/{classroom_id}/people/` trả hai danh sách `owners` và `students`, mỗi người chỉ có `id` và `name`. Chủ khóa học hoặc học viên còn quyền truy cập đúng lớp được xem. Danh sách học viên gồm ghi danh ACTIVE/COMPLETED có quyền khóa học còn hiệu lực; không trả email, điểm số hay tiến độ. Giao diện đặt chủ lớp trong phần Giáo viên phụ trách phía trên, tách khỏi học viên. Tab Kết quả dành cho kết quả bài làm trong buổi học và hiện chỉ có lời dẫn chờ triển khai.

### Công cụ PDF trong phiên prototype (10/10/2026)

Giáo viên và học viên có thanh công cụ theo thứ tự Con trỏ, Bút viết tay, Highlight, Tẩy, Text, Undo, Xóa toàn bộ, Toàn màn hình, Ghi chú. Nét vẽ/text gắn theo trang với tọa độ chuẩn hóa để giữ vị trí khi thu phóng. Xóa toàn bộ có xác nhận và chỉ xóa nét vẽ/text trên các trang, giữ sổ ghi chú riêng.

Dưới PDF có hàng “Nội dung này có hữu ích không?” với like/unlike (chọn một hoặc bỏ chọn) và báo cáo bài học. Báo cáo mở dialog Lý do (bắt buộc, tối đa 300 ký tự), Ý kiến của bạn (tùy chọn, tối đa 3000 ký tự), Gửi/Hủy. Dữ liệu `feedback` tùy chọn trong cùng payload gồm `vote` (`like/dislike/none`) và `report` (`reason/opinion`); chỉ lưu trong bộ nhớ prototype như ghi chú, chưa có luồng xử lý báo cáo cho quản trị viên. Undo nét vẽ không hoàn tác đánh giá hoặc báo cáo.

`GET/PUT /api/documents/{document_id}/study-notes/?version_id={version_id}` đọc/thay thế `{items, notes, scope}` riêng cho tài khoản đang đăng nhập và đúng phiên bản PDF được phép xem. `items` hỗ trợ `pen/highlight` với các điểm `[x,y]` trong khoảng 0–1, hoặc `text` với `x/y/text`; mỗi mục có `id` và `page`. Quyền truy cập tài liệu và lớp được kiểm tra lại mỗi yêu cầu. Dữ liệu chỉ nằm trong bộ nhớ backend, không có migration hay ghi database/tệp/localStorage. Thoát/vào lại bài học hoặc tải lại trang vẫn đọc lại được trong cùng phiên backend; tắt/khởi động lại backend Docker reset toàn bộ ghi chú prototype. Tải lại mã backend trong chế độ phát triển cũng reset bộ nhớ này. `scope` được cấp khi GET và gửi nguyên khi PUT; ghi từ phiên Docker cũ hoặc tài khoản khác trả 409, tránh khôi phục nhầm dữ liệu sau khi reset.
