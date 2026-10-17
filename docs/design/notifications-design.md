# Thiết kế thông báo realtime OHAYO

Ngày thiết kế: 17/10/2026. Đã được người dùng duyệt; triển khai ngày 18/10/2026. Phạm vi thực tế và giới hạn vận hành được ghi tại `docs/notifications.md`.

## Mục tiêu và phạm vi

Chuông thông báo cho học viên, giáo viên và quản trị viên; lưu lâu dài theo tài khoản ngay cả khi người nhận logout/offline. Khi đăng nhập lại, lịch sử và trạng thái đã đọc còn nguyên. WebSocket phục vụ người đang online; PostgreSQL là nguồn dữ liệu chính.

Không thêm RabbitMQ, email, push trình duyệt, nhắc hạn tự động, tùy chỉnh đăng ký thông báo hoặc tính năng @mention. Reply hiện có được hỗ trợ. Không tự bổ sung các nghiệp vụ ban/bỏ ban, lịch học hoặc quản trị chưa có chỉ để phát sinh thông báo.

## Kiến trúc

- App Django mới `apps.notifications`, tách models, services, API, consumer và kiểm tra quyền đích đến.
- Django Channels + channels_redis; backend chạy ASGI bằng Daphne. Redis nội bộ Docker, không mở cổng ra máy chủ.
- Bổ sung `/ws/notifications/` qua Nginx với HTTP Upgrade. HTTP API hiện có giữ nguyên.
- Tạo thông báo trong cùng transaction với thay đổi nghiệp vụ. Rollback nghiệp vụ thì không tồn tại thông báo. Sau commit mới phát tín hiệu WebSocket.
- Lỗi Redis không rollback thay đổi nghiệp vụ đã commit; ghi log lỗi, giữ thông báo trong PostgreSQL. Kết nối lại, mở chuông hoặc trở lại cửa sổ sẽ đồng bộ từ API. Khi mất realtime, kiểm tra API định kỳ có backoff để cập nhật badge.
- Không hứa bảo đảm gửi WebSocket từng thông điệp khi tiến trình chết giữa commit và phát. Lịch sử được bảo toàn; transactional outbox và worker retry là mở rộng riêng nếu cần bảo đảm phát lại chủ động.

## Dữ liệu và chống trùng

`Notification`: UUID, event_id, recipient FK, actor FK nullable, kind, title, body ngắn, context JSON chứa các ID khóa học/lớp/buổi học/tài nguyên, created_at, read_at nullable.

- Unique `(event_id, recipient)`; chỉ mục theo `(recipient, created_at, id)` và các mục chưa đọc.
- event_id thuộc một chuyển trạng thái nghiệp vụ; retry cùng thao tác dùng lại event_id. Hai lần công bố thực sự sau thu hồi là hai sự kiện khác nhau.
- Không phát thông báo khi gọi lại thao tác không làm đổi trạng thái. Dùng transaction/row lock ở các điểm chuyển trạng thái có cạnh tranh.
- Frontend upsert theo notification.id, không tăng badge theo số message nhận. Lấy unread_count do server trả và refetch khi nhận tín hiệu.
- Không tự xóa theo thời hạn ở đợt này. Xóa tài nguyên không cascade mất lịch sử thông báo; nội dung đã thu hồi quyền phải được hiển thị ở dạng tối thiểu, không lộ nội dung riêng.

## Xác thực và bảo mật WebSocket

- Frontend dùng access token đang ở bộ nhớ để gọi API nhận vé WebSocket ngắn hạn, dùng một lần. Vé lưu Redis với TTL 30 giây, được tiêu thụ nguyên tử.
- Không đưa JWT/refresh token vào URL. Vé không lưu ở localStorage, không ghi nội dung vé vào log; Nginx tránh ghi query string tại route WebSocket.
- Kiểm tra Origin theo allowlist chính xác cho cả localhost và 127.0.0.1; xác thực vé và tài khoản ACTIVE trước khi join group riêng theo user ID server xác định.
- Socket có thời hạn không vượt quá thời hạn access token dùng cấp vé; hết hạn yêu cầu frontend refresh qua luồng xác thực hiện có và kết nối lại.
- Logout gửi đóng phiên realtime đang liên quan; frontend hủy socket, reconnect timer và request đang chờ, xóa cache thông báo khỏi UI. Không xóa lịch sử database. Tài khoản bị khóa hoặc đổi mật khẩu không tiếp tục nhận nội dung riêng qua socket cũ; message realtime chỉ là tín hiệu đồng bộ, nội dung tải bằng API xác thực lại.
- Client không được tự chọn group hay recipient. Không gửi dữ liệu nội dung riêng qua broadcast toàn hệ thống.

## API và sự kiện

- GET `/api/notifications/?unread=true&page=1`: phân trang 20 mục, newest first với UUID làm thứ tự phụ, kèm unread_count.
- POST `/api/notifications/{id}/read/`: idempotent, chỉ sở hữu của chính tài khoản.
- POST `/api/notifications/read-all/`: chỉ đánh dấu các mục tồn tại ở thời điểm thao tác; notification đến sau vẫn chưa đọc.
- POST `/api/notifications/ws-ticket/`: nhận vé dùng một lần; có giới hạn tần suất.
- GET `/api/notifications/{id}/target/`: kiểm tra quyền hiện tại rồi trả đối tượng điều hướng có cấu trúc, không nhận URL tùy ý từ client; nội dung bị xóa/không còn quyền trả thông báo tiếng Việt phù hợp.
- Socket phát `notifications.changed` cho tạo mới/đã đọc/đọc tất cả; client đồng bộ API. Thay đổi đọc ở một tab được phát tới mọi tab đang đăng nhập của người đó.
- Swagger: summary và description tiếng Việt ngắn gọn.

## Ma trận sự kiện

| Sự kiện | Người nhận và điều kiện |
|---|---|
| Đăng ký tài khoản | Admin đang hoạt động; không gửi dữ liệu mật khẩu/token. |
| Yêu cầu tham gia lớp | Chủ khóa học; hủy yêu cầu cập nhật thông tin liên quan. |
| Duyệt/từ chối yêu cầu | Học viên yêu cầu; duyệt không tạo thêm thông báo tham gia trùng ý nghĩa cho học viên. |
| Tham gia lớp thành công | Chủ khóa học; dùng mã tham gia hoặc phê duyệt đều có sự kiện nhất quán. |
| Thu hồi ghi danh/quyền khóa học | Học viên bị ảnh hưởng, kể cả sau khi quyền đã mất; chỉ nội dung tối thiểu. |
| Mute/bỏ mute | Học viên bị ảnh hưởng; chỉ khi trạng thái thật sự đổi. |
| Tạo/cập nhật/xóa lớp, thay đổi khóa học | Chủ khóa học nếu do người khác thực hiện; học viên chỉ nhận thay đổi ảnh hưởng trực tiếp đến lớp của mình hoặc quyền truy cập. |
| Buổi học được công bố | Học viên có ghi danh và quyền khóa học hợp lệ; không gửi cho bản nháp hoặc chỉ lưu đổi tên khi soạn. |
| Bảng tin mới/cập nhật quan trọng | Thành viên hợp lệ của lớp; không gửi khi chỉ polling/làm mới giao diện. |
| Bình luận mới | Chủ khóa học; reply gửi thêm tác giả bình luận cha, gộp nếu trùng người nhận. Không gửi cho mọi học viên trong lớp. |
| Xóa bình luận của người khác | Tác giả bình luận; thông báo ngắn về thao tác quản lý. |
| Học liệu/video/bài tập công bố | Học viên có quyền trong lớp liên quan; học liệu chỉ gắn ở cấp khóa học dùng phạm vi khóa học tương ứng. |
| Thu hồi/xóa nội dung đã công bố | Học viên từng được phép truy cập tại thời điểm chuyển trạng thái, tránh lộ bản nháp. |
| Thay đổi hạn nộp/nội dung đã công bố | Học viên đang có quyền; chỉ trường thực sự thay đổi. Hiện hạn nộp bị khóa sau khi có lượt làm thì tiếp tục giữ quy tắc đó. |
| Nộp bài thủ công/tự động | Chủ khóa học; một thông báo cho mỗi lượt chuyển sang SUBMITTED, gồm tự nộp quiz khi hết hạn. |
| Công bố/cập nhật điểm và nhận xét | Chính học viên có bài làm; điểm ẩn không bị lộ trong thông báo. Công bố hàng loạt xử lý theo từng người nhận, không phát thông báo giả khi chấm nháp. |
| Vi phạm kiểm tra | Tổng hợp cho giáo viên theo một lượt làm khi lượt làm kết thúc; log chi tiết vẫn ở dashboard, không đẩy mỗi lần chuyển tab. |
| Báo cáo học liệu | Chủ khóa học và Admin phù hợp; thông tin ngắn, dẫn đến luồng báo cáo hiện có nếu có giao diện. |
| Khóa/mở tài khoản | Admin khác; người bị tác động chỉ đọc lại khi tài khoản được phép đăng nhập, không mở ngoại lệ xác thực. |

Người thực hiện bị loại khỏi danh sách nhận. Việc duyệt trạng thái không được bỏ sót người offline. Người nhận được xác định tại thời điểm sự kiện, không dựa trên danh sách socket đang kết nối. Chỉ tích hợp các nghiệp vụ có thật trong code; phần chưa có phải ghi rõ trong bàn giao, không tuyên bố đã hỗ trợ.

## Giao diện và điều hướng

- NotificationProvider cấp ứng dụng theo user ID; một kết nối cho mỗi tab. Đổi tài khoản không tái sử dụng dữ liệu người trước.
- Chuông ở header học viên, giáo viên, trang quản trị và workspace buổi học; badge 99+, popup Tất cả/Chưa đọc, Đánh dấu đã đọc, Đọc tất cả và Xem tất cả.
- Trang danh sách đầy đủ có phân trang, trạng thái rỗng/loading/lỗi và thử lại. Menu đóng bằng Esc/click ngoài, dùng bàn phím được.
- Toast 5 giây chỉ cho thông báo mới nhận sau khi kết nối, không phát toàn bộ lịch sử khi đăng nhập. Giới hạn số toast hiển thị đồng thời.
- Mở thông báo dùng context ID và bộ điều hướng có sẵn; vào đúng lớp, bảng tin/bình luận, buổi học, video, PDF hoặc bài tập. Không chỉ đưa về dashboard. Đánh dấu đã đọc giữ nguyên nếu tài nguyên không còn mở được.
- Không tự điều hướng hoặc làm gián đoạn bài kiểm tra đang fullscreen. Nút chuông bên ngoài vùng làm bài; thông báo đến vẫn được lưu và cập nhật badge sau khi kết thúc.
- Vibe xanh đậm/xanh nhạt hiện có, màu cam làm điểm nhấn, responsive và tôn trọng reduced-motion.

## Điểm tích hợp dự kiến

- `backend/apps/courses/enrollment_services.py`, `services.py`, API session/announcement/comment, video_services/API và assessment_services/API.
- `backend/apps/documents/services.py` và các luồng báo cáo hiện có; `backend/apps/users/services.py` và Django admin cho chuyển trạng thái tài khoản.
- `backend/config/asgi.py`, settings, urls; requirements; docker-compose; Dockerfile backend; Nginx frontend.
- `frontend/src/App.jsx`, HeaderProfile và header trong các trang TeacherHomePage/StudentHomePage/DashboardPage/SessionWorkspace; điều hướng `useHistoryState`.
- Phần `apps.operations` hiện là khung rỗng, vì vậy không coi đó là API quản trị đã hoàn chỉnh. Phần thông báo Admin được xây dựng trên các hoạt động và trang hiện có.

## Kiểm chứng bắt buộc khi triển khai

1. Tạo hoạt động lúc học viên logout, đăng nhập lại vẫn thấy mục chưa đọc; đọc rồi logout/login trạng thái còn nguyên.
2. Hai tài khoản khác lớp không nhận/đọc thông báo của nhau; không truy cập được ID người khác, socket không giả mạo group.
3. Rollback không tạo thông báo; gọi lại/retry/concurrent request không tạo trùng; công bố lần mới sau thu hồi vẫn có thông báo mới.
4. Hai tab nhận thông báo và đồng bộ đọc; thông báo đến cùng lúc đọc tất cả không bị mất trạng thái chưa đọc.
5. Redis/socket mất kết nối vẫn lưu DB; phục hồi tải bù, không nhân đôi hoặc phát lại toast lịch sử.
6. Vé hết hạn/dùng lại/sai Origin bị từ chối; logout/unmount/đổi tài khoản không reconnect bằng phiên cũ.
7. Bản nháp và điểm chưa công bố không lộ; kick/xóa nội dung dẫn đến trạng thái phù hợp, không lọt quyền.
8. Test hook nghiệp vụ cho từng dòng ma trận đang có; kiểm tra thao tác tự nộp và công bố điểm hàng loạt.
9. Frontend tests, lint, backend tests/migrations/schema, Docker build/health và kiểm tra WebSocket thật với hai tài khoản.
10. Cập nhật SRS, API và sơ đồ kiến trúc thông báo; ghi rõ giới hạn và các nghiệp vụ chưa tồn tại.
