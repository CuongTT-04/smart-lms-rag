# OHAYO – Smart LMS RAG

## Chạy cả dự án bằng Docker

Mở Docker Desktop, sau đó chạy tại thư mục gốc dự án:

```powershell
docker compose up --build -d
```

Mở http://localhost:5173. Lệnh này chạy frontend, Django backend, PostgreSQL và worker trích xuất PDF; migration tự chạy trước khi backend khởi động. Không cần chạy npm, Python hoặc worker riêng trên máy. Lần đầu build cần tải thư viện xử lý PDF và có thể mất vài phút; model Docling được tải khi trích xuất lần đầu và được giữ trong cache volume.

Nếu frontend/backend cũ đang chạy trên cổng 5173/8000, dừng các tiến trình đó trước. Có thể đổi `FRONTEND_PORT`, `BACKEND_PORT` trong file `.env`; các giá trị mặc định hoạt động cả khi chưa có `.env`. PostgreSQL chỉ dùng mạng nội bộ Docker, không chiếm cổng 5432 của máy.

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
