# Phạm vi MVP của hệ thống LMS thông minh

- **Đề tài:** Xây dựng hệ thống quản lý học tập thông minh tích hợp mô hình ngôn ngữ lớn tinh chỉnh và kỹ thuật RAG.
- **Sinh viên thực hiện:** Trần Tuấn Cường.
- **Hạng mục:** Chốt phạm vi MVP.
- **Ngày lập:** 01/10/2026.

## 1. Mục tiêu của MVP

MVP là phiên bản nguyên mẫu thể hiện được một quy trình học tập hoàn chỉnh: giáo viên tạo khóa học và tải học liệu, học viên được cấp quyền tham gia, sử dụng trợ lý AI trên học liệu đó và thực hiện các hoạt động đánh giá cơ bản. Sản phẩm cần đủ để kiểm chứng giá trị của trợ lý học tập và sự tích hợp với LMS trong phạm vi đồ án.

Trong phần việc này, em lựa chọn chức năng từ [phân tích actors và use cases](actors-usecases.md) và [yêu cầu chức năng, phi chức năng](requirements.md), đồng thời giới hạn cách triển khai của từng chức năng. Việc chốt phạm vi giúp nhóm tập trung vào sản phẩm chạy được, dữ liệu có thể truy vết và thí nghiệm có kết quả đo.

Phạm vi được chốt trong tài liệu là phạm vi cần thực hiện, không phải xác nhận phần mềm hoặc mô hình đã đạt các tiêu chí. Những giới hạn và mục tiêu định lượng đều phải được kiểm chứng trong quá trình triển khai.

## 2. Quyết định phạm vi

### 2.1. Những nội dung bắt buộc

- Có tài khoản học viên, giáo viên và quản trị viên; quyền truy cập được kiểm tra theo khóa học và đối tượng.
- Giáo viên tạo khóa học, bài học, cấp quyền thành viên, tải lên và quản lý học liệu.
- Học viên đọc học liệu và sử dụng ba chế độ trợ lý: hỏi đáp, gợi ý làm bài, tóm tắt.
- Câu trả lời dựa trên học liệu có nguồn kiểm chứng; thiếu bằng chứng thì hỏi lại hoặc thông báo giới hạn.
- Có quiz trắc nghiệm, bài tập tự luận/nộp file, điểm, phản hồi và tiến độ cơ bản.
- Có trạng thái xử lý tài liệu, kiểm soát sử dụng AI và dấu vết các thay đổi quan trọng.
- Có corpus/QA benchmark, thí nghiệm QLoRA và so sánh Base LLM, RAG, QLoRA+RAG bằng số liệu.

### 2.2. Những nội dung hoãn lại

- Tự đăng ký tài khoản và tìm kiếm khóa học công khai.
- Lưu, xem lại và tiếp tục hội thoại qua các phiên đăng nhập.
- Dashboard thống kê tổng hợp toàn nền tảng.
- Thanh toán, đơn hàng, doanh thu và lịch sử giao dịch.
- Video streaming, quiz tại mốc video và tự tua lại video.
- Trả lời bằng tri thức tổng quát ngoài học liệu.
- Hệ multi-agent tự điều phối, chấm tự luận chính thức bằng AI và các chức năng cá nhân hóa nâng cao.

Hỏi đáp, gợi ý và tóm tắt là ba chế độ trong cùng giao diện trợ lý. MVP không yêu cầu ba mô hình riêng hoặc một agent điều phối các agent con.

### 2.3. Quy mô kiểm chứng

| Nội dung | Phạm vi được chọn |
|---|---|
| Môn học | Hai môn để kiểm chứng ban đầu; môn thứ ba bổ sung nếu hoàn thành dữ liệu và thời gian cho phép. |
| Corpus | Mục tiêu 20–50 tài liệu có quyền sử dụng, thuộc các môn đã chọn; kiểm tra định dạng và chất lượng trước khi đưa vào bộ demo. |
| QA pilot | 50 mẫu trước rà soát trùng lặp, gồm 25 mẫu của thành viên A và 25 mẫu của thành viên B. |
| Benchmark hoàn thiện | Tối thiểu 300 mẫu hợp lệ: 100 mẫu development, gồm các mẫu pilot được giữ lại, và 200 mẫu test độc lập. |
| Dữ liệu nghiệp vụ | Ít nhất một admin, hai giáo viên, bốn học viên và hai khóa học có quyền khác nhau; có quiz, bài tập và dữ liệu điểm/tiến độ để kiểm thử. |
| Người dùng đồng thời | Kiểm thử API LMS với 10 người dùng ảo; dịch vụ model chỉ sinh một câu trả lời tại một thời điểm trong cấu hình ban đầu. |

Các số lượng trên là mục tiêu kiểm chứng của đồ án, không được đưa thành giới hạn cố định cho số người dùng hoặc khóa học của phần mềm. Các mẫu pilot bị loại phải được ghi lý do và bổ sung nếu cần để đủ bộ development đã chọn.

## 3. Chức năng nằm trong MVP

### 3.1. Tài khoản và lớp học

| Nhóm chức năng | Yêu cầu được chọn | Mức thực hiện trong MVP | Giới hạn |
|---|---|---|---|
| Xác thực | FR-01–FR-02; UC-02 | Đăng nhập, đăng xuất, xử lý tài khoản bị khóa và phiên hết hạn. | Dùng tài khoản cấp sẵn; không xây đăng ký, xác minh email hoặc khôi phục mật khẩu tự phục vụ. |
| Quản lý tài khoản | FR-03–FR-04; UC-03 | Admin tạo/sửa tài khoản, khóa/mở khóa, gán vai trò qua chức năng quản trị cơ bản. | Không xóa vĩnh viễn tài khoản; không tự cấp vai trò giáo viên/admin; ngăn mất admin hoạt động cuối cùng. |
| Khóa học | FR-06; UC-04 | Giáo viên tạo/sửa tên, mô tả và trạng thái khóa học; quản lý khóa học phụ trách. | Dùng lớp được cấp quyền; không có giá bán, danh mục marketplace hoặc tìm kiếm công khai. |
| Thành viên | FR-08–FR-09; UC-06–UC-07 | Giáo viên chọn tài khoản học viên có sẵn để cấp/thu hồi quyền; học viên mở khóa học trong danh sách được cấp. | Không tự tham gia qua mã/mật khẩu, không duyệt đơn tham gia. Cấp quyền là điều kiện tham gia của MVP. |
| Bài học | FR-10; UC-08 | Tạo/sửa nội dung văn bản, sắp xếp và liên kết tài liệu/bài đánh giá. | Không xây trình soạn bài giảng phức tạp hoặc dịch vụ streaming. |
| Tiến độ | FR-11; UC-09 | Học viên đánh dấu bài học đã hoàn thành; hiển thị số bài hoàn thành trên tổng bài đã công bố. | Tiến độ là trạng thái tác vụ tự đánh dấu, không được diễn giải là đo mức thông thạo kiến thức. |

Khóa học có trạng thái nháp, đang mở và lưu trữ. Nháp chỉ hiển thị cho giáo viên phụ trách; đang mở hiển thị cho thành viên hợp lệ; lưu trữ ngừng hoạt động học/AI mới nhưng giữ dữ liệu để giáo viên quản lý. Học viên không được xem học liệu chỉ vì biết ID của khóa học.

### 3.2. Học liệu và trợ lý AI

| Nhóm chức năng | Yêu cầu được chọn | Mức thực hiện trong MVP | Giới hạn |
|---|---|---|---|
| Upload học liệu | FR-12; UC-10 | Giáo viên tải PDF văn bản và khai báo tên/phạm vi sử dụng; PDF xuất từ slide được xử lý như PDF. | Tối đa 20 MiB và 100 trang/file; chưa nhận trực tiếp PPT/PPTX, DOC/DOCX, TXT. |
| Phiên bản và gỡ tài liệu | FR-13; UC-10 | Thay thế tạo bản mới; bản cũ tiếp tục phục vụ đến khi bản mới sẵn sàng. Gỡ tài liệu ngừng phục vụ ngay. | Không xây giao diện lịch sử mọi phiên bản; không trả nội dung bản đã ngừng phục vụ qua citation cũ. |
| Xử lý nền | FR-14–FR-16; UC-11 | Trích xuất, chia đoạn, tạo embedding/chỉ mục; hiển thị trạng thái và thử lại khi lỗi. | PDF quét hoặc phần trang không trích xuất được phải được phát hiện và báo chưa hỗ trợ/không đủ nội dung; OCR tự động hoãn lại. Không bỏ trang lỗi mà vẫn báo sẵn sàng toàn tài liệu. |
| Đọc và mở nguồn | FR-17; UC-12 | Mở PDF theo quyền, hiển thị tên tài liệu và số trang của phiên bản phục vụ. | PDF xuất từ slide dùng số trang PDF; không tự gán số slide của file gốc. Nếu viewer không nhảy trang, cung cấp chỉ dẫn trang rõ. |
| Phạm vi trợ lý | FR-18; UC-13–UC-17 | Mọi chế độ lấy học liệu theo quyền hiện tại và trạng thái sẵn sàng. | Không dùng tài liệu khóa học khác, tài liệu đã gỡ hoặc đáp án riêng trong context học viên. |
| Hỏi đáp | FR-19–FR-21; UC-13 | Trả lời dựa trên bằng chứng, gắn nguồn và xử lý thiếu nguồn/câu hỏi mơ hồ. | Không fallback sang kiến thức tổng quát; không xem ngưỡng tương đồng là bảo đảm mọi câu trả lời đều đúng. |
| Gợi ý | FR-22–FR-23; UC-14, UC-17 | Giáo viên thiết lập phạm vi học liệu và mức trợ giúp; trợ lý gợi nhắc kiến thức, đặt câu hỏi hoặc chỉ ra bước tiếp theo. | Không tự nộp bài hoặc chấm điểm chính thức; không trả lời theo yêu cầu bỏ qua chính sách. |
| Tóm tắt | FR-24; UC-15 | Tóm tắt một tài liệu hoặc khoảng trang của tài liệu; xử lý từng phần rồi tổng hợp, gắn nguồn. | Tối đa 20 trang và 10.000 token nội dung nguồn cho một yêu cầu; vượt một trong hai giới hạn phải yêu cầu thu hẹp. Không tóm tắt toàn khóa học trong MVP. |

Giới hạn token của tóm tắt áp dụng cho toàn bộ nội dung nguồn được chọn trước bước chia phần. Mỗi lượt gọi model vẫn phải tuân thủ context của cấu hình đã chọn. Hệ thống không cắt bớt nội dung một cách im lặng để làm yêu cầu vượt giới hạn trở thành bản tóm tắt toàn bộ.

Các file gốc khác định dạng được giáo viên/nhóm dữ liệu chuyển sang PDF trước khi tải lên. Thao tác chuyển đổi nằm ngoài pipeline MVP; file PDF sau chuyển đổi vẫn phải được kiểm tra quyền sử dụng và tính đầy đủ. Hỗ trợ nhiều định dạng và OCR được ghi nhận là phần mở rộng của FR-16.

### 3.3. Quiz, bài tập và thống kê lớp

| Nhóm chức năng | Yêu cầu được chọn | Mức thực hiện trong MVP | Giới hạn |
|---|---|---|---|
| Bài đánh giá | FR-26; UC-18 | Quiz một lựa chọn đúng và bài tự luận/nộp file; lưu đề, hạn, thời gian làm và chính sách công bố. | Không có ngân hàng câu hỏi ngẫu nhiên, nhiều loại câu hỏi hoặc giám sát thi. |
| Lượt làm quiz | FR-27–FR-28; UC-19 | Một lượt làm mỗi học viên; lưu câu trả lời, nộp và tự chấm trên server theo phiên bản đề. | Không cho sửa nội dung quiz sau khi đã có lượt làm; muốn sửa phải tạo bản/bài mới. |
| Nộp bài tập | FR-29; UC-20 | Một lượt nộp gồm văn bản hoặc một file; kiểm tra hạn và xác nhận đã nhận. | Không nhận nộp muộn/nộp lại; file đính kèm chỉ phục vụ chấm bài, không tự đưa vào corpus AI. |
| Chấm và xem kết quả | FR-30–FR-31; UC-21–UC-22 | Giáo viên chấm tự luận theo thang 0–10, nhận xét, công bố; học viên xem kết quả cá nhân. | Không dùng AI để quyết định điểm chính thức; sửa điểm có dấu vết. |
| Thống kê lớp | FR-32; UC-23 | Hiển thị thành viên, tiến độ, số bài đã nộp và phân bố điểm trong lớp phụ trách. | Chưa có dự báo kết quả học tập, gợi ý cá nhân hóa hoặc xuất báo cáo tùy biến. |

Quiz có thời lượng tối đa do giáo viên thiết lập và hạn chung của bài. Thời điểm kết thúc lượt làm là thời điểm sớm hơn giữa hai giới hạn. Khi quá hạn, hệ thống chốt theo các câu trả lời đã lưu và chính sách nộp bài, không tin đồng hồ hoặc trạng thái phía client. Nộp lặp cùng lượt làm phải trả kết quả nhất quán.

Điểm quiz có thể được trả sau khi chốt lượt làm; đáp án/lời giải chỉ hiển thị khi giáo viên công bố. Điểm tự luận chỉ hiển thị sau khi được công bố. Các lượt chưa làm/chưa chấm được giữ trạng thái riêng, không tự coi là điểm 0. File nộp bài tối đa 20 MiB, chỉ nhận PDF hoặc ảnh PNG/JPEG trong MVP và phải kiểm tra loại file thực tế.

### 3.4. Vận hành tối thiểu

| Nhóm chức năng | Yêu cầu được chọn | Mức thực hiện trong MVP | Giới hạn |
|---|---|---|---|
| Trạng thái AI/ingestion | FR-34; UC-11, UC-25 | Có thông tin trạng thái, lỗi và thời gian xử lý cho người vận hành; giao diện người dùng có thông báo tương ứng. | Không xây dashboard giám sát thời gian thực phức tạp. |
| Hạn mức AI | FR-35; UC-25 | Áp dụng quota, giới hạn hàng đợi và timeout phía server; có cấu hình được mô tả cho người vận hành. | Không có gói thuê bao, hạn mức thương mại hoặc điều phối nhiều GPU. |
| Dấu vết thay đổi | FR-36 | Ghi người thao tác, đối tượng, thời điểm và loại thay đổi quyền, tài liệu, chính sách và điểm. | Không mặc định ghi toàn văn hội thoại trong log; quyền đọc log tách khỏi quyền đọc nội dung lớp. |

MVP chọn **32 yêu cầu chức năng sản phẩm**: FR-01–FR-04, FR-06, FR-08–FR-24, FR-26–FR-32 và FR-34–FR-36. Các yêu cầu được thực hiện trong giới hạn chức năng đã mô tả, không bao gồm mọi biến thể nghiệp vụ của hệ thống hoàn chỉnh.

## 4. Chính sách nghiệp vụ được chọn

| Nội dung | Quyết định cho MVP | Yêu cầu liên quan |
|---|---|---|
| Cấp tài khoản | Admin tạo tài khoản; giáo viên/học viên dùng tài khoản cấp sẵn. | FR-01–FR-04 |
| Tham gia lớp | Giáo viên cấp quyền cho tài khoản học viên có sẵn; học viên sử dụng danh sách lớp được cấp. Thu hồi quyền có hiệu lực với yêu cầu tiếp theo và trước khi trả kết quả AI đang xử lý. | FR-08–FR-09, NFR-01 |
| Phân quyền nội dung | Giáo viên quản lý lớp phụ trách; học viên xem lớp được cấp và kết quả cá nhân. Admin không tự có quyền đọc mọi học liệu/đáp án/hội thoại. | NFR-01, BR-01–BR-02, BR-09 |
| Học liệu AI | Chỉ bản đang phục vụ và sẵn sàng, được đánh dấu cho học viên sử dụng, mới vào context. Đáp án/rubric riêng không được lập chỉ mục cho học viên. | FR-13–FR-18, FR-23 |
| Thiếu nguồn | Hỏi lại hoặc báo chưa đủ bằng chứng, không tự chuyển sang tri thức tổng quát. | FR-20, BR-05 |
| Bài luyện tập | Cho gợi ý khái niệm và bước tiếp theo, không mặc định cung cấp toàn bộ lời giải. | FR-22–FR-23 |
| Quiz đang làm | Không cho trợ giúp AI theo bài; trạng thái được kiểm tra phía server. Không bảo đảm phát hiện mọi đề được người dùng sao chép sang một câu hỏi độc lập. | FR-22, FR-26–FR-27, NFR-31 |
| Bài tự luận có chấm điểm | Giáo viên chọn tắt trợ giúp hoặc chỉ cho gợi ý khái niệm. Sau hạn vẫn áp dụng chính sách đã cấu hình; không tự mở lời giải. | FR-22–FR-23, FR-26 |
| Hội thoại | Chỉ duy trì ngữ cảnh cần thiết trong phiên hiện tại; không có lịch sử hội thoại lâu dài hoặc API xem lại. Nếu không còn phiên/quyền thì không tái sử dụng ngữ cảnh cũ. | NFR-01, NFR-05; FR-25 hoãn lại |
| Lưu trữ sau khi gỡ | Giữ metadata và dấu vết cần kiểm chứng; ngừng quyền đọc/phục vụ bản đã gỡ. File vật lý chỉ người có quyền vận hành tiếp cận theo chính sách lưu dữ liệu; chưa có xóa tự động theo lịch. | FR-13, FR-17, FR-36, NFR-05, NFR-16 |
| Dùng dữ liệu người học để nghiên cứu | Không tự lấy hội thoại hoặc bài nộp làm dữ liệu fine-tune. Corpus/instruction/QA nghiên cứu được chuẩn bị riêng, có quyền sử dụng và kiểm soát thông tin cá nhân. | FR-R01–FR-R02, NFR-05 |

Ba chức năng AI được giới hạn bằng quyền dữ liệu và chính sách ở backend, kết hợp prompt và kiểm tra đầu ra. Bộ test phải phân biệt lộ đáp án do truy cập dữ liệu riêng với việc mô hình tự suy luận ra lời giải. Giới hạn prompt không được xem là bằng chứng đã bảo vệ được đáp án.

## 5. Phạm vi nghiên cứu bắt buộc

### 5.1. Đầu ra nghiên cứu

| Nội dung | Yêu cầu được chọn | Đầu ra cần có |
|---|---|---|
| Corpus và QA | FR-R01; UC-R01 | Danh sách tài liệu, quyền sử dụng, checksum/phiên bản và QA có đáp án hoặc hành vi mong đợi, vị trí nguồn, loại mẫu và split. |
| QLoRA | FR-R02; UC-R02 | Dry-run, ít nhất một lượt huấn luyện adapter hoàn chỉnh, checkpoint, cấu hình, log và model/adapter card. |
| So sánh mô hình | FR-R03; UC-R03 | Kết quả Base LLM, RAG và QLoRA+RAG trên cùng protocol, với dữ liệu và cấu hình truy vết được. |
| Khảo sát retrieval | FR-R03; UC-R03 | Baseline dense và thí nghiệm thêm BM25/fusion, reranker trên development; ghi chất lượng và độ trễ để chọn cấu hình phục vụ. |
| Đánh giá thủ công | FR-R04; UC-R04 | Rubric, bảng chấm mẫu, phân tích lỗi và đối chiếu với metric tự động. |

QLoRA là đầu ra bắt buộc của đề tài, không bị chuyển thành chức năng tùy chọn vì upload tài liệu đã dùng RAG. Nhóm không yêu cầu adapter nhất thiết phải làm mọi metric tốt hơn. Kết quả không cải thiện vẫn phải được phân tích và báo cáo; không thay đổi tập test để tạo kết quả tốt hơn.

Base model dùng để so trước/sau adapter phải giống nhau. Nếu tài nguyên khiến nhóm chọn model nhỏ hơn, cần chạy lại các baseline tương ứng và ghi quyết định; không so chênh lệch giữa hai kích thước model như thể chỉ do QLoRA. Model và tham số training cụ thể được chốt trong cấu hình thí nghiệm sau dry-run.

### 5.2. Bộ đánh giá được chọn

| Tập | Số mẫu tối thiểu | Mục đích |
|---|---|---|
| Development | 100 | Bao gồm pilot hợp lệ; chọn retrieval, ngưỡng, prompt và hiệu chỉnh rubric trước đánh giá cuối. |
| Test hỏi đáp có nguồn | 140 | Đo retrieval, correctness, faithfulness và citation trong phạm vi học liệu. |
| Test thiếu nguồn/ngoài phạm vi/mơ hồ | 20 | Kiểm tra từ chối, thông báo giới hạn hoặc hỏi lại theo nhãn. |
| Test gợi ý | 20 | Đánh giá tính có ích và chính sách trợ giúp. |
| Test tóm tắt | 20 | Đánh giá ý chính, độ đúng, nguồn và độ bao phủ. |

Tập test có tối thiểu 200 mẫu, độc lập với 100 mẫu development. Ngoài benchmark 300 mẫu, nhóm lập tối thiểu 20 tình huống truy cập sai quyền và 20 tình huống prompt injection ở câu hỏi/học liệu. Các tình huống này được báo cáo riêng để phân biệt kiểm thử bảo mật với đánh giá kiến thức.

Nhóm kiểm tra thủ công ít nhất 30 mẫu trong kết quả test, có đại diện các nhóm tình huống và ghi cách chọn mẫu. Với gợi ý/tóm tắt, các mẫu của nhóm đó phải được chấm theo rubric phù hợp. Nhãn/đáp án test không dùng để fine-tune; instruction dataset được quản lý riêng và rà soát trùng với benchmark. Corpus dùng làm chỉ mục có thể chứa tài liệu làm căn cứ cho QA test theo protocol.

Faithfulness, retrieval và citation chỉ chấm khi cấu hình có thành phần tương ứng. Base LLM không có retrieval không bị gán một context giả để tính các metric này. Mọi báo cáo phải ghi số mẫu, lượt lỗi và trường hợp không áp dụng.

## 6. Phạm vi phi chức năng và mục tiêu nghiệm thu

### 6.1. Điều kiện bắt buộc

| Nhóm chất lượng | Yêu cầu áp dụng | Điều kiện nghiệm thu |
|---|---|---|
| Quyền và bảo mật | NFR-01–NFR-06 | Bộ test trong phạm vi phải đạt; không có lỗi truy cập trái phép, đọc đáp án riêng, lộ bí mật hoặc thực thi file upload. Lịch sử lâu dài không triển khai nhưng ngữ cảnh phiên/log vẫn phải theo quyền. |
| Hiệu năng và tài nguyên | NFR-07–NFR-10 | Có phép đo theo cấu hình và dữ liệu đã ghi; giới hạn tải, hàng đợi và timeout hoạt động; không còn OOM trong bộ chạy cấu hình demo. |
| Lỗi và phục hồi | NFR-11–NFR-14 | AI ngắt không làm mất chức năng LMS độc lập; thao tác lặp nhất quán; dữ liệu đã lưu tồn tại sau restart; có bằng chứng thử khôi phục. |
| Nhất quán dữ liệu | NFR-15–NFR-17 | Khóa học, tài liệu/phiên bản, lượt làm và điểm liên kết đúng; thay quyền/nguồn khi đang xử lý không trả nội dung đã mất quyền; hạn do server kiểm soát. |
| Giao diện | NFR-18–NFR-20 | Đọc được tiếng Việt, có thông báo trạng thái, chạy được ở 360 px/1.280 px và sử dụng các thao tác chính bằng bàn phím. |
| Triển khai và kiểm thử | NFR-21–NFR-25 | Có hướng dẫn chạy, cấu hình mẫu, kiểm thử các luồng đã chọn, log truy vết và dữ liệu/cấu hình tái lập. |
| Chất lượng AI | NFR-26–NFR-32 | Có kết quả trên bộ đã đóng băng, báo đạt/chưa đạt từng mục tiêu và đối chiếu thủ công. Không coi ID nguồn hợp lệ là citation đúng về nội dung. |

### 6.2. Cấu hình vận hành ban đầu

| Tham số | Giá trị được chọn cho nguyên mẫu |
|---|---|
| File học liệu | PDF văn bản, tối đa 20 MiB và 100 trang. |
| File bài nộp | PDF/PNG/JPEG, tối đa 20 MiB; không vào chỉ mục RAG. |
| Generation đồng thời | Một lượt trên một model service. |
| Hàng đợi AI | Tối đa 5 tác vụ chờ ngoài tác vụ đang chạy; vượt giới hạn trả thông báo bận. |
| Quota học viên | 20 yêu cầu AI/giờ/học viên cho tổng ba chế độ, kiểm tra tại backend. |
| Hỏi đáp/gợi ý | Tối đa 4.096 token đầu vào mỗi lượt và 512 token sinh; vượt ngân sách phải kiểm soát hoặc yêu cầu thu hẹp, không bỏ bằng chứng cần thiết mà vẫn khẳng định đủ nguồn. |
| Timeout hỏi đáp/gợi ý | 180 giây tính từ lúc tiếp nhận, gồm thời gian chờ; tác vụ hết hạn không tiếp tục chiếm hàng đợi hoặc ghi kết quả thành công. |
| Tóm tắt | Tối đa 20 trang và 10.000 token nguồn; timeout tác vụ 600 giây tính từ tiếp nhận. Báo phạm vi chưa hoàn thành nếu ngắt. |
| Ingestion | Timeout tác vụ 900 giây cho file trong giới hạn; lỗi quá thời gian được ghi để giáo viên thử lại. |

Các tham số được cấu hình thay vì ghi cứng trong nghiệp vụ. Đây là cấu hình ban đầu đã chọn để kiểm chứng. Nếu pilot cho thấy không phù hợp, nhóm ghi thay đổi, lý do và đo lại trước khi đóng băng bản demo. Việc điều chỉnh tham số không tự mở thêm loại file hoặc chức năng ngoài phạm vi.

### 6.3. Mục tiêu định lượng

| Thuộc tính | Mục tiêu đánh giá của MVP | Yêu cầu |
|---|---|---|
| API LMS | p95 ≤ 2 giây, 1.000 yêu cầu/10 người dùng ảo, đo riêng các endpoint không truyền file/AI/dịch vụ ngoài. | NFR-07 |
| Hỏi đáp/gợi ý AI | p95 ≤ 120 giây theo bộ đo 50 câu hỏi trong phạm vi ở development, một lượt sinh đồng thời và giới hạn token đã chọn; ghi cả lỗi và thời gian chờ. | NFR-08 |
| Tiếp nhận ingestion | ≤ 3 giây sau khi nhận và lưu file; thời gian truyền và xử lý nền đo riêng. | NFR-09 |
| Retrieval | Recall@5 trung bình ≥ 0,80 trên QA có nguồn chuẩn, với đơn vị bằng chứng thống nhất. | NFR-26 |
| Correctness | Ít nhất 75% QA hỏi đáp trong phạm vi đạt rubric. | NFR-27 |
| Faithfulness | Trung bình ≥ 0,85 trên câu trả lời có context, ghi evaluator và số mẫu chấm được. | NFR-28 |
| Citation | Accuracy ≥ 0,90 và coverage ≥ 0,90; toàn bộ tham chiếu được hiển thị phải qua kiểm tra ID/phiên bản/quyền. | NFR-29 |
| Từ chối/hỏi lại | ≥ 90% mẫu giới hạn được xử lý đúng; từ chối sai trên QA có đủ nguồn ≤ 10%. | NFR-30 |
| Gợi ý | ≥ 80% mẫu đạt rubric; không có mẫu lộ đáp án bảo vệ trong bộ test đã xác định. | NFR-31 |
| Tóm tắt | Bao phủ ≥ 80% ý chính có nhãn; nhận định không được nguồn hỗ trợ ≤ 10%. | NFR-32 |

Các ngưỡng này là mục tiêu được chọn cho kế hoạch đánh giá, chưa phải kết quả đã đạt. Nếu không đạt, nhóm phải ghi chỉ tiêu chưa đạt và phân tích lỗi. Thay ngưỡng cần quyết định có lý do trước test cuối, không hạ ngưỡng sau khi xem điểm test để tuyên bố nghiệm thu. Tính đạt/chưa đạt của các cấu hình phải được báo riêng; kết quả QLoRA không cải thiện không được che giấu.

## 7. Chức năng ngoài MVP

| Yêu cầu hoặc phần mở rộng | Quyết định | Lý do |
|---|---|---|
| FR-05; UC-01 | Hoãn tự đăng ký. | Tài khoản cấp sẵn đủ kiểm chứng luồng theo vai trò; giảm quy trình xác minh và khôi phục tài khoản. |
| FR-07; UC-05 | Hoãn khám phá/tìm kiếm khóa học công khai. | Bản đầu dùng danh sách lớp được cấp, tập trung vào tương tác học trong khóa học. |
| FR-25; UC-16 | Hoãn lịch sử hội thoại lâu dài. | Giảm lưu trữ dữ liệu riêng và xử lý citation lịch sử; vẫn bảo vệ ngữ cảnh phiên hiện tại. |
| FR-33; UC-24 | Hoãn dashboard thống kê tổng nền tảng. | Giữ thống kê lớp và thông tin vận hành cần thiết cho demo. |
| FR-X01–FR-X02; UC-X01–UC-X02 | Hoãn thanh toán và doanh thu. | Không cần để kiểm chứng trợ lý học tập; có thêm nghiệp vụ giao dịch và đối soát. |
| FR-X03; UC-X03 | Hoãn video tương tác. | Bài học văn bản/PDF đủ cho lát cắt học tập; streaming và điểm dừng tăng khối lượng tích hợp. |
| FR-X04; UC-X04 | Không bật chế độ kiến thức tổng quát trong MVP. | Giữ phạm vi trả lời và cách đánh giá theo corpus khóa học. |
| Các định dạng khác và OCR của FR-16 | Hoãn hỗ trợ trực tiếp; cho phép chuẩn hóa đầu vào sang PDF văn bản. | Cần thêm parser, kiểm tra vị trí nguồn và dữ liệu đánh giá trích xuất. |
| Tóm tắt toàn khóa học của FR-24 | Hoãn; chỉ một tài liệu/khoảng trang trong giới hạn. | Giảm tác vụ dài và có thể kiểm tra độ bao phủ theo nguồn cụ thể. |
| Multi-agent, chấm tự luận bằng AI | Ngoài phạm vi phiên bản này. | Ba chế độ không cần nhiều agent; điểm chính thức do giáo viên quyết định. |

Hoãn một chức năng không có nghĩa bỏ các kiểm soát đi kèm chức năng đang giữ. Ví dụ, không xây lịch sử lâu dài vẫn phải bảo vệ ngữ cảnh hiện tại; không có marketplace vẫn phải kiểm tra quyền tham gia lớp; chưa có OCR vẫn phải phát hiện tài liệu không đủ nội dung.

## 8. Lộ trình hoàn thành trong phạm vi đã chốt

| Mốc | Nội dung cần đạt | Bằng chứng |
|---|---|---|
| M1 — Lát cắt hỏi đáp | Tài khoản, khóa học/thành viên, upload PDF, xử lý nền, hỏi đáp và mở nguồn có quyền. | Demo trực tiếp và test quyền/lỗi; dữ liệu một môn và QA pilot. |
| M2 — Ba chế độ AI | Gợi ý theo chính sách, tóm tắt có độ bao phủ, quota/timeout và thay thế/gỡ học liệu nhất quán. | Kết quả kiểm thử gợi ý/tóm tắt, lỗi tài liệu và tác vụ bị ngắt. |
| M3 — LMS cơ bản | Bài học, tiến độ, quiz, bài tập, chấm điểm và thống kê lớp tích hợp với quyền/chính sách AI. | Luồng học viên làm/nộp bài, giáo viên chấm/công bố và kiểm thử trạng thái. |
| M4 — Nghiên cứu và nghiệm thu | Corpus/benchmark đủ quy mô, adapter QLoRA, so sánh và đánh giá thủ công; đóng gói, khôi phục và tài liệu chạy. | Log, kết quả từng mẫu, bảng chỉ số, rubric và bản demo có cấu hình tái lập. |

M1 là mốc tích hợp đầu tiên, không phải toàn bộ MVP. Ba chế độ AI, nghiệp vụ học tập cơ bản và đầu ra nghiên cứu vẫn là điều kiện hoàn thành phiên bản cuối. Nhóm phát triển và đo thử từ sớm, không đợi hoàn thành từng module độc lập mới tích hợp.

## 9. Kịch bản nghiệm thu MVP

| Mã | Kịch bản | Điều kiện đạt | Truy vết |
|---|---|---|---|
| MVP-01 | Admin cấp tài khoản, giáo viên tạo lớp và cấp quyền học viên. | Đăng nhập đúng vai trò; học viên chỉ thấy lớp được cấp; thu hồi quyền/khóa tài khoản có hiệu lực. | FR-01–FR-04, FR-06, FR-08–FR-09; AC-02 |
| MVP-02 | Giáo viên tải PDF, xử lý, thay bản và gỡ tài liệu. | Trạng thái đúng; nguồn/citation đúng phiên bản; retry không trùng; file không hỗ trợ không báo sẵn sàng; nguồn đã gỡ không tiếp tục phục vụ. | FR-12–FR-17; AC-01, AC-03–AC-04 |
| MVP-03 | Học viên hỏi câu có nguồn, câu mơ hồ và câu thiếu nguồn. | Có câu trả lời/nguồn kiểm chứng hoặc phản hồi giới hạn phù hợp; kiểm tra các mục tiêu chất lượng trên benchmark. | FR-18–FR-21; AC-01, AC-03 |
| MVP-04 | Học viên xin gợi ý trong các trạng thái bài và thử yêu cầu đáp án riêng. | Chính sách áp dụng đúng; không truy cập đáp án bảo vệ; ghi kết quả rubric và mẫu vi phạm nếu có. | FR-22–FR-23, FR-26–FR-27; AC-05 |
| MVP-05 | Tóm tắt một phạm vi hợp lệ và yêu cầu vượt giới hạn. | Tóm tắt có nguồn/độ bao phủ trong phạm vi; vượt giới hạn yêu cầu thu hẹp; tác vụ ngắt không báo đã tóm tắt đầy đủ. | FR-18, FR-21, FR-24; AC-06 |
| MVP-06 | Học viên học bài, làm quiz/nộp tự luận; giáo viên chấm/công bố. | Tiến độ nhất quán, thời gian server được áp dụng, nộp lặp không trùng; điểm và thống kê lớp đúng, không lộ dữ liệu người khác. | FR-10–FR-11, FR-26–FR-32, FR-36; AC-08 |
| MVP-07 | AI/worker bị ngắt, hàng đợi/quota đầy hoặc tiến trình khởi động lại. | Lỗi được báo; LMS độc lập còn hoạt động; tác vụ không kẹt vô hạn; dữ liệu đã lưu còn; có test khôi phục. | FR-14–FR-15, FR-34–FR-35; AC-07 |
| MVP-08 | Dùng tài khoản khác quyền và prompt injection ở câu hỏi/tài liệu. | Toàn bộ test sai quyền bị chặn; không lộ bí mật/đáp án riêng; log không chứa toàn văn dữ liệu ngoài chính sách. | NFR-01–NFR-06; AC-02, AC-05 |
| MVP-09 | Chạy so sánh mô hình và tái lập một phần thí nghiệm. | Có adapter thực, split độc lập, cấu hình và kết quả từng mẫu; báo metric đúng phạm vi áp dụng, có đánh giá thủ công và phân tích lỗi. | FR-R01–FR-R04, NFR-24–NFR-32; AC-09 |
| MVP-10 | Cài và chạy sản phẩm từ checkout sạch. | Hướng dẫn tái lập được; gọi model thật trong luồng web–AI, mở được nguồn theo quyền; phiên bản model/dữ liệu và cấu hình được ghi. | NFR-21–NFR-25; AC-01 |

Không nghiệm thu nếu còn lỗi truy cập trái phép, lộ đáp án riêng do sai quyền, mất/nhân đôi dữ liệu điểm hoặc bài nộp, hay citation dẫn tới tài liệu không được phép. Phần chất lượng AI phải có báo cáo đạt/chưa đạt mục tiêu; một chỉ số tốt không bù cho lỗi nghiêm trọng của nghiệp vụ hoặc bảo mật.

## 10. Hạ tầng, phụ thuộc và rủi ro

### 10.1. Phân biệt phần mềm web và thí nghiệm AI

LMS và dữ liệu nghiệp vụ được chạy trên môi trường phát triển có lưu trữ bền vững. Colab Free T4 được dùng cho dry-run, huấn luyện và đánh giá tương tác trong notebook; dữ liệu cần giữ, checkpoint và kết quả phải được lưu ra nơi có thể phục hồi.

Để đạt MVP-10, nhóm cần một môi trường inference phù hợp và kết nối được với dịch vụ web trong điều kiện demo. Nơi phục vụ model và cách kết nối là phụ thuộc kỹ thuật phải giải quyết trước nghiệm thu tích hợp. Tài nguyên Colab Free đã có không được xem là bằng chứng rằng đã có máy chủ inference hoạt động liên tục; phạm vi này không yêu cầu xây cơ chế vượt giới hạn hoặc giữ phiên GPU bằng thao tác tự động.

Nếu mới có web LMS và notebook AI riêng, nhóm có thể chứng minh hai phần hoạt động, nhưng phải ghi phần tích hợp chưa hoàn thành. Kết quả lưu sẵn hoặc mock được dùng khi phát triển/kiểm thử giao diện phải được nhận diện rõ, không thay cho demo gọi model thật để tuyên bố đạt MVP-10.

### 10.2. Phụ thuộc và biện pháp xử lý

| Rủi ro/phụ thuộc | Cách xử lý trong phạm vi |
|---|---|
| Corpus có nhiều file quét hoặc định dạng khác PDF | Kiểm tra từ khi chọn dữ liệu; bổ sung PDF văn bản có quyền sử dụng hoặc chuẩn hóa file. Không đưa OCR vào MVP chỉ để xử lý một file demo mà chưa có phép kiểm chứng. |
| PDF quá dài hoặc layout khó | Áp dụng giới hạn, kiểm tra nội dung/vị trí; chia tài liệu hợp lý hoặc báo chưa hỗ trợ. Không bỏ lỗi nguồn để giữ trạng thái sẵn sàng. |
| T4 không đủ tài nguyên hoặc runtime ngắt | Dry-run, giới hạn context/concurrency, lưu checkpoint; chọn model nhỏ hơn bằng quyết định và chạy lại baseline tương ứng. |
| Chưa có nơi inference cho demo web | Đánh giá khả năng triển khai ngay từ M1; xác định môi trường được phép dùng. Nếu chưa giải quyết, ghi blocker tích hợp, không cắt tiêu chí model thật khỏi nghiệm thu. |
| QA thiếu nhãn hoặc trùng | Thống nhất schema/định danh nguồn giữa A và B, rà trước khi đóng băng split; giữ đủ số mẫu hợp lệ thay vì đếm bản trùng. |
| QLoRA hoặc hybrid/rerank không cải thiện | Báo kết quả và phân tích; chọn cấu hình phục vụ theo development và tài nguyên, giữ đầy đủ kết quả thí nghiệm. |
| Tiến độ thiếu thời gian | Hoãn chức năng ở mục 7 trước; mọi cắt giảm ba chế độ AI, nghiệp vụ được chọn hoặc nghiên cứu bắt buộc phải có quyết định thay đổi phạm vi riêng. |

## 11. Đầu ra và nguyên tắc kiểm soát thay đổi

### 11.1. Đầu ra để kiểm tra hoàn thành

- Mã nguồn và hướng dẫn chạy các chức năng trong MVP, cùng cấu hình mẫu không chứa bí mật.
- Dữ liệu demo thể hiện ít nhất hai phạm vi khóa học và các vai trò khác nhau.
- Corpus/manifest, QA development/test có phiên bản, adapter QLoRA và thông tin lấy model/checkpoint.
- Kết quả kiểm thử MVP-01–MVP-10, phép đo hiệu năng, benchmark từng mẫu, rubric và phân tích lỗi.
- Demo trực tiếp luồng web–AI và luồng học/đánh giá; dữ liệu cần phục hồi không chỉ lưu trong phiên GPU tạm thời.

### 11.2. Kiểm soát thay đổi

Khi phát hiện cần thay đổi phạm vi, nhóm ghi rõ nội dung, lý do, yêu cầu/use case bị ảnh hưởng, tác động tới dữ liệu và kiểm thử, cùng quyết định thay thế. Thay đổi chức năng phải được cập nhật vào tài liệu SRS và danh sách nghiệm thu; các bản yêu cầu tổng thể vẫn được giữ để biết chức năng nào đang hoãn.

Thay đổi ngưỡng AI, model hoặc cấu hình retrieval phải được quyết định trên development trước đánh giá cuối. Nhóm không tự mở thêm chức năng chỉ vì có công nghệ mới, không cắt phần nghiên cứu bắt buộc mà vẫn giữ nguyên tuyên bố hoàn thành đề tài và không coi việc viết xong tài liệu phạm vi là sản phẩm đã được nghiệm thu.

## 12. Phần việc tiếp theo của em

Sau khi chốt phạm vi, em dùng các chức năng và kịch bản nghiệm thu đã chọn để xây 25 QA pilot của phần B, phối hợp với thành viên A về corpus và định danh nguồn. Các mẫu hỏi đáp, gợi ý, tóm tắt và giới hạn được gán hành vi mong đợi theo đúng phạm vi trợ lý; câu trả lời và vị trí nguồn được kiểm tra trên tài liệu thực tế.

Kết quả phần B được kết hợp với dữ liệu của A để hoàn thiện development, từ đó kiểm chứng cấu hình và chuẩn bị bộ test độc lập. Phân tích SRS/MVP phục vụ việc triển khai của nhóm, không đồng nghĩa một thành viên phải tự thực hiện toàn bộ module và thí nghiệm.
