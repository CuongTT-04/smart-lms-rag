# Bàn giao W2 của thành viên B và các nội dung cần chốt với A

**Thành viên B:** Trần Tuấn Cường — B22DCVT073. **Ngày cập nhật:** 09/10/2026. Tài liệu tổng hợp phần việc từ 07–10/10; các việc của ngày 09–10 đã được chuẩn bị, không có nghĩa nhóm đã ghi demo hoặc nộp báo cáo tuần. Code A được đối chiếu tại `origin/VuNamDuong_B22DCVT119_W2Tasks`, commit `0a0d63e`.

## Cập nhật tích hợp A/B ngày 09/10/2026

Đã nhận commit A `0a0d63e` (bổ sung lớp học, tham gia bằng mã, duyệt yêu cầu và enrollment), ghép với phần B tại `b7ac61a` trên nhánh `TranTuanCuong_B22DCVT073_W2Tasks`. Không sửa hoặc push nhánh A. Giữ requirements/URL/Vite chung, test B trong `backend/tests` và private storage. Đã đối chiếu 56 file backend User/Course và course service với commit A mới, không chỉnh nội dung các file này; điểm ghép frontend và runtime chung được bổ sung trên nhánh B.

- API cấp thành viên trực tiếp `POST /members/` đã bị A bỏ (405). Fixture và script B chuyển sang `POST /api/courses/join/`; `CourseMember` tiếp tục là căn cứ quyền khóa học và được A đồng bộ từ enrollment.
- Đã kiểm thử chờ duyệt → chưa có quyền, duyệt → có quyền; thu hồi cả khóa → bị chặn. Rút một lớp giữ quyền học liệu nếu còn enrollment ở lớp khác cùng khóa; rút lớp cuối chặn quyền.
- Giáo viên có tab **Học liệu** trong quản lý khóa; học viên có danh sách học liệu trong chi tiết khóa. Không cần mở trang riêng để dùng module B.
- Học liệu vẫn dùng phạm vi Course, nên các lớp của cùng khóa dùng chung học liệu. Đây là hành vi hiện tại, chưa có quyền/tài liệu riêng từng lớp hay model Lesson.
- Đã thêm mô tả Swagger cho API học liệu để tương thích kiểm thử tài liệu API mới của A. Sửa một kỳ vọng test lời chào học viên cho khớp UI đang hiển thị đầy đủ họ tên; không đổi hành vi lời chào.
- Compose đã có `ingestion-worker`, volume `documents_data` dùng chung API/worker và cache Docling. Worker đợi API healthy sau migration rồi mới xử lý. Cấu hình Compose được kiểm tra tĩnh; Docker Desktop engine đang không chạy nên **chưa build/chạy Docker hoặc kiểm chứng PostgreSQL**. Bốn test concurrency dành PostgreSQL bị skip trên SQLite, không tính là đạt.

**Bổ sung phần B đã hoàn thiện:** công bố/thu hồi công bố, viewer PDF có watermark mặc định, policy/tải sạch và UI thay/gỡ. Mô hình RAG chưa triển khai trong W2. **Các việc còn mở của nhóm:** tài khoản/khóa demo cố định, kiểm chứng PostgreSQL/Docker, ghi demo và hai PDF tuần; chốt Lesson/chương, học liệu chung khóa hay riêng lớp và upload khi ARCHIVED. Backend tham gia lớp/quyền của A đủ cho luồng đã kiểm thử; không sửa hoặc push nhánh A.

## 1. Kết quả phần B

| Công việc | Kết quả và bằng chứng | Trạng thái |
|---|---|---|
| Model học liệu, phiên bản và hàng đợi | `KnowledgeDocument`, `DocumentVersion`, `IngestionJob`, `DocumentOperation`; FK dùng User/Course UUID của A; migration riêng B. [ERD](../design/w2-document-erd.md), [API](../api.md). | Đã triển khai |
| Corpus v1 | Kiểm kê 27 PDF/JSON: THMLN 14, KTCTMLN 6, CNXHKH 7; manifest có checksum, trang, nguồn và thông tin quyền sử dụng được khai báo. [Manifest](../../data/data_manifest.csv), [báo cáo](w2-corpus-check.md). Quyền sử dụng chưa được xác minh độc lập. | Đã kiểm kê |
| Parser theo trang | Docling 2.135.0; giữ số trang PDF vật lý bắt đầu từ 1, checksum và định danh khóa/tài liệu/phiên bản. KTCTMLN chương 1: 29 trang; CNXHKH chương 1: 24 trang. [Đối chiếu extraction](w2-extraction-verification.json). | Đã kiểm chứng hai mẫu |
| Upload | JWT Bearer; kiểm tra quyền OWNER/ACTIVE qua hàm A; PDF văn bản tối đa 20 MiB, 100 trang. Lưu riêng, trả 202 rồi mới xử lý nền; idempotency chống lặp khi gửi lại. | Đã triển khai và kiểm thử |
| Worker | Management command riêng; timeout tiến trình con 900 giây; lease/token chống tác vụ cũ chốt kết quả; phát hiện worker gián đoạn; retry giữ cùng phiên bản. | Đã triển khai và kiểm thử |
| Thay và gỡ tài liệu | API thay tạo phiên bản mới, giữ chính sách; gỡ chặn truy cập, hủy job đang chờ/chạy, kết quả muộn không phục hồi nguồn. | Đã triển khai API và UI |
| Công bố, viewer và policy | Giáo viên chọn phiên bản EXTRACTED có watermark READY để công bố; học viên xem bản đang công bố. PROTECTED chặn tải sạch; PUBLIC_DOWNLOAD cho người có quyền khóa xem/tải sạch. Đổi lại bảo vệ chặn yêu cầu mới; thay nguồn giữ bản công bố cũ. | Đã triển khai và kiểm thử |
| Giao diện B | Trang `/documents.html` dùng login và API client A; chọn khóa, upload, trạng thái, lỗi, retry, làm mới danh sách. Giáo viên kiểm tra văn bản theo trang bằng nút **Kiểm tra trích xuất**. Đã gắn vào tab Học liệu của giáo viên và chi tiết khóa học của học viên. | Đã tích hợp trang chính trên nhánh B |
| Kiểm thử quyền | JWT thiếu/sai/hết hạn, tài khoản khóa, giáo viên khác, admin, học viên sai lớp/thu hồi quyền; học viên không được đọc JSON extraction hoặc original. ARCHIVED chặn học viên, giữ quyền quản lý của chủ khóa theo A. | Đã có test tự động |
| Chạy từ DB sạch và tiến trình worker khác | Script tạo SQLite tạm, chạy migration, login/course/membership API thật, upload hai PDF corpus, worker tiến trình riêng; phục hồi job gián đoạn, retry idempotent, PDF cần OCR và thu hồi quyền. [Script](../../scripts/verify_w2_delivery.py), [kết quả](w2-delivery-verification.json). Không ghi vào database demo của nhóm. | Có kiểm chứng local |
| Bàn giao W3 và nội dung báo cáo | Schema extraction, hướng dẫn tái chạy, kịch bản demo và đoạn báo cáo tại các mục dưới. | Đã chuẩn bị |

**Giới hạn W2:** PDF văn bản tối đa 20 MiB/100 trang; chưa OCR hoặc nhận DOCX/PPTX. Upload → worker → extraction và derivative watermark → giáo viên công bố → học viên xem theo quyền/policy đã có API và UI. Không tự công bố sau extraction. `published_version` dành bản xem, tách `active_version` dành RAG. `EXTRACTED` vẫn có `rag_ready=false`, `indexed_at=null`; chưa có chatbot/chunking/embedding. Watermark hạn chế chia sẻ nhưng không ngăn tuyệt đối chụp màn hình hoặc lưu bytes đã nhận hợp lệ.

## 2. Hợp đồng đã tích hợp được với code A

Các mục này là kết quả đối chiếu và kiểm thử, không phải biên bản xác nhận của thành viên A.

| Nội dung | Cách phần B đang sử dụng |
|---|---|
| User và Course | `users.User`, `courses.Course`, `courses.CourseMember`; UUID. Course không có `teacher_id` trực tiếp. |
| Giáo viên phụ trách | User TEACHER đang hoạt động, membership của chính khóa có `role=OWNER`, `status=ACTIVE`. OWNER là quan hệ sở hữu khóa; ACTIVE là trạng thái còn hiệu lực. |
| Quyền | `apps.courses.permissions.can_manage_course` và `can_view_course`. Học viên cần STUDENT/ACTIVE và khóa PUBLISHED. Admin không mặc định đọc học liệu riêng. |
| Xác thực | `POST /api/users/login/` trả access; refresh qua `/api/users/token/refresh/` với cookie HttpOnly. API B nhận `Authorization: Bearer ...`; không xác thực bằng refresh cookie hoặc session. |
| Cấu hình B | `config.settings.w2`, `config.urls` bổ sung storage; route học liệu đã gộp vào config/urls.py theo yêu cầu. API và worker phải dùng cùng database/storage. |
| Frontend | React JavaScript/JSX theo code A; B dùng lại `services/api.js`. Component nhận `courseId` UUID và `canManage`; backend luôn kiểm tra quyền lại. |
| Lỗi | 401 khi token không hợp lệ; 404 khi tài nguyên không khả dụng/sai quyền; 400/415 cho file không hợp lệ; 413 quá dung lượng; 409 xung đột hoặc thao tác chưa được phép. Không lộ storage key/stack trace. |

## 3. Những việc cần chốt chung với A

| Mã | Cần quyết định | Hiện trạng / đề xuất để chốt | Người xử lý tiếp |
|---|---|---|---|
| AB-01 | Học liệu thuộc Course hay Lesson? | W2 FK trực tiếp Course; A chưa có Lesson trong phần tích hợp. Đề xuất giữ Course cho W2, thống nhất Lesson/chương và migration trước khi tổ chức nội dung W3. Không tự thêm FK sang model chưa tồn tại. | A xác định cấu trúc bài học; B cập nhật quan hệ và API sau thống nhất. |
| AB-02 | Công bố học liệu khi nào? | `is_published=False` mặc định, extraction không tự công bố. Đã triển khai giáo viên chủ động công bố sau khi bản xem bảo vệ sẵn sàng; công bố học liệu, Course PUBLISHED và PUBLIC_DOWNLOAD là ba trạng thái riêng. Cần A/B xác nhận trải nghiệm trên môi trường chung. | B đã có công bố/viewer; A phối hợp kiểm tra trên demo chung. |
| AB-03 | ARCHIVED cho giáo viên làm gì? | Quyền A hiện cho OWNER/ACTIVE quản lý/upload cả khóa ARCHIVED; học viên bị chặn. SRS giữ quản lý giáo viên. Nhóm cần xác nhận có cho upload/thay file mới khi lưu trữ hay chỉ đọc/quản lý metadata. B hiện giữ nguyên hành vi A. | A/B thống nhất quy tắc; A quyết định thay permission chung nếu cần. |
| AB-04 | Gắn UI học liệu ở đâu? | Đã gắn `CourseDocuments.jsx` vào tab Học liệu của giáo viên và chi tiết khóa học học viên, dùng `key={course.id}`. Chỉ sửa điểm tích hợp trên nhánh B; nhánh A giữ nguyên. Backend kiểm tra quyền, học viên không có thao tác quản lý. | A/B rà trải nghiệm trên môi trường demo chung. |
| AB-05 | Bộ tài khoản và khóa demo chung | Cần một giáo viên, học viên có quyền, học viên không có quyền và hai khóa KTCTMLN/CNXHKH; học viên tham gia bằng mã lớp/duyệt yêu cầu. Nhãn môn corpus không phải UUID runtime; cần bảng ánh xạ chung. Script kiểm chứng chỉ tạo fixture tạm, không thay bộ seed demo. | A chuẩn bị tài khoản/khóa; B chọn PDF và cùng kiểm tra ánh xạ. |
| AB-06 | Database/migration/môi trường chung | Local đã kiểm chứng SQLite. PostgreSQL, chạy đồng thời nhiều worker và cấu hình deploy chưa được kiểm chứng. Chốt môi trường, biến DB/storage, thứ tự migration và người giữ worker; không phục vụ private storage qua web server. | A chuẩn bị môi trường chung; B chạy migration/test/worker B trên đó. |
| AB-07 | Bản xem, watermark và policy | B phụ trách: mặc định bảo vệ; người có quyền chỉ xem derivative watermark; giáo viên chuyển PUBLIC_DOWNLOAD mới có bản sạch, đổi lại bảo vệ chặn yêu cầu mới. Đã có viewer và watermark OHAYO/mã học liệu/phiên bản/trang; thay file giữ published_version cũ đến khi giáo viên công bố bản mới. Không dùng `active_version` dành RAG để kích hoạt bản xem trong W2. | B đã triển khai và kiểm thử; A/B xác nhận trải nghiệm và nội dung watermark khi demo. |
| AB-08 | Ghi demo và nộp tuần | Chạy kịch bản mục 5 cùng môi trường thật. Nhóm chỉ định một đại diện, tạo hai PDF W2 mới, giữ bản W1, kiểm tra quyền share trước submit. Chưa ghi video hoặc nộp Drive ở lần làm này. | A/B phối hợp; đại diện nhóm submit. |

**A còn thiếu gì để bàn giao?** Backend User/Course/Classroom/Enrollment/membership/JWT của A đã đủ cho upload và extraction W2; không còn blocker model/xác thực trong luồng đã kiểm thử. UI đã được ghép trên nhánh B. Còn cần A chuẩn bị seed demo chung và phối hợp kiểm chứng môi trường. Các quyết định AB-01 đến AB-08 chưa có xác nhận chung trong tài liệu này. Không ghi viewer/watermark/công bố học liệu là phần A chưa hoàn thành.

## 4. Kiểm thử và cách tái chạy

Hướng dẫn cài đặt/API/worker/frontend: [backend/README.md](../../backend/README.md). Dùng `backend/requirements.txt` chung cho A+B và kiểm thử. Các file requirements phụ đã được gộp theo yêu cầu; thay đổi chỉ ở nhánh hiện tại, không sửa nhánh A.

```powershell
# Từ root repo, sau khi cài venv:
.\.venv\Scripts\python.exe backend/manage.py migrate --settings=config.settings.w2
.\.venv\Scripts\python.exe backend/manage.py runserver --settings=config.settings.w2
# Terminal thứ hai, cùng database/storage:
.\.venv\Scripts\python.exe backend/manage.py run_ingestion_worker --settings=config.settings.w2
# Kiểm chứng độc lập: chỉ dùng DB/storage tạm rồi tự dọn
.\.venv\Scripts\python.exe scripts/verify_w2_delivery.py
```

Frontend: chạy `npm ci`, `npm run dev` tại `frontend`, mở `/documents.html`; build bằng `npm run build`. Cấu hình chung `vite.config.js` build cả `index.html` và `documents.html` vào `dist/w2`. A nhận component và service, không cần chép logic JWT mới.

| Bộ kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Backend tích hợp A+B và kiểm thử chung | 210 test: 206 đạt, 4 test concurrency PostgreSQL được bỏ qua trên SQLite | [Log](w2-final-integration-tests.txt) |
| Upload/worker B | 27 test | [Log](w2-final-worker-tests.txt) |
| Parser/corpus/CLI | 19 test | [Log](w2-final-parser-tests.txt) |
| Frontend A+B | 181 test, gồm kiểm thử gắn học liệu vào hai trang chính | [Log](w2-final-frontend-tests.txt) |
| Lint/build | Kiểm tra bằng cấu hình chung `vite.config.js` cho cả hai trang | [Log](w2-final-frontend-build.txt) |

Các bộ có phần trùng; không cộng thành tổng test duy nhất. Test giả lập timeout/lỗi phục vụ kiểm tra nhánh xử lý; script delivery mới kiểm tra Docling thật trên corpus với worker riêng. Thời gian upload trong report đo nhận/lưu file local bằng Django test client, không bao gồm truyền mạng và không phải SLA production. Thời gian worker gồm khởi động tiến trình/parser. Đã render/kiểm tra watermark trên PDF dọc, ngang và xoay trang; file gốc giữ nguyên hash. Chưa ghi demo trình duyệt hoặc kiểm chứng PostgreSQL/T4. Rà soát đã sửa truy vấn khóa với FK nullable để tránh lỗi PostgreSQL; chưa coi đó là kiểm chứng runtime PostgreSQL.

| Ca kiểm thử | Kỳ vọng | Kết quả thực tế |
|---|---|---|
| Upload hai PDF text bằng chủ khóa | 202, job bền vững; không chạy parser trong request | Đạt; tiếp nhận local 0,141 giây và 0,110 giây |
| Worker tiến trình riêng xử lý hai môn | EXTRACTED, đúng checksum/UUID và đủ trang vật lý | Đạt; 29 và 24 trang; RAG chưa sẵn sàng |
| Worker bị gián đoạn | Job hết lease thành WORKER_INTERRUPTED; API retry tạo job mới trên cùng version | Đạt; gửi lại cùng key nhận cùng job; bản text xử lý thành công |
| PDF ảnh cần OCR | Có lỗi rõ, không đánh dấu extraction thành công | FAILED / OCR_REQUIRED |
| Công bố, viewer và policy bằng API thật | Draft chặn; công bố mở watermark; PUBLIC_DOWNLOAD tải sạch; bảo vệ lại chặn tải sạch | Đạt với hai PDF corpus; checksum bản sạch đúng nguồn |
| Thu hồi membership qua API A | Yêu cầu metadata tiếp theo bị chặn | 404 |
| ARCHIVED | Chặn học viên, giữ quản lý OWNER hiện hành | Đạt trong integration test |
| Thay/gỡ khi xử lý | Phiên bản riêng, giữ policy; gỡ không hồi sinh từ worker muộn | Đạt trong integration/upload/worker tests |
| Kiểm tra extraction và làm mới UI | Trang vật lý hiển thị đúng; khi mất quyền xóa text/metadata | Đạt trong component tests |
| Phản hồi trạng thái khác phiên bản | Không ghi đè tên file/trạng thái/ID của phiên bản đang hiển thị | Đã thêm test thất bại trước và sửa điều kiện merge theo version_id |

Tại thời điểm kiểm chứng W2, đã đối chiếu 62 file thuộc các đường dẫn A được kiểm tra với commit bàn giao, không có file bị chỉnh nội dung: [source integrity](w2-a-source-integrity.json). Sau đó, theo yêu cầu gộp cấu hình, `backend/requirements.txt` được bổ sung dependency B, `frontend/vite.config.js` build cả hai trang, route B được gộp vào `backend/config/urls.py`. Hai test chung từ `backend/common` chuyển vào `backend/tests/common`; test Swagger cập nhật danh sách endpoint học liệu. Các test học liệu chuyển vào `backend/tests/documents`. Model, quyền, xác thực và nhánh A vẫn giữ nguyên. Báo cáo source integrity là bằng chứng trước các thay đổi cấu trúc được yêu cầu này.

## 5. Kịch bản demo chung

1. A chuẩn bị tài khoản/khóa, học viên tham gia bằng mã lớp và được giáo viên duyệt nếu bật duyệt. Giáo viên mở khóa KTCTMLN từ trang chính, chọn tab **Học liệu**; `/documents.html` vẫn là trang bổ sung.
2. Upload `data/corpus/KTCTMLN/ch01.pdf` (29 trang); xác nhận trạng thái chờ, worker chạy terminal riêng, trạng thái chuyển đã trích xuất. Giáo viên mở **Kiểm tra trích xuất**, kiểm tra trang đầu/giữa/cuối và tiếng Việt.
3. Làm tương tự với `data/corpus/CNXHKH/ch01.pdf` (24 trang). Đối chiếu checksum từ manifest và report; không dùng nhãn môn làm UUID khóa.
4. Upload PDF ảnh không có lớp văn bản: worker báo `OCR_REQUIRED`; chọn thử xử lý lại để minh họa retry. Retry cùng file quét sẽ tiếp tục lỗi, không tuyên bố retry tự sửa OCR. Khi có bản text đúng, API `/versions/` nhận bản thay và tạo phiên bản mới.
5. Kiểm tra học viên upload bị chặn và draft không hiển thị. Giáo viên chọn **Công bố phiên bản này**; học viên mở **Xem PDF**, đối chiếu watermark. Giáo viên **Cho phép tải bản sạch**, học viên tải; chuyển lại bảo vệ và xác nhận không tải sạch được. Thu hồi công bố/quyền phải chặn yêu cầu tiếp theo.
6. Thay PDF qua UI, giữ bản công bố cũ đến khi bản mới xử lý xong và được công bố. Gỡ tài liệu qua UI; status/extraction trả không khả dụng, job cũ không hồi sinh. Ghi kết quả thật, lỗi còn tồn tại và phiên bản mã dùng cho demo.

## 6. Nội dung phần B để đưa vào hai PDF W2

**Báo cáo kết quả tuần:** Trong tuần 2, em đã xây dựng module học liệu tích hợp với tài khoản, khóa học và cơ chế JWT của hệ thống; hoàn thành tiếp nhận PDF văn bản, lưu trữ riêng, hàng đợi xử lý nền, trích xuất theo trang, trạng thái và retry. Corpus được kiểm kê 27 cặp PDF/JSON; hai học liệu KTCTMLN và CNXHKH được dùng để kiểm chứng parser. Em bổ sung giao diện upload, theo dõi lỗi và kiểm tra extraction cho giáo viên, cùng kiểm thử quyền, file không hợp lệ, thu hồi quyền, gỡ/thay nguồn và worker gián đoạn. Kết quả W2 dừng ở extraction; chưa triển khai RAG hoặc đánh giá chất lượng chatbot. Giao diện học liệu đã được gắn vào trang chính trên nhánh B; em đã bổ sung công bố/thu hồi công bố, viewer watermark, chính sách tải sạch và UI thay/gỡ. Nhóm còn cần kiểm chứng môi trường chung và ghi demo.

**Version quyển đồ án W2:** Bổ sung thiết kế dữ liệu học liệu/phiên bản/job, hợp đồng API và sơ đồ upload → queue → worker → extraction/lỗi; mô tả provenance theo trang, kiểm tra quyền và lưu trữ riêng; đưa bảng kiểm thử cùng bằng chứng local vào phần triển khai bước đầu. Đưa viewer/watermark, công bố và policy vào phần đã hiện thực với bằng chứng test; RAG vẫn là phần chưa triển khai. Giữ bản W1, xuất bản W2 thành file PDF mới.

**Bàn giao W3:** Giữ schema extraction 1.0 với `course_id`, `document_id`, `version_id`, checksum, parser và trang vật lý. Retrieval phải kiểm tra quyền hiện hành và nguồn chưa gỡ; chỉ đánh dấu READY sau indexing hợp lệ. Batch toàn bộ 13 PDF hai môn là bước mở rộng, chưa phải kết quả đã chạy. Không tự đưa tài liệu chưa rõ quyền sử dụng lên nguồn công khai.

## 7. Điều kiện để nhóm đóng W2

- [x] Phần B upload/parser/worker/API trạng thái/retry chạy với code A và có kiểm thử local.
- [x] Có manifest, hai extraction mẫu, component UI, script kiểm chứng và nội dung báo cáo B.
- [x] Công bố, viewer watermark, policy/tải sạch và UI thay/gỡ đã có kiểm thử.
- [x] Component học liệu đã gắn vào trang chính giáo viên/học viên trên nhánh B.
- [ ] Nhóm chốt các quyết định chung, tài khoản/khóa demo và kiểm chứng môi trường dùng để demo.
- [ ] Cùng A chạy/ghi demo; xuất hai PDF mới và một đại diện submit hai link Drive đã share.

Phần code B của luồng W2 đã chuẩn bị để bàn giao; chưa đánh dấu toàn bộ W2 của nhóm hoàn thành khi các việc phối hợp và nộp báo cáo còn mở.


### Điều chỉnh giao diện và chính sách từng lớp ngày 09/10/2026

Theo yêu cầu cập nhật, danh sách lớp hiển thị tên cố định, mã lớp, nút Chỉnh sửa và Học viên. Dialog Chỉnh sửa lưu tên, mức hiển thị, yêu cầu giáo viên xét duyệt và mở đăng ký riêng lớp bằng một PATCH. Khi lưu lỗi, dialog giữ dữ liệu đang sửa. Đã bỏ form chính sách chung và checkbox mở đăng ký trực tiếp trên từng dòng.

Phần model/API khóa học được mở rộng trên nhánh B bằng migration `courses.0004_classroom_policy`; nhánh A không bị sửa hoặc push. Báo cáo đối chiếu tính toàn vẹn nguồn A trước đây là mốc lịch sử, không phải khẳng định các file nguồn trên nhánh B vẫn nguyên trạng sau điều chỉnh này. A cần đồng bộ migration và các trường mới của Classroom khi tích hợp.


### Không gian lớp học cập nhật theo giao diện đã thống nhất

Đã thêm hai lối truy cập cho giáo viên: sidebar Lớp học và tên lớp trong tab lớp học của khóa. Danh sách có tìm kiếm/lọc khóa học. Trang lớp có banner OHAYO, mã lớp, số học viên và Chỉnh sửa lớp học; navbar Bảng tin → Buổi học → Học viên → Kết quả. Tab Bảng tin có nút Thêm mới để nhập/đăng thông báo được lưu vào database. Tab Buổi học có nút Thêm mới tạo thẻ buổi học trống có thể mở. Trợ lý AI chỉ xuất hiện bên trong buổi học đã mở, chưa kết nối mô hình; Kết quả đang là giao diện chờ.

A cần đồng bộ migrations `courses.0005_classroomsession` và `documents.0003_knowledgedocument_session`, API sessions, trường `enrolled_count` và quyền học liệu riêng theo lớp. Dữ liệu học liệu cũ không bị chuyển hoặc xóa. Nguồn nhánh A không bị sửa/push; thay đổi nằm trên nhánh B.

### Cập nhật bảng tin và tạo buổi học (09/10/2026)

- Bổ sung API bảng tin theo lớp, kiểm tra chủ khóa học khi đăng và ghi danh đúng lớp khi đọc.
- Thông báo và buổi học trống lưu thật vào database; không tạo dữ liệu minh họa giả.
- UI thông báo giữ bản nháp khi lỗi; trợ lý đóng khi rời buổi học. Phần thiết kế bên trong buổi học chờ hướng dẫn tiếp.
- Kiểm tra: 188 frontend tests đạt; sau sửa lỗi tải lại danh sách, 3 kiểm tra chuyên biệt đạt và lint/build đạt; 218 backend tests, 214 đạt và 4 kiểm tra PostgreSQL được bỏ qua trong môi trường SQLite.
- Đã sao lưu SQLite trước khi áp dụng migration0006 vào môi trường W2 hiện tại.

### Đính kèm thông báo (09/10/2026)

Bổ sung một ảnh và một link tùy chọn cho thông báo; xem trước/bỏ ảnh, link HTTP(S), lưu ảnh riêng tư và kiểm tra quyền đúng lớp khi đọc. Đã sao lưu SQLite và áp dụng migration0007. Kiểm tra: 191 frontend tests đạt, lint/build đạt; 219 backend tests gồm 215 đạt và 4 kiểm tra PostgreSQL bỏ qua trong SQLite.

### Giao diện chi tiết buổi học (09/10/2026)

- Không gian riêng với sidebar xanh lá, chọn học liệu, bản xem PDF, đổi tên buổi học và công bố học liệu đang chọn. AI vẫn chưa kết nối; Video/Bài tập có khu vực chờ triển khai.
- Giữ quy trình PDF riêng tư, watermark và quyền lớp; thêm xem đúng phiên bản hiện tại cho giáo viên trước công bố, không cấp học viên quyền đọc bản nháp.
- Khung trích xuất cuộn riêng cao 360 px; khoảng cách giữa trạng thái và nút kiểm tra 24 px. Kiểm tra UI thật cho thấy nội dung cao 2998 px nằm trong khung cuộn 360 px.
- 195 frontend tests đạt, sau sửa điều kiện chờ PDF thay thế có 3 kiểm tra chuyên biệt đạt; lint/build đạt. Backend 221 tests gồm 217 đạt và 4 kiểm tra PostgreSQL bỏ qua trong SQLite.

### Thu phóng PDF (09/10/2026)

Đã thay iframe PDF bằng trình xem PDF.js một trang, khớp trọn trang theo kích thước khung. Nhãn Mặc định, thanh trượt nằm giữa nút thu nhỏ/phóng to, điều hướng trang và cuộn khi phóng lớn. Kiểm tra browser: trang 337×436 px nằm trọn khung 856×468 px; thanh trượt điều chỉnh bằng bàn phím và Mặc định khôi phục tỷ lệ vừa trang. 197 frontend tests đạt; sau đổi nhãn/thanh trượt, 4 kiểm tra PDF chuyên biệt đạt; lint/build đạt.


### Thẻ học liệu riêng trong buổi học (10/10/2026)

- Thêm học liệu tạo một thẻ trống cuối sidebar; mỗi thẻ chỉ nhận một PDF. Form upload chỉ hiện trong thẻ trống và ẩn sau khi upload thành công. Bản xem, trạng thái và thao tác kiểm tra trích xuất chỉ thuộc học liệu được chọn.
- Danh sách buổi học hiển thị tài liệu cũ trước, mới sau, giữ vị trí khi làm mới hoặc cập nhật phiên bản. Bài học, Video, Bài tập thu/mở độc lập; chevron phải khi đóng, xuống khi mở.
- Bản nháp trống và file đang chọn được giữ riêng từng thẻ trong phiên giao diện; chưa lưu xuống server cho đến khi upload thành công, nên rời buổi học hoặc tải lại trang sẽ mất thẻ chưa upload. Upload lỗi giữ bản nháp và khóa idempotency khi thử lại. Chuyển thẻ trong khi upload vẫn gắn kết quả đúng thẻ gốc.
- Kiểm tra: toàn bộ 200 frontend tests đạt; sau bổ sung trường hợp retry và refresh, 4 kiểm thử thẻ học liệu đạt. Lint/build đạt. Kiểm tra browser thật xác nhận thứ tự học liệu 1 → học liệu 2 → thẻ mới và upload ẩn khi chọn tài liệu có sẵn. Không thay đổi backend hay migration trong đợt này.


### Đổi tên học liệu và căn giữa nút thêm (10/10/2026)

Thay Đóng PDF trong workspace giáo viên bằng Đổi tên, nhập tên/Lưu tên/Hủy; lưu backend và đồng bộ sidebar, preview, tiêu đề trích xuất. Căn giữa riêng phần chữ Thêm học liệu, icon cộng nằm phía trái. Kiểm tra: 203 frontend tests đạt, lint/build đạt; 22 backend tests quyền học liệu/tích hợp đạt. Browser thật xác nhận form lưu thành công (giữ tên cũ để không thay nội dung người dùng). Không cần migration.


### Dialog xác nhận gỡ học liệu (10/10/2026)

Nút Gỡ học liệu và Xác nhận gỡ dùng nền đỏ/chữ trắng. Thay xác nhận inline bằng dialog giữa màn hình, overlay, tên tài liệu, Hủy/Escape và quản lý focus; trong khi gửi không cho đóng/gửi lặp. Lỗi thao tác hiện trong dialog để thử lại. Kiểm tra browser mở rồi hủy, không gỡ dữ liệu thật. 205 frontend tests đạt; lint/build đạt. Chỉnh kiểm thử PDF chờ React cập nhật tỷ lệ trước khi thao tác để tránh lỗi timing khi chạy cả suite.


### Trạng thái tạo buổi học (10/10/2026)

Thay nút xuất bản học liệu trên topbar thành Tạo buổi học; session mới có is_draft=true và nhãn Bản nháp trong danh sách/chi tiết. Nhấn nút gửi PATCH is_draft=false, bỏ nhãn và vô hiệu hóa nút Đã tạo buổi học. Công bố từng PDF vẫn qua nút riêng. Migration0008 đã áp dụng sau khi sao lưu SQLite; buổi học cũ cũng là bản nháp vì trước đây chưa có trạng thái hoàn tất. Kiểm tra: 207 frontend tests đạt, lint/build đạt; 223 backend tests gồm 219 đạt và 4 PostgreSQL skipped trong SQLite. Cập nhật kiểm tra OpenAPI để bao gồm PATCH đổi tên học liệu đã thêm trước đó. Browser xác nhận nhãn và nút mới, chưa hoàn tất buổi học thật đang soạn của người dùng.


### Chuyển động giao diện và chọn tệp (10/10/2026)

Thêm fade 220ms cho các trang/tab nội dung và dialog; sidebar buổi học luôn mounted, animate chiều rộng/trượt/opacity 280ms, có inert/aria-hidden khi đóng, trả focus về nút menu và giữ nguyên thẻ đang mở. Thiết kế chung FilePicker cho upload/thay PDF và ảnh thông báo: icon xanh, nút Chọn tệp/Đổi tệp, tên file, trạng thái disabled; input native phủ trong suốt vẫn hỗ trợ chọn file bằng chuột/bàn phím. Avatar đã có giao diện riêng nên giữ nguyên. Tôn trọng prefers-reduced-motion. Kiểm tra 209 frontend tests đạt, lint/build đạt; sau chỉnh bố cục CSS cho khung hẹp, build đạt. Browser xác nhận sidebar 0.28s và file picker với sidebar mở.

### Xóa buổi học với dialog xác nhận (10/10/2026)

Thêm nút thùng rác riêng bên phải thẻ buổi học; nhấn mở dialog có tên buổi học, cảnh báo học liệu bên trong bị gỡ, Hủy và Xác nhận xóa màu đỏ. Khóa thao tác lặp khi gửi; lỗi hiện trong dialog. Backend kiểm tra chủ khóa và phạm vi lớp, xóa mềm buổi học, gỡ học liệu, thu hồi công bố và hủy tác vụ trích xuất đang chờ/chạy; giữ bản ghi/tệp gốc nội bộ. Upload mới khóa buổi học trong giao dịch để tránh tạo học liệu vào buổi vừa xóa.

Migration0009 đã áp dụng sau khi sao lưu `data/backups/before-session-delete-20261010-023240.sqlite3`; kiểm tra migration không còn thay đổi. Kiểm tra: 210 frontend tests đạt, lint/build đạt; 224 backend tests gồm 220 đạt và 4 kiểm thử PostgreSQL bỏ qua trong SQLite. Browser thật mở rồi hủy dialog, giữ nguyên buổi học và học liệu của người dùng.
