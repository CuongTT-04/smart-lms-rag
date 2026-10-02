# Yêu cầu chức năng và phi chức năng của hệ thống LMS thông minh

- **Đề tài:** Xây dựng hệ thống quản lý học tập thông minh tích hợp mô hình ngôn ngữ lớn tinh chỉnh và kỹ thuật RAG.
- **Sinh viên thực hiện:** Trần Tuấn Cường.
- **Hạng mục:** Xác định functional và non-functional requirements.
- **Ngày lập:** 01/10/2026.

## 1. Mục đích và phạm vi phân tích

Hệ thống được xây dựng để giáo viên tổ chức khóa học và học liệu, đồng thời hỗ trợ học viên học tập thông qua quiz, bài tập và trợ lý AI. Trợ lý sử dụng tài liệu của từng khóa học để trả lời câu hỏi, gợi ý cách làm bài và tóm tắt nội dung. Người học có thể đối chiếu câu trả lời với nguồn trích dẫn thay vì chỉ tiếp nhận thông tin do mô hình sinh ra.

Trong phần việc này, em chuyển kết quả [phân tích actors và use cases](actors-usecases.md) thành các yêu cầu có thể thiết kế, triển khai và kiểm thử. Yêu cầu chức năng mô tả những hành vi hệ thống cần thực hiện. Yêu cầu phi chức năng xác định chất lượng, điều kiện vận hành và các giới hạn cần kiểm soát khi thực hiện những hành vi đó.

Phạm vi bao gồm nghiệp vụ LMS, xử lý học liệu và trợ lý theo khóa học. Các yêu cầu đối với corpus, huấn luyện QLoRA và benchmark được tách thành nhóm nghiên cứu. Thanh toán, doanh thu, video tương tác và trả lời kiến thức tổng quát được phân loại mở rộng. Việc lựa chọn chính thức các chức năng cho MVP được thực hiện ở Issue #7.

## 2. Quy ước và điều kiện áp dụng

### 2.1. Mã yêu cầu và mức ưu tiên

| Ký hiệu | Ý nghĩa |
|---|---|
| FR-xx | Yêu cầu chức năng của sản phẩm LMS. |
| FR-Rxx | Yêu cầu chức năng của công cụ nghiên cứu, huấn luyện và đánh giá. |
| FR-Xxx | Yêu cầu chức năng mở rộng. |
| NFR-xx | Yêu cầu phi chức năng hoặc tiêu chí chất lượng. |
| P0 | Ưu tiên luồng tạo khóa học, tải học liệu và hỏi đáp có nguồn. |
| P1 | Hoàn thiện nghiệp vụ học tập, quản lý và chất lượng của nguyên mẫu. |
| P2 | Mở rộng khi các chức năng cốt lõi đã được kiểm chứng. |

Mã UC, BR và AC được giữ thống nhất với tài liệu actors/use cases. Một yêu cầu có thể phục vụ nhiều use case; một use case có thể cần nhiều yêu cầu chức năng và phi chức năng.

### 2.2. Cách đọc tiêu chí chấp nhận

Trong các bảng dưới đây, từ **phải** mô tả hành vi mong đợi khi chức năng được chọn triển khai. Với yêu cầu có điều kiện như tự đăng ký hoặc lưu hội thoại, điều kiện áp dụng được ghi ngay trong nội dung. Mức ưu tiên không tự động quyết định một chức năng đã thuộc MVP.

Các yêu cầu phân quyền, bảo toàn dữ liệu và xử lý trạng thái được kiểm tra bằng những tình huống có kết quả xác định. Với chất lượng sinh câu trả lời và hiệu năng, các con số trong mục 4 là **mục tiêu đề xuất của nguyên mẫu**, chưa phải kết quả đo hoặc cam kết đã được nhóm phê duyệt. Nhóm sẽ kiểm chứng trên dữ liệu pilot/validation, ghi lại cấu hình và quyết định ngưỡng trước khi đánh giá tập test độc lập.

### 2.3. Điều kiện của nguyên mẫu

- Học viên, giáo viên và quản trị viên có vai trò và phạm vi truy cập khác nhau; quyền được kiểm tra trên từng đối tượng dữ liệu.
- Tài liệu phục vụ AI phải có quyền sử dụng, thuộc đúng khóa học và đã xử lý thành công.
- Ba chế độ hỏi đáp, gợi ý và tóm tắt dùng chung kho học liệu được phân quyền, nhưng có cách xử lý riêng.
- Thí nghiệm dự kiến dùng tài liệu của 2–3 môn học và khoảng 300–800 câu hỏi chuẩn. Nhóm chuẩn bị 50 QA pilot, mỗi thành viên 25 mẫu, trước khi mở rộng bộ đánh giá.
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
| FR-05 | Nếu áp dụng đăng ký tự phục vụ, khách phải có thể tạo tài khoản học viên. | Kiểm tra thông tin bắt buộc và định danh trùng; tài khoản mới chỉ nhận vai trò học viên, không tự có quyền khóa học hoặc quyền giáo viên/admin. | UC-01 | P1, có điều kiện |

### 3.2. Khóa học, bài học và thành viên

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-06 | Giáo viên phải có thể tạo và chỉnh sửa thông tin khóa học do mình quản lý. | Khóa học lưu định danh, thông tin giới thiệu và giáo viên phụ trách; người không có quyền không thể sửa bằng cách thay ID trong yêu cầu. | UC-04 | P0 |
| FR-07 | Hệ thống phải cung cấp danh sách và chức năng tìm thông tin giới thiệu của khóa học công khai. | Kết quả chỉ chứa khóa học được phép hiển thị; tìm kiếm không công bố tài liệu riêng hoặc lớp riêng tư. | UC-05 | P1 |
| FR-08 | Hệ thống phải cấp quyền tham gia khóa học sau khi học viên đáp ứng điều kiện của khóa học. | Có quan hệ tham gia hợp lệ mới cho phép học; thao tác tham gia lặp không tạo bản ghi trùng. Nếu chọn lớp riêng tư, mã/mật khẩu sai không cấp quyền. | UC-06 | P0 |
| FR-09 | Giáo viên phải có thể xem và quản lý thành viên trong khóa học phụ trách. | Cấp/thu hồi quyền theo cơ chế tham gia đã chọn; thay đổi có hiệu lực với truy cập tiếp theo và không tự xóa điểm/lượt nộp đã có. | UC-07 | P1 |
| FR-10 | Giáo viên phải có thể tạo, chỉnh sửa, sắp xếp và liên kết học liệu với bài học. | Bài học thuộc đúng khóa học, có thứ tự hiển thị; không liên kết tài liệu ngoài quyền quản lý; học viên chỉ thấy nội dung được công bố cho mình. | UC-08 | P1 |
| FR-11 | Hệ thống phải ghi và hiển thị tiến độ học của từng học viên. | Tiến độ gắn đúng học viên/bài học, được cập nhật theo tiêu chí hoàn thành đã cấu hình; tải lại trang không làm tăng tiến độ hoặc tự đánh dấu hoàn thành. | UC-09 | P1 |

### 3.3. Quản lý và xử lý học liệu

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-12 | Giáo viên phải có thể tải tài liệu vào khóa học được quản lý. | Kiểm tra quyền, loại file và giới hạn đã cấu hình; tài liệu được lưu với người tải, khóa học và định danh. File bị từ chối không tạo tài liệu sẵn sàng. | UC-10 | P0 |
| FR-13 | Hệ thống phải quản lý việc thay thế và gỡ tài liệu theo phiên bản. | Bản thay thế có phiên bản riêng và được xử lý lại; tài liệu đã gỡ ngừng phục vụ retrieval/mở nguồn theo chính sách. Thay file gốc không được coi là chỉ mục đã cập nhật. | UC-10 | P0 |
| FR-14 | Hệ thống phải xử lý tài liệu ở nền và hiển thị trạng thái cho giáo viên. | Phân biệt chờ xử lý, đang xử lý, sẵn sàng, lỗi và đã gỡ; chỉ chuyển sẵn sàng sau khi hoàn thành các bước cần thiết và kiểm tra kết quả trích xuất. | UC-11 | P0 |
| FR-15 | Giáo viên phải có thể yêu cầu thử lại tác vụ xử lý tài liệu bị lỗi. | Lưu nguyên nhân và kết quả lần thử; thử lại không tạo chunk/chỉ mục trùng hoặc phục vụ sai phiên bản. File đã gỡ không tự xuất hiện lại vì một tác vụ cũ kết thúc. | UC-11 | P0 |
| FR-16 | Pipeline phải trích xuất nội dung, chia đoạn và lưu thông tin nguồn cho các định dạng được chọn hỗ trợ. | Mỗi đoạn gắn với khóa học, tài liệu, phiên bản và vị trí trang/slide/mục; trang ảnh cần OCR được xử lý hoặc thông báo giới hạn. Không gán số trang khi không xác định được vị trí thực. | UC-10–UC-11 | P0 |
| FR-17 | Người có quyền phải có thể xem học liệu và mở vị trí được trích dẫn. | Kiểm tra lại quyền khi mở; hiển thị đúng tài liệu/phiên bản/vị trí hoặc chỉ dẫn vị trí nếu viewer chưa hỗ trợ nhảy trực tiếp. Nguồn không còn khả dụng được thông báo rõ. | UC-12 | P0 |

### 3.4. Trợ lý AI theo khóa học

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-18 | Mỗi yêu cầu trợ lý phải được xác định phạm vi khóa học và học liệu theo quyền hiện tại của người gửi. | Không chỉ tin mã khóa học từ client; cả các nhánh truy xuất, tóm tắt và cache chỉ dùng dữ liệu hợp lệ. Tài liệu chưa sẵn sàng hoặc đáp án riêng bị loại khỏi context học viên. | UC-13–UC-17 | P0 |
| FR-19 | Học viên phải có thể hỏi đáp nội dung trong học liệu khóa học. | Hệ thống nhận câu hỏi, truy xuất bằng chứng và trả câu trả lời theo phạm vi được chọn; lưu/hiển thị trạng thái xử lý khi yêu cầu chưa hoàn thành. | UC-13 | P0 |
| FR-20 | Trợ lý phải có nhánh xử lý câu hỏi mơ hồ, thiếu bằng chứng hoặc ngoài phạm vi học liệu. | Câu hỏi mơ hồ được yêu cầu làm rõ; không đủ bằng chứng thì thông báo thiếu nguồn. Trong chế độ học liệu, không tự chuyển sang trả lời kiến thức tổng quát. | UC-13–UC-14 | P0 |
| FR-21 | Câu trả lời sử dụng học liệu phải có thông tin trích dẫn tương ứng. | Hiển thị tên tài liệu, vị trí và tham chiếu nguồn; nguồn thuộc tập đã truy xuất, đúng phiên bản và được phép đọc. Tham chiếu không hợp lệ không được trình bày như citation đã xác nhận. | UC-12–UC-15 | P0 |
| FR-22 | Trợ lý phải cung cấp gợi ý làm bài theo mức trợ giúp được phép. | Có thể hỏi học viên bổ sung đề/cách làm, nhắc kiến thức và gợi ý bước tiếp theo; với bài trong LMS, trạng thái bài được lấy từ backend. Không xác định được chính sách không được tự coi là được giải toàn bộ. | UC-14 | P1 |
| FR-23 | Giáo viên phải có thể thiết lập học liệu được sử dụng và chính sách trợ giúp của trợ lý trong khóa học. | Cấu hình phân biệt tài liệu học viên và tài liệu riêng/đáp án; lưu chính sách có phiên bản, áp dụng trong các yêu cầu tiếp theo; không cho phép cấu hình bỏ qua quyền nền tảng. | UC-17 | P1 |
| FR-24 | Học viên phải có thể yêu cầu tóm tắt tài liệu hoặc phạm vi nội dung được chọn. | Kiểm tra quyền trên toàn phạm vi; xử lý nhiều phần khi cần; trả ý chính và nguồn, ghi rõ phần chưa xử lý nếu chưa bao phủ đủ. Không dùng vài đoạn top-k để đại diện cho toàn tài liệu. | UC-15 | P1 |
| FR-25 | Nếu bật lưu hội thoại, hệ thống phải cho học viên xem lại và tiếp tục lịch sử của mình. | Lịch sử gắn tài khoản/khóa học; mở lại kiểm tra quyền hiện tại. Người khác không đọc được; nội dung liên quan nguồn đã gỡ hoặc quyền đã thu hồi được xử lý theo chính sách lưu trữ. | UC-16 | P1, có điều kiện |

Kiểm tra tham chiếu nguồn tồn tại trong FR-21 là kiểm tra cấu trúc. Việc nguồn có thực sự hỗ trợ nhận định trong câu trả lời hay không được đánh giá riêng ở NFR-29. Tương tự, FR-22 xác định chức năng gợi ý; chất lượng hướng dẫn và mức tuân thủ được đo ở NFR-31.

### 3.5. Quiz, bài tập và kết quả học tập

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-26 | Giáo viên phải có thể tạo và quản lý quiz/bài tập trong khóa học phụ trách. | Lưu đề, kiểu bài, tiêu chí chấm, thời gian/lượt làm và chính sách trợ giúp nếu áp dụng; tách đáp án/rubric riêng khỏi dữ liệu trả cho học viên. | UC-18 | P1 |
| FR-27 | Hệ thống phải kiểm tra điều kiện và quản lý lượt làm quiz. | Chỉ bắt đầu khi có quyền, còn thời gian và lượt; lượt làm gắn phiên bản đề. Hạn và thời gian được kiểm soát phía server, không phụ thuộc đồng hồ client. | UC-19 | P1 |
| FR-28 | Hệ thống phải nhận bài quiz và tự chấm theo đáp án của phiên bản đề tương ứng. | Lưu câu trả lời/điểm nhất quán; yêu cầu nộp lặp không tạo điểm khác nhau cho cùng lượt; chỉ trả kết quả/đáp án theo thời điểm được công bố. | UC-19 | P1 |
| FR-29 | Học viên phải có thể nộp bài tự luận hoặc file cho bài tập được giao. | Kiểm tra quyền, định dạng và hạn; lưu người nộp, phiên bản bài, nội dung/file và thời điểm, rồi xác nhận đã nhận. Nộp muộn/nộp lại áp dụng đúng cấu hình. | UC-20 | P1 |
| FR-30 | Giáo viên phải có thể chấm và phản hồi bài nộp trong lớp phụ trách. | Kiểm tra thang điểm, lưu nhận xét và trạng thái công bố; sửa điểm có dấu vết. Không mặc định giao AI quyền chấm tự luận chính thức. | UC-21 | P1 |
| FR-31 | Học viên phải có thể xem điểm và phản hồi cá nhân đã được công bố. | Chỉ hiển thị kết quả của đúng học viên; chưa chấm/chưa công bố có trạng thái riêng; không dùng điểm 0 để thay cho kết quả còn thiếu. | UC-22 | P1 |

### 3.6. Thống kê và vận hành

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-32 | Giáo viên phải có thể xem thống kê tiến độ và kết quả trong khóa học phụ trách. | Có phạm vi và thời điểm tính; số liệu khớp dữ liệu học/lượt nộp/điểm; học viên chưa có điểm được phân biệt với điểm 0. | UC-23 | P1 |
| FR-33 | Quản trị viên phải có thể xem thống kê sử dụng nền tảng ở mức tổng hợp. | Tổng người dùng, khóa học và hoạt động được tính theo định nghĩa đã chọn; quyền xem thống kê không tự cấp quyền đọc hội thoại hoặc học liệu riêng. | UC-24 | P1 |
| FR-34 | Người được cấp quyền vận hành phải có thể theo dõi tình trạng xử lý tài liệu và dịch vụ AI. | Có trạng thái, lỗi và thời gian xử lý; AI bị ngắt không được hiển thị là đang sẵn sàng hoặc đã xử lý thành công. | UC-11, UC-25 | P1 |
| FR-35 | Hệ thống phải hỗ trợ cấu hình và thực thi hạn mức sử dụng AI. | Áp dụng quota tại backend theo phạm vi được chọn; vượt hạn trả thông báo phù hợp, không gọi model tiếp và không ảnh hưởng quyền xem bài học. | UC-25 | P1 |
| FR-36 | Hệ thống phải ghi dấu vết các thay đổi quản trị và nghiệp vụ có ảnh hưởng tới quyền hoặc kết quả học tập. | Ghi người thao tác, đối tượng, thời điểm và loại thay đổi cho cấp/thu hồi quyền, gỡ tài liệu, chỉnh chính sách và sửa điểm; chỉ người có quyền đọc được dấu vết. | UC-03, UC-07, UC-10, UC-17, UC-21, UC-25 | P1 |

### 3.7. Nghiên cứu, huấn luyện và đánh giá

Các yêu cầu này được thực hiện qua công cụ hoặc notebook nghiên cứu. Chúng không yêu cầu xây giao diện huấn luyện dành cho người dùng LMS và không đồng nghĩa giao toàn bộ hoạt động nghiên cứu cho một thành viên.

| Mã | Yêu cầu | Tiêu chí chấp nhận | Use case |
|---|---|---|---|
| FR-R01 | Bộ công cụ nghiên cứu phải hỗ trợ quản lý corpus và QA benchmark có phiên bản. | Mỗi mẫu có câu hỏi, đáp án hoặc hành vi mong đợi, định danh nguồn/vị trí khi có, loại tình huống và split; có manifest, quyền sử dụng và kết quả rà soát dữ liệu. | UC-R01 |
| FR-R02 | Quy trình huấn luyện phải tạo và lưu adapter QLoRA từ dữ liệu instruction được kiểm soát. | Có dry-run, cấu hình, checkpoint, log và model/adapter card; tách dữ liệu huấn luyện khỏi nhãn test; ghi lại lỗi OOM/ngắt phiên và điểm tiếp tục nếu có. | UC-R02 |
| FR-R03 | Bộ công cụ đánh giá phải chạy và lưu kết quả so sánh Base LLM, RAG và QLoRA+RAG. | Dùng cùng QA và protocol; lưu câu trả lời, context, citation, cấu hình, latency và metric từng mẫu; hỗ trợ khảo sát retrieval dense/hybrid/rerank khi được chọn, ghi nhận lượt lỗi. | UC-R03 |
| FR-R04 | Quy trình đánh giá phải hỗ trợ kiểm tra thủ công và phân tích lỗi. | Có rubric và bộ mẫu được chấm; phân loại lỗi truy xuất, sinh câu trả lời, nguồn, từ chối và gợi ý; số liệu báo cáo truy ngược tới kết quả đã lưu. | UC-R04 |

### 3.8. Chức năng mở rộng

| Mã | Yêu cầu | Tiêu chí chấp nhận khi triển khai | Use case | Ưu tiên |
|---|---|---|---|---|
| FR-X01 | Hệ thống hỗ trợ thanh toán để tham gia khóa học trả phí. | Kết quả giao dịch được xác thực phía server; chỉ cấp quyền khi thành công; thông báo giao dịch lặp không cấp quyền/ghi doanh thu nhiều lần. | UC-X01 | P2 |
| FR-X02 | Hệ thống cung cấp lịch sử giao dịch và thống kê doanh thu theo vai trò. | Học viên xem giao dịch cá nhân, giáo viên xem doanh thu của mình, admin xem tổng hợp; phân biệt giao dịch chờ, thất bại và hoàn tiền. | UC-X02 | P2 |
| FR-X03 | Hệ thống hỗ trợ video có câu hỏi tại các mốc thời gian. | Giáo viên cấu hình mốc; học viên xem, trả lời và nhận phản hồi theo chính sách; tiến độ không tăng sai khi tua lại hoặc tải lại. | UC-X03 | P2 |
| FR-X04 | Trợ lý có chế độ kiến thức tổng quát được lựa chọn riêng. | Ghi rõ câu trả lời chưa được xác nhận bằng học liệu; không tự bật khi thiếu nguồn và không bỏ qua quyền/chính sách bài tập. | UC-X04 | P2 |

## 4. Yêu cầu phi chức năng

### 4.1. Bảo mật và quyền riêng tư

| Mã | Yêu cầu chất lượng | Cách kiểm tra và tiêu chí chấp nhận | Liên quan |
|---|---|---|---|
| NFR-01 | Phân quyền phải được thực thi nhất quán ở mức đối tượng, kể cả file, retrieval, history và cache. | Bộ test sai vai trò/sai khóa học/sai chủ thể phải bị chặn ở tất cả trường hợp đã liệt kê. Kiểm tra lại trước khi trả kết quả AI nếu quyền thay đổi trong lúc xử lý. Thất bại một test truy cập trái phép là lỗi cần sửa, không bù bằng điểm AI cao. | FR-03–FR-04, FR-06–FR-36; BR-01–BR-02, BR-09 |
| NFR-02 | Thông tin xác thực và bí mật hệ thống phải được bảo vệ khi lưu, truyền và ghi log. | Mật khẩu dùng cơ chế băm mật khẩu thích hợp, không lưu rõ; token/bí mật không xuất hiện trong repo, phản hồi hoặc log. Truy cập từ xa có xác thực phải dùng kết nối mã hóa; cấu hình cookie/token được rà theo cách triển khai đã chọn. | FR-01–FR-04 |
| NFR-03 | File tải lên phải được kiểm tra trước khi lưu vào vùng phục vụ hoặc xử lý. | Test file sai loại, giả phần mở rộng, vượt giới hạn và tên file có ý đồ truy cập đường dẫn; tất cả bị từ chối hoặc cô lập an toàn. Không thực thi file như mã; dùng định danh lưu trữ do hệ thống tạo. | FR-12, FR-16, FR-29 |
| NFR-04 | Nội dung câu hỏi và học liệu không được thay đổi quyền hoặc chính sách hệ thống. | Dùng bộ test prompt injection từ câu hỏi và tài liệu; kiểm tra không có quyền bị nâng, không truy xuất khóa học khác và không lộ đáp án riêng. Tỷ lệ tuân thủ nội dung sinh ra được báo cáo riêng theo NFR-31. | FR-18, FR-22–FR-23; UC-R04 |
| NFR-05 | Dữ liệu hội thoại và log phải được thu thập ở mức cần thiết, với phạm vi truy cập rõ ràng. | Mặc định log vận hành không lưu toàn văn học liệu/hội thoại. Nếu cần dữ liệu đánh giá, nêu mục đích, quyền truy cập, cách ẩn danh và thời gian lưu; việc mở lịch sử áp dụng quyền hiện tại. | FR-25, FR-34, FR-36, FR-R04 |
| NFR-06 | Hệ thống phải giới hạn lạm dụng tài nguyên ở các chức năng xác thực, upload và AI. | Gửi yêu cầu vượt cấu hình kiểm thử phải nhận phản hồi giới hạn; không tạo vô hạn tác vụ hoặc hàng đợi. Quota và giới hạn tải lên kiểm tra phía server, không chỉ qua giao diện. | FR-01, FR-12, FR-19, FR-24, FR-35 |

Các tiêu chí bảo mật được kiểm tra trên bộ tình huống đã xây dựng và cấu hình được lưu. Kết quả đạt bộ test không được diễn giải thành bảo đảm chống mọi cách tấn công có thể xảy ra.

### 4.2. Hiệu năng và sử dụng tài nguyên

| Mã | Yêu cầu chất lượng | Điều kiện đo và mục tiêu đề xuất | Liên quan |
|---|---|---|---|
| NFR-07 | API nghiệp vụ LMS phải đáp ứng trong thời gian phù hợp với thao tác web. | Đề xuất p95 không quá 2 giây khi chạy 1.000 yêu cầu với 10 người dùng ảo trên dữ liệu thử nghiệm đã ghi nhận. Không tính truyền file, AI và dịch vụ ngoài; đo riêng từng nhóm endpoint thay vì chỉ lấy trung bình chung. | FR-01–FR-11, FR-17, FR-26–FR-33 |
| NFR-08 | Thời gian trả lời AI phải được đo và kiểm soát theo cấu hình tài nguyên. | Đề xuất p95 không quá 120 giây cho 50 câu hỏi trong phạm vi ở tập pilot/validation, một lượt sinh đồng thời, tối đa 4.096 token đầu vào và 512 token đầu ra. Đo toàn bộ retrieval/rerank/generation phía server; ghi thêm thời gian chờ nếu có. Ghi model, lượng tử hóa, phần cứng và lỗi thay vì loại lượt lỗi khỏi báo cáo. | FR-19, FR-22, FR-R03 |
| NFR-09 | Tác vụ ingestion không được giữ kết nối của thao tác tải lên đến khi xử lý hoàn tất. | Sau khi nhận và lưu file, đề xuất xác nhận tiếp nhận tác vụ trong 3 giây; thời gian truyền file đo riêng. Với bộ pilot, đo thời gian trích xuất/embedding và OCR riêng, không gộp PDF văn bản với PDF quét để báo một con số. | FR-12, FR-14–FR-16 |
| NFR-10 | Khối lượng yêu cầu AI phải được giới hạn theo khả năng phục vụ của nguyên mẫu. | Khởi đầu đề xuất một lượt generation đồng thời, tối đa 5 tác vụ chờ; quá giới hạn thì từ chối có thông báo. Chạy toàn bộ bộ pilot trong cấu hình đã chọn, ghi peak RAM/VRAM và số OOM; có lỗi OOM phải điều chỉnh trước khi khóa cấu hình demo. | FR-14–FR-15, FR-19, FR-24, FR-35 |

Với tóm tắt tài liệu dài, nhóm chia tác vụ theo phần và hiển thị trạng thái tiến độ; không áp ngưỡng hỏi đáp 512 token đầu ra cho bản tóm tắt đầy đủ. Thời gian xử lý tóm tắt được đo theo số trang/token và loại tài liệu, từ đó xác định timeout phù hợp trước khi chốt MVP. Thời gian khởi động model và tải lại checkpoint được ghi riêng khỏi latency của dịch vụ đã sẵn sàng.

### 4.3. Độ tin cậy và khả năng phục hồi

| Mã | Yêu cầu chất lượng | Cách kiểm tra và tiêu chí chấp nhận | Liên quan |
|---|---|---|---|
| NFR-11 | Lỗi AI phải được cô lập khỏi các nghiệp vụ LMS không phụ thuộc AI. | Tắt dịch vụ AI rồi kiểm tra đăng nhập, mở bài học, xem học liệu và nộp bài vẫn hoạt động; yêu cầu AI nhận trạng thái lỗi phù hợp, không chờ vô hạn. | FR-01, FR-10–FR-11, FR-17, FR-19, FR-29, FR-34 |
| NFR-12 | Thao tác lặp hoặc thử lại không được gây dữ liệu trùng/mâu thuẫn. | Gửi lặp enrollment, retry ingestion và nộp cùng lượt quiz/bài tập; kết quả chỉ có bản ghi hợp lệ theo chính sách, không chấm hai lần hoặc nhân đôi chunk. | FR-08, FR-15, FR-28–FR-29 |
| NFR-13 | Dữ liệu đã xác nhận lưu phải tồn tại sau khi tiến trình ứng dụng khởi động lại. | Lưu tài khoản/khóa học/file/lượt nộp/điểm, khởi động lại và đối chiếu. Các tác vụ bị gián đoạn phải được phát hiện để thử lại hoặc báo lỗi, không bị kẹt ở trạng thái đang xử lý mãi. | FR-03, FR-06, FR-12–FR-15, FR-28–FR-31 |
| NFR-14 | Nguyên mẫu phải có quy trình sao lưu và kiểm tra khôi phục dữ liệu cần thiết. | Thực hiện một lần khôi phục trên môi trường thử: đối chiếu số bản ghi, quyền, điểm và checksum file với bản sao lưu. Chỉ mục có thể khôi phục hoặc xây lại từ corpus/manifest có phiên bản; checkpoint cần thiết không chỉ nằm trong phiên GPU tạm thời. | FR-12–FR-16, FR-28–FR-31, FR-R01–FR-R02 |

### 4.4. Tính toàn vẹn và nhất quán dữ liệu

| Mã | Yêu cầu chất lượng | Cách kiểm tra và tiêu chí chấp nhận | Liên quan |
|---|---|---|---|
| NFR-15 | Các đối tượng dữ liệu phải có quan hệ hợp lệ và đúng phạm vi sở hữu. | Không tạo bài học, chunk, lượt nộp hoặc điểm tham chiếu đối tượng không tồn tại/sai khóa học. Bản ghi trùng định danh và quan hệ không hợp lệ bị từ chối; thao tác nhiều bước có kết quả nhất quán khi lỗi giữa chừng. | FR-06–FR-17, FR-26–FR-32 |
| NFR-16 | File, metadata, chỉ mục và citation phải nhất quán theo phiên bản phục vụ. | Thay/gỡ tài liệu trong lúc truy vấn; kết quả phải dùng snapshot hợp lệ và được kiểm tra lại trước khi trả. Nếu nguồn hoặc quyền không còn hợp lệ, hủy/trả trạng thái thay đổi và cho thử lại, không trả nguồn cũ như hiện hành. | FR-13–FR-21, FR-24–FR-25 |
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
| NFR-21 | Môi trường phải có hướng dẫn cài đặt và cấu hình có thể tái lập. | Cài từ checkout sạch theo hướng dẫn, áp dụng cấu hình mẫu không chứa bí mật và chạy luồng tạo khóa học → upload → hỏi đáp. Ghi phiên bản dependency, dữ liệu mẫu và vị trí lấy model/adapter thay vì đưa toàn bộ weights vào Git. | FR-06, FR-12–FR-21, FR-R02 |
| NFR-22 | Nghiệp vụ LMS, ingestion và xử lý AI phải có ranh giới rõ để thay đổi cấu hình. | Có giao diện đầu vào/đầu ra được mô tả; đổi adapter hoặc cấu hình retrieval không làm thay đổi quyền khóa học hay buộc huấn luyện lại khi thêm tài liệu. Kiểm thử cùng luồng với các cấu hình thí nghiệm được chọn. | FR-14–FR-24, FR-R02–FR-R03 |
| NFR-23 | Các luồng và quy tắc trọng yếu phải có kiểm thử truy vết tới yêu cầu. | Có test cho các AC-01–AC-09 và các nhánh quyền/lỗi tương ứng với chức năng đã chọn. Toàn bộ test bắt buộc phải đạt trước khi nghiệm thu cấu hình; ghi rõ các use case chưa triển khai, không dùng code coverage để thay cho kiểm tra hành vi. | Toàn bộ yêu cầu trong phạm vi triển khai |
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

## 6. Ma trận truy vết use cases và yêu cầu

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
| UC-R01 | FR-R01 | NFR-25–NFR-26 |
| UC-R02 | FR-R02 | NFR-14, NFR-21–NFR-22, NFR-25 |
| UC-R03 | FR-R03 | NFR-08, NFR-24–NFR-30 |
| UC-R04 | FR-R04 | NFR-05, NFR-23–NFR-25, NFR-27–NFR-32 |
| UC-X01 | FR-X01 | NFR-01–NFR-02, NFR-12, NFR-15 |
| UC-X02 | FR-X02 | NFR-01, NFR-05, NFR-15 |
| UC-X03 | FR-X03 | NFR-01, NFR-12, NFR-18–NFR-20 |
| UC-X04 | FR-X04 | NFR-01, NFR-04, NFR-06, NFR-08 |

Ma trận giúp kiểm tra mỗi use case đã có yêu cầu cụ thể và xác định phần nào cần cập nhật khi thay đổi phạm vi. Các NFR dùng chung như triển khai và kiểm thử còn áp dụng cho toàn bộ chức năng được chọn, không chỉ các liên kết tiêu biểu trong bảng.

## 7. Tham số và chính sách cần thống nhất trước khi chốt MVP

| Nội dung | Đề xuất hoặc cách xác định | Tác động |
|---|---|---|
| Cấp tài khoản | Có thể dùng tài khoản cấp sẵn cho demo đầu tiên; tự đăng ký chỉ triển khai nếu chọn FR-05. | FR-01–FR-05 |
| Điều kiện tham gia | Chọn luồng lớp công khai/riêng tư và quy trình giáo viên cấp/thu hồi quyền. | FR-06–FR-09 |
| Định dạng và kích thước file | Ưu tiên PDF văn bản để kiểm chứng luồng đầu tiên; thử nghiệm thêm PPT/PPTX, DOC/DOCX, TXT và OCR trên corpus thực. Mức khởi đầu đề xuất 20 MiB/file, cấu hình được và rà lại bằng kích thước corpus. | FR-12, FR-16, NFR-03, NFR-09 |
| Thay thế/gỡ học liệu | Đề xuất giữ bản cũ hợp lệ đến khi bản mới sẵn sàng; khi gỡ thì ngừng phục vụ ngay. Xác định cách giữ metadata của citation lịch sử và việc xóa dữ liệu lưu. | FR-13, FR-17, FR-25, NFR-16 |
| Mức trợ giúp | Xác định mức gợi ý theo bài luyện tập, bài có chấm điểm và bài đang thi; cấu hình từ chối hoặc hỗ trợ giới hạn khi chưa có chính sách rõ. | FR-22–FR-23, NFR-31 |
| Hội thoại và dữ liệu đánh giá | Xác định có lưu lịch sử, thời hạn lưu và quy trình xóa/ẩn danh. Chỉ số vận hành không yêu cầu toàn văn hội thoại. | FR-25, NFR-05 |
| Quiz/bài tập và tiến độ | Chốt tiêu chí hoàn thành, số lượt, nộp muộn, nộp lại, sửa đề và công bố điểm/đáp án. | FR-11, FR-26–FR-32 |
| Quota, hàng đợi và timeout | Khởi đầu đề xuất 20 yêu cầu AI/giờ/học viên, một lượt sinh đồng thời, tối đa 5 tác vụ chờ; timeout hỏi đáp 180 giây. Tóm tắt/ingestion có giới hạn riêng sau đo pilot, không dùng chung timeout hỏi đáp. | FR-35, NFR-06, NFR-08–NFR-11 |
| Model, retrieval và nơi phục vụ AI | Chọn cấu hình phù hợp tài nguyên thử nghiệm; xác định cách tích hợp với web và thông báo khi dịch vụ ngắt. Không ràng buộc mô hình phải chạy liên tục. | FR-18–FR-24, FR-34, NFR-10–NFR-11 |
| Chỉ tiêu chất lượng AI | Rà lại NFR-26–NFR-32 bằng pilot/validation, thống nhất rubric và ngưỡng trước test cuối. Nếu thay ngưỡng phải ghi quyết định và lý do. | FR-R01–FR-R04 |

## 8. Kết quả phân tích và hướng hoàn thiện SRS

Phần phân tích xác định 36 yêu cầu chức năng của LMS, 4 yêu cầu nghiên cứu, 4 yêu cầu mở rộng và 32 yêu cầu phi chức năng. Các yêu cầu được liên kết với use cases và có cách kiểm chứng để hỗ trợ thiết kế, triển khai và nghiệm thu nguyên mẫu.

Ở bước tiếp theo, em sử dụng danh mục và ma trận truy vết để xác định chức năng cần đưa vào MVP, chức năng giữ ở giai đoạn sau và các chính sách phải thống nhất trước khi triển khai. Các tiêu chí định lượng được kiểm chứng bằng dữ liệu pilot, còn quyền truy cập, dữ liệu học tập và khả năng xử lý lỗi là những điều kiện phải được kiểm tra trong các luồng đã chọn.
