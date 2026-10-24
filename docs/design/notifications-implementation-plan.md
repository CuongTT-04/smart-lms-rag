# Kế hoạch triển khai chuông thông báo realtime

> Thực hiện lần lượt bằng skill executing-plans; dùng kiểm thử trước khi viết phần triển khai và ghi kết quả từng bước. Chưa commit/push hoặc xóa thay đổi đang có.

**Mục tiêu:** thông báo đúng người, lưu khi offline, nhận realtime khi online, đồng bộ đọc và mở đúng nội dung.

**Kiến trúc:** PostgreSQL lưu lịch sử cùng transaction nghiệp vụ; Django Channels + Redis phát tín hiệu sau commit. API xác thực trả nội dung và kiểm tra quyền đích đến. React dùng provider cấp tài khoản và bộ điều hướng hiện có.

**Công nghệ:** Django/DRF, PostgreSQL, Channels, channels_redis, Daphne, Redis, React, Vitest, Docker/Nginx.

**Thiết kế:** [notifications-design.md](notifications-design.md).

**Cách thực hiện đề xuất:** tự triển khai trong phiên hiện tại; review độc lập cuối đợt. Giữ nguyên nhánh và thay đổi chưa commit hiện có vì video/bài tập đang được tích hợp tại đây; không tạo checkout thiếu các thay đổi này.

## Ràng buộc chung

- Không thêm RabbitMQ/email/push/nhắc hạn/@mention; không dựng nghiệp vụ ban/lịch học chưa có.
- API và giao diện tiếng Việt; chỉ người nhận xem được thông báo của mình.
- PostgreSQL là nguồn dữ liệu chính; Redis lỗi không làm mất nghiệp vụ đã commit.
- Không dùng JWT trong URL, không mở Redis ra máy chủ, không đưa token vào log.
- Bản nháp/điểm ẩn không lộ; không thông báo cho chính người thực hiện.
- Không reset database/volumes, không sửa dữ liệu người dùng để chạy demo.

## Trọng tâm review

1. Tài khoản đổi trong lúc request/socket đang chạy: không hiển thị dữ liệu tài khoản cũ.
2. Mất Redis hoặc tiến trình chết sau commit: DB vẫn lưu, tải bù không tạo trùng.
3. Quyền lớp bị thu hồi sau sự kiện: không rò nội dung qua API lịch sử hoặc đích đến.
4. Công bố lại sau thu hồi: sự kiện mới được lưu, retry cùng chuyển trạng thái không trùng.
5. Nộp tự động hoặc công bố điểm hàng loạt: phát đúng người và không lộ điểm trước khi cho phép.

## Bước 1: Kho thông báo và API riêng tư

**Tệp:** tạo `backend/apps/notifications/{__init__,apps,models,services,targets}.py`, `api/{__init__,views,serializers,urls}.py`, migration đầu tiên và `backend/tests/common/test_notifications.py`; sửa settings/urls.

**Giao tiếp:** `notify(event_id, recipients, actor, kind, title, body, context)` nhận danh sách user ID; trả các thông báo mới tạo. `context` chỉ gồm ID và loại tài nguyên đã kiểm tra. `resolve_target(notification, user)` trả đối tượng điều hướng hoặc lỗi tài nguyên không khả dụng.

- [ ] Viết test lưu offline, unique event/người nhận, loại người thực hiện, rollback, quyền API, phân trang, đọc lặp, đọc tất cả và quyền bị thu hồi.

```python
with transaction.atomic():
    notify(event_id="event-1", recipients=[student.pk], actor=teacher,
           kind="SESSION_PUBLISHED", title="Buổi học mới", body="",
           context={"course_id": str(course.pk), "classroom_id": str(room.pk)})
notify(event_id="event-1", recipients=[student.pk], actor=teacher,
       kind="SESSION_PUBLISHED", title="Buổi học mới", body="", context={})
assert Notification.objects.filter(recipient=student, event_id="event-1").count() == 1
```

- [ ] Chạy `docker compose exec -T backend python manage.py test tests.common.test_notifications --settings=config.settings.test --noinput`; dự kiến thất bại do app chưa có.
- [ ] Tạo model UUID, unique `(event_id, recipient)`, read_at, context; service `get_or_create`/bulk insert có chống trùng; POST read/read-all idempotent; paginated GET có unread_count. Read-all lọc created_at đến thời điểm server nhận thao tác. Target resolver kiểm tra lại course/class/session và publication của tài nguyên.
- [ ] Đảm bảo serializer chỉ trả nội dung tối thiểu khi quyền mất; không trả context riêng qua đường bỏ qua kiểm tra.
- [ ] Chạy lại bộ test trên; dự kiến pass. Sinh migration và kiểm tra `makemigrations --check --dry-run` sau khi áp dụng.

## Bước 2: WebSocket có xác thực và Docker

**Tệp:** tạo `backend/apps/notifications/{consumers,tickets,routing}.py`, `test_notification_websocket.py`; sửa requirements, ASGI, settings, Dockerfile backend, compose và Nginx.

**Giao tiếp:** POST ws-ticket trả `{ticket, expires_at}`; ticket Redis TTL30 giây dùng một lần. Socket chỉ phát `{type:"notifications.changed", reason:"created|read|read_all", notification_id}`; thông tin hiển thị tải qua API.

- [ ] Viết test vé hợp lệ/dùng lại/hết hạn, Origin sai, group giả mạo, khóa tài khoản, socket hết hạn access token và Redis lỗi.

```python
socket = WebsocketCommunicator(application, f"/ws/notifications/?ticket={ticket}",
                              headers=[(b"origin", b"http://localhost:5173")])
connected, _ = await socket.connect()
assert connected
assert (await WebsocketCommunicator(application, f"/ws/notifications/?ticket={ticket}").connect())[0] is False
```

- [ ] Chạy test mới; dự kiến fail vì routing chưa có.
- [ ] Thêm Channels/channels_redis/Daphne với khoảng phiên bản tương thích Django đang dùng; vé bí mật qua Redis atomic GETDEL, nhóm do server gán; timer đóng khi hết hạn; kiểm tra Origin allowlist.
- [ ] Service bước1 đăng ký `transaction.on_commit` phát tín hiệu với bắt lỗi và log không chứa vé. Đăng ký logout để ngắt phiên tương ứng; frontend cleanup vẫn bắt buộc.
- [ ] Chuyển backend sang Daphne ASGI; thêm Redis có healthcheck và mạng nội bộ; Nginx `/ws/` proxy HTTP1.1 Upgrade, timeout và log không query string. Giữ endpoint health hiện có.
- [ ] Chạy test bằng layer/cache thử nghiệm tách biệt; kiểm tra tích hợp thật Redis để chứng minh vé chỉ dùng một lần. Build backend và xác nhận HTTP API còn hoạt động.

## Bước 3: Tích hợp ghi danh, lớp, bảng tin và quản trị hiện có

**Tệp:** sửa `courses/enrollment_services.py`, `courses/services.py`, API `session_views.py`, `announcement_views.py`, `comment_views.py`, users services/admin và điểm báo cáo học liệu hiện có; tạo helper `notifications/events.py` và `test_notification_events.py`.

**Giao tiếp:** helper tìm owner và học viên đủ quyền từ DB; không dựa vào socket. Context gồm course_id/classroom_id/session_id/announcement_id/comment_id theo từng loại.

- [ ] Viết test theo ma trận thiết kế: đăng ký Admin, yêu cầu/hủy/duyệt/từ chối, ghi danh trực tiếp, thu hồi, mute/bỏ mute, hoàn tất buổi học, tạo lớp/thay đổi quyền, bảng tin, bình luận/reply/xóa bình luận và báo cáo.

```python
review_request(actor=teacher, course=course, request_id=request.pk, decision="approve")
review_request(actor=teacher, course=course, request_id=request.pk, decision="approve")
assert Notification.objects.filter(recipient=student, kind="JOIN_APPROVED").count() == 1
assert not Notification.objects.filter(recipient=outsider, kind="JOIN_APPROVED").exists()
```

- [ ] Chạy test mới trước thay đổi; dự kiến thiếu thông báo.
- [ ] Gọi helper tại chuyển trạng thái thật trong transaction hiện có; lưu snapshot trạng thái trước thay đổi. Mutation chưa bọc transaction thì thêm atomic quanh mutation và tạo thông báo. Với xóa/thu hồi phải chụp tập người nhận trước khi mất quyền.
- [ ] Dùng event ổn định theo bản ghi/chuyển trạng thái; khóa row ở thao tác dễ retry, không phát cho thao tác no-op. Reply và thông báo owner gộp một mục nếu cùng người nhận.
- [ ] Chạy lại test notifications và các test course/enrollment/comments/users; dự kiến pass. Ghi rõ nghiệp vụ chưa có trong tài liệu thay vì tạo API ban mới.

## Bước 4: Học liệu, video, bài tập và điểm

**Tệp:** sửa `documents/services.py` cùng API báo cáo, `courses/video_services.py`, API video/assessment và `assessment_services.py`; mở rộng `test_notification_events.py`.

**Giao tiếp:** context có resource ID loại tài liệu/video/bài tập/attempt; events công bố riêng với sửa nháp. Chính sách điểm hiện có quyết định thông báo kết quả.

- [ ] Viết test công bố/revoke/công bố lại, đổi hạn hợp lệ, nộp thủ công/tự động, chấm nháp không phát, công bố và sửa điểm đã công khai, vi phạm tổng hợp.

```python
finalize(attempt, automatic=True)
finalize(attempt, automatic=True)
assert Notification.objects.filter(kind="ATTEMPT_SUBMITTED", context__attempt_id=str(attempt.pk)).count() == 1
```

- [ ] Chạy test trước; dự kiến fail vì chưa có hook.
- [ ] Gắn hook cùng transaction, giữ nguyên thời hạn/điểm/publication của tính năng đang có. Thông báo vi phạm tổng hợp theo lượt đã nộp, không từng event chuyển tab; không đẩy đáp án/điểm ẩn vào payload.
- [ ] Chạy toàn bộ tests.common và apps.courses.tests; dự kiến không lỗi mới; các skipped sẵn có ghi riêng.

## Bước 5: Provider, chuông, danh sách và điều hướng

**Tệp:** tạo `frontend/src/components/notifications/{NotificationProvider,NotificationBell,NotificationList}.jsx`, stylesheet, tests và `services/notification.service.js`; sửa App, header TeacherHomePage/StudentHomePage/DashboardPage/SessionWorkspace và bộ điều hướng hiện có.

**Giao tiếp:** provider theo user.id quản lý unread_count, list, socket, read(id), readAll(), refresh(). Callback mở context đi qua API target trước rồi chuyển trạng thái navigation đang có; không nhận URL bên ngoài.

- [ ] Viết test dùng WebSocket mock: bootstrap không toast lịch sử, mới đến toast5s, duplicate không thêm, hai tab đọc được đồng bộ, logout cleanup, tài khoản đổi khi request chưa xong, reconnect/backoff/tải bù và API lỗi có retry.

```jsx
render(<NotificationProvider user={student}><NotificationBell onNavigate={navigate} /></NotificationProvider>)
await userEvent.click(screen.getByRole('button', { name: /Thông báo/ }))
expect(await screen.findByText('Buổi học mới')).toBeVisible()
await userEvent.click(screen.getByRole('button', { name: 'Đọc tất cả' }))
expect(screen.queryByLabelText('1 thông báo chưa đọc')).not.toBeInTheDocument()
```

- [ ] Chạy test mới với Vitest; dự kiến import fail trước khi có component.
- [ ] Provider dùng generation/AbortController để chặn response tài khoản cũ; reconnect exponential backoff, resync lúc online/focus/open menu và polling khi mất realtime; hủy toàn bộ timer khi logout.
- [ ] Giao diện chuông badge99+, All/Unread, đọc từng mục/đọc tất cả, danh sách đầy đủ phân trang, empty/error/loading, click ngoài/Esc và keyboard. Toast tối đa3, tự tắt5s; không chồng lên phần kiểm tra fullscreen.
- [ ] Điều hướng tới đúng nội dung qua ID; với bình luận cần tải đúng trang chứa mục thay vì giả định nằm trang đầu, cuộn và highlight ngắn. Giữ browser Back/F5.
- [ ] Chạy test mới, navigation/sessionworkspace tests và `npm run lint`; dự kiến pass.

## Bước 6: Kiểm chứng tích hợp, tài liệu và bàn giao

**Tệp:** cập nhật `docs/api.md`, `docs/SRS.md`, các tài liệu yêu cầu liên quan; thêm sơ đồ `docs/design/notifications-architecture.md` và kết quả kiểm thử.

- [ ] Build Docker backend/frontend và khởi động Redis; migration không xóa dữ liệu. Kiểm tra health các service.
- [ ] Chạy backend test, frontend fulltest và lint; lưu output đầy đủ vào `.private/notification-qa/` để kiểm chứng.
- [ ] Dùng fixture riêng tạo giáo viên/học viên/Admin để thử socket thật; logout học viên, tạo thông báo, đăng nhập kiểm tra còn dữ liệu; mở hai tab kiểm tra đọc; ngắt Redis rồi phục hồi; thu hồi quyền và thử mở thông báo.
- [ ] Chạy kiểm tra security Origin/ticket/auth và quy trình nộp bài/công bố điểm; xóa đúng fixture QA sau khi kết thúc, không chạm dữ liệu người dùng.
- [ ] Review độc lập toàn bộ thay đổi thông báo; sửa các lỗi quan trọng kèm test tái hiện. Không đưa thay đổi video/bài tập có sẵn vào phạm vi sửa không liên quan.
- [ ] Tài liệu nêu giới hạn: không bảo đảm từng gói WebSocket được giao, DB tải bù là cơ chế phục hồi; các nghiệp vụ chưa tồn tại chưa phát được sự kiện; không tự sinh lịch sử trước khi cài chức năng.
- [ ] Báo cáo những gì đã chạy thực tế, kết quả và các giới hạn còn lại. Không commit/push khi chưa được yêu cầu.
