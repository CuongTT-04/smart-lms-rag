# OHAYO – Smart LMS RAG

## Chạy cả dự án bằng Docker

Mở Docker Desktop, sau đó chạy tại thư mục gốc dự án:

```powershell
docker compose up --build -d
```

Mở http://localhost:5173. Lệnh này chạy frontend, Django backend, PostgreSQL và worker trích xuất PDF; migration tự chạy trước khi backend khởi động. Không cần chạy npm, Python hoặc worker riêng trên máy. Lần đầu build cần tải thư viện xử lý PDF và có thể mất vài phút; model Docling được tải khi trích xuất lần đầu và được giữ trong cache volume.

Nếu frontend/backend cũ đang chạy trên cổng 5173/8000, dừng các tiến trình đó trước. Có thể đổi `FRONTEND_PORT`, `BACKEND_PORT` trong file `.env`. PostgreSQL là DB chính thức, lưu trong volume `postgres_data`. Container kết nối `database:5432`; chạy backend trực tiếp kết nối cùng DB qua `127.0.0.1:5433` (chỉ mở cổng loopback, đổi bằng `POSTGRES_PORT` và `DB_PORT`). Không chạy lại SQLite cũ.

## Chạy riêng backend trên máy

Docker PostgreSQL phải đang chạy. Copy `.env.example` thành `.env` nếu chưa có, điền đúng `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`; các biến `DB_NAME/USER/PASSWORD` để trống sẽ dùng chung giá trị `POSTGRES_*`. `config.settings.local` tự đọc `.env`, biến môi trường hiện có có độ ưu tiên cao hơn.

```powershell
docker compose up -d database redis
./.venv/Scripts/python.exe backend/manage.py check
# Dùng cổng 8001 nếu backend Docker đang giữ cổng 8000.
./.venv/Scripts/python.exe backend/manage.py runserver 127.0.0.1:8001
```

Chạy trực tiếp và Docker đều dùng cùng PostgreSQL; không được chạy hai worker trích xuất ngoài ý muốn. File học liệu vẫn ở storage/volume riêng của môi trường chạy, không nằm trong DB. Dùng Docker cho luồng học liệu đầy đủ; không giả định đường dẫn storage trong container tự tồn tại trên host.

## Kiểm thử không dùng SQLite

Unit test dùng `SimpleTestCase`/mock; cấu hình `unit` dùng dummy DB để chặn mọi truy vấn SQL ngoài ý muốn:

```powershell
./.venv/Scripts/python.exe backend/manage.py test tests.common.test_database_config tests.ai.test_w4_contract tests.ai.test_w4_harness --settings=config.settings.unit
```

Test tích hợp quyền/transaction vẫn kiểm tra PostgreSQL thật, trong DB `test_<DB_NAME>` riêng do Django tạo/xóa; không dùng DB nghiệp vụ làm DB test. Ví dụ `docker compose exec backend python manage.py test tests.ai --noinput`. Các bộ test tài liệu độc lập dùng `--settings=tests.documents_settings`, cũng chạy PostgreSQL test riêng.

```powershell
# Xem trạng thái và log
docker compose ps
docker compose logs -f backend ingestion-worker

# Dừng dự án, giữ dữ liệu
docker compose down

# Chạy lại sau khi đã build (không cần --build)
docker compose up -d
```

Database, PDF, ảnh thông báo, avatar và cache model được lưu trong Docker volumes. Tránh dùng `docker compose down -v` nếu muốn giữ dữ liệu.

Docker dùng PostgreSQL riêng; tài khoản/khóa học trong `backend/db-w2.sqlite3` của cách chạy cũ chưa tự chuyển sang Docker. File SQLite cũ được giữ nguyên. Bạn có thể đăng ký tài khoản mới trên giao diện Docker.

Đây là cấu hình chạy cục bộ; backend ở http://localhost:8000, tài liệu API ở http://localhost:8000/api/docs/. Frontend trong Docker là bản đã build, vì vậy sau khi sửa giao diện hãy chạy lại `docker compose up --build -d`.

## Giảm thời gian khởi động

Lần đầu cần tải image và cài Docling/PyTorch nên lâu hơn. Các lần mở bình thường dùng `docker compose up -d`, không cài lại thư viện. Backend và worker dùng chung image Python; Compose chỉ build image này một lần. Cache Docker được giữ để khi sửa mã nguồn, bước cài thư viện không chạy lại nếu `backend/requirements.txt` và bước cài dependencies không đổi.

Khi chỉ sửa frontend, chạy `docker compose up -d --build frontend`. Backend được bind mount từ mã nguồn: Django tự reload; nếu sửa mã worker, chạy `docker compose restart ingestion-worker`. Khi thêm migration, chạy `docker compose restart backend` để entrypoint áp dụng migration. Khi đổi thư viện Python hoặc Dockerfile, chạy `docker compose up --build -d` để cập nhật cả backend và worker.
