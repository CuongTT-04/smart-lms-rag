# Bàn giao W2 — tích hợp phần B với code A nguyên bản

Tham chiếu nhánh A `origin/VuNamDuong_B22DCVT119_W2Tasks`, commit `0a0d63e`. Phần User/Course/CourseMember, JWT và frontend A được dùng nguyên bản. Không commit/push lên nhánh A. Cấu hình bổ sung của B nằm ở w2.py; route học liệu được gộp vào config/urls.py theo yêu cầu. Theo yêu cầu gộp dependency, `requirements.txt` trong nhánh hiện tại chứa thư viện chung A+B và thư viện tạo PDF cho kiểm thử.

## Cài đặt

Từ repo root với Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe backend/manage.py migrate --settings=config.settings.w2
.\.venv\Scripts\python.exe backend/manage.py runserver --settings=config.settings.w2
# Terminal khác, cùng settings/database:
.\.venv\Scripts\python.exe backend/manage.py run_ingestion_worker --settings=config.settings.w2
```

Giữ database cũ: A dùng db-w2.sqlite3 cho User UUID, không migrate vào database từng dùng auth.User mặc định. Có thể đặt DB_NAME/DOCUMENTS_STORAGE_ROOT bằng biến môi trường trước khi chạy. Worker chạy riêng, không xử lý Docling trong request HTTP. Lần đầu cần chuẩn bị cache Docling.

## Giao diện học liệu B

```powershell
cd frontend
npm ci
npm run dev
```

Mở http://127.0.0.1:5173/documents.html. Giáo viên chọn khóa, upload PDF, theo dõi xử lý và kiểm tra extraction theo trang. Khi bản xem có watermark đã sẵn sàng, chọn **Công bố phiên bản này** để học viên trong khóa được xem. Có thao tác thu hồi công bố, đổi chính sách, thay PDF và gỡ học liệu. Thay file giữ bản đã công bố đến khi công bố phiên bản mới. Mặc định PROTECTED: xem có watermark, không tải bản sạch. **Cho phép tải bản sạch** chuyển PUBLIC_DOWNLOAD cho người có quyền khóa; chuyển lại bảo vệ chặn yêu cầu sạch mới.

Trên nhánh B đã ghép, trang chính `/` có tab **Học liệu** trong quản lý khóa của giáo viên và danh sách học liệu trong chi tiết khóa của học viên. Hai trang dùng `CourseDocuments.jsx` theo UUID khóa học. `/documents.html` vẫn dùng được. Nhánh A không bị sửa hoặc push. Học viên tham gia bằng mã lớp/duyệt yêu cầu; không dùng POST cấp thành viên trực tiếp.

Build cả trang chính và trang học liệu:

```powershell
npm run build
npm run lint
npm test
```

## Kiểm thử

```powershell
# API tích hợp với model/auth/permission thật của A:
.\.venv\Scripts\python.exe backend/manage.py test tests.documents.test_material_access tests.documents.test_integration tests.common apps.users.tests apps.courses.tests --settings=config.settings.w2_test
# Bộ test riêng về upload/worker của B:
.\.venv\Scripts\python.exe backend/manage.py test tests.documents.test_upload tests.documents.test_worker --settings=tests.documents_settings
# Parser/corpus/CLI độc lập:
.\.venv\Scripts\python.exe backend/manage.py test tests.documents.test_parser --settings=config.settings.w2_test
.\.venv\Scripts\python.exe -m unittest scripts.tests.test_corpus_audit scripts.tests.test_ingest_cli -v
```

Test fixture Course/Membership chỉ dùng ở tests.documents_settings, không deploy. Môi trường tích hợp dùng `users.User`, `courses.Course` và `courses.CourseMember` thật. Tham khảo docs/api.md và docs/reports/w2-b-handoff-and-ab-decisions.md.

Kiểm chứng W2 bằng hai PDF corpus, database SQLite mới và worker chạy ở tiến trình khác:

```powershell
.\.venv\Scripts\python.exe scripts/verify_w2_delivery.py
```

Script tự tạo database/storage tạm trong `data/processed`, chạy migration, kiểm tra restart/retry/file cần OCR, công bố qua API, viewer watermark, policy/tải sạch và thu hồi quyền rồi dọn fixture. Không seed hay xóa database của ứng dụng. Report không chứa password/token hoặc toàn văn học liệu. Bàn giao hiện tại và các quyết định A/B: [w2-b-handoff-and-ab-decisions.md](../docs/reports/w2-b-handoff-and-ab-decisions.md).

## Hành vi đã triển khai và giới hạn

PDF tối đa 20 MiB/100 trang; kiểm tra file thực, mã hóa/cấu trúc; upload trả 202 sau lưu/xếp hàng. PDF quét/thiếu text layer có thể nhận 202 rồi FAILED từ worker. File gốc và extraction nằm ngoài MEDIA_ROOT, không có URL original công khai. Worker có timeout subprocess 900 giây, lease recovery và retry idempotent. Kết quả thành công là EXTRACTED, không tự READY/indexed/active_version. Gỡ hủy job, kết quả muộn không phục hồi nguồn; thay file giữ policy và active_version cũ.

Trang B poll 2 giây khi QUEUED/PROCESSING, dừng ở trạng thái cuối hoặc rời trang; mất quyền xóa metadata đang hiển thị. Network failure không bị coi là extraction failure và giữ Idempotency-Key cho thao tác chưa rõ kết quả.

Chưa kiểm chứng PostgreSQL/nhiều worker/Colab T4; thời gian local chỉ là mẫu đo. Crash upload có thể để lại file tạm/original chưa có record, cần dọn theo đối chiếu DB. Viewer/publication/policy/download đã triển khai; RAG tiếp tục W3. Watermark không ngăn tuyệt đối chụp màn hình hoặc lưu bản đã nhận. Migration documents.0002 thêm published_version và hash derivative; chạy migrate trước API/worker. Học liệu EXTRACTED cũ thiếu watermark có nút **Tạo lại bản xem**, xử lý lại cùng phiên bản.

## Docker tích hợp API và worker

Từ root repo, khi Docker Desktop engine đã chạy:

```powershell
docker compose up --build -d
docker compose logs -f ingestion-worker
```

Compose khởi động database, backend và ingestion-worker. Backend migrate trước; worker đợi backend healthy, dùng cùng database và volume `documents_data` ở `/app/.private/documents`. Volume không phục vụ qua MEDIA_URL. Cache Docling riêng tránh tải lại model khi tạo lại worker; lần đầu cần mạng để tải model. Không dùng `docker compose down -v` nếu cần giữ dữ liệu. Lần kiểm chứng 09/10 mới kiểm tra cú pháp Compose; Docker engine chưa chạy, chưa xác nhận runtime Docker/PostgreSQL.
