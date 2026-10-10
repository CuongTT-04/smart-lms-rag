# Rà soát biểu đồ lớp và định hướng database W2

Ngày rà soát: 06/10/2026. Cơ sở đối chiếu: SRS hiện tại, tài liệu yêu cầu, phạm vi MVP và các quy tắc nghiệp vụ nhóm đã thống nhất.

## 1. W2 cần thiết kế dữ liệu đến mức nào?

W2 triển khai LMS skeleton và ingestion pipeline, vì vậy cần chốt mô hình dữ liệu cho luồng đăng nhập, giáo viên tạo khóa học, cấp quyền học viên và tải tài liệu. Biểu đồ lớp giúp nhận diện thực thể, thuộc tính và quan hệ; trước khi viết migration, nhóm cần chuyển phần W2 thành ERD, chọn kiểu dữ liệu và xác định khóa chính, khóa ngoại, ràng buộc và chỉ mục.

Không cần xây toàn bộ database của sản phẩm cuối ngay trong W2. Biểu đồ tổng thể vẫn giữ các chức năng đã cam kết để tránh thiết kế phần lõi gây khó khăn khi bổ sung quiz, bài tập, thanh toán, video và trợ lý AI. Phần đánh dấu W2 là ưu tiên thiết kế/triển khai, không phải xác nhận chức năng đã hoàn thành.

| Tài liệu | Cách sử dụng |
|---|---|
| `smartlms_class_diagram.puml` | Biểu đồ lớp tổng thể của sản phẩm và dữ liệu thí nghiệm ngoại tuyến. |
| `smartlms_class_diagram_w2.puml` | Bản lọc các lớp liên quan W2; lấy trực tiếp từ biểu đồ tổng thể bằng PlantUML include. |
| Hai file `.svg` cùng tên | Bản xem có thể phóng to; biểu đồ tổng thể cần chia theo nhóm chức năng khi đưa vào báo cáo để bảo đảm đọc được. |

## 2. Những điểm điều chỉnh chính

| Nội dung trong bản ban đầu | Điều chỉnh và lý do |
|---|---|
| Khai báo lặp `AccessType`, `Visibility`; thuộc tính chưa thống nhất ký hiệu | Giữ một khai báo cho mỗi enum, thống nhất thuộc tính `tên: kiểu` và thể hiện khóa/quan hệ rõ hơn. |
| Quyền truy cập và giá lặp giữa `Course`, `Classroom`, `AccessPolicy`; `Enrollment` đồng thời thuộc khóa học và lớp | Dùng `Course` làm đơn vị khóa học/lớp theo SRS hiện tại; tập trung công khai/riêng tư, miễn phí/có phí và điều kiện tham gia trong `AccessPolicy`; bỏ `Classroom` khỏi mô hình hiện tại. Nếu bổ sung nhiều lớp mở theo từng đợt cho cùng một khóa học thì phải xác định nghiệp vụ cohort riêng trước khi đưa lớp này trở lại. |
| Quan hệ nghiệp vụ phụ thuộc profile; tài khoản chỉ có một trường vai trò | Dùng `User` làm chủ thể, `UserRoleAssignment` ghi vai trò và phạm vi được cấp; profile là thông tin bổ sung, không quyết định quyền. Giáo viên quản lý theo `Course.teacherId`; admin không tự được đọc nội dung riêng. |
| `Lesson` luôn có đúng một `Video` | Bài học có thể chỉ có văn bản/PDF; video là tùy chọn và có phiên bản riêng. |
| Tài liệu chỉ có một file URL và một trạng thái chung | Tách `KnowledgeDocument`, `DocumentVersion`, `IngestionJob`; lưu khóa file gốc riêng, checksum, phiên bản, kết quả trích xuất/chỉ mục và trạng thái tác vụ. Không coi hoàn tất trích xuất là đã sẵn sàng RAG. |
| Chưa có chính sách học liệu/watermark | Học liệu mới mặc định `PROTECTED`: xem có watermark, không tải bản sạch. `PUBLIC_DOWNLOAD` bỏ watermark và cho người đã có quyền đọc tải xuống. Thay file giữ chính sách; đổi chính sách tăng revision; OCR/RAG dùng nguồn sạch riêng. |
| Chunk/citation gắn tài liệu nhưng không gắn phiên bản, chỉ có trang PDF | Chunk và citation gắn `DocumentVersion`; vị trí nguồn hỗ trợ trang PDF, slide PPTX, mục/đoạn DOCX và dòng/đoạn TXT. Citation có thể không có chunk khi tóm tắt nhưng vẫn phải có phiên bản nguồn. |
| Question buộc liên quan checkpoint; mọi Answer buộc có option | Question thuộc đúng một phiên bản quiz hoặc một checkpoint. Option được chọn có thể rỗng với câu chưa trả lời; tự luận nằm trong Assignment, không trộn vào quiz một đáp án. |
| Chưa có phiên bản đề, người chấm và trạng thái công bố điểm | Thêm `QuizVersion`, `AssignmentVersion`; lượt làm/bài nộp giữ phiên bản đã dùng. Bài tự luận nhận văn bản hoặc một file, có người chấm, thời điểm chấm/công bố; giữ quy tắc một lượt, không nộp muộn/nộp lại đã chốt. |
| Checkpoint có cờ tùy chọn quay lại nhưng thiếu dữ liệu người học | Bỏ `rewindOnWrong`; có `CheckpointProgress`, `CheckpointAttempt`, `VideoProgress`. Trả lời sai phải xem lại đoạn quy định trước khi thử lại, trả lời đúng mới qua mốc; server kiểm soát mốc và tiến độ theo phiên bản. |
| Tiền dùng Float, chưa có refund/callback và nguồn cấp quyền | Chuyển sang Decimal, lưu giá/người nhận tiền tại thời điểm mua; bổ sung sự kiện thanh toán, hoàn tiền và `EnrollmentGrant`. Callback phải được xác thực, xử lý lặp an toàn; hoàn tiền không xóa kết quả học tập. |
| `AIExperiment.trafficPercent` và adapter bắt buộc cho mọi thí nghiệm | Chuyển sang mô hình thí nghiệm ngoại tuyến Base LLM/RAG/QLoRA+RAG; adapter và cấu hình RAG chỉ bắt buộc theo phương pháp. Không bổ sung actor nghiên cứu vào LMS. |
| `confidenceScore` chưa có cơ sở hiệu chuẩn | Bỏ trường này; điểm retrieval chỉ dùng phân tích truy xuất, không được trình bày như xác suất câu trả lời đúng. |

## 3. Nhóm bảng ưu tiên trong W2

| Mức ưu tiên | Nhóm bảng | Đầu ra cần kiểm chứng |
|---|---|---|
| Lõi W2 | `User`, `UserRoleAssignment` | Đăng nhập, trạng thái tài khoản và kiểm tra quyền trên server. |
| Lõi W2 | `Course`, `AccessPolicy`, `Enrollment` | Giáo viên tạo khóa học/cấp quyền; học viên chỉ mở khóa học được phép; cấp quyền lặp không sinh bản ghi trùng. W2 chưa cần luồng mua khóa học. |
| Lõi W2 | `Lesson`, `KnowledgeDocument`, `DocumentVersion` | Bài học và PDF văn bản thuộc đúng khóa học; lưu file riêng và metadata/checksum; học liệu mới có chính sách bảo vệ mặc định. |
| Lõi W2 | `IngestionJob` | Tiếp nhận, trích xuất, báo lỗi và thử lại; retry không nhân đôi dữ liệu, tác vụ cũ không phục hồi tài liệu đã gỡ. |
| Bổ sung theo luồng demo | `LessonDocument`, `AuditLog` | Liên kết tài liệu với bài học khi cần và truy vết thay đổi quyền/học liệu. |
| Thông tin hồ sơ tùy chọn | `StudentProfile`, `TeacherProfile` | Chỉ triển khai nếu giao diện cần mục tiêu học tập/tiểu sử/chuyên môn; không là điều kiện để phân quyền. |

Trong W2, nhóm có thể chứng minh ingestion bằng file và nội dung trích xuất có vị trí nguồn. `DocumentChunk`, embedding và chỉ mục được triển khai ở W3 theo kế hoạch. Không đặt `indexedAt` hoặc công bố tài liệu sẵn sàng trả lời AI khi chưa hoàn tất chỉ mục và các kiểm tra liên quan.

Quiz, tự luận, hoàn thành bài học, trợ lý, thanh toán và video thuộc các giai đoạn tiếp theo. Quiz/tự luận/trợ lý vẫn thuộc MVP, còn thanh toán và video tương tác bắt buộc có ở bản cuối; làm sau W2 không có nghĩa là loại khỏi phạm vi.

## 4. Ràng buộc khi chuyển thành ERD/migration

1. Dùng UUID cho khóa chính, khóa ngoại cho các quan hệ; email/username có chuẩn hóa và ràng buộc duy nhất. Dùng thời gian server có múi giờ rõ ràng.
2. Đặt `UNIQUE(userId, courseId)` cho Enrollment, `UNIQUE(documentId, versionNumber)` cho DocumentVersion, `UNIQUE(lessonId, documentId)` cho LessonDocument và khóa idempotency cho tác vụ. Các ràng buộc phần sau đã được ghi trong ghi chú của từng lớp.
3. `activeVersionId` ban đầu được phép rỗng. Tạo đối tượng cha và phiên bản trước, sau đó kích hoạt trong transaction; phiên bản phải thuộc đúng đối tượng cha và đáp ứng điều kiện phục vụ. Quan hệ vòng này cần được xử lý trong thứ tự migration.
4. Kiểm tra chéo khóa học tại service/transaction: tài liệu và bài học được liên kết phải cùng khóa học; quiz/bài tập phải cùng khóa học với bài học nếu có; người thao tác phải đúng vai trò và phạm vi. Một FK đơn lẻ không đủ kiểm tra các điều kiện này.
5. Quy tắc một đáp án đúng, chủ sở hữu câu hỏi XOR, đề đã sử dụng bất biến và các điều kiện hoàn tiền cần CHECK/UNIQUE thích hợp cùng kiểm tra giao dịch. Không chỉ ghi quy tắc trên biểu đồ rồi bỏ qua khi triển khai.
6. Quan hệ trong biểu đồ không mặc định yêu cầu xóa dây chuyền. Thu hồi thành viên/gỡ học liệu/khóa tài khoản phải giữ những metadata, bài nộp, điểm và dấu vết cần truy vết. File, citation và retrieval vẫn phải bị chặn theo trạng thái hiện hành.
7. Dùng chỉ mục cho FK và các truy vấn chính: thành viên theo user/course; bài học theo course/order; tài liệu theo course/trạng thái; tác vụ theo status/thời gian. Vector/BM25 là dữ liệu dẫn xuất có thể xây lại, không thay thế database quản lý quyền.
8. Không lưu progressPercent/doanh thu/dashboard như các giá trị độc lập thiếu quy tắc đồng bộ. Tính từ dữ liệu gốc; nếu dùng cache hoặc aggregate sau này phải có quy tắc cập nhật và đối soát.

## 5. Điểm cần đồng bộ khi triển khai

Quy tắc video trong biểu đồ dùng mô tả cụ thể đã thống nhất: sai phải quay lại xem đoạn được định trước rồi mới thử lại. Những chỗ SRS/use case còn diễn đạt “có thể quay lại” cần được đồng bộ trước nghiệm thu chức năng video để tránh cách hiểu đây là lựa chọn của người học.

Biểu đồ là thiết kế dữ liệu đề xuất, chưa phải migration đã chạy hoặc bằng chứng sản phẩm đã hoạt động. Phạm vi quản trị được biểu diễn bởi `grantedScopes`; danh sách quyền cụ thể, các CHECK/index và ánh xạ kiểu dữ liệu của ORM cần được chốt trong ERD và thiết kế API của W2.

## Cập nhật B1 ngày 07/10/2026

Thiết kế phần học liệu tại `w2-document-erd.md` bổ sung trạng thái DocumentVersion EXTRACTED trước READY và payload digest/lease cho IngestionJob. W2 trích xuất đủ chưa đồng nghĩa chỉ mục RAG sẵn sàng. Nhóm đã xác nhận Django/DRF + JWT Bearer; FK và endpoint cụ thể cần đối chiếu phần A.
