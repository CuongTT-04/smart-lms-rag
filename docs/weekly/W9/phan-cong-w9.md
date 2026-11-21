# Phân công hoàn thiện LMS core và AI assistant

**Mục tiêu:** Hoàn thiện LMS core: course/lesson/quiz/submission + AI assistant, chứng minh bằng demo tích hợp và kiểm thử có thể chạy lại.

**Căn cứ nghiệm thu theo giảng viên:** “Hoàn thiện LMS core: course/lesson/quiz/submission + AI assistant”, thuộc mốc W8 theo lịch giảng viên giao. Ưu tiên tiêu đề và nội dung yêu cầu này khi lịch trong tài liệu đề cương bị lệch. Đầu ra là demo LMS tích hợp với dữ liệu hoạt động giả lập và bằng chứng kiểm chứng.

**Tiêu đề milestone:** `Hoàn thiện LMS core: course/lesson/quiz/submission + AI assistant`. Mã việc `W9-01`, `W9-02` và đường dẫn `weekly/W9`, `Evidence/W09` là các định danh đã dùng trong hồ sơ triển khai; nghiệm thu theo nội dung yêu cầu giảng viên ở trên. Các mã kế hoạch chưa phải số Issue GitHub. Khi tạo Issue mới dùng số thật cho `Refs`/`Closes`.

**Thành viên:** Trần Tuấn Cường (B, B22DCVT073), Vũ Nam Dương (A, B22DCVT119).

> Hướng dẫn agent: đọc SRS, bản phân công này và code hiện tại trước khi triển khai. Thực hiện từng tác vụ kèm kiểm thử; dùng skill executing-plans nếu có. Có thể dùng agent để triển khai và review, không cần thêm vòng duyệt tay. Ghi đúng người phụ trách, công cụ thực hiện và bằng chứng thực tế; không ghi nghiệm thu khi chưa chạy. Không tự commit/push/merge nếu chưa được yêu cầu.

## 1. Hiện trạng và ranh giới

**Căn cứ phân công cập nhật:** Trước W9, Cường phụ trách tích hợp AI vào LMS, Dương phụ trách train model. Theo thống nhất mới, Dương tiếp nhận toàn bộ phần Ayo đang có, gồm backend/gateway/RAG, giao diện trợ lý, memory, citation, gợi ý làm bài, tóm tắt và câu hỏi gợi ý tiếp theo. Cường phụ trách hoàn thiện LMS: course/lesson, tiến độ, kết quả lớp, quiz/submission và dữ liệu demo. Việc chuyển trách nhiệm W9 không thay đổi người thực hiện công việc trước đây. Không yêu cầu train lại để hoàn thành W9.

Đã có tài khoản, khóa học/lớp, tham gia/duyệt lớp, buổi học, PDF và pipeline indexing, video tương tác, quiz, tự luận/file, chấm điểm, dashboard từng bài, lịch sử Ayo và gợi ý ôn tập. Mở rộng các luồng đang có, không xây lại LMS.

Kiểm ngày 17/11: 6 dịch vụ Docker đang chạy, không còn migration chờ; 40 chunk không sai provenance. Hai câu CPU qua backend–Kaggle đều `ANSWERED`; chu kỳ CPU lấy trang 8–9, nhưng câu ALU còn citation chưa hỗ trợ hết ý. Bộ backend chạy trong Docker: 353 test, 7 failure và 11 error. Các số này là đầu vào điều tra, không phải kết quả hoàn thành W9.

Tài liệu gốc: `docs/SRS.md`, `D:/ĐATN_Đề cương chi tiết.docx`. Log kiểm ban đầu tại `.private/lms-live-audit-20261117/`; không đưa nội dung học liệu riêng, token, tài khoản hoặc log thô nhạy cảm lên Git.

Trong W9 phải hoàn thiện tiến độ, thống kê lớp, tính bền vững, quyền và luồng trợ lý tích hợp. OCR, DOCX/PPTX/TXT, thanh toán/doanh thu và dashboard quản trị nền tảng tiếp tục là phạm vi sản phẩm cuối; không coi hoàn thành W9 là hoàn thành toàn bộ SRS. Không huấn luyện lại hoặc thay benchmark W7 trong công việc này.

## 2. W9-01 – Cường: tiến độ, kết quả lớp và độ ổn định LMS

**Kế hoạch thực thi cho agent:** [plan-w9-01-cuong.md](plan-w9-01-cuong.md) – tác vụ T0–T7, hợp đồng API, test và bàn giao.

**Tiêu đề Issue:** `W9-01 – Trần Tuấn Cường – Hoàn thiện tiến độ học, kết quả lớp và luồng quiz/submission`.

**Đầu vào:** Code hiện tại, SRS về học/đánh giá/thống kê, models Enrollment/VideoProgress/AssessmentAttempt, dashboard từng bài; hợp đồng nguồn/học liệu do Dương bàn giao tại mục 4.

### L1. Tiến độ học và hoàn thành

- [ ] Khảo sát `backend/apps/courses/models.py`, `video_services.py`, `assessment_services.py`, `api/serializers.py` và `backend/apps/learning/`; chọn một nơi tính tiến độ dùng chung, tránh thêm bộ tính thứ hai.
- [ ] Viết test các tình huống: chưa học, hoàn thành một phần, hoàn thành toàn bộ, không có hoạt động, gửi lặp, nhiều lượt ôn tập, hoạt động bị gỡ và học viên mất quyền.
- [ ] Triển khai API và lưu trạng thái hoàn thành từng hoạt động; cập nhật tổng tiến độ theo hợp đồng mục 4. Nối giao diện học viên và roster giáo viên với dữ liệu thật.
- [ ] Reload/restart vẫn giữ trạng thái; hai học viên có tiến độ riêng; học viên không tự ghi điểm hoặc tiến độ của người khác.

**Đầu ra:** tiến độ buổi học/lớp hoạt động thật, API có tài liệu, migration và test. `Enrollment.progress_percent`/`completed_at` có quy tắc cập nhật rõ, không chỉ là trường mặc định.

### L2. Kết quả và teacher analytics toàn lớp

- [ ] Thay placeholder tại `frontend/src/components/ClassroomWorkspace.jsx` bằng bảng kết quả học tập thật; bổ sung API/selectors, tái sử dụng `assessment_reports.py` và dashboard hiện có.
- [ ] Có từng học viên, tiến độ, số bài đã nộp/chưa nộp, điểm đã công bố, trạng thái chờ chấm và bộ lọc. Hiển thị được lớp chưa có học viên/bài, bài quá hạn và bài bị gỡ.
- [ ] Ghi rõ cách lấy kết quả ôn tập nhiều lượt (điểm cao nhất trong các lượt đã nộp/chấm), kiểm tra lấy lượt hợp lệ duy nhất. Đếm nộp bài theo học viên/bài, không nhân số lượt làm thành số học viên.
- [ ] Tách bản nháp, đã nộp, chờ chấm và điểm 0. Giáo viên xem lớp mình; học viên chỉ xem kết quả được phép của chính mình.
- [ ] Nếu có xuất Excel, kết quả xuất khớp bộ lọc và API; thống kê tổng phải đối chiếu được dữ liệu gốc.

**Đầu ra:** tab Kết quả dùng được cho giáo viên/học viên theo quyền; số liệu khớp dữ liệu hoạt động giả lập.

### L3. Quiz/submission và kiểm thử tích hợp

- [ ] Rà `frontend/src/components/assessments/AssessmentRunner.jsx`, `AssessmentDashboard.jsx`, `backend/apps/courses/api/assessment_views.py` và tests liên quan.
- [ ] Kiểm tạo/công bố, làm/lưu nháp/nộp, hết hạn, gửi lặp, nộp lại ôn tập, chấm/công bố điểm; không lộ đáp án kiểm tra trước thời điểm cho phép.
- [ ] Sửa thống kê câu đã trả lời nếu giá trị là mảng rỗng; thống nhất hai nút trợ giúp theo API AI do Dương cung cấp, bỏ thông báo “chưa kết nối” cố định khi thực tế đã có Ayo.
- [ ] Điều tra và sửa lỗi DB đóng kết nối trong nhóm test buổi học; phân biệt lỗi test harness với lỗi sản phẩm. Chạy lại nhóm test và toàn bộ bộ kiểm backend liên quan.
- [ ] Chuẩn bị script/command dữ liệu demo có seed cố định, chỉ chạy với môi trường demo/test riêng, có chống tạo trùng. Không sửa tài khoản/dữ liệu đang dùng.

**Đầu ra bàn giao Dương:** mã nguồn/migration/test, hướng dẫn tạo dữ liệu demo, các API và quy tắc tiến độ/điểm cuối cùng; log đã lọc nhạy cảm và SHA commit khi có commit thực.

### L4. Bàn giao phần tích hợp hiện có và ghép demo

- [ ] Cường bàn giao Dương baseline code đang dùng, cách khởi động Docker, cấu hình runtime đã khử bí mật và vị trí cell Kaggle hiện hành; ghi commit/hash khi có bản cố định. Secrets chỉ truyền riêng, không đưa vào tài liệu công khai.
- [ ] Gửi luồng gọi hiện tại từ UI → API chat/conversations → retrieval/runtime → gateway; các test liên quan và log lỗi CPU trong `.private/lms-live-audit-20261117/` để Dương tái hiện trước khi sửa.
- [ ] Bàn giao API/state LMS mà Ayo cần: scope course/classroom/session/document/version, trạng thái bài kiểm tra, công bố/gỡ/thu hồi quyền; không giao đáp án riêng cho model.
- [ ] Nhận code/hợp đồng AI từ Dương, ghép với LMS, kiểm độc lập theo mục 6 và gửi bằng chứng LMS cho Dương tổng hợp Evidence.

**Đầu ra bổ sung:** ghi chú bàn giao đủ để Dương chạy lại Ayo hiện có và bản demo tích hợp có thể kiểm lại.

## 3. W9-02 – Dương: tích hợp Ayo, học liệu và quyền vào LMS

**Tiêu đề Issue:** `W9-02 – Vũ Nam Dương – Hoàn thiện Ayo có nguồn và tích hợp học liệu vào LMS`.

**Đầu vào:** pipeline tại `backend/apps/ai/`, `backend/apps/documents/`, UI trợ lý/học liệu, cell Kaggle hiện dùng, PDF CPU đã được phép kiểm tra nội bộ; API/trạng thái LMS từ Cường.

### I1. Quyền học liệu và lưu trữ bền vững

- [ ] Viết regression cho học viên gọi trực tiếp API buổi học nháp và PDF bên trong; sửa nhất quán `courses/api/session_views.py`, `documents/access.py`, API/media và retrieval scope. Chủ khóa vẫn xem được bản nháp theo quyền quản lý.
- [ ] Kiểm lớp khác, học viên bị thu hồi, buổi học/tài liệu bị gỡ và URL nguồn cũ; frontend ẩn không thay thế kiểm quyền backend.
- [ ] Chuyển ghi chú/nét vẽ/đánh giá học liệu trong `documents/api/study_notes.py` từ LocMemCache sang database, giữ giao diện API nếu khả thi. Scope theo user/document/version, không trộn với like/dislike câu trả lời Ayo.
- [ ] Test lưu–đọc lại–restart, hai tài khoản, thay phiên bản và thu hồi quyền. Dữ liệu tạm cũ không được báo là đã khôi phục nếu thực tế không còn.

**Đầu ra:** quyền buổi học/học liệu thống nhất; ghi chú được lưu bền vững; migration, API docs và regression tests.

### I2. Ayo hỏi đáp, gợi ý và tóm tắt

- [ ] Phân biệt chưa indexing/đang lỗi indexing với không có căn cứ học thuật. UI báo đúng và hướng dẫn thử lại khi đã READY; không dùng tài liệu sai scope để lấp nguồn thiếu.
- [ ] Điều tra citation sai hỗ trợ trong câu ALU: mỗi ý phải dẫn đúng đoạn/trang hỗ trợ ý đó; không gán tất cả nguồn cho mọi ý hoặc thêm citation dựa trên suy đoán.
- [ ] Giữ trả lời quy trình nhiều trang đầy đủ; không cắt về một trang để né lỗi. Tài liệu không đủ thì nêu giới hạn, không bịa phần tiếp nối.
- [ ] Hoàn thiện tóm tắt theo tài liệu/phạm vi chọn, có nguồn và giới hạn bao phủ rõ. Bổ sung mode/schema/gateway/UI/test đồng bộ; không gọi tóm tắt toàn tài liệu nếu mới đọc top-5 đoạn.
- [ ] Kiểm câu nối “Nó có mấy cổng?” sau ALU, chuyển chủ đề CU, câu thiếu căn cứ và hai hội thoại độc lập; lịch sử không trở thành bằng chứng nguồn.
- [ ] Dương triển khai 2–3 câu hỏi gợi ý tiếp theo dưới câu trả lời Ayo, sau khi citation và memory ổn định. Gợi ý bám nội dung và phạm vi học liệu hiện tại, tránh lặp câu vừa hỏi hoặc giả định thông tin chưa có căn cứ. Bấm gợi ý tạo lượt hỏi mới trong đúng hội thoại, dùng cùng kiểm quyền và chống gửi trùng như nhập tay. Không tự gửi khi chưa bấm; nếu sinh gợi ý lỗi thì vẫn hiển thị câu trả lời chính. Kiểm thử bấm gợi ý, giữ memory, chuyển hội thoại và lỗi sinh gợi ý. Đây là phần bổ sung trải nghiệm do nhóm chọn cho W9, không phải tiêu chí bắt buộc riêng được trích từ đề cương.
- [ ] Sửa `ai/policy.py` để lượt kiểm tra bị gỡ/mất quyền không chặn AI vô thời hạn; khi kiểm tra còn hiệu lực vẫn chặn đúng. Gợi ý chỉ gửi đề/choices được phép, không gửi đáp án/rubric riêng tới model.
- [ ] Cung cấp một hợp đồng gợi ý thống nhất cho Cường nối UI. Khi Kaggle ngắt/bận/timeout/config lệch, báo đúng lỗi; phần LMS vẫn học/lưu/nộp/chấm được.
- [ ] Dương đối chiếu thông tin model/revision, adapter/checksum/config từ phần train mình phụ trách; xác minh trạng thái triển khai thật. Ghi model/revision, adapter bật hay tắt, prompt/config và phiên bản cell thật. Adapter W7 không tự được coi là đã bật trên web; không tuyên bố tuned tốt hơn khi chưa có bằng chứng.

**Đầu ra:** QA/hint/summary dùng được, nguồn đúng phạm vi và hỗ trợ từng ý; test offline + log gọi model thật, hướng dẫn đồng bộ cell/config và các giới hạn còn lại.

### I3. OpenAPI, bàn giao và Evidence cuối

- [ ] Sửa mô tả/response/schema các API chat mới; cập nhật test schema cho endpoint thực và điều tra `DatabaseOperationForbidden`, không bỏ assertion để lấy kết quả xanh.
- [ ] Kiểm độc lập tiến độ/kết quả do Cường bàn giao bằng seed và bảng đáp án số liệu; Cường kiểm lại QA/hint/summary và quyền của Dương.
- [ ] Bàn giao Cường kết quả kiểm nguồn, memory, hint/summary, câu hỏi tiếp theo, lỗi Kaggle và quyền học liệu để ghép demo. Dương nhận bằng chứng LMS từ Cường và tổng hợp `Evidence/W09/` theo cấu trúc Evidence tuần đã dùng: README, test results, metrics, manifest và figures/log. Bằng chứng phải thuộc cùng bản code/config chạy cuối.
- [ ] Lưu cấu hình đã khử bí mật, thời gian chạy, số test thực, trạng thái từng kịch bản và known limitations. Log dùng `.txt` để được Git theo dõi; checkpoint/PDF/token/log thô đặt riêng nếu cần, ghi checksum và đường dẫn bàn giao.

**Đầu ra bàn giao Cường:** code/migration/test, hợp đồng AI cuối, hướng dẫn chạy Kaggle/backend, báo cáo nguồn/latency và gói Evidence cuối có thể kiểm lại. Evidence chưa được gọi là hoàn thành nếu kịch bản còn lỗi.

## 4. Hợp đồng chung và tránh sửa chồng file

Hai bên áp dụng mặc định sau để agent bắt đầu ngay; nếu triển khai cần đổi thì cập nhật tài liệu/API/tests trong cùng thay đổi trước khi bên còn lại tích hợp.

| Nội dung | Quy tắc |
|---|---|
| Hoạt động tính tiến độ | PDF đang công bố, video và bài đánh giá đang công bố trong buổi học đang hiển thị. Không tính bản nháp, bản gỡ hoặc ngoài lớp. Không đếm lại cùng hoạt động theo số lần xem/lượt nộp. |
| PDF hoàn thành | Học viên chủ động đánh dấu hoàn thành sau khi được phép mở. Đây là tự xác nhận đã học, không chứng minh đã hiểu. Gắn phiên bản; đổi bản công bố thì bản mới chưa hoàn thành. |
| Video hoàn thành | Dùng quy tắc server hiện có: xem đủ và qua checkpoint bắt buộc. Không tin chỉ số phần trăm client gửi. |
| Bài hoàn thành | Có lượt nộp hợp lệ; chờ chấm vẫn tính đã nộp. Điểm đậu và hoàn thành nội dung là hai khái niệm riêng. |
| Công thức | Số hoạt động hoàn thành / số hoạt động đang áp dụng ×100, mỗi hoạt động trọng số bằng nhau; mẫu số 0 hiển thị “Chưa có hoạt động”, không tự hoàn thành lớp. |
| Thay đổi nội dung | Thêm/gỡ/công bố lại hoạt động phải tính lại tổng; tiến độ có thể giảm. `completed_at` phản ánh hoàn thành theo chương trình hiện tại, lịch sử sự kiện giữ riêng nếu cần. Không tự khôi phục enrollment bị thu hồi. |
| Quyền dữ liệu | Giáo viên sở hữu lớp xem tổng hợp; học viên chỉ xem trạng thái/điểm cá nhân được phép. API cũng thực thi điều kiện, không chỉ UI. |
| Ownership file | Cường sở hữu assessment/progress/analytics/UI kết quả và fixtures demo. Dương sở hữu AI/documents, API quyền session và schema chat. `AssessmentRunner.jsx` do Cường sửa; Dương bàn giao hợp đồng hint. |
| File chung | Cường tích hợp `ClassroomWorkspace.jsx`; Dương tích hợp `SessionWorkspace.jsx`. `AssessmentRunner.jsx` do Cường giữ, nhận hợp đồng hint/patch từ Dương; không sửa đồng thời. Migration có phụ thuộc chéo thì thống nhất thứ tự, không tạo hai migration cùng số. |

## 5. Thứ tự phối hợp và bộ dữ liệu demo

1. **Đợt 1 – bàn giao và chạy song song:** Cường bàn giao baseline Ayo theo L4; Dương chạy lại baseline, ghi lỗi trước khi thay đổi. Sau đó Cường làm L1/L2 và điều tra test LMS; Dương làm I1/I2 và schema chat. Khóa API/progress/hint theo mục 4, ghi trạng thái bàn giao trong PR.
2. **Đợt 2 – tích hợp:** Cường nối completion/kết quả/AI buttons và chạy seed demo; Dương kiểm nguồn, quyền, lưu trữ và gọi model thật. Mỗi bên review/test phần người kia bằng agent, giữ kết quả kiểm độc lập.
3. **Đợt 3 – chốt:** chạy kiểm thử cuối trên cùng commit/config; Cường chạy demo tích hợp, Dương đối chiếu phần AI và tổng hợp Evidence và hai bên sửa findings đến khi điều kiện mục 6 đạt.

Seed demo tối thiểu: 2 giáo viên, 3 học viên, 2 lớp khác nhau; một học viên chưa tham gia/bị thu hồi; lớp có buổi nháp và buổi công bố; PDF CPU, video có checkpoint, quiz ôn tập, quiz kiểm tra và bài tự luận/file. Có trạng thái chưa học, đang học, hoàn thành, chưa nộp, quá hạn, chờ chấm, điểm 0 và đã công bố. Kèm bảng kết quả mong đợi để đối chiếu dashboard. Không chạy seed vào DB đang sử dụng.

## 6. Điều kiện hoàn thành milestone

| ID | Kịch bản bắt buộc | Đạt khi |
|---|---|---|
| E01 | Course → lớp → lesson → học liệu | Giáo viên tạo/công bố; học viên đúng lớp xem được; nháp/lớp khác/đã thu hồi bị chặn cả API/media. |
| E02 | Học và progress | Hoàn thành PDF/video/bài làm cập nhật đúng; gửi lặp không tăng sai; reload/restart giữ dữ liệu; thêm/gỡ hoạt động tính lại đúng. |
| E03 | Quiz/submission | Làm, lưu nháp, nộp, kiểm tra hết hạn, ôn tập nhiều lượt, nộp file, chấm và công bố đúng; không rò đáp án. |
| E04 | Teacher analytics | Bảng lớp và dashboard từng bài khớp seed; chờ chấm khác điểm 0; không lộ điểm riêng cho người khác. |
| E05 | QA/citation nhiều trang | CPU trả đủ phần tiếp nối trang 8–9; ALU dẫn đúng nguồn từng ý; câu ngoài tài liệu không bịa nguồn. Có ít nhất 10 câu kiểm nguồn phủ factual, nhiều trang và thiếu căn cứ, ghi kết quả từng câu. |
| E06 | Memory, hint, summary và câu hỏi tiếp theo | Ít nhất 2 kịch bản nhiều lượt gồm chuyển chủ đề và hai phiên độc lập; hint không lộ đáp án; summary báo đúng phạm vi/nguồn. Câu hỏi gợi ý do Dương phụ trách: bấm tạo lượt mới đúng hội thoại, không gửi trùng; lỗi gợi ý không làm mất câu trả lời chính. |
| E07 | Lỗi và lifecycle | Ngắt Kaggle/index chưa READY/timeout báo đúng; LMS vẫn nộp/chấm được; bài kiểm tra còn hiệu lực chặn AI, gỡ/mất quyền không khóa nhầm. |
| E08 | Lưu trữ | Restart giữ điểm/bài/tiến độ/lịch sử/ghi chú đã lưu; phiên bản và quyền nguồn vẫn đúng. |
| E09 | Kiểm thử/tái lập | Backend suite liên quan, frontend test/build/lint và migration đều đạt trong môi trường hỗ trợ. Ghi rõ lệnh/phạm vi/count; lỗi tồn đọng liên quan không được ghi “đã hoàn tất”. |
| E10 | Evidence/demo | Một kịch bản xuyên suốt giáo viên–học viên–giáo viên, dữ liệu giả lập, ảnh/video và số liệu truy ngược cùng commit/config; không có bí mật hoặc nội dung riêng bị xuất công khai. |

Kiểm Docker tham khảo: `docker compose ps`; `docker compose exec backend python manage.py check`; `docker compose exec backend python manage.py check_w4_chat_runtime`. Lệnh cuối chỉ là preflight, không chứng minh model trả lời đúng.

Backend test phải dùng `config.settings.test` và database test riêng; không dùng migration/flush/xóa dữ liệu trên DB đang chạy để “làm sạch” kết quả. Frontend dùng `npm.cmd test -- --maxWorkers=2`, `npm.cmd run build`, `npm.cmd run lint` trong `frontend/`.

Milestone chỉ đóng khi cả W9-01 và W9-02 đạt cùng bảng E01–E10. Có code hoặc container healthy chưa đủ. Các thiếu sót ngoài W9 được ghi rõ thành việc sản phẩm cuối, không ghi hoàn thành thay.
