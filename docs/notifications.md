# Chuông thông báo OHAYO

Triển khai ngày 18/10/2026. Thiết kế và kế hoạch ở `docs/design/notifications-*.md`.

## Cách sử dụng

Chuông nằm cạnh ảnh đại diện; trong buổi học nằm ở thanh công cụ trên cùng. Badge là số chưa đọc, hiển thị tối đa `99+`. Mở chuông để xem Tất cả/Chưa đọc, đánh dấu từng mục hoặc Đọc tất cả. Xem tất cả mở danh sách đầy đủ có phân trang. Thông báo mới nhận qua WebSocket có toast 5 giây; lịch sử tải khi đăng nhập không phát lại toast.

Nhấn thông báo sẽ đánh dấu đã đọc, kiểm tra quyền rồi mở lớp, bảng tin/bình luận, buổi học, video, bài tập hoặc lượt nộp tương ứng. PDF cấp khóa học mở trong trình xem học liệu. Thông báo quản trị mở chi tiết chỉ đọc về tài khoản/báo cáo; không bổ sung các công cụ quản trị chưa có.

## Sự kiện đang tích hợp

- Tài khoản mới đến Admin; thay đổi trạng thái tài khoản đến Admin và tài khoản bị ảnh hưởng.
- Yêu cầu tham gia/hủy yêu cầu đến giáo viên; duyệt/từ chối đến học viên; ghi danh đến giáo viên; thu hồi quyền đến học viên.
- Mute/bỏ mute, thay đổi hoặc gỡ lớp, thay đổi khóa học đã công bố.
- Hoàn tất tạo buổi học, cập nhật tên hoặc gỡ buổi học đã công bố.
- Bảng tin mới, bình luận mới, reply và xóa bình luận của người khác.
- Công bố/thu hồi/gỡ/cập nhật học liệu, video và bài tập; không gửi cho bản nháp.
- Nộp bài thủ công/tự động đến giáo viên, vi phạm tổng hợp theo lượt khi nộp; công bố và cập nhật điểm/nhận xét đến học viên, không đưa điểm ẩn vào thông báo.
- Báo cáo học liệu đến chủ khóa học và Admin. Báo cáo gửi trong ghi chú PDF vốn là chức năng prototype; nội dung tóm tắt được lưu trong thông báo, không biến kho ghi chú tạm thành hệ thống xử lý báo cáo bền vững.

Không gửi cho chính người thực hiện. Người nhận dựa vào ghi danh/quyền hiện tại trong DB, không dựa vào việc có socket online. Đăng xuất không xóa lịch sử hoặc trạng thái đã đọc. Nội dung lịch sử được tối giản khi quyền bị thu hồi; các thông báo cá nhân về thu hồi/mute vẫn cho biết hoạt động áp dụng với chính người nhận.

## API

| Phương thức | Đường dẫn | Mục đích |
|---|---|---|
| GET | `/api/notifications/?page=1&unread=false` | Phân trang 20 mục, có `unread_count`. |
| POST | `/api/notifications/{id}/read/` | Đánh dấu đã đọc; idempotent. |
| POST | `/api/notifications/read-all/` | Đọc tất cả thông báo tồn tại tại thời điểm thao tác. |
| GET | `/api/notifications/{id}/target/` | Kiểm tra quyền, trả context điều hướng. |
| POST | `/api/notifications/ws-ticket/` | Vé một lần TTL30 giây, giới hạn 30 lần/phút. |
| WebSocket | `/ws/notifications/?ticket=...` | Tín hiệu `notifications.changed`, không chứa JWT/nội dung riêng. |

Mỗi endpoint chỉ thao tác inbox của chính người đăng nhập. GET target kiểm tra lớp, quyền khóa học, buổi học, tài nguyên và công bố hiện tại. ID không thuộc người gọi trả 404. Vé WebSocket tiêu thụ nguyên tử trong Redis; Origin phải nằm đúng allowlist. Socket hết hạn theo access token và tự kết nối lại qua luồng refresh hiện có. Logout đóng socket và hủy request/timer của giao diện.

## Vận hành và giới hạn

- `docker compose up -d --build` tạo Redis nội bộ và chạy backend ASGI bằng Daphne. Migration `notifications.0001_initial` chỉ thêm bảng mới.
- `NOTIFICATION_REDIS_URL` mặc định `redis://redis:6379/0`; `CORS_ALLOWED_ORIGINS` cũng là allowlist Origin WebSocket. Khi đổi domain/port frontend cần cập nhật cấu hình này.
- Redis giữ vé và channel layer, không giữ lịch sử thông báo. Redis lỗi sau commit không rollback nghiệp vụ; DB vẫn có inbox. Giao diện tải bù lúc reconnect/focus/online và định kỳ30 giây.
- Không có cam kết giao từng gói realtime. Nếu cần retry chủ động sau sự cố tiến trình, bổ sung transactional outbox/worker ở đợt riêng.
- Không tạo hồi tố thông báo từ hoạt động trước khi cài chức năng. Không tự xóa lịch sử theo thời hạn trong đợt này.
- Không thêm ban/bỏ ban riêng cho lớp, lịch học, email, push trình duyệt, nhắc hạn tự động hoặc @mention. Khi nghiệp vụ tương ứng được triển khai mới nối thêm sự kiện; reply hiện có đã hỗ trợ.
- Vi phạm được tổng hợp theo lượt nộp, không gửi mỗi lần chuyển tab. Bài chưa nộp xem log trực tiếp trong dashboard; cơ chế tự nộp quiz hiện tại vẫn được kích hoạt khi API xử lý lượt đã hết hạn.
- Các thay đổi nghiệp vụ đi qua ORM save/delete/service được theo dõi; `QuerySet.update`, SQL ngoài ứng dụng hoặc sửa trực tiếp DB không tự sinh thông báo. Luồng xóa lớp và thu hồi quyền dùng cập nhật hàng loạt hiện có đã được bổ sung sự kiện tại service.
- Hai tab không được âm thầm đổi chủ thể JWT khi refresh cookie thuộc tài khoản khác; tab cũ yêu cầu đăng nhập lại.

## Kiểm chứng

Các bộ test nằm tại `backend/tests/common/test_notification*.py`, `frontend/src/components/notifications/*test*` và kiểm thử refresh JWT trong `frontend/src/services/api.test.js`.

Đã kiểm tra tích hợp WebSocket thật qua Nginx: tạo bảng tin, nhận tín hiệu, đồng bộ đọc, từ chối vé dùng lại/Origin ngoài allowlist và logout → phát sinh hoạt động → đăng nhập lại giữ lịch sử đã đọc/chưa đọc. Tài khoản/course kiểm thử được tạo riêng và dọn sau kiểm tra.
