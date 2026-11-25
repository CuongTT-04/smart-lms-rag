# Bàn giao W9-ADM-01 (`#25`) — Khung SMTP, Xác minh email, `auth_version` và CSRF

**Người phụ trách:** Trần Tuấn Cường (`B22DCVT073`)  
**Người tiếp nhận (`W9-ADM-02` / `#26`):** Vũ Nam Dương (`B22DCVT119`)  
**Tham chiếu phân công:** [phan-cong-w9-guardrails.md](phan-cong-w9-guardrails.md)

---

## 1. Migration đợt 1 của `apps.users` (Dương rebase lấy trước khi tạo đợt 2)

- **File migration:** `backend/apps/users/migrations/0004_email_verification_and_auth_version.py` (phụ thuộc `0003_role_specific_profiles`).
- **Trường mới trên `User`:**
  - `email_verified_at` (`DateTimeField(null=True, blank=True)`) + property `user.email_verified`.
  - `email_version` (`PositiveIntegerField(default=1, db_default=1)`): tự động tăng khi đổi email (đồng thời xóa `email_verified_at` và vô hiệu mọi token xác minh cũ).
  - `auth_version` (`PositiveIntegerField(default=1, db_default=1)`): tự động tăng khi khóa tài khoản (`ACTIVE → BLOCKED/INACTIVE`) hoặc đổi `role`.
- **Bảng mới:** `EmailVerificationToken` (lưu `token_hash` SHA-256 64 ký tự, gắn `email` + `email_version`, hạn 24 giờ, `used_at`, `invalidated_at`).

---

## 2. Hợp đồng tích hợp cho `W9-ADM-02` (Dương sử dụng trực tiếp)

### 2.1. Hook tự duyệt `.edu.vn` (`AUTO_EDU_VN`) trong cùng transaction
- **Module:** `backend/apps/users/email_verification.py`
- **Cách đăng ký:**
  ```python
  from apps.users.email_verification import register_email_verified_hook

  def auto_approve_edu_vn(user):
      # Được gọi bên trong @transaction.atomic của confirm_email_verification(),
      # ngay sau khi user (đã select_for_update) được đánh dấu email_verified_at.
      ...

  register_email_verified_hook(auto_approve_edu_vn)
  ```
  *(Hoặc khai báo đường dẫn dotted path trong setting `USERS_EMAIL_VERIFIED_HOOKS`.)*
- **API hồ sơ:** `UserSerializer` (`GET /api/users/me/`, `login`, `session`) đã trả `email_verified` (boolean) và `email_verified_at` (read-only, chặn client tự gửi).

### 2.2. Helper vô hiệu phiên tức thời khi Admin khóa hoặc đổi vai trò
- **Module:** `backend/apps/users/services.py`
- **Hàm dùng chung:** `bump_auth_version(user, *, revoke_tokens=True, close_sockets=True)`
  - Khóa dòng `User`, tăng `auth_version`, đưa toàn bộ refresh token hiện có vào blacklist và gửi sự kiện `session.close` đóng WebSocket thông báo.
- **Phạm vi kiểm tra `auth_version`:**
  - Access JWT: `apps.users.authentication.VersionedJWTAuthentication` (mặc định của DRF, `documents/api/views.py`, `notifications/context.py`). *(Ghi chú nhỏ cho Dương: đổi import `JWTAuthentication` → `VersionedJWTAuthentication` ở `backend/apps/ai/api/views.py` khi làm PR AI/Admin để đồng bộ toàn bộ endpoint AI.)*
  - Refresh & Session: `TokenRefreshView` và `SessionView`.
  - WebSocket thông báo: `apps/notifications/tickets.py` + `consumers.py` kiểm khớp `auth_version` trên cả kết nối mới và vòng lặp duy trì kết nối.

### 2.3. Endpoints mới & CSRF đồng bộ backend–frontend
- `GET /api/users/csrf/` — thiết lập cookie `csrftoken` và trả `{"csrfToken": "..."}`.
- `GET /api/users/session/` — gắn `@ensure_csrf_cookie`, tự cấp `csrftoken` ngay khi mở ứng dụng.
- `POST /api/users/email-verification/send/` — yêu cầu đăng nhập; gửi link xác minh một lần (hạn 24 giờ, gốc lấy từ `EMAIL_VERIFICATION_URL`, không dùng `Host` header); giới hạn **3 lần/giờ** và **cách nhau 60 giây** (`429` + `Retry-After`).
- `POST /api/users/email-verification/confirm/` — nhận `{"token": "..."}`, xác thực 1 lần và gọi `on_email_verified(user)`.
- **Kiểm CSRF + `Origin`/`Referer`:** áp dụng ở `LoginView`, `TokenRefreshView`, `LogoutView` (`backend/apps/users/csrf.py`), trả `403` `{"code": "CSRF_FAILED", ...}` khi thiếu/sai token hoặc sai origin.
- **Frontend (`frontend/src/services/api.js` & `auth.service.js`):** tự đọc động `csrftoken` từ `document.cookie` trên mọi request thay đổi trạng thái (gồm `login`, nhánh auto-refresh `/users/token/refresh/` và `logout`), tự phục hồi 1 lần qua `GET /users/csrf/` nếu gặp `403 CSRF_FAILED`, và xuất sẵn `sendEmailVerification()` + `confirmEmailVerification(token)`.

### 2.4. Khung SMTP chờ điền credential thật
- Các biến cấu hình đã khai báo đầy đủ trong `.env.example` và `backend/config/settings/base.py` / `production.py`: `FRONTEND_ORIGIN`, `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`, `EMAIL_VERIFICATION_URL`, `EMAIL_VERIFICATION_TIMEOUT`, `CSRF_TRUSTED_ORIGINS`, `CSRF_COOKIE_SECURE`.
- `production.py` ép `PASSWORD_RESET_PREVIEW = False`.
- **Trạng thái kiểm thử SMTP:** đã kiểm đầy đủ luồng gửi/xác nhận/hết hạn/đổi email bằng `locmem` email backend; **chưa kiểm SMTP thật** (sẽ bổ sung credential SMTP thực tế để chạy lượt gửi/nhận/click thật sau).

---

## 3. Kết quả kiểm thử thực chạy (`W9-ADM-01`)

Chạy ngày `25/11/2026`:

- **Backend tests trong Docker (`DJANGO_SETTINGS_MODULE=config.settings.test`):**
  ```powershell
  docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test backend python manage.py test apps.users.tests apps.courses.tests tests.documents.test_w9_guardrails_access tests.documents.test_material_access tests.documents.test_retrieval_scope tests.documents.test_session_access tests.documents.test_retrieval_adapter tests.documents.test_study_annotations tests.ai --noinput
  ```
  - **Kết quả:** `Ran 402 tests in 68.013s — OK` (**402/402 PASS**, gồm toàn bộ bộ mới `test_w9_adm_01_security.py` cho xác minh email + hook, `auth_version` + WebSocket, CSRF full chain + `Origin`, login rate limit và toàn bộ hồi quy `users`, `courses`, `documents`, `ai`).
- **Migration & system check:**
  - `python manage.py makemigrations --check --dry-run` → `No changes detected`.
  - `python manage.py check` → `System check identified no issues (0 silenced)`.
- **Frontend (`frontend/`):**
  - `npx eslint . --max-warnings 0` → `0 lỗi, 0 cảnh báo`.
  - `npm.cmd test -- --run --maxWorkers=2` → **56/56 files, 376/376 tests PASS** (bao gồm test CSRF động + tự refresh + phục hồi `403 CSRF_FAILED` ở `api.test.js` và `auth.service.test.js`).
  - `npm.cmd run build` (`vite build`) → thành công trong `1.56s`.
- **Ghi chú:** chưa chạy `migrate` lên DB live nếu bạn chưa rebuild/restart Docker, và giữ trạng thái **chưa kiểm SMTP thật** cho tới khi bổ sung thông tin máy chủ SMTP thực tế.
