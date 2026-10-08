# Hợp đồng API học liệu W2 — phần B

Ngày 07/10/2026. Hợp đồng phục vụ tích hợp A/B. Upload/list/status/retry/thay phiên bản/gỡ/extraction đã có triển khai phần B và kiểm thử với model khóa học riêng cho test; đã tích hợp trong cấu hình config.settings.w2 với model Course và đăng nhập nguyên bản của A. Nhóm đã thống nhất Django/DRF + JWT Bearer. Phần B sử dụng SimpleJWT để kiểm tra access token; User UUID, Course/CourseMember và JWT dùng nguyên bản nhánh A b8b03df. Quyền được kiểm tra bằng apps.courses.permissions.can_manage_course/can_view_course.

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
| POST /api/documents/{document_id}/retry/ | Giáo viên phụ trách | version_id, Idempotency-Key | 202 job_id; chỉ retry phiên bản FAILED, không tạo version mới |
| POST /api/documents/{document_id}/versions/ | Giáo viên phụ trách | multipart file; Idempotency-Key | 202 phiên bản mới; giữ policy, không ghi đè bản cũ |
| DELETE /api/documents/{document_id}/ | Giáo viên phụ trách | none | 204 soft remove; nguồn/job muộn không phục hồi |
| GET /api/documents/{document_id}/extraction/ | Giáo viên phụ trách | version_id | 200 schema extraction 1.0 khi đã xong; không dùng làm API học viên tải sạch |
| GET /api/documents/{document_id}/view/ | Người có quyền đọc | phiên bản được phép | Nếu viewer đã thực hiện: derivative watermark hoặc bản sạch theo policy; chưa hoàn thiện thì không expose original |
| PATCH /api/documents/{document_id}/policy/ | Giáo viên phụ trách | material_policy=PROTECTED/PUBLIC_DOWNLOAD | Nếu đã thực hiện: policy mới, tăng revision, vô hiệu cache/link vượt policy |
| GET /api/documents/{document_id}/download/ | Người có quyền đọc, PUBLIC_DOWNLOAD | none | File sạch qua backend kiểm tra quyền; PROTECTED chặn tải sạch |

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

Lỗi trước lưu/queue từ chối request; lỗi extraction sau 202 cập nhật job/status, không đổi response trước đó thành thành công xử lý. Mã pipeline gồm INVALID_PDF, ENCRYPTED_PDF, OCR_REQUIRED, TEXT_LAYER_REQUIRED, PAGE_LIMIT, SIZE_LIMIT, INCOMPLETE_CONVERSION, PAGE_MAPPING_ERROR, CONVERSION_FAILED, SOURCE_CHANGED, TIMEOUT, WORKER_INTERRUPTED. Thông điệp lỗi không chứa nội dung/file path nhạy cảm.

## Schema extraction 1.0

- course_id/document_id/version_id: UUID runtime hoặc UUID fixture offline ghi rõ mục đích; không là nhãn môn.
- subject_code: nhãn dataset tùy chọn; checksum_sha256: hash file gốc.
- parser: name=docling, version đã cài, ocr_enabled=false, table_structure_enabled=false trong B1.
- pages: đủ số trang vật lý, page_number 1-based; text/status/warnings. Trang trống được giữ. Ảnh không được OCR có cảnh báo; không tuyên bố đã hiểu mọi hình/bảng.
- extraction_status=EXTRACTED, rag_ready=false, indexed_at=null trong W2 standalone.

Kiểm tra lại quyền/policy/version trước trả nội dung. Source/license corpus là khai báo, chưa thay thế bằng chứng cho phép công bố. Không đưa PDF hoặc extraction nội bộ lên dịch vụ ngoài để xử lý.
