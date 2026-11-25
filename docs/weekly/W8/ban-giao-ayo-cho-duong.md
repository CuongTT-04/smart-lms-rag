# Bàn giao phần Ayo hiện có cho Vũ Nam Dương (W8-01 / T0)

**Quy ước hồ sơ:** Tài liệu thuộc W8, được chuyển về `docs/weekly/W8/` ngày 24/11/2026. Thông tin HEAD và trạng thái môi trường bên dưới ghi nhận tại ngày bàn giao 18/11.

- **Ngày lập:** 18/11/2026
- **Người bàn giao:** Trần Tuấn Cường (B, B22DCVT073)
- **Người nhận:** Vũ Nam Dương (A, B22DCVT119)
- **Mục đích:** Bàn giao baseline Ayo đang chạy, đường dẫn/lệnh khởi động, log lỗi kiểm thử ngày 17/11 và hợp đồng LMS/file ownership để Dương triển khai W8-02.

---

## 1. Trạng thái Git & Môi trường hiện hành

- **Nhánh làm việc:** `TranTuanCuong_B22DCVT073_W8Tasks`
- **HEAD hiện tại:** `8b180aa` (*Merge pull request #18 from CuongTT-04/VuNamDuong_B22DCVT119_W7Tasks*)
- **Dirty / Untracked files liên quan W8:** `docs/weekly/W8/phan-cong-w8.md`, `docs/weekly/W8/plan-w8-01-cuong.md` (chưa commit).
- **Dịch vụ Docker (`docker-compose.yml`):** gồm 6 service `redis`, `database` (PostgreSQL 16, port host `5433`), `backend` (Django/DRF, port `8000`), `ingestion-worker` (`run_ingestion_worker`), `indexing-worker` (`run_indexing_worker`), `frontend` (React/Vite qua Nginx, port `5173`).
- **Kiểm tra trạng thái thực tế ngày 18/11:** cả 6 container đều đang chạy (`backend`, `database`, `frontend`, `redis` trạng thái `healthy`).

### Danh sách biến môi trường AI cần có (không chứa giá trị bí mật)

Khai báo trong `.env` (tham khảo mẫu tại `.env.example`) và truyền vào `backend` / workers qua `docker-compose.yml`:
- `AI_GENERATOR`: dotted Python path (ví dụ `apps.ai.remote.generate_answer`).
- `AI_GENERATION_CONFIG`: đường dẫn file JSON cấu hình sinh trong container (ví dụ `/app/backend/config/ai/kaggle-dual-gpu.json` hoặc `/app/backend/config/ai/w4-generation-kaggle.json`).
- `AI_EMBEDDING_CONFIG`: `/app/backend/config/ai/embedding.json`.
- `AI_INDEX_DIRECTORY`: `/app/.private/documents/ai/index`.
- `AI_CATALOG_MANIFESTS`: `@index` (nạp danh sách manifest chunk từ `current.json` của index).
- `AI_INFERENCE_URL`: HTTPS base URL (ngrok tunnel tới Kaggle, không có hậu tố `/generate`).
- `AI_INFERENCE_TOKEN`: Bearer token ASCII >= 32 ký tự (khớp với secret `OHAYO_INFERENCE_TOKEN` trên Kaggle).

### Đường dẫn Kaggle cell & script cấu hình thực tế

- **Notebook chính:** `notebooks/generation_setup.ipynb`
  - Cell `ohayo-independent-startup` (index 42): gateway đơn GPU.
  - Cell `ohayo-dual-gpu-startup` (index 44): gateway dual GPU T4 x2.
  - Cell `ohayo-chat-memory-startup` (index 46, kèm guide index 45): gateway dual GPU hỗ trợ giao thức `chat_history_v1` (mới nhất).
- **Scripts hỗ trợ:**
  - `scripts/kaggle_startup_cell.py`, `scripts/kaggle_dual_gpu_cell.py`, `scripts/append_kaggle_dual_gpu.py`, `scripts/append_kaggle_memory.py`
  - `scripts/configure_kaggle_inference.py` (chạy đồng bộ URL/token an toàn vào `.env` và ghi file config JSON, hỗ trợ cờ `--dual-gpu --chat-memory`).
  - Lệnh preflight trên backend: `docker compose exec backend python manage.py check_w4_chat_runtime`.

---

## 2. Kiến trúc và Luồng gọi Ayo hiện tại

1. **Frontend UI (`frontend/src/components/ai/`, `frontend/src/services/ai.service.js`):**
   - `SessionAssistant.jsx`: điều phối theo ngữ cảnh. Nếu không có `exercise` và có `documentId`, render `DocumentAssistant.jsx` (có phiên chat bền vững); ngược lại (hoặc khi có `exercise` cho gợi ý bài tập) render `AssistantForm` gửi thẳng `POST /api/ai/chat/` không tạo conversation.
   - `DocumentAssistant.jsx`: gọi `GET /api/ai/conversations/`, `POST /api/ai/conversations/`, `GET /api/ai/conversations/<id>/`, `POST /api/ai/chat/` (kèm `conversation_id` và `client_message_id`), `PATCH /api/ai/chat/<answer_id>/feedback/`.
   - `ChatAnswer.jsx`, `CitationText.jsx`, `CitationViewer.jsx`: parse nhãn `[1]`, `[2]`, hover xem excerpt, click mở `PdfViewer` đúng `document_id`, `version_id`, `page_number`.
   - `ai.service.js` (`chatErrorMessage`): ánh xạ mã lỗi từ backend (`AI_NOT_ALLOWED`, `SCOPE_CHANGED`, `GENERATION_MISSING_CITATION`, `GENERATION_INVALID_CITATION`, `GENERATION_CONFIG_MISMATCH`, `CONVERSATION_BUSY`, `CHAT_SUPERSEDED`, ...).

2. **Backend API & Policy (`backend/apps/ai/`):**
   - `api/urls.py` & `api/views.py`: expose 4 endpoints dưới `/api/ai/`: `conversations/`, `conversations/<uuid>/`, `chat/`, `chat/<uuid>/feedback/`.
   - `conversations.py`: kiểm quyền sở hữu phiên (`owned_conversation` -> `document_scope` -> `resolve_scope`), chống gửi trùng bằng `client_message_id` (`claim_turn`), giữ 1 lượt `PENDING` mỗi phiên (`CONVERSATION_BUSY`), lease 180s (`expire_turns`), lấy tối đa 4 lượt `COMPLETED` gần nhất làm `history` (không giữ SQL lock trong lúc gọi model), kiểm tra `CHAT_SUPERSEDED` trước khi lưu kết quả.
   - `policy.py` (`enforce_chat_policy`): kiểm tra nếu học viên có `AssessmentAttempt` chế độ `TEST` trạng thái `DRAFT` còn hạn thì chặn toàn bộ AI (`403 AI_NOT_ALLOWED`). Nếu `mode == 'hint'`, kiểm tra bài tập thuộc `PRACTICE`, lọc chỉ giữ thông tin công khai (`assessment_id`, `title`, `description`, `kind`, `question.id/prompt/choices.id/text`), tuyệt đối không gửi đáp án đúng.

3. **Retrieval, Pipeline & Gateway (`services.py`, `runtime.py`, `remote.py`, `rag/`, `inference_gateway.py`):**
   - `services.py` (`answer_chat`): gọi `enforce_chat_policy` -> `resolve_scope` -> `retrieve_dense_authorized` (FAISS + BGE-M3 từ `runtime.py`, kiểm snapshot `current.json` và catalog) -> gọi `runtime.generate` (`remote.generate_answer` hoặc local `integration.generate_answer`) -> `map_output` kiểm chặt chẽ chuỗi `[1]`, `[2]` khớp `references` -> `enforce_chat_policy` & `live_scope` lại lần cuối trước khi trả về.
   - `remote.py` -> Kaggle `inference_gateway.py` (`start_gateway`): gửi `POST /generate` qua HTTPS ngrok kèm Bearer token, validate schema `used_source_ids` và `memory` (`protocol == 'chat_history_v1'`, `turns_used <= 4`, `history_tokens <= 768`).

---

## 3. Hiện trạng kiểm định ngày 17/11 & Các vấn đề đã ghi nhận

Log kiểm ban đầu được lưu tại `.private/lms-live-audit-20261117/`:
- `live-ai.txt`: kết quả gọi thật 2 câu CPU qua backend–Kaggle (đều `ANSWERED`).
  - Câu *"ALU là gì?"* (~38.6s): trả về 3 ý đều gắn `[1]`, trong đó ý 3 liệt kê các đơn vị con (cộng, trừ, nhân, chia, dịch, quay, logic cơ bản) nhưng trích đoạn chunk `3612ddc3-...` (trang 23) không chứa các chi tiết đơn vị con đó -> **citation chưa hỗ trợ hết ý**.
  - Câu *"Mỗi chu kỳ lệnh CPU được mô tả theo các bước nào?"* (~80.5s): lấy đủ trang 8–9 và gắn `[1]`, `[2]` theo bước.
- `backend-docker-tests.txt`: chạy 353 tests trong Docker, kết quả `FAILED (failures=7, errors=11)`:
  - **10 errors tại `tests.common.test_classroom_sessions.ClassroomSessionTests`:** `psycopg.OperationalError: the connection is closed` (thuộc phạm vi T1 của Cường điều tra).
  - **1 error + 7 failures tại `tests.common.test_schema.OpenAPITests`:**
    - `test_error_responses_include_real_shapes_and_pagination_not_found` (`KeyError: 'additionalProperties'`)
    - `test_every_operation_has_concise_vietnamese_documentation` cho 4 operations mới của AI (`/api/ai/conversations/` GET/POST, `/api/ai/conversations/{conversation_id}/` GET, `/api/ai/chat/{answer_id}/feedback/` PATCH)
    - `test_schema_validates_and_documents_all_business_operations` (thiếu 5 endpoint AI trong expected set)
    - `test_schema_swagger_and_health_are_public` và `test_write_operations_use_bearer_security_without_csrf_header` (`DatabaseOperationForbidden` trên `SimpleTestCase`)
    *(Nhóm OpenAPI/schema chat này thuộc phạm vi I3 của Dương).*
- **Giới hạn trạng thái hiện tại:**
  - Baseline hiện tại **mới có QA và hint**; chưa triển khai mode `summary` và `câu hỏi gợi ý tiếp theo` (thuộc W8-02 do Dương triển khai). Chưa thực hiện review đầy đủ cho summary và multi-turn memory với model thật trên tập kịch bản W8.
  - Quyền buổi học nháp (`session_views.py`, `documents/access.py`), lưu trữ bền vững `study_notes.py` (hiện vẫn dùng `LocMemCache`), và lỗi `ai/policy.py` giữ khóa AI khi bài kiểm tra bị gỡ/thu hồi quyền thuộc phần I1/I2 của Dương.
  - Phụ thuộc phía Cường ở W8-01 (T5): `AssessmentRunner.jsx` hiện còn nút `"Trợ giúp AI"` gọi `POST .../assistance/` trả về thông báo tĩnh `"Chưa kết nối mô hình AI..."` từ `AssessmentAssistanceView`; cần hợp đồng hint thống nhất từ Dương để hợp nhất hai nút trợ giúp.

---

## 4. Hợp đồng LMS & Ranh giới Ownership W8

### Hợp đồng trạng thái bài tập, tiến độ và quyền LMS (phía Cường quản lý)
- **Định nghĩa hoạt động tính tiến độ:** PDF đã công bố (theo `published_version`), Video đã công bố, Assessment đã công bố trong buổi học không nháp (`is_draft=False`) và không bị gỡ (`removed_at__isnull=True`).
- **Quy tắc hoàn thành & Công thức:**
  - PDF: xác nhận chủ động theo cặp duy nhất `(enrollment, document_version)`; đổi phiên bản công bố thì bản mới chưa hoàn thành.
  - Video: theo `VideoProgress.completed_at` của server.
  - Assessment: có ít nhất 1 `AssessmentAttempt` trạng thái `SUBMITTED` (tính cả auto-submit/chờ chấm; không tính `DRAFT`).
  - `percent = round(completed_activities / total_activities * 100, 2)` (tổng = 0 -> `percent=0, has_activities=false, completed_at=null`).
- **Trạng thái bài làm & Chính sách AI cần giữ:**
  - `Assessment.mode`: `PRACTICE` (cho phép AI hint) vs `TEST` (chặn AI khi có attempt `DRAFT` còn hiệu lực).
  - `Enrollment.status`: `ACTIVE`, `COMPLETED`, `WITHDRAWN` (khi bị thu hồi `WITHDRAWN`, không cho phép đọc/ghi học liệu hoặc dùng AI trong lớp đó).
  - Tuyệt đối không đưa đáp án đúng (`correct_choice_ids` / `solutions_published` / rubric) vào context của AI.

### Ranh giới Ownership file theo `phan-cong-w8.md`
- **Cường (W8-01):** `apps/courses/` (progress models/services/APIs, classroom results/analytics, assessment reports/views, demo seed), `frontend/src/components/ClassroomResults.jsx`, `LearningProgress.jsx`, `ClassroomRoster.jsx`, `ClassroomWorkspace.jsx`, `AssessmentRunner.jsx` (nhận hợp đồng hint từ Dương).
- **Dương (W8-02):** `backend/apps/ai/`, `backend/apps/documents/` (access, session draft permissions, `study_notes.py`), OpenAPI schema (`test_schema.py` cho AI/documents), UI trợ lý (`components/ai/`), `SessionWorkspace.jsx`, `documents/CourseDocuments.jsx`.
- **Phối hợp file chung / callback:**
  - Khi Dương hoàn tất sửa đổi publish/replace/remove tài liệu trong `apps/documents/`, sẽ cần gắn callback `refresh_classroom_progress(classroom_id=...)` do Cường cung cấp tại T2.
  - `AssessmentRunner.jsx` do Cường giữ, chờ hợp đồng endpoint/payload hint cuối từ Dương để nối hoàn chỉnh ở T5.
