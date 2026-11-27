# W8-01 – Hướng dẫn dữ liệu Demo và Bảng kết quả mong đợi

**Tuần nghiệm thu là W8.** Code demo dùng lệnh `seed_w9_demo`, biến `W9_DEMO_*`, tên dữ liệu `W9 Demo` và DB/project có tiền tố `w9`. Các tên bên dưới khớp code đã triển khai để chạy lại được.

- **Command:** `python manage.py seed_w9_demo`
- **Điều kiện bắt buộc để chạy (khóa an toàn mặc định):**
  1. Biến môi trường `W9_DEMO_ENABLED=1`
  2. Tên database kết nối (`DB_NAME` / `POSTGRES_DB`) phải bắt đầu bằng `w9_demo_` (chặn tuyệt đối trên `smart_lms` thật).
  3. Truyền mật khẩu riêng qua biến môi trường `W9_DEMO_PASSWORD` (>= 8 ký tự, không lưu trong Git và command không in ra stdout).
  4. Tùy chọn `--anchor <ISO-8601>` để cố định mốc hạn nộp (mặc định dùng thời gian hiện tại lúc chạy để bài không bị quá hạn giả).

---

## 1. Tài khoản và Phạm vi tạo sẵn

| Mã | Username | Vai trò | Phạm vi quyền |
|---|---|---|---|
| T1 | `w9demo_t1` | TEACHER | Chủ sở hữu Course 1 (`W9 Demo - Kiến trúc máy tính`), gồm `Lớp chính` và `Lớp kiểm tra`. |
| T2 | `w9demo_t2` | TEACHER | Chủ sở hữu Course 2 (`W9 Demo - Cơ sở dữ liệu`). Bị chặn (404) khi truy cập Course 1. |
| S1 | `w9demo_s1` | STUDENT | Ghi danh `ACTIVE` ở `Lớp chính`. |
| S2 | `w9demo_s2` | STUDENT | Ghi danh `COMPLETED` ở `Lớp chính`, `ACTIVE` ở `Lớp kiểm tra`. |
| S3 | `w9demo_s3` | STUDENT | Đã bị thu hồi ghi danh (`WITHDRAWN`) ở `Lớp chính`. Bị chặn (404) ở mọi API lớp. |

---

## 2. Dữ liệu hoạt động và Bảng kết quả mong đợi

### A. `W9 Demo - Lớp chính` (4 hoạt động áp dụng)
- **Buổi 1 (đã công bố):**
  1. `W9 Demo - Tài liệu tổng hợp` (PDF 2 trang tạo bằng ReportLab + derivative watermark, `status=EXTRACTED`, `watermark_status=READY`; mở được qua `/view/`, chưa cấu hình AI index nên `rag_ready=False`).
  2. `W9 Demo - Video bài giảng` (video WebM VP8 phát được dài `12.0s`, có 1 checkpoint tại `5.0s`).
  3. `W9 Demo - Quiz ôn tập` (`PRACTICE`, đã công bố kết quả).
  4. `W9 Demo - Tự luận ôn tập` (`PRACTICE`, chưa công bố kết quả).
- **Buổi nháp (`is_draft=True`):** chứa 1 tài liệu PDF nháp (bị loại khỏi mẫu số tiến độ và danh sách học viên).

| Học viên | Tiến độ (`progress/`) | PDF | Video | Quiz ôn tập (cao nhất) | Tự luận ôn tập | Trạng thái Enrollment |
|---|---|---|---|---|---|---|
| **S1** | `2/4` (`50.0%`, `completed_at=null`) | Đã học | Chưa xong | Đã nộp · `0.0/10` (`GRADED`) | Bản nháp (`DRAFT`) | `ACTIVE` |
| **S2** | `4/4` (`100.0%`, có `completed_at`) | Đã học | Hoàn thành | 2 lượt (`0.0`, `10.0`) · chọn **`10.0/10`** | Đã nộp · `PENDING` (chờ chấm) | `COMPLETED` |
| **S3** | `404 Not Found` | Bị chặn | Bị chặn | Bị chặn | Bị chặn | `WITHDRAWN` |

### B. `W9 Demo - Lớp kiểm tra` (dành cho S2 & T1)
- `W9 Demo - Quiz kiểm tra` (`TEST`, `grade_published=False`):
  - **T1 xem `results/`:** thấy điểm nội bộ `10.0/10` (`GRADED`).
  - **S2 xem `results/`:** điểm còn ẩn (`score=null`, `grading_status=PENDING`).
- `W9 Demo - Bài quá hạn` (`due_at = anchor - 1 day`, chưa nộp): cờ `is_overdue=true` hiển thị trên bảng kết quả.

---

## 3. Lệnh chạy demo trên DB riêng (không chạm DB đang dùng)

Chạy các lệnh sau trong một cửa sổ PowerShell riêng tại root dự án. Compose project `smart-lms-w9-demo` tạo database, mạng và volume riêng. Backend và frontend demo cùng dùng database `w9_demo_local`.

```powershell
$env:POSTGRES_DB = "w9_demo_local"
$env:POSTGRES_PORT = "5434"
$env:BACKEND_PORT = "8001"
$env:FRONTEND_PORT = "5174"
$env:CORS_ALLOWED_ORIGINS = "http://localhost:5174,http://127.0.0.1:5174"
docker compose -p smart-lms-w9-demo up -d --build

# Thay placeholder bằng mật khẩu demo riêng trước khi chạy.
docker compose -p smart-lms-w9-demo exec -T -e W9_DEMO_ENABLED=1 -e W9_DEMO_PASSWORD="<mat-khau-rieng>" backend python manage.py seed_w9_demo
```

Mở `http://localhost:5174`, đăng nhập bằng tài khoản trong mục 1 và mật khẩu vừa truyền. Mở `/api/health/` qua cổng 5174 để kiểm kết nối frontend–backend. Entrypoint backend đã chạy migration cho DB demo khi khởi động.

Các lệnh `exec -e DB_NAME=...` chỉ đổi database cho tiến trình lệnh đó. Để demo trên trình duyệt, cả web backend và tiến trình seed phải cùng kết nối database demo như project riêng ở trên. Đóng cửa sổ PowerShell sau khi dùng để các biến demo không ảnh hưởng lệnh chạy project chính sau này.

> Lưu ý: Các tài liệu synthetic trong seed này chỉ phục vụ kiểm thử tiến độ và kết quả LMS; khi kiểm AI RAG thật (E05–E07), sử dụng tài liệu CPU đã được cấp quyền và lập chỉ mục riêng.
