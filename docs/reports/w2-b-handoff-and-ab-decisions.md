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

**Các phần còn thiếu:** (1) phần B: công bố/thu hồi công bố học liệu, viewer/watermark, policy/download và UI thay/gỡ; (2) phần chung: tài khoản/khóa demo cố định, kiểm chứng PostgreSQL/Docker, ghi demo và hai PDF tuần; (3) cần chốt: Lesson/chương, học liệu chung khóa hay riêng lớp, giới hạn upload của khóa ARCHIVED. Backend tham gia lớp và quyền của A không còn là blocker cho luồng đã kiểm thử; không ghi các chức năng B chưa làm là A thiếu.

## 1. Kết quả phần B

| Công việc | Kết quả và bằng chứng | Trạng thái |
|---|---|---|
| Model học liệu, phiên bản và hàng đợi | `KnowledgeDocument`, `DocumentVersion`, `IngestionJob`, `DocumentOperation`; FK dùng User/Course UUID của A; migration riêng B. [ERD](../design/w2-document-erd.md), [API](../api.md). | Đã triển khai |
| Corpus v1 | Kiểm kê 27 PDF/JSON: THMLN 14, KTCTMLN 6, CNXHKH 7; manifest có checksum, trang, nguồn và thông tin quyền sử dụng được khai báo. [Manifest](../../data/data_manifest.csv), [báo cáo](w2-corpus-check.md). Quyền sử dụng chưa được xác minh độc lập. | Đã kiểm kê |
| Parser theo trang | Docling 2.135.0; giữ số trang PDF vật lý bắt đầu từ 1, checksum và định danh khóa/tài liệu/phiên bản. KTCTMLN chương 1: 29 trang; CNXHKH chương 1: 24 trang. [Đối chiếu extraction](w2-extraction-verification.json). | Đã kiểm chứng hai mẫu |
| Upload | JWT Bearer; kiểm tra quyền OWNER/ACTIVE qua hàm A; PDF văn bản tối đa 20 MiB, 100 trang. Lưu riêng, trả 202 rồi mới xử lý nền; idempotency chống lặp khi gửi lại. | Đã triển khai và kiểm thử |
| Worker | Management command riêng; timeout tiến trình con 900 giây; lease/token chống tác vụ cũ chốt kết quả; phát hiện worker gián đoạn; retry giữ cùng phiên bản. | Đã triển khai và kiểm thử |
| Thay và gỡ tài liệu | API thay tạo phiên bản mới, giữ chính sách; gỡ chặn truy cập, hủy job đang chờ/chạy, kết quả muộn không phục hồi nguồn. | Đã triển khai API; chưa có UI thay/gỡ |
| Giao diện B | Trang `/documents.html` dùng login và API client A; chọn khóa, upload, trạng thái, lỗi, retry, làm mới danh sách. Giáo viên kiểm tra văn bản theo trang bằng nút **Kiểm tra trích xuất**. Đã gắn vào tab Học liệu của giáo viên và chi tiết khóa học của học viên. | Đã tích hợp trang chính trên nhánh B |
| Kiểm thử quyền | JWT thiếu/sai/hết hạn, tài khoản khóa, giáo viên khác, admin, học viên sai lớp/thu hồi quyền; học viên không được đọc JSON extraction hoặc original. ARCHIVED chặn học viên, giữ quyền quản lý của chủ khóa theo A. | Đã có test tự động |
| Chạy từ DB sạch và tiến trình worker khác | Script tạo SQLite tạm, chạy migration, login/course/membership API thật, upload hai PDF corpus, worker tiến trình riêng; phục hồi job gián đoạn, retry idempotent, PDF cần OCR và thu hồi quyền. [Script](../../scripts/verify_w2_delivery.py), [kết quả](w2-delivery-verification.json). Không ghi vào database demo của nhóm. | Có kiểm chứng local |
| Bàn giao W3 và nội dung báo cáo | Schema extraction, hướng dẫn tái chạy, kịch bản demo và đoạn báo cáo tại các mục dưới. | Đã chuẩn bị |

**Giới hạn W2:** Demo hiện chỉ có upload → xử lý nền → trạng thái/lỗi → kiểm tra extraction của giáo viên. Học liệu mới là draft và `PROTECTED`. Chưa có thao tác công bố học liệu, viewer, đổi policy hoặc download trên UI/API; không mở file gốc sạch để thay thế viewer. Các test học viên dùng `is_published=True` như **fixture kiểm thử**, không chứng minh chức năng công bố đã triển khai. FR Chính sách học liệu và FR Watermark vẫn phải hoàn thành trong MVP của sản phẩm, không bị loại khỏi SRS. `EXTRACTED` luôn có `rag_ready=false`, `indexed_at=null`; W2 chưa có chatbot/chunking/embedding.

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
| AB-02 | Công bố học liệu khi nào? | `is_published=False` mặc định, extraction không tự công bố. Đề xuất giáo viên chủ động công bố sau khi bản xem bảo vệ đã sẵn sàng; phải tách công bố học liệu, Course PUBLISHED và PUBLIC_DOWNLOAD. Cần chốt UI/API và quyền. | B làm công bố/viewer; A phối hợp trạng thái khóa và vị trí thao tác. |
| AB-03 | ARCHIVED cho giáo viên làm gì? | Quyền A hiện cho OWNER/ACTIVE quản lý/upload cả khóa ARCHIVED; học viên bị chặn. SRS giữ quản lý giáo viên. Nhóm cần xác nhận có cho upload/thay file mới khi lưu trữ hay chỉ đọc/quản lý metadata. B hiện giữ nguyên hành vi A. | A/B thống nhất quy tắc; A quyết định thay permission chung nếu cần. |
| AB-04 | Gắn UI học liệu ở đâu? | Đã gắn `CourseDocuments.jsx` vào tab Học liệu của giáo viên và chi tiết khóa học học viên, dùng `key={course.id}`. Chỉ sửa điểm tích hợp trên nhánh B; nhánh A giữ nguyên. Backend kiểm tra quyền, học viên không có thao tác quản lý. | A/B rà trải nghiệm trên môi trường demo chung. |
| AB-05 | Bộ tài khoản và khóa demo chung | Cần một giáo viên, học viên có quyền, học viên không có quyền và hai khóa KTCTMLN/CNXHKH; học viên tham gia bằng mã lớp/duyệt yêu cầu. Nhãn môn corpus không phải UUID runtime; cần bảng ánh xạ chung. Script kiểm chứng chỉ tạo fixture tạm, không thay bộ seed demo. | A chuẩn bị tài khoản/khóa; B chọn PDF và cùng kiểm tra ánh xạ. |
| AB-06 | Database/migration/môi trường chung | Local đã kiểm chứng SQLite. PostgreSQL, chạy đồng thời nhiều worker và cấu hình deploy chưa được kiểm chứng. Chốt môi trường, biến DB/storage, thứ tự migration và người giữ worker; không phục vụ private storage qua web server. | A chuẩn bị môi trường chung; B chạy migration/test/worker B trên đó. |
| AB-07 | Bản xem, watermark và policy | B phụ trách: mặc định bảo vệ; người có quyền chỉ xem derivative watermark; giáo viên chuyển PUBLIC_DOWNLOAD mới có bản sạch, đổi lại bảo vệ chặn yêu cầu mới. Cần chốt viewer, nội dung watermark, phiên bản đang phục vụ và hành vi thay file trước khi code. Không dùng `active_version` dành RAG để kích hoạt bản xem trong W2. | B triển khai sau W2 metadata; A thống nhất UI/quyền khóa. Đây là phần B chưa làm, không phải A thiếu. |
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
| Backend tích hợp A+B và kiểm thử chung | 202 test: 198 đạt, 4 test concurrency PostgreSQL được bỏ qua trên SQLite | [Log](w2-final-integration-tests.txt) |
| Upload/worker B | 27 test | [Log](w2-final-worker-tests.txt) |
| Parser/corpus/CLI | 19 test | [Log](w2-final-parser-tests.txt) |
| Frontend A+B | 171 test, gồm kiểm thử gắn học liệu vào hai trang chính | [Log](w2-final-frontend-tests.txt) |
| Lint/build | Kiểm tra bằng cấu hình chung `vite.config.js` cho cả hai trang | [Log](w2-final-frontend-build.txt) |

Các bộ có phần trùng; không cộng thành tổng test duy nhất. Test giả lập timeout/lỗi phục vụ kiểm tra nhánh xử lý; script delivery mới kiểm tra Docling thật trên corpus với worker riêng. Thời gian upload trong report đo nhận/lưu file local bằng Django test client, không bao gồm truyền mạng và không phải SLA production. Thời gian worker gồm khởi động tiến trình/parser. Chưa kiểm thử trực quan trên trình duyệt hoặc PostgreSQL/T4.

| Ca kiểm thử | Kỳ vọng | Kết quả thực tế |
|---|---|---|
| Upload hai PDF text bằng chủ khóa | 202, job bền vững; không chạy parser trong request | Đạt; tiếp nhận local 0,266 giây và 0,125 giây |
| Worker tiến trình riêng xử lý hai môn | EXTRACTED, đúng checksum/UUID và đủ trang vật lý | Đạt; 29 và 24 trang; RAG chưa sẵn sàng |
| Worker bị gián đoạn | Job hết lease thành WORKER_INTERRUPTED; API retry tạo job mới trên cùng version | Đạt; gửi lại cùng key nhận cùng job; bản text xử lý thành công |
| PDF ảnh cần OCR | Có lỗi rõ, không đánh dấu extraction thành công | FAILED / OCR_REQUIRED |
| Draft / metadata đã công bố bằng fixture | Học viên không thấy draft; thấy metadata đã công bố, không đọc extraction | 404 / 200 / 404 đúng kỳ vọng |
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
5. Kiểm tra học viên upload bị chặn và draft không hiển thị. Ca đọc metadata đã công bố/thu hồi quyền hiện được chứng minh qua test fixture và API A, chưa có UI công bố để thao tác trong demo. Không sửa database demo rồi mô tả như chức năng người dùng.
6. Gỡ tài liệu qua API; status/extraction trả không khả dụng, job cũ không hồi sinh. Ghi kết quả thật, lỗi còn tồn tại và phiên bản mã dùng cho demo.

## 6. Nội dung phần B để đưa vào hai PDF W2

**Báo cáo kết quả tuần:** Trong tuần 2, em đã xây dựng module học liệu tích hợp với tài khoản, khóa học và cơ chế JWT của hệ thống; hoàn thành tiếp nhận PDF văn bản, lưu trữ riêng, hàng đợi xử lý nền, trích xuất theo trang, trạng thái và retry. Corpus được kiểm kê 27 cặp PDF/JSON; hai học liệu KTCTMLN và CNXHKH được dùng để kiểm chứng parser. Em bổ sung giao diện upload, theo dõi lỗi và kiểm tra extraction cho giáo viên, cùng kiểm thử quyền, file không hợp lệ, thu hồi quyền, gỡ/thay nguồn và worker gián đoạn. Kết quả W2 dừng ở extraction; chưa triển khai RAG hoặc đánh giá chất lượng chatbot. Giao diện học liệu đã được gắn vào trang chính trên nhánh B; nhóm còn cần kiểm chứng môi trường chung, hoàn thiện viewer/watermark và thống nhất công bố học liệu.

**Version quyển đồ án W2:** Bổ sung thiết kế dữ liệu học liệu/phiên bản/job, hợp đồng API và sơ đồ upload → queue → worker → extraction/lỗi; mô tả provenance theo trang, kiểm tra quyền và lưu trữ riêng; đưa bảng kiểm thử cùng bằng chứng local vào phần triển khai bước đầu. Chỉ trình bày thiết kế cho viewer/watermark và RAG ở phần chưa hiện thực, không viết như kết quả đã đạt. Giữ bản W1, xuất bản W2 thành file PDF mới.

**Bàn giao W3:** Giữ schema extraction 1.0 với `course_id`, `document_id`, `version_id`, checksum, parser và trang vật lý. Retrieval phải kiểm tra quyền hiện hành và nguồn chưa gỡ; chỉ đánh dấu READY sau indexing hợp lệ. Batch toàn bộ 13 PDF hai môn là bước mở rộng, chưa phải kết quả đã chạy. Không tự đưa tài liệu chưa rõ quyền sử dụng lên nguồn công khai.

## 7. Điều kiện để nhóm đóng W2

- [x] Phần B upload/parser/worker/API trạng thái/retry chạy với code A và có kiểm thử local.
- [x] Có manifest, hai extraction mẫu, component UI, script kiểm chứng và nội dung báo cáo B.
- [x] Component học liệu đã gắn vào trang chính giáo viên/học viên trên nhánh B.
- [ ] Nhóm chốt các quyết định chung, tài khoản/khóa demo và kiểm chứng môi trường dùng để demo.
- [ ] Cùng A chạy/ghi demo; xuất hai PDF mới và một đại diện submit hai link Drive đã share.

Phần code B của luồng W2 đã chuẩn bị để bàn giao; chưa đánh dấu toàn bộ W2 của nhóm hoàn thành khi các việc phối hợp và nộp báo cáo còn mở.
