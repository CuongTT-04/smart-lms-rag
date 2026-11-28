# W9 · Guardrails, quyền truy cập tài liệu, chống lộ nội dung/citation sai (và nền Admin + SMTP)

**Milestone:** `W9 – Guardrails, quyền truy cập tài liệu, chống lộ nội dung/citation sai`.

**Quy ước tuần đã được Cường xác nhận.** Lịch đề cương đang lệch một tuần so với yêu cầu giảng viên. Mốc Security/privacy/cost controls được ghi W10 trong đề cương tương ứng **W9 thực tế**, gồm guardrails, quyền truy cập tài liệu và chống lộ nội dung/citation sai. Kế hoạch, Issue, milestone, PR, báo cáo và Evidence của mốc này dùng `W9` / `Evidence/W09/`. Tiêu đề yêu cầu của giảng viên là căn cứ nghiệm thu chính. Hồ sơ LMS core W8 nằm tại [phân công W8](../W8/phan-cong-w8.md).

**Thứ tự ưu tiên trong W9 (2 chặng nối tiếp):**
1. **Chặng 1 — Trọng tâm bắt buộc (điều kiện chốt Milestone W9 & `Evidence/W09/`):** Hoàn thành trọn vẹn **Guardrails, quyền truy cập tài liệu, chống lộ nội dung và độ đúng citation** (`W9-GR-01`, `W9-GR-02`).
2. **Chặng 2 — Nền tảng Admin & SMTP (thực hiện sau khi khóa Chặng 1):** Hoàn thiện **Admin, duyệt giáo viên, danh mục trường, khung SMTP/xác minh email và bảo mật phiên nền** (`W9-ADM-01`, `W9-ADM-02`) theo tài liệu gửi riêng `2026-11-24-admin-thanh-toan.md`.

**Thành viên:** Trần Tuấn Cường (`B22DCVT073`), Vũ Nam Dương (`B22DCVT119`).

**Cập nhật kiểm chứng ngày 28/11/2026:** kết quả hiện tại xem tại [báo cáo tóm tắt Evidence/W09](../../../Evidence/W09/README.md). Ma trận sau bản vá citation đạt 36/36 tình huống; hồi quy backend đạt 1.055/1.060, năm ca bỏ qua; frontend đạt 413/413. Đã bổ sung ảnh mở lại PDF bị chặn sau thu hồi công bố và ảnh nhận thư/xác minh qua SMTP thật trong môi trường thử riêng. Luồng mở lại citation trên UI và việc áp dụng SMTP vào backend vận hành còn cần kiểm; kết quả đối chiếu nội dung chờ thành viên ký duyệt. So sánh Base–tuned fixed-context gồm 14 yêu cầu mỗi nhánh, được ghi riêng với ma trận 36 tình huống.

**Mốc kiểm chứng sau ghép PR #27 (trước lượt chạy cuối):** đã tích hợp `f04c7df` và sửa lỗi xác thực/quyền sau model bị đổi thành 503; lượt hồi quy tại mốc này đạt 1.050/1.055, năm ca bỏ qua. Kết quả trước vá được giữ riêng để đối chiếu, không dùng thay kết quả sau sửa. Nhật ký ghép được lưu tại `.private/w9-evidence-review-20261128/logs/safe-merge.json`; bản tóm tắt và kết quả hiện hành nằm trong Evidence/W09.

> **Hướng dẫn agent:** Đọc [SRS](../../SRS.md), bản phân công này, tài liệu gửi riêng `2026-11-24-admin-thanh-toan.md` và mã nguồn hiện tại trước khi triển khai. Làm xong và kiểm chứng từng mục kèm test (viết test → thấy fail đúng lý do → triển khai → chạy hồi quy). Ghi rõ bằng chứng thực chạy; không đánh dấu đạt khi chưa chạy. Không tự `commit`/`push`/`merge` khi chưa được yêu cầu; không đưa secrets, token, dữ liệu lớp thật hoặc log thô nhạy cảm lên Git.

---

## 1. Bảng phân công tổng thể và phạm vi sở hữu

| Chặng | Mã kế hoạch và tiêu đề Issue đề xuất | Người chính | Đầu vào | Đầu ra bàn giao |
| --- | --- | --- | --- | --- |
| **Chặng 1** (Ưu tiên 1) | `W9-GR-01` – Kiểm soát quyền học liệu và thu hồi quyền xuyên suốt LMS | Trần Tuấn Cường · B22DCVT073 | LMS đã ghép, quyền khóa/lớp, tài liệu và phiên bản, cơ chế xem/tải, API mở nguồn, SRS FR-37–38 và NFR-16 | Ma trận quyền, bộ dữ liệu kiểm thử dùng chung, hợp đồng phạm vi nguồn, sửa lỗi quyền tìm thấy, kiểm thử API/file/UI và kết quả demo tích hợp |
| **Chặng 1** (Ưu tiên 1) | `W9-GR-02` – Kiểm chứng guardrails Ayo, độ đúng citation và đóng gói `Evidence/W09/` | Vũ Nam Dương · B22DCVT119 | Phạm vi nguồn từ Cường, Ayo/RAG hiện hành, câu hỏi và trang có đáp án chuẩn, SRS FR-21, FR-35 và NFR-29 | Bộ ca kiểm có đáp án kỳ vọng, guardrails và test cho chat/gợi ý/tóm tắt/lịch sử, bảng điểm citation theo nhận định, log đã lọc và gói `Evidence/W09/` tổng hợp |
| **Chặng 2** (Sau Chặng 1) | `W9-ADM-01` – Khung SMTP, xác minh email và bảo mật phiên nền (`SEC-01`) | Trần Tuấn Cường · B22DCVT073 | Code sau Chặng 1, `apps.users`, `config/settings`, `frontend/src/services/api.js`, Mục 5.2 & `SEC-01` trong `2026-11-24-admin-thanh-toan.md` | Khung cấu hình SMTP (`.env.example` + console/mock test), API gửi/xác nhận email + hook `on_email_verified`, `auth_version`, kiểm CSRF đồng bộ backend–frontend, bộ test hồi quy auth |
| **Chặng 2** (Sau Chặng 1) | `W9-ADM-02` – Không gian Admin, tài khoản, duyệt giáo viên, danh mục trường và vận hành (`ADM-01/02`, Mục 5) | Vũ Nam Dương · B22DCVT119 | Migration đợt 1 từ `W9-ADM-01`, `apps.operations`, tín hiệu quota/health từ `W9-GR-02`, Mục 5 & `ADM-01/02` trong `2026-11-24-admin-thanh-toan.md` | `Institution` (seed 7 trường Hà Nội) + combobox tìm kiếm, `TeacherApproval` (`PENDING/APPROVED/REJECTED/REVOKED` + migration `LEGACY` + rule `AUTO_EDU_VN`), banner/tooltip giáo viên chờ duyệt, không gian Admin (Tổng quan, Tài khoản/Giáo viên, Vận hành) và test đầy đủ |

*Ghi chú:* Các mã trên là mã lập kế hoạch; khi tạo Issue GitHub, dùng số Issue thực tế trong commit/PR. Mỗi người (hoặc agent) review chéo PR của người còn lại trước khi merge.

---

## 2. Hợp đồng chung và ranh giới tránh xung đột file/migration

### 2.1. Hợp đồng Chặng 1 — Dữ liệu và phạm vi nguồn (Guardrails & Citation)
- [ ] **Fixture dùng chung (Cường chuẩn bị, hai bên cùng dùng):** hai lớp cùng khóa, một khóa khác, hai học viên có quyền khác nhau, hai giáo viên và một Admin chỉ có quyền xem tổng hợp; có tài liệu được phép, tài liệu lớp khác, tài liệu đã gỡ và tài liệu có hai phiên bản khác số trang/nội dung. Quy trình seed chạy lại được trong môi trường test.
- [ ] **Học liệu giả lập kiểm chứng:** chứa cụm từ nhận biết riêng cho từng phạm vi, bảng ánh xạ trang hỗ trợ từng ý, câu hỏi thiếu căn cứ, một bài ôn tập (`PRACTICE`), một bài kiểm tra đang làm (`TEST`), một đoạn tài liệu chứa chỉ dẫn giả lập vô hại (prompt injection) và một câu hỏi nối tiếp dựa vào lịch sử. Ưu tiên chạy model thật với fixture này để không gửi dữ liệu lớp thật ra dịch vụ ngoài.
- [ ] **Hợp đồng phạm vi nguồn:** backend xác định actor, khóa, lớp, buổi học, tài liệu, phiên bản và tập bằng chứng của **lượt hiện hành** (client chỉ đề nghị phạm vi). Dương nhận danh sách đoạn được phép kèm ID nguồn và trang để dựng prompt; đường mở citation gọi lại kiểm quyền của Cường. Thống nhất hành vi khi thiếu nguồn, tài liệu đổi phiên bản/bị gỡ, người dùng mất quyền hoặc đang làm bài `TEST`.
- [ ] **Bảng ca kiểm cố định:** lưu ID ổn định, vai trò, nguồn được phép/bị cấm, câu hỏi, ý và trang chuẩn, trạng thái mong đợi, kết quả thực tế và người phụ trách. Khóa bộ ca trước lần đo cuối; giữ nguyên bộ đánh giá W7 đã khóa.

### 2.2. Hợp đồng Chặng 2 — Ranh giới file & thứ tự migration (Admin + SMTP)
- **Thứ tự migration `apps.users` (bắt buộc để không xung đột):**
  1. **Cường (`W9-ADM-01`) merge đợt 1 trước:** thêm `email_verified_at`, `email_version` (hoặc cơ chế gắn phiên bản email), bảng token xác minh email (lưu băm, 1 lần, hạn 24h) và `auth_version` trên `User`. Cung cấp hook sạch `on_email_verified(user)` chạy trong cùng transaction xác nhận email.
  2. **Dương (`W9-ADM-02`) rebase và làm đợt 2:** thêm `Institution`, liên kết trường trên `TeacherProfile`, `TeacherApproval` (1-1 với `TeacherProfile`), data migration `APPROVED/LEGACY` cho giáo viên cũ (dùng `get_or_create`, **không** tự gán `email_verified_at`, chạy lại không ghi đè trạng thái đã đổi), và gắn rule tự duyệt `.edu.vn` (`AUTO_EDU_VN`) vào hook `on_email_verified(user)`.
- **Ranh giới mã nguồn:**
  - **Cường sở hữu:** `backend/apps/courses/permissions.py`, `backend/apps/documents/retrieval_scope.py`, `backend/apps/documents/api/` (Chặng 1); `backend/config/settings/` (SMTP/CSRF), luồng xác minh email & CSRF/auth (`apps/users/email_verification*`, `apps/users/api/views.py`, `frontend/src/services/api.js`) (Chặng 2).
  - **Dương sở hữu:** `backend/apps/ai/`, `frontend/src/components/ai/CitationViewer.jsx`, `Evidence/W09/` (Chặng 1); `backend/apps/operations/`, `TeacherApproval`/`Institution` trong `apps/users/`, routing Admin trong `frontend/src/App.jsx`, giao diện Admin và banner/tooltip trên `TeacherHomePage` (Chặng 2).
- **Tái sử dụng tín hiệu giữa 2 chặng:** dữ liệu health/lỗi/quota Ayo đo ở `W9-GR-02` dùng đúng cấu trúc để tab **Vận hành** trong `W9-ADM-02` hiển thị trực tiếp.
- **Khung SMTP chờ điền credential:** Cường dựng sẵn cấu hình và biến môi trường SMTP trong `.env.example` (chạy test bằng console/mock, đánh dấu riêng mục “chưa kiểm SMTP thật” để bổ sung thông tin SMTP thật sau).

---

## 3. Công việc của Trần Tuấn Cường (`B22DCVT073`)

### 3.1. Chặng 1 — `W9-GR-01`: Quyền học liệu và thu hồi quyền xuyên suốt LMS
- [ ] **Lập ma trận quyền:** lần theo đủ các đường xem metadata, preview, file gốc, tải xuống, mở nguồn từ chat, lịch sử và summary; chỉ rõ nơi quyết định quyền đọc, quyền tải bản sạch, điều kiện tài liệu công khai/bảo vệ và điểm có nguy cơ dùng cache cũ. Bắt đầu từ `backend/apps/courses/permissions.py`, `backend/apps/documents/retrieval_scope.py` và `backend/apps/documents/api/`.
- [ ] **Chuẩn bị fixture & hợp đồng nguồn:** hoàn thiện bộ fixture dùng chung (mục 2.1) có thể reset/chạy lại được và bàn giao hợp đồng lọc nguồn cho Dương.
- [ ] **Kiểm API và file:** trên cùng một tài liệu, thử học viên có quyền, học viên lớp bên cạnh, giáo viên khác và Admin chỉ xem tổng hợp. Chuyển chế độ bảo vệ, thay file/phiên bản, gỡ file hoặc thu hồi enrollment sau khi đã mở được tài liệu; kiểm cả URL cũ và tải bản sạch. Không lộ tiêu đề hay trích đoạn nguồn riêng.
- [ ] **Kiểm thời điểm thu hồi giữa lượt:** phối hợp Dương tạo ca tạm dừng sau retrieval (trước khi gửi model) và ca sau khi model trả về (trước khi trả UI). Nếu mất quyền trước khi gửi, prompt không được chứa nguồn đó; nếu mất quyền sau khi gửi, backend kiểm lại trước khi trả kết quả, chặn trả lời cũ và ngăn đọc lại từ cache/lịch sử.
- [ ] **Kiểm chứng & bàn giao Chặng 1:** tái sử dụng và mở rộng `backend/tests/documents/test_material_access.py`, `test_retrieval_scope.py` cùng bộ test quyền lớp. Kiểm ghép UI trực tiếp mở citation tới đúng trang rồi thu hồi quyền và thử mở lại từ chat cũ; gửi bảng quyền, kết quả chạy test và log đã lọc cho Dương tổng hợp `Evidence/W09/`.

### 3.2. Chặng 2 — `W9-ADM-01`: Khung SMTP, xác minh email và bảo mật phiên nền (`SEC-01`)
- [ ] **Khung cấu hình SMTP:** chuẩn hóa cấu hình `EMAIL_BACKEND` SMTP, host, port, TLS, tài khoản gửi, `FRONTEND_ORIGIN` cố định (không lấy từ `Host` header), tắt `PASSWORD_RESET_PREVIEW` ở production; khai báo đủ tên biến trong `.env.example` (không chứa secret) để bổ sung thông tin SMTP thật sau.
- [ ] **API & dịch vụ xác minh email:** bổ sung `email_verified_at`, phiên bản email và token dùng một lần (lưu băm, hạn 24 giờ; gửi lại hoặc đổi email làm vô hiệu token cũ). Triển khai `POST /api/users/email-verification/send/` (giới hạn tối đa 3 lần/giờ/tài khoản, cách nhau 60 giây qua Redis/cache nguyên tử) và `POST /api/users/email-verification/confirm/` gọi hook `on_email_verified(user)` trong cùng transaction. Trả `email_verified` ở API hồ sơ; không cho client tự ghi `email_verified`.
- [ ] **Vô hiệu phiên tức thời (`auth_version`):** bổ sung `auth_version` trên `User`, kiểm tra đồng nhất ở access token, refresh token, `SessionView` và WebSocket. Tăng `auth_version` khi khóa tài khoản hoặc đổi vai trò để token cũ mất hiệu lực ngay ở request tiếp theo (kể cả sau khi mở khóa lại).
- [ ] **Kiểm CSRF đồng bộ backend & frontend:** gắn `@ensure_csrf_cookie` cho `GET /api/users/session/` và thêm `GET /api/users/csrf/` cho các trang công khai; bật kiểm CSRF + `Origin`/`Referer` cho các endpoint dùng cookie (`login`, `token/refresh`, `logout`, Django Admin). Cập nhật `frontend/src/services/api.js` đọc động `csrftoken` từ cookie ở mọi request thay đổi trạng thái kể cả nhánh auto-refresh; giữ tương thích bộ test cũ và thêm test `enforce_csrf_checks=True` cho chuỗi *đăng nhập → F5 → access hết hạn → tự refresh → đăng xuất* và chặn POST thiếu CSRF.
- [ ] **Rate limit đăng nhập cơ bản (`SEC-01`):** giới hạn thử sai đăng nhập theo tài khoản chuẩn hóa (10 lần/15 phút) và theo IP (30 lượt/phút) có `Retry-After`, không khóa vĩnh viễn tài khoản do người ngoài thử sai; đảm bảo log không ghi token xác minh hay dữ liệu nhạy cảm.

---

## 4. Công việc của Vũ Nam Dương (`B22DCVT119`)

### 4.1. Chặng 1 — `W9-GR-02`: Guardrails Ayo, độ đúng citation và `Evidence/W09/`
- [ ] **Kiểm tuyến Ayo thực sự chạy:** lần theo luồng từ UI → backend → retrieval → gateway → model → UI; xác định chính xác model/adapter/runtime đang phục vụ (`backend/apps/ai/rag/guardrails.py`, `rag/citations.py`, `hints.py`, `summary.py`, `frontend/src/components/ai/CitationViewer.jsx`). Lọc nguồn theo đúng hợp đồng từ Cường trước khi tạo prompt; coi đoạn tài liệu và lịch sử hội thoại thuần túy là dữ liệu.
- [ ] **Kiểm chặn lộ và phạm vi:** bao phủ yêu cầu đòi nguồn ngoài lớp, prompt injection vô hại trong tài liệu, hỏi lại nguồn đã gỡ và đổi sang bài khác. Chặn hỗ trợ bị cấm ở bài `TEST` trước khi gọi model; bài `PRACTICE` gợi ý đúng bước không lộ đáp án riêng; kiểm lại chủ sở hữu và phiên bản nguồn ở cache, lịch sử, summary và câu hỏi gợi ý nối tiếp trên cả API lẫn UI.
- [ ] **Kiểm citation kỹ thuật và theo từng nhận định:** server xác thực mọi ID citation thuộc tập bằng chứng trong lượt, đúng tài liệu, phiên bản và trang thực (sai ID/trang/hết quyền chuyển nhánh xử lý an toàn). Chấm riêng mức hỗ trợ nội dung theo từng ý (bao gồm câu nhiều trang, trang tồn tại nhưng không hỗ trợ nhận định, và câu thiếu căn cứ); gửi Cường bảng nhận định để kiểm chéo.
- [ ] **Kiểm quota, health và log (tái sử dụng cho Admin):** đối chiếu giới hạn `FR-35` (20 yêu cầu/giờ/học viên, 1 lượt sinh đồng thời, tối đa 5 tác vụ chờ, timeout theo loại), xác nhận yêu cầu vượt quota/hàng đợi đầy dừng trước khi gọi model trong khi luồng đọc tài liệu vẫn hoạt động. Ghi nhận số lượt được phép/bị chặn, số lần gọi model, lý do, độ trễ và token (nếu có); lọc sạch prompt riêng, đáp án, trích đoạn thật, token và secret khỏi log công khai.
- [ ] **Chạy kiểm chứng & tổng hợp `Evidence/W09/`:** chạy bộ ca xác định bằng mock cho các nhánh lỗi và chạy lại các ca đại diện qua Docker + model thật (ghi rõ phiên bản model/runtime, commit và ca mock vs thật). Tổng hợp đầy đủ gói `Evidence/W09/` và báo cáo tuần chuẩn.

### 4.2. Chặng 2 — `W9-ADM-02`: Không gian Admin, tài khoản, duyệt giáo viên, danh mục trường và vận hành (`ADM-01/02`, Mục 5)
- [ ] **Danh mục Trường đang công tác (`Institution`):** thêm model `Institution` (hỗ trợ tiểu học, THCS, THPT, cao đẳng, đại học/học viện, liên cấp), seed idempotent đợt đầu 7 trường đại học/học viện tại Hà Nội theo Mục 5.3 trong `2026-11-24-admin-thanh-toan.md`, `GET /api/users/institutions/?q=&province=&level=` (tối đa 20 kết quả, tìm có dấu/không dấu/viết tắt, giới hạn `q` 100 ký tự, có rate limit) và cơ chế Admin thêm/sửa/import CSV/XLSX có dry-run. Thêm combobox tìm kiếm (debounce 300ms, hủy request cũ, nhánh “Chưa có trường trong danh sách”) trên form đăng ký khi chọn Giáo viên.
- [ ] **Trạng thái duyệt giảng dạy & tự duyệt `.edu.vn` (`TeacherApproval`):** thêm model `TeacherApproval` (`PENDING/APPROVED/REJECTED/REVOKED`, nguồn `AUTO_EDU_VN/ADMIN/LEGACY`, `reason`, `revision`, nhật ký quản trị). Chạy data migration gán `APPROVED/LEGACY` cho giáo viên cũ (thử trước trên bản sao DB; giữ nguyên tài khoản đang bị khóa; chạy lại idempotent). Nối rule chuẩn hóa domain khớp đuôi `.edu.vn` hoàn chỉnh vào hook `on_email_verified(user)` của Cường (khóa cùng bản ghi tránh đua với Admin; không tự duyệt lại `REJECTED`/`REVOKED` hay `STUDENT`).
- [ ] **Rà quyền giảng dạy & giao diện chờ duyệt:** chặn `403 TEACHER_NOT_APPROVED` tại toàn bộ API/service giảng dạy (khóa, lớp, buổi học, học liệu, video, bài kiểm tra, chấm điểm, thông báo, duyệt học viên, cấu hình AI) khi chưa `TEACHER + APPROVED + ACTIVE`. Trên `TeacherHomePage` và trang khóa/lớp: hiển thị banner chờ duyệt (đóng tạm theo phiên + phiên bản trạng thái duyệt, kèm hướng dẫn xác minh email nếu chưa xác minh), làm mờ mọi nút Tạo khóa học/Tạo lớp kèm tooltip bubble hỗ trợ hover/focus/cảm ứng và chặn submit/mở modal.
- [ ] **Quản trị tài khoản & phân quyền Admin (`ADM-01`):** bổ sung service quản trị dùng chung (cho cả API và Django Admin), tách quyền bằng Django groups/permissions (xem tổng quan, quản lý tài khoản, cấp vai trò/duyệt giảng dạy, vận hành), `GET/POST /api/operations/users/`, `PATCH /api/operations/users/{id}/`, đổi vai trò và duyệt/từ chối/thu hồi giáo viên có lý do + nhật ký; chặn tự nâng quyền và chặn mất quản trị viên hữu hiệu cuối cùng kể cả 2 request đồng thời; gọi tăng `auth_version` khi khóa hoặc đổi vai trò.
- [ ] **Không gian Admin & Tổng quan/Vận hành (`ADM-02`):** điều hướng `ADMIN` trong `frontend/src/App.jsx` vào giao diện Admin gồm *Tổng quan*, *Tài khoản (có tab Giáo viên lọc Chờ duyệt/Đã duyệt/Từ chối/Thu hồi)*, *Vận hành*, giữ hồ sơ/đăng xuất/chuông thông báo. `GET /api/operations/overview/` lọc ngày theo `Asia/Ho_Chi_Minh` (nửa mở, có `as_of`, đếm `AssessmentAttempt.submitted_at != null`, không trả nội dung riêng); tab *Vận hành* hiển thị tín hiệu thật của AI, ingestion và quota từ `W9-GR-02` (mất tín hiệu báo rõ “Chưa có dữ liệu” hoặc “Mất kết nối”). Hỗ trợ desktop/mobile, loading/rỗng/lỗi từng khối và thử lại.

---

## 5. Tiêu chí nghiệm thu và đầu ra chuẩn

### 5.1. Tiêu chí bắt buộc khóa Milestone W9 (`Evidence/W09/`)
| Hạng mục | Điều kiện đạt chuẩn cho W9 |
| --- | --- |
| **Quyền và chống lộ** | Toàn bộ ca cấm trong ma trận bị chặn (`403`/`404` phù hợp), **0 trường hợp** lộ nội dung hay metadata riêng trên mọi kênh (API, file, tải bản sạch, citation, lịch sử, summary). Có ca đối chứng người đúng quyền vẫn truy cập bình thường và ca thu hồi giữa lượt đạt yêu cầu. |
| **Citation kỹ thuật** | **100%** citation hiển thị trỏ tới bằng chứng trong lượt, đúng tài liệu, phiên bản và trang được phép. Citation giả, nguồn đã gỡ và link cũ sau thu hồi quyền đều bị chặn/xử lý an toàn. |
| **Citation hỗ trợ nội dung (`NFR-29`)** | `accuracy` = số liên kết ý–nguồn thực sự hỗ trợ / số liên kết ý–nguồn đã chấm; `coverage` = số ý cần nguồn có ít nhất một nguồn hỗ trợ / tổng số ý cần nguồn. Mục tiêu mỗi tỷ lệ **≥ 90%**. Ghi đủ tử số, mẫu số, câu trả lời thiếu ý và tỷ lệ trả lời/từ chối trên câu có đáp án (mẫu số bằng 0 ghi chưa đo). |
| **Guardrails và vận hành** | Ca thiếu căn cứ trả trạng thái phù hợp; ca `TEST` chặn hỗ trợ bị cấm trước khi gọi model và không lộ đáp án; ca đổi bài không dùng lại lịch sử trái phạm vi; đo được quota (`FR-35`) và số lần gọi model. Tách rõ ca dùng mock, ca chạy model thật và ca chưa chạy. |
| **Gói bằng chứng `Evidence/W09/`** | Dương tổng hợp theo mẫu `Evidence/W08/` gồm: `README.md` (sơ đồ luồng dữ liệu, bảng rủi ro → cơ chế → ID test → kết quả, liên kết Issue/PR, hướng dẫn chạy lại demo), `metrics.csv`, `test-results.txt`, `manifest.json`, figures/log đã lọc nhạy cảm và báo cáo tuần 1–2 trang (Planned / Done / Evidence / Problems / Next week + nguồn số liệu). |

*Nguyên tắc chất lượng:* Mọi ca lộ dữ liệu hoặc citation sai quyền đều là lỗi chặn chốt milestone — phải ghi lỗi, sửa và chạy lại trước khi đóng `Evidence/W09/`. Nếu Kaggle gián đoạn, tiếp tục hoàn tất toàn bộ kiểm quyền và ca xác định trong Docker, ghi rõ giới hạn phần model thật còn chờ.

### 5.2. Tiêu chí hoàn thành Chặng 2 (Nền Admin + SMTP)
*Chặng 2 nghiệm thu độc lập, không làm treo việc nộp gói `Evidence/W09/` nếu mốc nộp giảng viên đến trước.*
- **Xác minh email & phiên (`W9-ADM-01`):** chạy xanh test gửi/xác nhận email (hạn 24h, 1 lần, đổi email/gửi lại vô hiệu link cũ, rate limit 3 lần/giờ), chuỗi CSRF *đăng nhập → F5 → access hết hạn → tự refresh → đăng xuất*, chặn POST thiếu CSRF, và token cũ bị từ chối ngay sau khóa/đổi vai trò (kể cả khi mở khóa lại). Đánh dấu riêng trạng thái “chưa kiểm SMTP thật” nếu chưa điền credential SMTP.
- **Admin, duyệt giáo viên & danh mục trường (`W9-ADM-02`):** kiểm đủ đăng ký `STUDENT`, `TEACHER` email thường (`PENDING`), `TEACHER` `.edu.vn` trước/sau xác minh (`AUTO_EDU_VN`), địa chỉ giả đuôi (`.edu.vn.attacker.com`, `fakeedu.vn`), chặn tự gửi `APPROVED`/`ADMIN`; kiểm data migration `LEGACY` trên bản sao DB (giáo viên cũ quản lý được lớp cũ, tài khoản đã khóa vẫn khóa, chạy lại không cấp thêm quyền); kiểm banner/tooltip mọi nút tạo khóa/lớp; kiểm bảo vệ Admin cuối cùng trên 2 request đồng thời; kiểm số liệu Tổng quan sát ranh giới ngày `Asia/Ho_Chi_Minh` và trạng thái tab Vận hành.
- **Lệnh kiểm chứng chuẩn trước bàn giao:**
  ```powershell
  docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test backend python manage.py test apps.users.tests apps.courses.tests apps.operations.tests tests.documents tests.ai --noinput
  docker compose exec -T backend python manage.py makemigrations --check --dry-run
  cd frontend
  npx eslint . --max-warnings 0
  npm.cmd test -- --maxWorkers=2
  npm.cmd run build
  ```
