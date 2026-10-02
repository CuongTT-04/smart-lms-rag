# Yêu cầu chức năng và phi chức năng của hệ thống LMS thông minh

- **Đề tài:** Xây dựng hệ thống quản lý học tập thông minh tích hợp mô hình ngôn ngữ lớn tinh chỉnh và kỹ thuật RAG.
- **Sinh viên thực hiện:** Trần Tuấn Cường.
- **Hạng mục:** Xác định functional và non-functional requirements.
- **Ngày lập:** 01/10/2026.
- **Ngày cập nhật:** 02/10/2026.

## 1. Mục đích và phạm vi phân tích

Hệ thống được xây dựng để giáo viên tổ chức khóa học và học liệu, đồng thời hỗ trợ học viên học tập thông qua quiz, bài tập và trợ lý AI. Trợ lý sử dụng tài liệu của từng khóa học để trả lời câu hỏi, gợi ý cách làm bài và tóm tắt nội dung. Người học có thể đối chiếu câu trả lời với nguồn trích dẫn thay vì chỉ tiếp nhận thông tin do mô hình sinh ra.

Trong phần việc này, em chuyển kết quả [phân tích actors và use cases](actors-usecases.md) thành các yêu cầu có thể thiết kế, triển khai và kiểm thử. Yêu cầu chức năng mô tả những hành vi hệ thống cần thực hiện. Yêu cầu phi chức năng xác định chất lượng, điều kiện vận hành và các giới hạn cần kiểm soát khi thực hiện những hành vi đó.

Phạm vi bao gồm nghiệp vụ LMS, xử lý học liệu và trợ lý theo khóa học. Các yêu cầu đối với corpus, huấn luyện QLoRA và benchmark được tách thành nhóm nghiên cứu. Thanh toán, doanh thu, video tương tác và nguồn kiến thức tổng quát được triển khai sau MVP nhưng thuộc phạm vi sản phẩm cuối. Chức năng được chọn và giới hạn triển khai đã được cụ thể hóa trong [phạm vi MVP](mvp-scope.md) và [SRS phiên bản 1.1](../SRS.md); tài liệu này đặc tả toàn bộ danh mục yêu cầu của sản phẩm cuối để truy vết.

## 2. Quy ước và điều kiện áp dụng

### 2.1. Mã yêu cầu và mức ưu tiên

| Ký hiệu | Ý nghĩa |
|---|---|
| FR-xx | Yêu cầu chức năng của sản phẩm LMS. |
| FR-Rxx | Đầu ra nghiên cứu, huấn luyện và đánh giá của đồ án; không phải chức năng dành cho người dùng LMS. |
| FR-Xxx | Yêu cầu sản phẩm triển khai sau MVP; mã được giữ để truy vết, không có nghĩa tùy chọn. |
| NFR-xx | Yêu cầu phi chức năng hoặc tiêu chí chất lượng. |
| P0 | Ưu tiên luồng tạo khóa học, tải học liệu và hỏi đáp có nguồn. |
| P1 | Hoàn thiện nghiệp vụ học tập, quản lý và chất lượng của sản phẩm. |
| Sau MVP | Chức năng thuộc sản phẩm cuối, triển khai sau giai đoạn nguyên mẫu và vẫn bắt buộc nghiệm thu. |

Mã UC, BR và AC được giữ thống nhất với tài liệu actors/use cases. Một yêu cầu có thể phục vụ nhiều use case; một use case có thể cần nhiều yêu cầu chức năng và phi chức năng.

### 2.2. Cách đọc tiêu chí chấp nhận

Trong các bảng dưới đây, từ **phải** mô tả hành vi bắt buộc trong phạm vi sản phẩm cuối. Đăng ký và lịch sử hội thoại thuộc bản cuối; giai đoạn triển khai được xác định riêng trong ma trận phạm vi. Mức ưu tiên không tự động quyết định một chức năng đã thuộc MVP.

Các yêu cầu phân quyền, bảo toàn dữ liệu và xử lý trạng thái được kiểm tra bằng những tình huống có kết quả xác định. Với chất lượng sinh câu trả lời và hiệu năng, các con số trong mục 4 là **mục tiêu kiểm chứng ban đầu của nguyên mẫu**, được đưa vào phạm vi MVP và SRS, chưa phải kết quả đo. Nhóm sẽ kiểm chứng trên dữ liệu development, ghi cấu hình và quyết định mọi điều chỉnh ngưỡng trước khi đánh giá tập test độc lập.

### 2.3. Điều kiện áp dụng và quy mô kiểm chứng

- Học viên, giáo viên và quản trị viên có vai trò và phạm vi truy cập khác nhau; quyền được kiểm tra trên từng đối tượng dữ liệu.
- Tài liệu phục vụ AI phải có quyền sử dụng, thuộc đúng khóa học và đã xử lý thành công.
- Ba chế độ hỏi đáp, gợi ý và tóm tắt dùng chung kho học liệu được phân quyền, nhưng có cách xử lý riêng.
- Dữ liệu hiện có thuộc ba môn THMLN, KTCTMLN và CNXHKH, gồm 27 PDF và 50 QA pilot: 24 mẫu THMLN của thành viên A, 26 mẫu của thành viên B chia đều KTCTMLN/CNXHKH. Benchmark hoàn thiện đặt mục tiêu tối thiểu 300 mẫu hợp lệ, gồm 100 development và 200 test độc lập, theo phạm vi MVP.
- Tài nguyên thử nghiệm AI dự kiến là GPU T4 của Google Colab Free. Nguyên mẫu cần xử lý được tình huống dịch vụ AI bị ngắt; chưa đặt yêu cầu phục vụ liên tục 24/7.
- Công nghệ model, vector store và cách điều phối được xác định ở phần kiến trúc; các yêu cầu nghiệp vụ không phụ thuộc vào một thư viện cụ thể.

## 3. Yêu cầu chức năng

### 3.1. Tài khoản và xác thực

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-01 | Hệ thống phải cho phép tài khoản đang hoạt động đăng nhập bằng thông tin xác thực hợp lệ. | Đăng nhập đúng tạo phiên gắn tài khoản và vai trò; thông tin sai hoặc tài khoản bị khóa không tạo phiên. | UC-02 | P0 |
| FR-02 | Hệ thống phải cho phép đăng xuất và kết thúc hiệu lực phiên tương ứng. | Sau đăng xuất, sử dụng lại phiên đã kết thúc để gọi API được bảo vệ phải bị từ chối; phiên hết hạn yêu cầu xác thực lại. | UC-02 | P0 |
| FR-03 | Quản trị viên phải có thể tạo, cập nhật và khóa/mở khóa tài khoản theo quyền quản trị. | Thay đổi được lưu; tài khoản bị khóa không tiếp tục thực hiện yêu cầu được bảo vệ; định danh tài khoản trùng bị từ chối. | UC-03 | P0 |
| FR-04 | Hệ thống phải cho phép quản trị viên được cấp quyền quản lý vai trò của tài khoản. | Học viên không thể tự nâng quyền; thay đổi vai trò ảnh hưởng đến các yêu cầu tiếp theo. Thao tác làm mất tài khoản quản trị hoạt động cuối cùng phải được ngăn chặn trong cơ chế cấp quyền được chọn. | UC-03 | P0 |
| FR-05 | Hệ thống phải cho khách đăng ký tài khoản học viên. | Kiểm tra dữ liệu bắt buộc và định danh trùng; mật khẩu lưu bằng cơ chế băm. Tài khoản mới chỉ có vai trò học viên, chưa có quyền khóa học; không tự cấp giáo viên/admin. | UC-01 | P1 |

### 3.2. Khóa học, bài học và thành viên

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-06 | Giáo viên phải có thể tạo và chỉnh sửa thông tin khóa học do mình quản lý. | Giáo viên tạo/sửa khóa học phụ trách với tên, mô tả, trạng thái, loại công khai/riêng tư và miễn phí/có phí; khóa có phí lưu giá hợp lệ phía server. Không được sửa bằng cách thay ID lớp của người khác. | UC-04 | P0 |
| FR-07 | Hệ thống phải cung cấp danh sách và chức năng tìm thông tin giới thiệu của khóa học công khai. | Tìm theo tên/từ khóa, xem giới thiệu và điều kiện tham gia các khóa đang mở, được công khai. Không công bố nội dung học liệu, đáp án hoặc lớp riêng tư qua kết quả tìm kiếm. | UC-05 | P1 |
| FR-08 | Hệ thống phải cấp quyền học khi đáp ứng điều kiện tham gia của khóa học. | MVP dùng giáo viên cấp quyền. Bản cuối hỗ trợ lớp công khai miễn phí tự tham gia, lớp riêng tư xác thực mã/mật khẩu và khóa có phí yêu cầu giao dịch thành công được xác thực. Cấp quyền lặp không tạo bản ghi trùng; các điều kiện riêng tư và có phí phải cùng thỏa mãn khi áp dụng. | UC-06 | P0 |
| FR-09 | Giáo viên phải có thể xem và quản lý thành viên trong khóa học phụ trách. | Cấp/thu hồi quyền theo cơ chế tham gia đã chọn; thay đổi có hiệu lực với truy cập tiếp theo và không tự xóa điểm/lượt nộp đã có. | UC-07 | P1 |
| FR-10 | Giáo viên phải có thể tạo, chỉnh sửa, sắp xếp và liên kết học liệu với bài học. | Giáo viên tạo/sửa bài học văn bản, sắp xếp và liên kết tài liệu/bài đánh giá trong cùng khóa học. Học viên chỉ thấy bài đã công bố; liên kết ngoài quyền bị từ chối. | UC-08 | P1 |
| FR-11 | Hệ thống phải ghi và hiển thị tiến độ học của từng học viên. | Lưu đánh dấu hoàn thành bài theo học viên/bài học; hiển thị tiến độ trên nội dung đã công bố. Với video tương tác, lưu riêng các mốc đã trả lời và tiến độ xem; tải lại/tua/gửi sự kiện lặp không nhân đôi tiến độ hoặc tự chứng minh đã học xong. | UC-09 | P1 |

### 3.3. Quản lý và xử lý học liệu

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-12 | Giáo viên phải có thể tải tài liệu vào khóa học được quản lý. | Kiểm tra quyền, loại file thực tế và giới hạn trước lưu. MVP nhận PDF văn bản; bản cuối nhận PDF, DOCX, PPTX, TXT và PDF quét có thể OCR. Lưu người tải, lớp, file và phiên bản; file chưa xử lý không được báo sẵn sàng. | UC-10 | P0 |
| FR-13 | Hệ thống phải quản lý việc thay thế và gỡ tài liệu theo phiên bản. | Thay thế tạo phiên bản mới, giữ bản cũ hợp lệ đến khi bản mới sẵn sàng. Gỡ ngừng phục vụ retrieval/mở nguồn ngay; kết quả tác vụ cũ không khôi phục bản đã gỡ. | UC-10 | P0 |
| FR-14 | Hệ thống phải xử lý tài liệu ở nền và hiển thị trạng thái cho giáo viên. | Xử lý nền sau tiếp nhận upload; có trạng thái chờ, đang xử lý, sẵn sàng, lỗi và đã gỡ. Chỉ sẵn sàng khi trích xuất, chia đoạn, lưu vị trí, tạo chỉ mục và kiểm tra nội dung hoàn tất. | UC-11 | P0 |
| FR-15 | Giáo viên phải có thể yêu cầu thử lại tác vụ xử lý tài liệu bị lỗi. | Lưu nguyên nhân và kết quả lần thử; thử lại không tạo chunk/chỉ mục trùng hoặc phục vụ sai phiên bản. File đã gỡ không tự xuất hiện lại vì một tác vụ cũ kết thúc. | UC-11 | P0 |
| FR-16 | Pipeline phải trích xuất, chuẩn hóa và chia đoạn học liệu thuộc các định dạng đã chọn. | Bản cuối dùng Docling cho PDF/DOCX/PPTX và OCR PDF quét khi cần; TXT được chuẩn hóa bằng bộ đọc văn bản phù hợp. Mỗi chunk có lớp/tài liệu/phiên bản và vị trí thực: trang PDF, slide PPTX hoặc mục/đoạn DOCX/TXT. Kết quả thiếu nội dung/OCR không đáp ứng kiểm tra chất lượng phải báo lỗi hoặc yêu cầu bản rõ hơn, không âm thầm bỏ phần lỗi. | UC-10–UC-11 | P0 |
| FR-17 | Người có quyền phải có thể xem học liệu và mở vị trí được trích dẫn. | Mở học liệu hoặc vị trí được trích dẫn theo quyền và phiên bản hiện hành. Hiển thị tên nguồn và trang/slide/mục/đoạn thực; cung cấp chỉ dẫn vị trí nếu viewer không nhảy trực tiếp. Không mở nguồn đã gỡ hoặc ngoài quyền qua link cũ. | UC-12 | P0 |

### 3.4. Trợ lý AI theo khóa học

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-18 | Mỗi yêu cầu trợ lý phải được xác định phạm vi khóa học và học liệu theo quyền hiện tại của người gửi. | Backend xác định quyền lớp/học liệu và chính sách theo tài khoản hiện hành. Mọi nhánh retrieval, tóm tắt, ngữ cảnh, lịch sử và cache loại dữ liệu ngoài quyền/đáp án riêng; kiểm tra lại trước khi trả. Nhánh kiến thức tổng quát được tách riêng, không đọc học liệu ngoài quyền. | UC-13–UC-17, UC-X04 | P0 |
| FR-19 | Học viên phải có thể hỏi đáp nội dung trong học liệu khóa học. | Hệ thống nhận câu hỏi, truy xuất bằng chứng và trả câu trả lời theo phạm vi được chọn; lưu/hiển thị trạng thái xử lý khi yêu cầu chưa hoàn thành. | UC-13 | P0 |
| FR-20 | Trợ lý phải có nhánh xử lý câu hỏi mơ hồ, thiếu bằng chứng hoặc ngoài phạm vi học liệu. | Trong chế độ học liệu, câu hỏi mơ hồ yêu cầu làm rõ, thiếu nguồn thông báo giới hạn. Nếu học viên chọn nguồn kiến thức tổng quát theo FR-X04 thì ghi nhãn riêng; không tự fallback mà trình bày câu trả lời như đã được học liệu chứng minh. | UC-13–UC-14 | P0 |
| FR-21 | Câu trả lời sử dụng học liệu phải có thông tin trích dẫn tương ứng. | Câu trả lời dùng học liệu hiển thị tên tài liệu, phiên bản, vị trí trang/slide/mục/đoạn và tham chiếu nguồn. Citation thuộc bằng chứng hợp lệ, đúng quyền; không gán trang PDF cho DOCX khi không có bản phân trang. Nguồn hỗ trợ nhận định được đánh giá riêng ở NFR-29. | UC-12–UC-15 | P0 |
| FR-22 | Trợ lý phải cung cấp gợi ý làm bài theo mức trợ giúp được phép. | Học viên có thể nhận gợi nhắc khái niệm/bước tiếp theo theo chính sách bài hoặc mốc video. Lấy trạng thái từ backend, loại đáp án riêng; bài đang thi/tắt trợ giúp được xử lý theo chính sách, không tự coi là được giải toàn bộ. | UC-14, UC-X03 | P1 |
| FR-23 | Giáo viên phải có thể thiết lập học liệu được sử dụng và chính sách trợ giúp của trợ lý trong khóa học. | Cấu hình phân biệt tài liệu học viên và tài liệu riêng/đáp án; lưu chính sách có phiên bản, áp dụng trong các yêu cầu tiếp theo; không cho phép cấu hình bỏ qua quyền nền tảng. | UC-17 | P1 |
| FR-24 | Học viên phải có thể yêu cầu tóm tắt tài liệu hoặc phạm vi nội dung được chọn. | Tóm tắt một tài liệu hoặc phạm vi trang/slide/mục được chọn. MVP dùng PDF; bản cuối áp dụng các định dạng được hỗ trợ, tối đa 10.000 token nguồn và 20 trang/slide khi định dạng có đơn vị đó. Kiểm tra quyền/độ bao phủ, gắn nguồn; vượt giới hạn yêu cầu thu hẹp, ngắt thì báo phần thiếu. | UC-15 | P1 |
| FR-25 | Hệ thống phải cho học viên lưu, xem lại và tiếp tục hội thoại cá nhân. | Hội thoại/lượt trao đổi gắn học viên và khóa học, được giữ sau restart; học viên có thể xóa lịch sử của mình. Khi mở/tiếp tục phải kiểm tra quyền hiện tại; lớp mất quyền hoặc nguồn đã gỡ không được trả lại từ lịch sử/cache. Giáo viên/admin không mặc định đọc toàn bộ hội thoại. | UC-16 | P1 |

Kiểm tra tham chiếu nguồn tồn tại trong FR-21 là kiểm tra cấu trúc. Việc nguồn có thực sự hỗ trợ nhận định trong câu trả lời hay không được đánh giá riêng ở NFR-29. Tương tự, FR-22 xác định chức năng gợi ý; chất lượng hướng dẫn và mức tuân thủ được đo ở NFR-31.

### 3.5. Quiz, bài tập và kết quả học tập

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-26 | Giáo viên phải có thể tạo và quản lý quiz/bài tập trong khóa học phụ trách. | Lưu quiz một lựa chọn đúng hoặc tự luận/nộp file, đề, hạn/thời lượng, chính sách trợ giúp và công bố. Đáp án/rubric riêng tách khỏi dữ liệu học viên; đề đã có lượt làm giữ nguyên phiên bản. | UC-18 | P1 |
| FR-27 | Hệ thống phải kiểm tra điều kiện và quản lý lượt làm quiz. | Mỗi học viên một lượt quiz, chỉ bắt đầu khi có quyền và còn thời gian. Lượt gắn phiên bản đề; server kiểm soát hạn/thời lượng và chốt câu trả lời đã lưu khi hết thời gian. | UC-19 | P1 |
| FR-28 | Hệ thống phải nhận bài quiz và tự chấm theo đáp án của phiên bản đề tương ứng. | Lưu câu trả lời/điểm nhất quán; yêu cầu nộp lặp không tạo điểm khác nhau cho cùng lượt; chỉ trả kết quả/đáp án theo thời điểm được công bố. | UC-19 | P1 |
| FR-29 | Học viên phải có thể nộp bài tự luận hoặc file cho bài tập được giao. | Nhận một lượt nộp bằng văn bản hoặc một file PDF/PNG/JPEG tối đa 20 MiB trong hạn. Lưu người nộp, phiên bản bài và thời điểm server; không nhận nộp muộn/nộp lại, gửi lặp cùng thao tác không tạo bản ghi trùng. | UC-20 | P1 |
| FR-30 | Giáo viên phải có thể chấm và phản hồi bài nộp trong lớp phụ trách. | Giáo viên lớp phụ trách chấm tự luận thang 0–10, ghi nhận xét, lưu và công bố. Sửa điểm có dấu vết; AI không quyết định điểm chính thức. | UC-21 | P1 |
| FR-31 | Học viên phải có thể xem điểm và phản hồi cá nhân đã được công bố. | Chỉ hiển thị kết quả của đúng học viên; chưa chấm/chưa công bố có trạng thái riêng; không dùng điểm 0 để thay cho kết quả còn thiếu. | UC-22 | P1 |

### 3.6. Thống kê và vận hành

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-32 | Giáo viên phải có thể xem thống kê tiến độ và kết quả trong khóa học phụ trách. | Có phạm vi và thời điểm tính; số liệu khớp dữ liệu học/lượt nộp/điểm; học viên chưa có điểm được phân biệt với điểm 0. | UC-23 | P1 |
| FR-33 | Quản trị viên phải có thể xem thống kê sử dụng nền tảng ở mức tổng hợp. | Dashboard hiển thị người dùng, khóa học, hoạt động và giao dịch/doanh thu theo định nghĩa thống nhất. Có phạm vi/thời điểm tính, phân biệt chờ/thất bại/hoàn tiền; quyền tổng hợp không tự cho đọc nội dung riêng. | UC-24, UC-X02 | P1 |
| FR-34 | Người được cấp quyền vận hành phải có thể theo dõi tình trạng xử lý tài liệu và dịch vụ AI. | Người có quyền vận hành xem trạng thái, loại lỗi và thời gian xử lý AI/ingestion; người dùng có thông báo tương ứng. AI ngắt không báo sẵn sàng; không yêu cầu dashboard tổng hợp toàn nền tảng. | UC-11, UC-25 | P1 |
| FR-35 | Hệ thống phải hỗ trợ cấu hình và thực thi hạn mức sử dụng AI. | Thực thi quota 20 yêu cầu AI/giờ/học viên, một lượt sinh đồng thời, tối đa 5 tác vụ chờ và timeout theo loại tác vụ. Vượt quota/hàng đợi không gọi model tiếp; không ảnh hưởng quyền đọc bài. | UC-25 | P1 |
| FR-36 | Hệ thống phải ghi dấu vết các thay đổi quản trị và nghiệp vụ có ảnh hưởng tới quyền hoặc kết quả học tập. | Ghi người thao tác, đối tượng, thời điểm và loại thay đổi cho cấp/thu hồi quyền, gỡ tài liệu, chỉnh chính sách và sửa điểm; chỉ người có quyền đọc được dấu vết. | UC-03, UC-07, UC-10, UC-17, UC-21, UC-25 | P1 |

### 3.7. Đầu ra nghiên cứu, huấn luyện và đánh giá

Các yêu cầu này được thực hiện qua công cụ hoặc notebook nghiên cứu. Chúng không yêu cầu xây giao diện huấn luyện dành cho người dùng LMS và không đồng nghĩa giao toàn bộ hoạt động nghiên cứu cho một thành viên.

| Mã | Yêu cầu | Tiêu chí chấp nhận | Hoạt động nghiên cứu |
|---|---|---|---|
| FR-R01 | Bộ công cụ nghiên cứu phải hỗ trợ quản lý corpus và QA benchmark có phiên bản. | Mỗi mẫu có câu hỏi, đáp án hoặc hành vi mong đợi, định danh nguồn/vị trí khi có, loại tình huống và split; có manifest, quyền sử dụng và kết quả rà soát dữ liệu. | RES-01 |
| FR-R02 | Quy trình huấn luyện phải tạo và lưu adapter QLoRA từ dữ liệu instruction được kiểm soát. | Có dry-run, cấu hình, checkpoint, log và model/adapter card; tách dữ liệu huấn luyện khỏi nhãn test; ghi lại lỗi OOM/ngắt phiên và điểm tiếp tục nếu có. | RES-02 |
| FR-R03 | Bộ công cụ đánh giá phải chạy và lưu kết quả so sánh Base LLM, RAG và QLoRA+RAG. | Dùng cùng QA và protocol; lưu câu trả lời, context, citation, cấu hình, latency và metric từng mẫu; hỗ trợ khảo sát retrieval dense/hybrid/rerank khi được chọn, ghi nhận lượt lỗi. | RES-03 |
| FR-R04 | Quy trình đánh giá phải hỗ trợ kiểm tra thủ công và phân tích lỗi. | Có rubric và bộ mẫu được chấm; phân loại lỗi truy xuất, sinh câu trả lời, nguồn, từ chối và gợi ý; số liệu báo cáo truy ngược tới kết quả đã lưu. | RES-04 |

### 3.8. Chức năng bản cuối triển khai sau MVP

| Mã | Yêu cầu | Tiêu chí chấp nhận khi triển khai | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-X01 | Hệ thống phải hỗ trợ thanh toán để tham gia khóa học có phí. | Server tạo đơn với giá/điều kiện khóa học đã kiểm tra; xác thực thông báo hoặc đối soát với cổng thanh toán. Chỉ cấp quyền khi giao dịch thành công và đủ điều kiện lớp; callback/gửi lại không cấp quyền hoặc ghi doanh thu nhiều lần. Chờ/thất bại/hủy/hết hạn không cấp quyền; demo kiểm chứng trong sandbox. | UC-X01 | P1 |
| FR-X02 | Hệ thống phải cung cấp lịch sử giao dịch và thống kê doanh thu theo vai trò. | Học viên xem giao dịch cá nhân, giáo viên xem khóa học phụ trách và admin xem tổng hợp theo quyền. Doanh thu là số tiền giao dịch thành công trừ khoản hoàn tiền đã xác nhận, ghi đơn vị tiền/phạm vi/thời điểm. Hoàn tiền có bằng chứng đối soát và dấu vết; không xóa giao dịch cũ. | UC-X02 | P1 |
| FR-X03 | Hệ thống phải hỗ trợ video có câu hỏi tại các mốc thời gian. | Giáo viên quản lý video và mốc hỏi trong bài học; player dừng tại mốc, nhận câu trả lời rồi cho tiếp tục theo cấu hình. Trả lời sai có thể nhận gợi ý được phép hoặc quay lại đoạn đã chỉ định. Mốc/sự kiện gắn học viên và phiên bản, tua/tải lại không tăng tiến độ sai; không để đáp án riêng trong dữ liệu player. | UC-X03 | P1 |
| FR-X04 | Trợ lý phải hỗ trợ lựa chọn nguồn kiến thức tổng quát riêng trong chế độ hỏi đáp. | Mặc định dùng học liệu. Khi thiếu nguồn, học viên có thể chủ động chọn nguồn tổng quát; phản hồi ghi chưa được xác nhận bằng học liệu, không có citation khóa học giả. Tất cả chính sách bài tập, quyền và quota vẫn áp dụng; không dùng lựa chọn này để lấy đáp án riêng. | UC-X04 | P1 |

## 4. Yêu cầu phi chức năng

### 4.1. Bảo mật và quyền riêng tư

| Mã | Yêu cầu chất lượng | Cách kiểm tra và tiêu chí chấp nhận | Liên quan |
|---|---|---|---|
| NFR-01 | Phân quyền phải áp dụng cho API, file, video, retrieval, lịch sử/cache và giao dịch. | Toàn bộ tình huống sai vai trò/lớp/chủ thể bị chặn, gồm media, hội thoại và đơn/giao dịch. Kiểm tra lại trước trả AI khi quyền thay đổi; quyền dashboard không cho đọc dữ liệu riêng. | FR-03–FR-04, FR-06–FR-36; BR-01–BR-02, BR-09 |
| NFR-02 | Thông tin xác thực và bí mật hệ thống phải được bảo vệ khi lưu, truyền và ghi log. | Mật khẩu dùng cơ chế băm mật khẩu thích hợp, không lưu rõ; token/bí mật không xuất hiện trong repo, phản hồi hoặc log. Truy cập từ xa có xác thực phải dùng kết nối mã hóa; cấu hình cookie/token được rà theo cách triển khai đã chọn. | FR-01–FR-04 |
| NFR-03 | File tải lên phải được kiểm tra trước khi lưu vào vùng phục vụ hoặc xử lý. | Kiểm tra file sai loại/giả phần mở rộng, hỏng, vượt giới hạn hoặc tên có ý đồ truy cập đường dẫn; DOCX/PPTX phải được kiểm tra trước parse. Không thực thi file như mã; định danh lưu do hệ thống tạo. Video và học liệu tuân giới hạn riêng. | FR-12, FR-16, FR-29 |
| NFR-04 | Nội dung câu hỏi và học liệu không được thay đổi quyền hoặc chính sách hệ thống. | Dùng bộ test prompt injection từ câu hỏi và tài liệu; kiểm tra không có quyền bị nâng, không truy xuất khóa học khác và không lộ đáp án riêng. Tỷ lệ tuân thủ nội dung sinh ra được báo cáo riêng theo NFR-31. | FR-18, FR-22–FR-23; RES-04 |
| NFR-05 | Hội thoại, dữ liệu đánh giá và log phải có mục đích/phạm vi lưu và truy cập rõ. | MVP giữ ngữ cảnh phiên; bản cuối lưu lịch sử cá nhân, cho xóa và kiểm tra quyền hiện tại. Log không mặc định ghi toàn văn. Thời hạn lưu/cách xóa, mục đích đánh giá và quyền truy cập được cấu hình, ghi rõ trước triển khai. | FR-25, FR-34, FR-36, FR-R04 |
| NFR-06 | Hệ thống phải giới hạn lạm dụng tài nguyên ở các chức năng xác thực, upload và AI. | Gửi yêu cầu vượt cấu hình kiểm thử phải nhận phản hồi giới hạn; không tạo vô hạn tác vụ hoặc hàng đợi. Quota và giới hạn tải lên kiểm tra phía server, không chỉ qua giao diện. | FR-01, FR-12, FR-19, FR-24, FR-35 |

Các tiêu chí bảo mật được kiểm tra trên bộ tình huống đã xây dựng và cấu hình được lưu. Kết quả đạt bộ test không được diễn giải thành bảo đảm chống mọi cách tấn công có thể xảy ra.

### 4.2. Hiệu năng và sử dụng tài nguyên

| Mã | Yêu cầu chất lượng | Điều kiện đo và mục tiêu đề xuất | Liên quan |
|---|---|---|---|
| NFR-07 | API nghiệp vụ LMS phải đáp ứng trong thời gian phù hợp với thao tác web. | Đề xuất p95 không quá 2 giây khi chạy 1.000 yêu cầu với 10 người dùng ảo trên dữ liệu thử nghiệm đã ghi nhận. Không tính truyền file, AI và dịch vụ ngoài; đo riêng từng nhóm endpoint thay vì chỉ lấy trung bình chung. | FR-01–FR-11, FR-17, FR-26–FR-33 |
| NFR-08 | Thời gian trả lời AI phải được đo và kiểm soát theo cấu hình tài nguyên. | Mục tiêu p95 ≤ 120 giây cho 50 câu hỏi trong phạm vi ở development, một lượt sinh đồng thời, tối đa 4.096 token đầu vào/512 token sinh. Đo retrieval/rerank/generation và thời gian chờ; ghi model, phần cứng, lượng tử hóa, cache, lỗi và timeout. Tóm tắt có phép đo riêng. | FR-19, FR-22, FR-R03 |
| NFR-09 | Tác vụ ingestion không được giữ kết nối của thao tác tải lên đến khi xử lý hoàn tất. | Sau nhận/lưu file, mục tiêu xác nhận tiếp nhận trong 3 giây; truyền file và xử lý nền đo riêng. Đo theo PDF văn bản, PDF OCR, DOCX, PPTX, TXT; không gộp các loại để che lỗi OCR hoặc thời gian xử lý. | FR-12, FR-14–FR-16 |
| NFR-10 | Khối lượng yêu cầu AI phải được giới hạn theo khả năng phục vụ của nguyên mẫu. | Khởi đầu đề xuất một lượt generation đồng thời, tối đa 5 tác vụ chờ; quá giới hạn thì từ chối có thông báo. Chạy toàn bộ bộ pilot trong cấu hình đã chọn, ghi peak RAM/VRAM và số OOM; có lỗi OOM phải điều chỉnh trước khi khóa cấu hình demo. | FR-14–FR-15, FR-19, FR-24, FR-35 |

Với tóm tắt tài liệu dài, nhóm chia tác vụ theo phần và hiển thị trạng thái tiến độ; không áp ngưỡng hỏi đáp 512 token đầu ra cho bản tóm tắt đầy đủ. Thời gian xử lý tóm tắt được đo theo số trang/token và loại tài liệu, từ đó xác định timeout phù hợp trước khi chốt MVP. Thời gian khởi động model và tải lại checkpoint được ghi riêng khỏi latency của dịch vụ đã sẵn sàng.

### 4.3. Độ tin cậy và khả năng phục hồi

| Mã | Yêu cầu chất lượng | Cách kiểm tra và tiêu chí chấp nhận | Liên quan |
|---|---|---|---|
| NFR-11 | Lỗi AI phải được cô lập khỏi các nghiệp vụ LMS không phụ thuộc AI. | Tắt dịch vụ AI rồi kiểm tra đăng nhập, mở bài học, xem học liệu và nộp bài vẫn hoạt động; yêu cầu AI nhận trạng thái lỗi phù hợp, không chờ vô hạn. | FR-01, FR-10–FR-11, FR-17, FR-19, FR-29, FR-34 |
| NFR-12 | Thao tác lặp hoặc thử lại không được gây dữ liệu trùng/mâu thuẫn. | Gửi lặp tham gia, ingestion, nộp bài, callback thanh toán và sự kiện video; không tạo quyền/chunk/điểm/doanh thu/tiến độ trùng. Giao dịch sai thứ tự được xử lý theo trạng thái đã xác thực. | FR-08, FR-15, FR-28–FR-29 |
| NFR-13 | Dữ liệu đã xác nhận lưu phải tồn tại sau khi tiến trình ứng dụng khởi động lại. | Sau xác nhận lưu, restart và đối chiếu tài khoản/lớp/file/bài nộp/điểm, lịch sử, giao dịch và tiến độ video. Tác vụ gián đoạn được phát hiện để thử lại/báo lỗi; không kẹt xử lý vô hạn. | FR-03, FR-06, FR-12–FR-15, FR-28–FR-31 |
| NFR-14 | Nguyên mẫu phải có quy trình sao lưu và kiểm tra khôi phục dữ liệu cần thiết. | Thử khôi phục DB/file và đối chiếu quyền, điểm, giao dịch, lịch sử, tiến độ video, checksum. Chỉ mục khôi phục hoặc xây lại từ corpus/manifest; checkpoint cần giữ ngoài phiên GPU tạm thời. | FR-12–FR-16, FR-28–FR-31, FR-R01–FR-R02 |

### 4.4. Tính toàn vẹn và nhất quán dữ liệu

| Mã | Yêu cầu chất lượng | Cách kiểm tra và tiêu chí chấp nhận | Liên quan |
|---|---|---|---|
| NFR-15 | Các đối tượng dữ liệu phải có quan hệ hợp lệ và đúng phạm vi sở hữu. | Không tạo bài học, chunk, lượt nộp hoặc điểm tham chiếu đối tượng không tồn tại/sai khóa học. Bản ghi trùng định danh và quan hệ không hợp lệ bị từ chối; thao tác nhiều bước có kết quả nhất quán khi lỗi giữa chừng. | FR-06–FR-17, FR-26–FR-32 |
| NFR-16 | File, metadata, chỉ mục và citation phải nhất quán theo phiên bản phục vụ. | Thử thay/gỡ tài liệu hoặc thu hồi quyền khi truy vấn. Phải dùng phiên bản hợp lệ và kiểm tra lại trước khi trả; nguồn/quyền không còn hợp lệ thì hủy/báo trạng thái thay đổi, không trả nội dung cũ như nguồn hiện hành. | FR-13–FR-21, FR-24–FR-25 |
| NFR-17 | Thời gian và trạng thái bài đánh giá phải được xác định phía server. | Thử đổi giờ client, nộp tại thời điểm hết hạn và sửa đề khi đã có lượt làm; kết quả tuân theo thời gian server và phiên bản đề. Thời điểm lưu có múi giờ rõ, hiển thị cho người dùng Việt Nam theo UTC+7. | FR-27–FR-32 |

### 4.5. Khả năng sử dụng và tương thích giao diện

| Mã | Yêu cầu chất lượng | Cách kiểm tra và tiêu chí chấp nhận | Liên quan |
|---|---|---|---|
| NFR-18 | Giao diện và nội dung phải hỗ trợ tiếng Việt có dấu. | Kiểm tra tên khóa học, file, câu hỏi, câu trả lời và kết quả xuất; không lỗi mã hóa, mất dấu hoặc cắt nội dung khiến không đọc được. | FR-06–FR-36 |
| NFR-19 | Người dùng phải hiểu trạng thái và cách xử lý lỗi của tác vụ. | Các trạng thái chưa có dữ liệu, đang xử lý, thiếu nguồn, hết quyền, vượt quota và lỗi dịch vụ có thông báo riêng; không hiển thị lỗi kỹ thuật/bí mật nội bộ. Có cách thử lại khi phù hợp. | FR-14–FR-15, FR-19–FR-25, FR-34–FR-35 |
| NFR-20 | Các luồng chính phải sử dụng được trên màn hình phổ biến và bằng bàn phím. | Kiểm tra viewport 360 px và 1.280 px, cùng các phiên bản Chrome/Edge được ghi trong biên bản; không mất nút hoặc buộc cuộn ngang toàn trang. Dùng bàn phím truy cập được trường nhập, nút gửi và liên kết nguồn, có trạng thái focus rõ. | FR-01, FR-06, FR-12, FR-17, FR-19, FR-22, FR-24, FR-28–FR-29 |

### 4.6. Bảo trì, triển khai và khả năng kiểm thử

| Mã | Yêu cầu chất lượng | Cách kiểm tra và tiêu chí chấp nhận | Liên quan |
|---|---|---|---|
| NFR-21 | Môi trường phải có hướng dẫn cài đặt và cấu hình có thể tái lập. | Cài từ checkout sạch, cấu hình mẫu không chứa bí mật, chạy cả luồng lõi và các tích hợp bản cuối; có đóng gói/hướng dẫn triển khai, cấu hình sandbox/production được phân biệt. Không đưa toàn bộ model weights vào Git. | FR-06, FR-12–FR-21, FR-R02 |
| NFR-22 | Nghiệp vụ LMS, ingestion và xử lý AI phải có ranh giới rõ để thay đổi cấu hình. | Có giao diện đầu vào/đầu ra được mô tả; đổi adapter hoặc cấu hình retrieval không làm thay đổi quyền khóa học hay buộc huấn luyện lại khi thêm tài liệu. Kiểm thử cùng luồng với các cấu hình thí nghiệm được chọn. | FR-14–FR-24, FR-R02–FR-R03 |
| NFR-23 | Các luồng và quy tắc trọng yếu phải có kiểm thử truy vết tới yêu cầu. | Kiểm thử truy vết MVP-01–MVP-10 và FIN-01–FIN-09, BR và các nhánh quyền/lỗi. Chức năng sau MVP phải có bằng chứng trước nghiệm thu cuối; chưa triển khai ghi chưa kiểm chứng, không thay bằng code coverage. | Toàn bộ yêu cầu trong phạm vi triển khai |
| NFR-24 | Tác vụ phải có thông tin đủ để theo dõi và phân tích lỗi. | Yêu cầu/tác vụ có ID, trạng thái, thời gian, loại lỗi và phiên bản cấu hình liên quan; kết quả benchmark truy được từng mẫu. Không ghi toàn văn dữ liệu nhạy cảm chỉ để phục vụ giám sát. | FR-14–FR-15, FR-34–FR-36, FR-R03–FR-R04 |
| NFR-25 | Kết quả nghiên cứu phải có khả năng tái lập và so sánh công bằng. | Lưu checksum/split dữ liệu, cấu hình, seed, commit và môi trường chạy; chạy lại một tập mẫu theo protocol. Nếu có yếu tố không xác định, báo biến thiên và sai khác thay vì yêu cầu mọi lần sinh giống hệt từng chữ. | FR-R01–FR-R04 |

### 4.7. Chất lượng truy xuất và câu trả lời AI

Các mục tiêu sau được đề xuất để nhóm có cơ sở đánh giá. Chúng áp dụng cho tập mẫu có nhãn và điều kiện ghi rõ ở mục 5, không diễn giải thành độ chính xác tuyệt đối trong mọi tình huống.

| Mã | Thuộc tính chất lượng | Cách đo và mục tiêu đề xuất | Liên quan |
|---|---|---|---|
| NFR-26 | Khả năng truy xuất bằng chứng | Đề xuất Recall@5 trung bình ≥ 0,80 trên QA có nguồn chuẩn trong corpus. Chuẩn hóa đơn vị bằng chứng theo trang/section hoặc chunk được gán nhãn; ghi thêm MRR/nDCG nếu đủ nhãn relevance. | FR-18–FR-19, FR-R01, FR-R03 |
| NFR-27 | Tính đúng của câu trả lời | Đề xuất ít nhất 75% câu hỏi trong phạm vi đạt rubric correctness. Rubric quy định câu trả lời đúng nội dung cốt lõi và không có sai sót trọng yếu; cùng cách chấm áp dụng cho các cấu hình. | FR-19, FR-R03–FR-R04 |
| NFR-28 | Mức bám sát bằng chứng | Đề xuất faithfulness trung bình ≥ 0,85 trên câu trả lời có nội dung học liệu. Ghi evaluator/model/prompt, context và score từng mẫu; không dùng chỉ số này thay cho correctness. | FR-19–FR-21, FR-R03–FR-R04 |
| NFR-29 | Độ đúng và độ bao phủ của citation | Đề xuất citation accuracy ≥ 0,90 và citation coverage ≥ 0,90 trên nhận định cần nguồn. Accuracy đo citation có hỗ trợ nhận định; coverage đo nhận định cần nguồn đã có citation hỗ trợ. ID nguồn hợp lệ phải đạt toàn bộ kiểm tra cấu trúc theo FR-21. | FR-17, FR-21–FR-24, FR-R04 |
| NFR-30 | Từ chối và hỏi lại phù hợp | Đề xuất ≥ 90% trường hợp thiếu nguồn/ngoài phạm vi có hành vi đúng theo nhãn; tỷ lệ từ chối sai trên QA có đủ bằng chứng ≤ 10%. Hai tỷ lệ được báo riêng; phản hồi làm rõ được chấm theo nhãn dự kiến. | FR-20, FR-R01, FR-R04 |
| NFR-31 | Gợi ý có ích và tuân thủ chính sách | Đề xuất ≥ 80% mẫu gợi ý đạt rubric về tính phù hợp và giúp học viên tiến thêm một bước. Bộ test có đáp án được bảo vệ phải không có trường hợp lộ đáp án; tách lỗi lộ dữ liệu khỏi việc LLM tự giải và báo rõ cả hai. | FR-22–FR-23, FR-26, FR-R04 |
| NFR-32 | Độ bao phủ và tính chính xác của tóm tắt | Đề xuất bao phủ ≥ 80% ý chính được gán nhãn trong phạm vi; tỷ lệ nhận định không được tài liệu hỗ trợ ≤ 10%. Mẫu có ý ở đầu/giữa/cuối được kiểm tra; bản tóm tắt một phần phải nêu phạm vi thực tế. | FR-24, FR-R01, FR-R04 |

Nhóm theo dõi thêm answer relevancy và context precision để phân tích mức trả lời đúng trọng tâm và chất lượng context. Hai chỉ số này không thay thế việc kiểm tra đáp án chuẩn, độ đúng của citation hoặc chính sách bài tập.

## 5. Phương pháp kiểm chứng yêu cầu

### 5.1. Bộ dữ liệu và tình huống kiểm thử

Nhóm chuẩn bị hai loại dữ liệu. Dữ liệu nghiệp vụ gồm tài khoản có các vai trò khác nhau, ít nhất hai khóa học có quyền truy cập khác nhau, tài liệu nhiều phiên bản và các lượt làm/nộp bài. Dữ liệu AI gồm câu hỏi, đáp án hoặc hành vi mong đợi, nguồn chuẩn và loại tình huống. Mỗi mẫu phải có định danh để liên kết với kết quả kiểm thử.

| Nhóm tình huống | Cách xây dựng và đánh giá |
|---|---|
| Hỏi đáp trong phạm vi | Có đáp án và bằng chứng chuẩn; chấm retrieval, correctness, faithfulness và citation. |
| Thiếu nguồn/ngoài phạm vi/mơ hồ | Gán hành vi mong đợi là từ chối, báo giới hạn hoặc hỏi lại; không chấm như một câu trả lời kiến thức thông thường. |
| Gợi ý bài tập | Có mức trợ giúp, trạng thái bài và đáp án bảo vệ khi cần; rubric đánh giá tính có ích và mức tiết lộ. |
| Tóm tắt | Có phạm vi tài liệu và danh sách ý chính; đo độ bao phủ, độ đúng và nguồn của bản tóm tắt. |
| Phân quyền và prompt injection | Sử dụng tài khoản/khóa học khác nhau, yêu cầu sửa ID, link file/citation và nội dung nhằm bỏ qua chính sách. |
| Lỗi và thao tác lặp | Ngắt AI/worker, lỗi file, thử lại, nộp lặp, sửa quyền và thay tài liệu trong khi yêu cầu đang xử lý. |

Cần phân biệt một chỉ dẫn độc hại trong tài liệu với dữ liệu học liệu thực sự. Các bài đánh giá có đáp án riêng phải có mẫu kiểm tra đường truy cập dữ liệu và mẫu kiểm tra lời giải do mô hình tự sinh. Nhờ đó, nhóm xác định được lỗi nằm ở phân quyền, truy xuất hay hành vi sinh câu trả lời.

### 5.2. Quy tắc đo lường

1. Dùng pilot/validation để chọn cấu hình và hiệu chỉnh các mục tiêu đề xuất. Mọi thay đổi ngưỡng phải có lý do và được ghi trước khi chạy đánh giá cuối.
2. Tách dữ liệu fine-tune khỏi nhãn/đáp án của bộ test; kiểm tra trùng lặp. Corpus phục vụ retrieval có thể chứa tài liệu của QA test theo protocol, nhưng không dùng nhãn test để chọn cấu hình.
3. Ghi rõ tập mẫu và mẫu số cho từng tỷ lệ. QA trong phạm vi, từ chối, gợi ý và tóm tắt được báo theo nhóm riêng; không chỉ công bố một điểm trung bình cho tất cả.
4. Với retrieval, đối chiếu bằng chứng chuẩn và kết quả top-k ở đơn vị đã thống nhất. Với metric dùng LLM chấm, lưu evaluator, prompt, phiên bản và đối chiếu một phần bằng đánh giá thủ công.
5. Với citation, tách kiểm tra ID/vị trí hợp lệ khỏi đánh giá nguồn hỗ trợ nhận định. Với tóm tắt, dùng danh sách ý chính đã gán nhãn cho đúng phạm vi.
6. Với hiệu năng, ghi phần cứng thực được cấp, model, context/output token, concurrency, trạng thái cache và thời gian khởi động. Tính p95 theo phân vị thực nghiệm và báo số mẫu, lỗi/timeout, không chỉ báo latency trên lượt thành công.
7. Lưu bằng chứng kiểm thử dạng dữ liệu có thể truy vết: ID mẫu, cấu hình/run, kết quả mong đợi, kết quả thực tế và lỗi. Chưa triển khai một chức năng phải ghi là chưa kiểm chứng, không đánh dấu đạt.

Base LLM không có retrieval được so sánh bằng các chỉ số phù hợp như correctness, relevancy và latency. Faithfulness với retrieved context, chất lượng retrieval và citation chỉ áp dụng khi cấu hình có thành phần tương ứng; trường hợp không áp dụng được ghi riêng, không tạo context/citation giả hoặc gán điểm 0 để làm sai ý nghĩa phép so sánh. Các lượt lỗi, timeout và từ chối sai trên QA có đáp án được tính vào tỷ lệ hoàn thành/correctness; metric cần câu trả lời hoặc citation được báo cùng số mẫu thực sự chấm được.

Khi đo hiệu năng, cấu hình quota của môi trường kiểm thử phải đủ cho số mẫu đã chọn và được ghi trong biên bản. Kiểm thử vượt quota được thực hiện riêng theo NFR-06 để không nhầm yêu cầu bị giới hạn với một lượt AI chậm hoặc lỗi.

### 5.3. Mối liên hệ với kịch bản chấp nhận

| Kịch bản | Yêu cầu trọng yếu cần kiểm chứng |
|---|---|
| AC-01 — Luồng tạo khóa học, tải tài liệu và hỏi đáp có nguồn | FR-01, FR-06, FR-08, FR-12–FR-21; NFR-07–NFR-10, NFR-26–NFR-29 |
| AC-02 — Truy cập sai khóa học | FR-18, FR-17, FR-25; NFR-01, NFR-04–NFR-05 |
| AC-03 — Thiếu nguồn hoặc tài liệu chưa sẵn sàng | FR-14, FR-18, FR-20–FR-21; NFR-19, NFR-30 |
| AC-04 — Thay thế/gỡ tài liệu | FR-13–FR-17, FR-21; NFR-12, NFR-16 |
| AC-05 — Gợi ý và bảo vệ đáp án | FR-18, FR-22–FR-23, FR-26–FR-27; NFR-01, NFR-04, NFR-31 |
| AC-06 — Tóm tắt tài liệu dài | FR-18, FR-21, FR-24; NFR-10, NFR-16, NFR-32 |
| AC-07 — AI/worker bị ngắt | FR-14–FR-15, FR-34–FR-35; NFR-11–NFR-14, NFR-19 |
| AC-08 — Điểm, quyền lớp và nộp lặp | FR-09, FR-26–FR-32; NFR-01, NFR-12, NFR-15, NFR-17 |
| AC-09 — Tái lập nghiên cứu | FR-R01–FR-R04; NFR-24–NFR-25 |

Ngoài các kịch bản AC, phần hoàn thiện sản phẩm phải đạt FIN-01–FIN-09 tại mục 13.2 của [SRS](../SRS.md). Ma trận tại mục 13.3–13.4 của SRS bao phủ toàn bộ yêu cầu chức năng và phi chức năng, gồm các chức năng triển khai sau MVP. Đạt các kiểm thử MVP chưa đồng nghĩa nghiệm thu sản phẩm cuối.

## 6. Ma trận truy vết use cases, hoạt động nghiên cứu và yêu cầu

| Use case | Yêu cầu chức năng tương ứng | Yêu cầu phi chức năng tiêu biểu |
|---|---|---|
| UC-01 | FR-05 | NFR-02, NFR-06, NFR-18–NFR-20 |
| UC-02 | FR-01–FR-02 | NFR-01–NFR-02, NFR-06–NFR-07 |
| UC-03 | FR-03–FR-04, FR-36 | NFR-01–NFR-02, NFR-13, NFR-24 |
| UC-04 | FR-06 | NFR-01, NFR-07, NFR-15 |
| UC-05 | FR-07 | NFR-01, NFR-07, NFR-18–NFR-20 |
| UC-06 | FR-08 | NFR-01, NFR-12, NFR-15 |
| UC-07 | FR-09, FR-36 | NFR-01, NFR-15–NFR-16 |
| UC-08 | FR-10 | NFR-01, NFR-15, NFR-18 |
| UC-09 | FR-11 | NFR-07, NFR-13, NFR-15 |
| UC-10 | FR-12–FR-13, FR-16, FR-36 | NFR-01, NFR-03, NFR-09, NFR-14–NFR-16 |
| UC-11 | FR-14–FR-16, FR-34 | NFR-09–NFR-14, NFR-19, NFR-24 |
| UC-12 | FR-17, FR-21 | NFR-01, NFR-16, NFR-20, NFR-29 |
| UC-13 | FR-18–FR-21 | NFR-01, NFR-04, NFR-08, NFR-26–NFR-30 |
| UC-14 | FR-18, FR-20–FR-22 | NFR-01, NFR-04, NFR-08, NFR-29–NFR-31 |
| UC-15 | FR-18, FR-21, FR-24 | NFR-01, NFR-10, NFR-16, NFR-29, NFR-32 |
| UC-16 | FR-25 | NFR-01, NFR-05, NFR-13, NFR-16 |
| UC-17 | FR-18, FR-23, FR-36 | NFR-01, NFR-04, NFR-16, NFR-31 |
| UC-18 | FR-26 | NFR-01, NFR-15, NFR-17 |
| UC-19 | FR-27–FR-28 | NFR-01, NFR-12, NFR-15, NFR-17 |
| UC-20 | FR-29 | NFR-01, NFR-03, NFR-12–NFR-15, NFR-17 |
| UC-21 | FR-30, FR-36 | NFR-01, NFR-13, NFR-15, NFR-17, NFR-24 |
| UC-22 | FR-31 | NFR-01, NFR-07, NFR-15 |
| UC-23 | FR-32 | NFR-01, NFR-07, NFR-15, NFR-17 |
| UC-24 | FR-33 | NFR-01, NFR-05, NFR-07 |
| UC-25 | FR-34–FR-36 | NFR-05–NFR-06, NFR-10–NFR-11, NFR-19, NFR-24 |
| RES-01 | FR-R01 | NFR-25–NFR-26 |
| RES-02 | FR-R02 | NFR-14, NFR-21–NFR-22, NFR-25 |
| RES-03 | FR-R03 | NFR-08, NFR-24–NFR-30 |
| RES-04 | FR-R04 | NFR-05, NFR-23–NFR-25, NFR-27–NFR-32 |
| UC-X01 | FR-X01 | NFR-01–NFR-02, NFR-12, NFR-15 |
| UC-X02 | FR-X02 | NFR-01, NFR-05, NFR-15 |
| UC-X03 | FR-X03 | NFR-01, NFR-12, NFR-18–NFR-20 |
| UC-X04 | FR-X04 | NFR-01, NFR-04, NFR-06, NFR-08 |

Ma trận giúp kiểm tra mỗi use case đã có yêu cầu cụ thể và xác định phần nào cần cập nhật khi thay đổi phạm vi. Các NFR dùng chung như triển khai và kiểm thử còn áp dụng cho toàn bộ chức năng được chọn, không chỉ các liên kết tiêu biểu trong bảng.

## 7. Phân chia giai đoạn và quyết định nghiệp vụ

| Nội dung | MVP | Sản phẩm cuối |
|---|---|---|
| Tài khoản | Admin cấp tài khoản | Có thêm đăng ký học viên; vai trò giáo viên/admin do người có quyền cấp. |
| Khóa học | Giáo viên cấp quyền lớp | Công khai/riêng tư, miễn phí/có phí; mã/mật khẩu và thanh toán theo điều kiện lớp. |
| Học liệu | PDF văn bản | PDF, DOCX, PPTX, TXT; Docling và OCR PDF quét khi cần, có kiểm tra chất lượng/vị trí nguồn. |
| Hội thoại | Ngữ cảnh phiên | Lưu/xem/tiếp tục/xóa lịch sử cá nhân; quyền hiện tại vẫn áp dụng. |
| Thống kê | Kết quả/tiến độ lớp, vận hành cơ bản | Dashboard nền tảng, lịch sử giao dịch và doanh thu theo quyền. |
| Bài học | Văn bản/PDF, tiến độ tự đánh dấu | Có thêm video tương tác và trạng thái các mốc kiểm tra. |
| Trợ lý | Ba chế độ dựa trên học liệu | Giữ ba chế độ; lựa chọn nguồn kiến thức tổng quát riêng trong hỏi đáp, ghi nhãn và giữ chính sách bài tập. |
| Nghiên cứu | Chuẩn bị và thử từ sớm | Bắt buộc có QLoRA, benchmark, so sánh và phân tích lỗi trước hoàn thành đồ án. |

MVP không thay thế phạm vi sản phẩm cuối. Thanh toán/video đã được đưa vào phần cam kết của đồ án; không được đánh dấu tùy chọn chỉ vì triển khai sau MVP. Cấu hình model, retrieval, cổng thanh toán, OCR, video và nơi inference được chốt trong thiết kế kỹ thuật trước nghiệm thu.

## 8. Kết quả phân tích và hướng hoàn thiện SRS

Phần phân tích xác định 40 yêu cầu chức năng sản phẩm (FR-01–FR-36 và FR-X01–FR-X04), 4 đầu ra nghiên cứu và 32 yêu cầu phi chức năng. Các yêu cầu được liên kết với use cases và có cách kiểm chứng để hỗ trợ thiết kế, triển khai và nghiệm thu sản phẩm cuối; bộ MVP được dùng cho mốc tích hợp đầu tiên.

Danh mục và ma trận truy vết đã được sử dụng để hoàn thiện phạm vi MVP và SRS phiên bản 1.1. Ở bước tiếp theo, nhóm thiết kế và triển khai theo các yêu cầu được chọn, kiểm chứng mục tiêu định lượng trên development và đánh giá bằng test độc lập. Quyền truy cập, dữ liệu học tập và khả năng xử lý lỗi là những điều kiện phải được kiểm tra trong các luồng đã chọn.
