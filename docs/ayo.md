# Ayo: hiện trạng và lộ trình hoàn thiện

## 1. Tiếp nhận baseline

Rà soát ngày 19/11/2026 tại nhánh `VuNamDuong_B22DCVT119_W8Tasks`, commit nền `8b180aa865a8f7c86af7b9ac3f693e61532bb95e`. Căn cứ: SRS, bản phân công và mã nguồn hiện tại. Đây là kết quả khảo sát ban đầu, không phải nghiệm thu các chức năng dự kiến bổ sung.

### Luồng hiện tại

```text
SessionWorkspace / DocumentAssistant / SessionAssistant
  -> ai.service.js -> API chat / conversations
  -> kiểm quyền, trạng thái kiểm tra và phạm vi học liệu
  -> truy xuất chunk được phép -> context và lịch sử hội thoại
  -> remote.generate_answer -> gateway Kaggle -> Qwen
  -> kiểm cấu trúc/citation, kiểm lại quyền -> lưu và hiển thị
```

Vector chỉ dùng để tìm nguồn; context đưa vào model là văn bản và metadata nguồn được phép. Lịch sử không thay thế bằng chứng từ học liệu. Cấu hình hiện tại truy xuất top-5, có thể bổ sung đoạn tiếp nối quy trình; memory giới hạn 4 lượt hoàn chỉnh và ngân sách 768 token.

| Phần | Vị trí cần theo dõi |
|---|---|
| Chat, hội thoại, policy | `backend/apps/ai/api/`, `conversations.py`, `services.py`, `policy.py` |
| Remote và runtime | `backend/apps/ai/remote.py`, `runtime.py`, `inference_gateway.py`, `providers/local.py` |
| Nguồn và quyền | `backend/apps/documents/access.py`, `retrieval_scope.py`, `backend/apps/courses/api/session_views.py` |
| Ghi chú học liệu | `backend/apps/documents/api/study_notes.py` |
| UI và hợp đồng gọi | `frontend/src/components/SessionWorkspace.jsx`, `components/ai/`, `services/ai.service.js` |

### Cấu hình đã đọc

| Thuộc tính | Giá trị |
|---|---|
| Generator | `apps.ai.remote.generate_answer` |
| Model | `Qwen/Qwen2.5-7B-Instruct` |
| Revision | `a09a35458c702b33eeacc393d103063234e8bc28` |
| Prompt | `bounded_guidance` |
| Input / output tối đa | 3584 / 1024 token |
| Temperature / timeout model | 0 / 90 giây |
| Config | `backend/config/ai/kaggle-dual-gpu.json` |

Đã đồng bộ cấu hình bằng health xác thực và đối chiếu với backend đang chạy: model/revision, prompt, token budget, temperature và timeout khớp gateway hai replica. Không công bố URL/token. Log khởi động người vận hành cung cấp cho thấy checkpoint NF4 được nạp trên hai T4; provider hiện tại chưa có đường nạp LoRA bằng `PeftModel`. Baseline phục vụ checkpoint NF4 hiện có, không mặc định adapter đã huấn luyện đang phục vụ chatbot. Health chưa cung cấp checksum trọng số/adapter nên không coi đây là chứng thực độc lập nội dung trọng số GPU.

### Kết quả kiểm tra

| Kiểm tra thực chạy | Kết quả và phạm vi |
|---|---|
| Frontend build, lint | Đạt; build có cảnh báo bundle lớn, không phải lỗi build |
| Frontend test | 52 file, 338 test đạt khi chạy ngoài giới hạn sandbox |
| Django system check | Đạt |
| Migration plan | Không còn migration chờ trên database hiện tại; không chạy migrate |
| Retrieval preflight | `CONFIGURED_NOT_MODEL_VERIFIED`: 1 tài liệu đã công bố, 20 chunk, 0 chunk sai provenance |
| Backend tổng hợp, settings `config.settings.test` | 418 test; 7 failure, 17 error. Không phải kết quả đạt |
| Upload/worker, settings `tests.documents_settings` | Chạy riêng đúng cấu hình: 27/27 test đạt |
| Health endpoint Kaggle | Ban đầu 404; sau khởi động lại đạt HTTP 200, ready, 2 replica; config khớp backend và có `chat_history_v1` |
| Kiểm API thật | Tạo được hội thoại; 4 lượt hỏi qua backend–retrieval–Kaggle, không dùng mock |
| Kiểm cú pháp | 112 file Python liên quan và cell khởi động đều parse được |

Trong 17 error: 2 lỗi nạp fixture upload/worker do cần settings riêng; 4 lỗi parser do thiếu model Docling trong cache khi kiểm offline; 10 lỗi nhóm buổi học liên quan kết nối DB đã đóng; 1 lỗi schema `KeyError: additionalProperties`. Các failure liên quan mô tả/schema API chat và `DatabaseOperationForbidden` của test schema. Chưa quy tất cả thành lỗi sản phẩm, chưa sửa ở bước tiếp nhận.

Phạm vi 418 test khác lượt kiểm 353 test trong bản phân công, không dùng chênh lệch tổng để kết luận hồi quy. Máy hiện có 20 chunk, không lấy số 40 chunk từ bản bàn giao làm kết quả tại máy này. Chưa có log `.private/lms-live-audit-20261117/` để đối chiếu.

Log backend lưu riêng tại `.private/ayo/baseline/backend-tests.txt`; log chạy nhóm upload/worker với settings riêng tại `documents-tests.txt` trong cùng thư mục. Dùng báo cáo riêng để phân biệt lượt kiểm này với lượt kiểm tổng hợp.

### Kiểm inference thực tế sau đồng bộ

Đã kiểm qua HTTP API thật với quyền chủ khóa đang hoạt động, không sửa tài khoản/quyền hay thay học liệu. Hai hội thoại kiểm tra được lưu như lịch sử sử dụng thông thường; chưa kiểm UI hoặc ma trận quyền học viên ở lượt này.

| Ca kiểm | Kết quả | Kết luận |
|---|---|---|
| Hai câu ngoài chủ đề tài liệu | HTTP 200, `INSUFFICIENT_EVIDENCE`, không citation; lần lượt 33,085 và 15,819 giây | Log khảo sát cũ, không dùng để nghiệm thu nội dung giáo trình Triết học. Bộ kiểm hiện tại dùng câu hỏi từ `ch01.pdf` |
| Định nghĩa Triết học | HTTP 200, `ANSWERED`; 13,376 giây | Nội dung khớp định nghĩa trong nguồn, citation trang PDF 4 khớp chunk/version/excerpt |
| Câu nối hỏi điều kiện ra đời | HTTP 200, `ANSWERED`; 17,134 giây; memory dùng 1 lượt trước, 55 token | Citation trang PDF 4 khớp nguồn, nhưng chỉ có câu dẫn và bỏ hai điều kiện trong nguồn: chưa đạt độ đầy đủ |

Citation khớp catalog không tự chứng minh trả lời đủ ý. Đã đối chiếu nội dung câu nối với đoạn trích: thiếu điều kiện về vốn hiểu biết/khả năng khái quát và sự hình thành tầng lớp lao động trí óc. Giữ phát hiện này cho bước hoàn thiện QA/memory, không sửa prompt để làm đẹp baseline.

Log và nguồn đối chiếu giữ riêng tại `.private/ayo/baseline/live-console.txt` và `live-grounded-console.txt`; tóm tắt có cấu trúc tại `report.json`. Cảnh báo tokenizer regex trong output Kaggle vẫn là điểm cần điều tra; chưa thay tokenizer hoặc khẳng định đã hết cảnh báo. Các ca trên chứng minh gọi model thực tế hoạt động, không thay bộ đánh giá holdout hoặc nghiệm thu chất lượng toàn hệ thống.

### Các điểm cần xử lý tiếp

| Vấn đề | Căn cứ và việc tiếp theo |
|---|---|
| Cell Kaggle đã lưu lệch source | Cell 47 của `notebooks/generation_setup.ipynb` khác gateway và 5 file provider/RAG hiện tại; phải đồng bộ trước khi kiểm model thật |
| Quyền buổi học nháp | Đọc code thấy list session và kiểm quyền tài liệu chưa lọc nháp nhất quán với retrieval; cần regression gọi trực tiếp API/media trước khi sửa |
| Ghi chú chưa bền vững | `study_notes.py` dùng LocMemCache; cần chuyển DB và kiểm theo user/document/version |
| Tóm tắt chưa được hỗ trợ đồng bộ | API/gateway hiện nhận `qa` và `hint`; cần mở rộng schema, retrieval, gateway và UI cùng nhau |
| Gợi ý câu hỏi tiếp theo | Chưa thấy luồng 2–3 câu gợi ý dưới câu trả lời; triển khai sau citation/memory |
| Chặn AI theo bài kiểm tra | Policy lấy lượt TEST nháp, cần kiểm thêm bài bị gỡ/mất quyền; đây là phát hiện tĩnh, chưa tái hiện bằng người dùng thật |
| Citation và memory | Đã có câu có nguồn và câu nối thật; câu nối thiếu nội dung dù có citation. Kiểm nội dung nhiều trang và hội thoại độc lập trên giáo trình Triết học hiện có |
| OpenAPI và test | Cập nhật đúng API hiện hành, điều tra cách ly DB; không bỏ assertion để lấy kết quả xanh |

### Khởi động lại để kiểm model thật

Đã tạo `.private/ayo/runtime.ipynb` từ source hiện tại, gồm cell tìm/giải nén checkpoint và cell khởi động, không sửa notebook gốc. Notebook này phục vụ inference, không huấn luyện và không tự bật adapter đã train.

1. Import notebook này vào môi trường Kaggle phục vụ chatbot. Bật Internet và GPU T4 x2; giữ Input chứa checkpoint NF4 và quyền truy cập hai Secret `NGROK_AUTHTOKEN`, `OHAYO_INFERENCE_TOKEN`.
2. Restart session Python nếu đang có service cũ, chạy cell tìm checkpoint rồi cell khởi động. Cell đầu nhận thư mục hoặc ZIP checkpoint trong Input; thiếu model sẽ báo cần thêm Input, nhiều bản khác nhau sẽ yêu cầu chọn rõ. Không Factory Reset nếu cần giữ file trong phiên.
3. Khi hiện `SAN SANG`, dùng URL thực vừa cấp để đồng bộ từ thư mục gốc dự án:

```powershell
.\.venv\Scripts\python.exe scripts/configure_kaggle_inference.py --url https://URL-THUC-TE --use-env-token --dual-gpu --chat-memory
```

Helper chỉ ghi cấu hình khi health hợp lệ. Token trong `.env` phải trùng Secret Kaggle; nếu đã đổi, bỏ `--use-env-token` để nhập kín, không gửi token qua chat. Sau khi đồng bộ thành công mới recreate backend để nhận environment mới. Backend entrypoint có chạy migration nên cần kiểm trạng thái database trước khi vận hành, không dùng việc khởi động toàn stack như một bước kiểm đọc-only.

Lượt khảo sát đầu chỉ khởi động database/Redis. Lượt đồng bộ sau đã kiểm `migrate --check` đạt rồi chạy `docker compose up -d --no-deps backend`; không có migration chờ. Kiểm cuối thấy cả 6 dịch vụ đang chạy, backend/frontend/database/Redis healthy; không chủ động khởi động lại workers trong lượt đồng bộ. Kiểm test trước đó dùng container tạm bỏ qua entrypoint migrate và database tên ngẫu nhiên riêng. Không seed, flush, rebuild index hoặc thay học liệu đang dùng.

## 2. Lộ Trình Và Trạng Thái Hiện Tại

**Nguồn học liệu cho toàn bộ các bước tiếp theo:** dùng PDF có thật trong dự án và bản được phép truy cập trên LMS; mặc định là `data/corpus/THMLN/ch01.pdf` (giáo trình Triết học), đã công bố/READY. Không phụ thuộc PDF CPU/ALU, câu hỏi về CPU/ALU, số trang hoặc dữ liệu demo riêng trên máy thành viên khác. Nếu cần thêm học liệu để kiểm phạm vi, phải chọn tệp thực tế, ghi đúng document/version/trang và kiểm quyền trước; không giả định tài liệu đã upload/index.

| Bước | Công việc | Đầu ra / Điều kiện hoàn thành | Trạng thái |
|---|---|---|---|
| 1. Tiếp nhận và khóa baseline | Rà mã, luồng UI–API–retrieval–Kaggle; đồng bộ runtime và xác minh model/config thực tế | Baseline chạy được, ghi rõ lỗi ban đầu và trạng thái adapter phục vụ | Đã xong |
| 2. Đánh giá adapter trên holdout | Kiểm adapter đã khóa với 116 mẫu holdout, tiếp nhận và audit kết quả | Kết quả/checksum và nhận xét đúng phạm vi; không train lại hoặc trộn benchmark 300 câu | Đã xong |
| 3. Hoàn thiện quyền học liệu | Kiểm buổi nháp, lớp khác, thu hồi quyền, bản gỡ và URL nguồn cũ | API/media/retrieval thực thi quyền, chủ khóa vẫn quản lý được bản nháp; regression đạt | Đã xong |
| 4. Lưu ghi chú bền vững | Lưu ghi chú/nét vẽ/đánh giá theo user/document/version vào PostgreSQL | Đọc lại sau restart, không trộn tài khoản/phiên bản, migration và test đạt | Đã xong |
| 5. QA và citation | Kiểm factual, nội dung nhiều trang, đúng nguồn từng ý và thiếu căn cứ trên PDF Triết học | Lượt đủ 10/10 câu đã đối chiếu nguồn; hai câu khó dùng trích nguyên văn có nhãn rõ | Đã xong |
| 6. Memory, hint và tóm tắt | Kiểm câu nối, đổi chủ đề và hội thoại độc lập; hint không lộ đáp án; tóm tắt đúng phạm vi | API/schema/UI đồng bộ; đọc toàn bộ chunk của trang chọn, không lấy top-5 | Đã kiểm runtime mới và UI học viên: tóm tắt đủ 12 trang, mở đúng nguồn. Có hai lần tiếp tục sau gián đoạn; chất lượng diễn đạt còn giới hạn, không coi là đạt factuality toàn bộ. Chi tiết mục 9 |
| 7. Gợi ý câu hỏi tiếp theo | Hiển thị gợi ý bám nguồn hiện tại; bấm mới tạo lượt hỏi | Giữ đúng hội thoại/memory/quyền, chống gửi trùng; gợi ý lỗi không làm mất câu trả lời chính | Đã xong: API thật trả 3 gợi ý, kiểm chọn/gửi lại/lưu lịch sử đạt; regression và frontend deploy đạt |
| 8. Policy, lỗi vận hành và OpenAPI | Kiểm chặn AI khi bài kiểm tra còn hiệu lực; gỡ/mất quyền không khóa nhầm; kiểm lỗi Kaggle/index; hoàn thiện hợp đồng API | Không gửi đáp án/rubric riêng tới model; báo đúng lỗi, LMS vẫn hoạt động; schema và regression liên quan đạt; bàn giao hợp đồng hint cho Cường nối UI | Đã sửa policy, timeout proxy và phân loại lỗi; hồi quy backend/frontend, OpenAPI và kiểm triển khai đạt. Hợp đồng hint tại mục 10 |
| 9. Tích hợp và bàn giao cuối | Đối chiếu progress/kết quả lớp từ phần Cường; chạy demo xuyên suốt, hồi quy và tổng hợp Evidence | Một bản code/config nhất quán; test/build/lint/migration và kịch bản liên quan đạt; `Evidence/W09/` theo cấu trúc đã dùng; Cường tiếp nhận, kiểm cuối và yêu cầu sửa nếu cần | Chưa thực hiện |

**Bản tóm tắt mạch lạc theo yêu cầu bổ sung được ghi ở mục 9; kiểm policy/vận hành đã hoàn tất tại mục 10.** Memory đã kiểm bằng câu hỏi điều kiện ra đời của Triết học → hỏi rõ điều kiện thứ hai → chuyển sang thế giới quan; một hội thoại khác bắt đầu độc lập để kiểm không nhiễm lịch sử. Hint dùng đề bài hợp lệ dựa trên học liệu thực tế, chỉ gửi nội dung người học được phép thấy. Gợi ý tiếp theo cũng bám các chủ đề này, không tái sử dụng câu hỏi từ PDF đã loại khỏi lộ trình.

Quy định thay nguồn demo/kiểm học liệu này không thay đổi bộ 116 holdout, benchmark đã khóa hoặc log lịch sử. Giữ test cơ chế tổng quát khi vẫn cần kiểm hồi quy, nhưng không dùng ví dụ/tài liệu ngoài máy này làm điều kiện nghiệm thu. Các số liệu và trạng thái ở mục tiếp nhận bên dưới là ảnh chụp baseline ban đầu; bảng trên là tiến độ hiện hành.

**Trạng thái bước tiếp nhận: hoàn thành khảo sát và chốt baseline.** Backend đã đồng bộ gateway, có inference/citation/memory thực tế và danh sách lỗi/giới hạn rõ. Chưa nghiệm thu QA đầy đủ trên học liệu hiện có, chưa xác thực adapter fine-tune trên web. Các điểm này chuyển vào công việc hoàn thiện tương ứng; có thể sang bước đánh giá adapter trên 116 mẫu holdout riêng, không train lại.

## 3. Đánh giá instruction holdout

**Trạng thái: hoàn thành bước 2.** Đã nhận lượt GPU `holdout-20261119T104136680364Z`, kiểm checksum, tính lại audit trên máy nhận và đối chiếu 9 mẫu tiêu biểu với nguồn. Kết quả bên dưới là inference trên adapter đã khóa, không phải một lần huấn luyện mới.

### Dữ liệu và giao thức đã khóa

- Dùng đúng bộ 1.000 mẫu trước đây: giữ nguyên 770 train / 114 validation / 116 instruction holdout. Đối chiếu checksum gói nguồn, manifest chuẩn hóa và sidecar. Kiểm ID, nhóm nguồn và họ biến thể không giao giữa holdout với train/validation.
- 116 holdout gồm 74 QA, 22 summary, 10 hint và 10 insufficient-evidence. Prompt giữ nguyên giao thức instruction đã huấn luyện, có evidence được cung cấp sẵn; không chạy retrieval FAISS. Đây không phải benchmark ba nhánh 300 câu hoặc kiểm frontend.
- Adapter cuối bước 193 đã được chọn trước lượt này, SHA-256 `51713be1e630135099f95ed08c89b5be8669b75c9e1908a1346c5c9cc4942ae7`. Không chọn lại checkpoint, chỉnh prompt hay train bằng holdout.
- So sánh base có evidence (tắt adapter) với tuned có cùng evidence (bật adapter): 232 đầu ra, một lượt sinh mỗi cặp, greedy, seed 42, tối đa 512 output token, timeout mềm 90 giây. Hai nhánh luân phiên thứ tự; không sửa định dạng hoặc sinh lại ngầm.
- Completion chuẩn chỉ dùng tính loss và chấm sau lượt sinh, không nối vào prompt generation. Loss chỉ tính token completion và EOS, không tính prompt/padding; toàn bộ model đóng băng, không tạo optimizer.
- Nguồn của holdout instruction từng xuất hiện trong benchmark main trước đó. Cần công bố giới hạn này, không gọi đây là phép kiểm nguồn/chủ đề hoàn toàn chưa từng thấy trong quá trình đánh giá dự án.

### Đầu ra và ý nghĩa

| Đầu ra | Dùng để đọc kết quả |
|---|---|
| `outputs.jsonl` | Từng mẫu/hai nhánh: output thô, trạng thái dừng, loss, token, thời gian, VRAM, trạng thái adapter và điểm tự động |
| `audit.json` | Kiểm đủ 232 cặp, khớp prompt/ID/adapter, tính lại điểm và tổng hợp theo task |
| `runtime.json`, `plan.json` | Phiên bản dependency thực, model/adapter, danh sách mẫu và cấu hình chạy |
| `figures/loss.png`, `figures/format.png` | So sánh loss và tỷ lệ đúng định dạng; không đưa nhận xét vào ảnh |
| ZIP và receipt | Lưu log, kết quả/biểu đồ và checksum; lỗi cũng được đóng gói để kiểm lại |

Loss/perplexity thấp hơn chỉ cho thấy mô hình gán xác suất cao hơn cho completion chuẩn, không tự chứng minh trả lời đúng hơn. Citation-ID hợp lệ chỉ xác nhận mã nguồn tồn tại, không xác nhận ý trả lời được nguồn hỗ trợ. Exact match và độ bao phủ item theo câu chuẩn có thể thấp với diễn đạt khác nhưng đúng; không coi chúng là factuality. Sau khi nhận output cần đọc đối chiếu nguồn, nhất là câu bị từ chối nhầm, JSON lỗi và thiếu ý.

### Kiểm tra và công cụ

- `scripts/comparison/package_holdout.py`: dựng gói Input riêng, chỉ mang adapter/tokenizer, 116 holdout và 4 mẫu validation smoke; không đưa 770 train hoặc toàn bộ validation vào gói.
- `scripts/comparison/holdout.py`: kiểm package, tokenize lại, inference hai nhánh, tính completion-only loss, chấm/audit và xuất biểu đồ. Tái sử dụng runtime NF4/LoRA đã có, không tạo trainer thứ hai.
- `scripts/comparison/tests/test_holdout.py`: 17 test về JSON/hint, citation ID, từ chối, item recall, loss có trọng số, ID/adapter/điểm bị sửa và notebook chạy đúng module.
- Đã đạt 176/176 test comparison khi dùng đủ dependency CPU có sẵn. Đã kiểm lại tokenizer thật, EOS/mask của toàn bộ 116 holdout và 4 validation smoke; chưa nạp trọng số Qwen hoặc chạy GPU ở máy này. Log giữ riêng tại `.private/ayo/holdout/tests-complete.txt`.

### Quy trình Kaggle đã sử dụng

1. Tạo notebook riêng, có thể đặt tên `OHAYO - Instruction Holdout`; import `notebooks/instruction_holdout.ipynb`. Không chạy chung kernel với notebook đang phục vụ chatbot.
2. Tạo dataset **Private**, tên gợi ý `ohayo-instruction-holdout`, từ `.private/ayo/holdout/package/holdout-evaluation.zip`, rồi thêm vào Input. Không cần dataset training, checkpoint `ohayo-model` hoặc Secrets ngrok; model base đúng revision sẽ dùng cache hoặc tải từ Hugging Face.
3. Bật Internet và GPU T4. Nếu chọn T4 x2, notebook chỉ hiện GPU 0 cho tiến trình đánh giá; không cần cả hai GPU. Nếu Kaggle không cấp GPU vì phiên inference đang giữ tài nguyên, dừng phiên đó trước; chatbot sẽ tạm mất kết nối, không phải lỗi code.
4. Chạy 4 code cell theo thứ tự: xác thực Input; chuẩn bị môi trường riêng và kiểm token/mask; smoke 4 mẫu validation trên hai nhánh; đánh giá 116 holdout trên hai nhánh. Smoke không cập nhật trọng số. Cell cuối chỉ chạy sau smoke đủ 8 đầu ra và không lỗi generation.
5. Gửi ZIP, receipt và `audit.json` của lượt holdout; giữ cả smoke ZIP/receipt để đối chiếu. Nếu lỗi thì gửi ZIP lỗi, không chạy lặp để chọn lượt điểm đẹp. Không dùng điểm holdout để sửa adapter trong cùng thí nghiệm.

### Kết quả đã tiếp nhận

Gói ZIP 75.399 byte có SHA-256 `90b51c7061007c29d8b3678bffb305cc6dbcb2a690fe863cc64eaf703b8bf414`. ZIP/receipt/audit rời khớp; các file trong manifest khớp checksum, plan khớp package đã khóa, thứ tự và prompt của đủ 116 cặp khớp. Đã tokenize lại, tính lại điểm từng output và các số tổng hợp, khớp hoàn toàn audit gửi về. Không có lỗi generation, không có optimizer update.

Trong bảng, **Base + evidence** là base đã tắt adapter nhưng vẫn nhận đúng evidence như tuned, không phải nhánh Base không nguồn của benchmark 300 câu.

| Chỉ số trên 116 mẫu | Base + evidence | Tuned + evidence |
|---|---:|---:|
| Generation hoàn tất | 116/116 | 116/116 |
| Completion-token loss | 0,7173 | **0,3168** |
| Perplexity | 2,0488 | **1,3727** |
| Đúng định dạng | 115/116 | **116/116** |
| Citation ID hợp lệ trên 106 mẫu có thể trả lời | 105/106 | **106/106** |
| Exact match toàn bộ reference object/action | 24/116 (20,69%) | **45/116 (38,79%)** |
| Exact match QA | 4/74 | **21/74** |
| Exact match summary | 1/22 | **4/22** |
| Hint đúng action chuẩn | 9/10 | **10/10** |
| Từ chối khớp 10 mẫu thiếu căn cứ | 10/10 | 10/10 |
| Từ chối nhầm mẫu có thể trả lời | 0 | 0 |
| Trung bình thời gian generation/mẫu | 4,67 giây | 6,11 giây |
| Đỉnh VRAM allocated trong generation | 5,687 GiB | 5,682 GiB |

Loss tổng hợp giảm 55,83%; 106/116 mẫu có NLL thấp hơn với adapter, 10 mẫu ngược lại. Exact match tăng ở 21 mẫu và không giảm ở mẫu nào; 95 mẫu còn lại giữ cùng trạng thái exact/non-exact. Tuy nhiên, generation tổng của tuned lâu hơn khoảng 30,96%. VRAM trên đây là số đo trong generation, không phải đỉnh toàn tiến trình bao gồm forward tính loss; perplexity của hai nhánh dùng cùng token completion/EOS chuẩn.

**Đối chiếu nguồn 9 mẫu / 18 output:** chọn các trường hợp đại diện task, tăng exact match và ca base duy nhất lỗi định dạng; không phải mẫu ngẫu nhiên để ước lượng độ chính xác ngữ nghĩa toàn bộ.

- `W5_A_00093`: tuned trả đúng hoạt động được hỏi dù khác câu chuẩn; base lệch trọng tâm. Cho thấy exact match có thể bỏ sót câu đúng.
- `W5_A_00102`: tuned có nguồn nhưng tóm tắt bỏ phần định nghĩa và sự khác nhau theo giai cấp; base bao phủ nhiều ý được hỏi hơn. Chưa thể nói tuned tốt hơn ở mọi ca.
- `W5_A_00207`: hai nhánh đều nêu đủ ba phương diện trong nguồn, nhưng tuned gộp thành một item giống reference. Đây là tăng exact match, không đủ căn cứ gọi là tăng chất lượng nội dung.
- `W6_A_00031`: base sinh JSON lỗi, lẫn tiếng Trung và thông tin ngoài đoạn; tuned giữ tiếng Việt, định dạng hợp lệ và phân biệt được cơ hội/thách thức có nguồn.
- Hai ca hint `W5_A_00105`, `W5_B_00210` xác nhận tuned chọn đúng thao tác đối chiếu/lập dàn ý; ca thiếu căn cứ `W5_A_00106` được cả hai nhánh từ chối phù hợp.
- Hai summary `W6_B_00097`, `W6_B_00098` cho thấy có ca chỉ chép lại câu nguồn ngắn; tuned giữ thêm vế giải thích ở ca sau. Kết quả này chưa kiểm năng lực tóm tắt cả tài liệu dài.

**Kết luận:** adapter học được cách biểu đạt và giao thức của tập instruction, gán xác suất tốt hơn cho đáp án chuẩn trên tập giữ riêng và có một số cải thiện nội dung cụ thể. Vẫn có câu thiếu ý; ID đúng/exact match cao không thay thế đánh giá tính đúng và độ bao phủ. Không kết luận hết overfitting, không suy ra tuned+RAG chắc chắn vượt RAG trong chatbot hay benchmark khác. Giữ adapter đã chọn, không tinh chỉnh lại theo điểm holdout.

### Minh chứng và công cụ tiếp nhận

- `.private/ayo/holdout/results/`: giữ ZIP gốc, receipt, audit rời, `verification.json`, `source-review.json`, log test và thư mục `run/` chứa output/biểu đồ gốc. Không đưa học liệu/output riêng lên Git.
- `scripts/comparison/receive_holdout.py`: kiểm ZIP/receipt/manifest, plan/runtime/adapter và tính lại audit từ output; không thực thi code trong ZIP và không nạp Qwen lên GPU.
- Sau bổ sung 5 test nhận gói bị sửa, bộ comparison đạt **181/181 test**; log ở `.private/ayo/holdout/results/receiver-tests.txt`.
- Trong `runtime.json`, các cờ `assets.base_weights_loaded=false` và `runtime_reload=PENDING_GPU_SMOKE` là metadata kiểm asset trước khi nạp, được runner chép lại; không dùng riêng các cờ này để diễn giải trạng thái sau inference. Việc tiếp nhận đối chiếu plan, phiên bản thư viện CUDA, 232 output và trạng thái bật/tắt 196 lớp LoRA đã ghi; đây không phải chạy GPU độc lập lần nữa.

**Có thể sang bước 3: hoàn thiện quyền học liệu và buổi học nháp.** Chưa thay adapter phục vụ chatbot, benchmark cũ hoặc commit/push.

## 4. Quyền học liệu và buổi học nháp

**Hoàn thành bước 3.** Không thay model, schema database hoặc dữ liệu học liệu đang dùng.

| Trường hợp | Hành vi sau sửa |
|---|---|
| Học viên xem danh sách buổi học | Chỉ thấy buổi đã hoàn tất trong lớp còn quyền; không thấy buổi nháp hoặc đã gỡ |
| Đoán hoặc dùng URL PDF của buổi nháp | Backend trả 404, kể cả PDF đã được công bố riêng; status, download và ghi chú cũng bị chặn |
| Chủ khóa học mở buổi nháp | Vẫn xem danh sách/PDF, đọc ghi chú và quản lý học liệu; retrieval preview chỉ dành cho chủ khóa |
| Chủ khóa hoàn tất buổi học | Học viên thấy học liệu đã công bố; không tự công bố PDF chưa công bố |
| Học viên còn học lớp khác nhưng mất quyền lớp chứa PDF | Không dùng được URL cũ, nguồn retrieval hoặc lịch sử hội thoại trong lớp đã mất quyền |
| Buổi/lớp/tài liệu hoặc bản đang công bố bị gỡ | Không trả metadata/nguồn không còn được phép; bản PDF đã gỡ không được tính vào số học liệu học viên thấy |
| Tài liệu thay phiên bản | Học viên vẫn chỉ xem bản đang công bố; URL citation yêu cầu phiên bản khác trả 409 |
| Quyền thay đổi trong khi đọc PDF | Nạp lại quyền tài liệu/buổi/lớp/khóa trước khi trả nội dung; không dùng quan hệ ORM đã cache để quyết định lần cuối |
| Học liệu chung cấp khóa học | Giữ quyền đọc theo thành viên khóa học, không gán nhầm vào buổi học nháp |

Mã sửa giới hạn ở `courses/api/session_views.py`, `documents/access.py` và `documents/api/views.py`; giữ nguyên hợp đồng response và các kiểm quyền retrieval/conversation đã có. Bổ sung mô tả API danh sách buổi/học liệu. Không cần sửa notebook Kaggle hoặc frontend cho thay đổi này.

**Minh chứng kiểm thử:**

- `backend/tests/documents/test_session_access.py`: 18 test mới, bao gồm danh sách, URL trực tiếp, ghi chú, chủ khóa, hoàn tất buổi, lớp khác, thu hồi quyền, bản thay thế, hội thoại cũ và thay đổi quyền giữa lúc đọc PDF/truy xuất nguồn.
- Trước sửa, 15 test đầu tái hiện 12 failure kể cả subtest; sau sửa, nhóm quyền/retrieval/buổi học đạt **42/42 test**. Bộ hồi quy rộng tài khoản/khóa học/tài liệu/media/AI/lớp học đạt **363/363 test**. Hai lượt có test trùng nhau, không cộng thành số test độc lập.
- Test ảnh thông báo cũ gọi trực tiếp `response.close()` làm đóng kết nối DB trong `TestCase`. Đã đổi sang đọc hết `streaming_content` qua wrapper của Django và kiểm PNG/response đã đóng; không đổi endpoint ảnh và không bỏ kiểm tra quyền.
- Django system check đạt, không có migration chờ. Test dùng database tên ngẫu nhiên riêng, storage tạm, không chạy seed/flush/rebuild index hoặc GPU. Các lỗi OpenAPI/parser ngoài phạm vi chưa được coi là đã sửa.
- Log trước/sau và báo cáo có checksum giữ riêng tại `.private/ayo/access/`: `before.txt`, `after.txt`, `focused.txt`, `regression.txt`, `report.json`. Backend được khởi động lại riêng để nạp mã; không thay phiên Kaggle.

Bước 3 bảo vệ quyền đọc/ghi. Phần lưu trữ bền vững được hoàn tất riêng ở mục dưới, không gộp vào bằng chứng kiểm quyền.

## 5. Ghi Chú Học Liệu Bền Vững

**Hoàn thành bước 4.** Ghi chú, nét vẽ và đánh giá học liệu chuyển từ LocMemCache sang PostgreSQL; giữ hợp đồng GET/PUT mà giao diện đang dùng. Đây là feedback học liệu, không phải like/dislike câu trả lời Ayo.

| Nội dung | Cách lưu và bảo vệ |
|---|---|
| Ghi chú và nét vẽ | `DocumentStudyNotes`: `items`, `notes`, `feedback`, thời điểm tạo/cập nhật; không sửa PDF gốc |
| Tách dữ liệu | Unique theo user/version; version đã thuộc một document cố định. Chủ khóa không đọc được ghi chú riêng của học viên |
| Qua restart/nhiều worker | Scope HMAC gắn user/document/version, không phụ thuộc UUID ngẫu nhiên của tiến trình; database là nơi lưu chính |
| PDF thay phiên bản | Phiên bản mới bắt đầu trống; không chép nhầm nét vẽ/ghi chú cũ. Bản cũ giữ nội bộ, chỉ đọc nếu còn quyền và phiên bản được phép |
| Thu hồi quyền | Chặn cả đọc và ghi; kiểm lại quyền và phiên bản trước khi trả dữ liệu hoặc hoàn tất transaction |
| Ghi đồng thời | Khóa document cùng luồng công bố/gỡ và tạo bản ghi đầu tiên; mỗi PUT thay toàn bộ nội dung, lần ghi sau thay lần trước, không tự ghép thay đổi giữa nhiều cửa sổ |
| Báo cáo học liệu | Ghi chú/báo cáo và thông báo lưu cùng transaction; gửi lại report không đổi qua autosave không phát thông báo trùng |
| Dữ liệu lỗi | Chặn trang/tọa độ sai, tọa độ không hữu hạn, ID annotation trùng, scope sai hoặc body không phải object |

**Mã nguồn:** `backend/apps/documents/models.py`, `api/study_notes.py` và migration `0004_documentstudynotes.py`. Mô tả OpenAPI đã đổi sang cơ chế lưu database; không cần sửa frontend để dùng API mới.

**Kiểm chứng:**

- 12 test ghi chú, gồm một `TransactionTestCase` lưu ở tiến trình thứ nhất, mở tiến trình Python mới để đọc đúng payload/scope và ghi lại, rồi tiến trình đầu đọc được thay đổi. Đây là kiểm database test PostgreSQL, không phải chỉ xóa cache rồi tự suy ra độ bền vững.
- Nhóm ghi chú/quyền đạt **30/30 test**; hồi quy backend tài khoản, học liệu/media, AI, lớp học và thông báo đạt **391/391 test**. Các lượt có test trùng nhau, không cộng tổng thành số độc lập.
- Ba file test frontend PDF/service đạt **16/16 test**. Đây là test component/service, không phải một lượt kiểm browser end-to-end.
- Đã kiểm scope sai tài khoản/phiên bản, key đổi, PDF chưa công bố, mất quyền, ghi đè/xóa nội dung, ràng buộc duy nhất, report lặp và rollback nếu kiểm quyền/thông báo thất bại.

**Triển khai:** trước migration đã sao lưu PostgreSQL vào `.private/ayo/notes/database-before-notes.dump` và kiểm bằng `pg_restore --list`. Kế hoạch chỉ tạo bảng mới; đã áp dụng thành công, restart riêng backend, không còn migration chờ. Health và GET ghi chú thật trả 200, schema mới hoạt động, response `private, no-store`; GET không tự tạo bản ghi trống. Số tài khoản/khóa học/buổi học/tài liệu/phiên bản trước và sau không đổi, không tạo ghi chú giả trên dữ liệu thật.

**Lưu ý vận hành:** dữ liệu cache cũ không được coi là đã chuyển hoặc khôi phục. PDF đang mở cần đóng/mở lại một lần để nhận scope mới; các lượt lưu mới sẽ vào database. Scope ổn định khi giữ nguyên `SECRET_KEY`; đổi key cần mở lại PDF nhưng không xóa ghi chú đã lưu. Backup chứa dữ liệu riêng, không đưa lên Git hoặc gửi chung với gói minh chứng.

Log kiểm thử và báo cáo/checksum giữ riêng tại `.private/ayo/notes/`: `focused.txt`, `regression.txt`, `report.json` và backup. Không dùng GPU, không train lại, không đổi model phục vụ, chưa commit/push.

**Có thể sang bước 5: hoàn thiện QA và citation trên học liệu thực tế.**

## 6. QA Và Citation

**Bước 5 hoàn thành trong phạm vi bộ kiểm QA dự án: lượt cuối đủ 10/10 câu đạt sau đối chiếu nội dung và nguồn.** Dùng `data/corpus/THMLN/ch01.pdf` đã công bố/READY trên LMS, không cần thêm PDF khác. Có 8 câu có căn cứ và 2 câu từ chối đúng; hai câu khó dùng trích nguyên văn, không coi là cải thiện diễn giải tự do của Qwen. Không thay adapter, fine-tune, dữ liệu holdout hoặc benchmark. Các ghi chép chờ triển khai/lỗi bên dưới là lịch sử; kết quả và thao tác hiện tại nằm cuối mục này. Không sửa lại các lượt thất bại thành đạt.

| Nội dung | Kết quả |
|---|---|
| Câu trả lời chỉ có câu dẫn | Chặn câu như “trong những điều kiện sau đây:” dù có citation. Chat được thử sinh lại tối đa một lần, trong thời gian còn lại; nếu vẫn lỗi trả `GENERATION_INCOMPLETE_CONTENT`, không tự điền điều kiện hoặc suy đoán nguồn |
| Citation từng ý | Giữ ID đoạn do server cấp, kiểm nguồn của lượt hiện tại, không lấy citation từ lịch sử hoặc gán đồng loạt. ID/trang hợp lệ không tự chứng minh ý nghĩa được nguồn hỗ trợ |
| Nội dung nhiều trang | Kiểm ba hình thức chủ nghĩa duy vật ở trang PDF 7–8 và hai nguồn gốc chủ nghĩa duy tâm ở trang PDF 8–9; từng ý phải có nguồn hỗ trợ, không bỏ phần tiếp nối. Đây là nội dung giải thích, không gọi sai thành quy trình. Giữ test fixture riêng cho cơ chế quy trình nhiều bước |
| Trạng thái nguồn | Khi chọn rõ tài liệu đang xử lý/lỗi hoặc bản được phép chưa có trong catalog đang nạp, trả `RETRIEVAL_NOT_READY`; không biến lỗi hạ tầng thành thiếu căn cứ học thuật. Phạm vi tổng hợp không chỉ rõ tài liệu giữ hành vi cũ |
| Giao diện/gateway | Đồng bộ allowlist lý do lỗi và thông báo frontend. Không hiển thị câu trả lời bị chặn hoặc nội dung lỗi riêng của provider |

**Mã và test:** `ai/rag/conversation.py`, `pipeline.py`, `citations.py`, `errors.py`; `ai/services.py`; `documents/retrieval_scope.py`, `retrieval_adapter.py`; service AI frontend. Thêm 10 test trong `backend/apps/ai/tests/test_answer_completeness.py`, bổ sung test gateway/service/quyền retrieval. Kiểm tra câu dẫn là heuristic bảo thủ, không phải bộ chấm entailment hay cam kết phát hiện mọi dạng câu trả lời thiếu ý.

**Kết quả offline:** toàn bộ unit AI **315/315**; nhóm API chat, gateway, scope, quyền học liệu và retrieval **118/118**; frontend service AI **5/5**. Không cộng các lượt thành số test độc lập. Test API dùng PostgreSQL test riêng, không sửa học liệu thật. Lượt unit đầy đủ cần gắn `scripts`/`data` chỉ đọc và vùng `data/processed` tạm có quyền ghi; các lỗi thiếu mount/quyền ghi của lượt chuẩn bị không được tính là lỗi sản phẩm. Log cuối tại `.private/ayo/qa/all-ai-unit-final.txt`, `api-final.txt`; test frontend đã quan sát trên terminal.

**Kiểm nguồn thật:** `scripts/check_grounded_qa.py` có 10 câu bám `ch01.pdf`: định nghĩa triết học; thời gian/nơi ra đời; điều kiện ra đời; hai mặt vấn đề cơ bản; thế giới quan và các loại hình; ba hình thức chủ nghĩa duy vật; nguồn gốc chủ nghĩa duy tâm; các cấp độ phương pháp luận; hai câu thiếu căn cứ về lịch thi/liên hệ giảng viên lớp. Có 8 câu có căn cứ, 2 câu thiếu căn cứ và 2 câu trong nhóm có căn cứ cần đọc qua nhiều trang. Số trang là trang vật lý của PDF, không phải số in chân trang.

Chỉ gọi model khi truyền `--run`, chọn đúng document UUID, kiểm quyền và bản công bố đã READY/có trong catalog; checksum phải khớp PDF dự án `4544a1ece75d7f14e77cf2514ae156e7b2aa48bcd94321eaf43740808389aeb2`. Mỗi câu tạo một hội thoại riêng, lưu response, thời gian, citation/đoạn nguồn và tiêu chí đối chiếu; kết quả luôn chờ đọc nguồn để kết luận, không tự đánh dấu đạt vì HTTP 200. Công cụ dùng API với chủ khóa hiện có; không thay thế test quyền học viên hay memory nhiều lượt. Khi chạy tạo 10 hội thoại kiểm thông thường, không tạo tài khoản/tài liệu giả. Bộ kiểm có 8/8 test riêng, gồm kiểm câu hỏi/nguồn và preflight từ chối gateway cũ hoặc config lệch trước khi tạo hội thoại. Phiên phục vụ mới phải có capability `qa_completeness_v1`.

Lệnh sau dùng tại PowerShell ở gốc dự án với bản `ch01.pdf` đã công bố trên LMS. Raw output giữ riêng, không đưa token lên Git:

```powershell
Get-Content -Raw scripts/check_grounded_qa.py | docker compose exec -T backend python -B - --document 3724aa92-4a4a-4c61-9063-df2ce124540e --run 2>&1 | Tee-Object -FilePath .private/ayo/qa/live.txt
```

**Các bước vận hành đã thực hiện trong quá trình sửa:**

1. Import lại `.private/ayo/runtime.ipynb` đã nhúng mã QA/gateway mới. Giữ Input checkpoint, GPU T4 x2, Internet và hai Secrets; restart kernel rồi chạy hai cell code theo thứ tự. Không chạy notebook training hoặc holdout cho việc này.
2. Gửi URL `SAN SANG` để kiểm health-config backend; phiên hiện đã kết nối thành công. Lượt nghiệm thu kế tiếp phải có cả `qa_completeness_v1` và `qa_atomic_evidence_v1`, không dùng kết quả của phiên chỉ có bản completeness cũ.
3. Dùng `ch01.pdf` Triết học đã công bố/READY và khớp PDF dự án; không yêu cầu upload thêm học liệu.
4. Chạy 10 câu, đọc từng ý với đoạn/trang được dẫn; nếu sai hỗ trợ, thiếu ý hoặc từ chối nhầm thì sửa và chạy lại. Chỉ kết luận bước 5 hoàn thành khi lượt kiểm này đạt; không dùng test offline để suy ra chất lượng trả lời thật. Tiêu chí thực tế là QA/citation và nội dung nhiều trang trên học liệu dự án, không phải tái hiện dữ liệu của máy thành viên khác.

Notebook mới là bản sinh phục vụ, nằm riêng ngoài Git; notebook lịch sử không bị ghi đè. Tiến độ và checksum ở `.private/ayo/qa/report.json`. Chưa commit/push.

**Kiểm lại ngày 20/11/2026:** sau khi chạy notebook mới, Kaggle health trả 200 và cấu hình khớp backend. Hai câu gọi Qwen thật trên `ch01.pdf`: định nghĩa trả đúng nội dung và citation (43,107 giây); câu nối hỏi điều kiện ra đời vẫn bị model trả thiếu nội dung, hệ thống chặn bằng `GENERATION_INCOMPLETE_CONTENT` (40,774 giây). Điều này xác nhận guard mới đang chạy, không xác nhận đã giải quyết đầy đủ chất lượng câu trả lời. Log giữ tại `.private/ayo/qa/live-philosophy.txt`. Cảnh báo regex tokenizer còn cần điều tra, không tự coi là hết lỗi chỉ vì nạp được hai GPU.

**Sửa tiếp cơ chế thử lại:** lượt structured đầu và lượt sửa trước đây có thể nhận cùng prompt khi lỗi chỉ có câu dẫn (không có danh sách bước thiếu). Đã chuyển lý do `INCOMPLETE_ANSWER_BODY` vào `repair_feedback`, yêu cầu sinh ý thực chất từ evidence hiện tại hoặc từ chối nếu thiếu; không tự thêm nội dung hay gán ID nguồn. Thêm test xác nhận prompt lần hai khác lần đầu nhưng evidence giữ nguyên; toàn bộ unit AI đạt **316/316**, log `.private/ayo/qa/retry-feedback-unit.txt`. Notebook riêng đã sinh lại nhưng bản sửa feedback này chưa được nạp lên Kaggle, chưa có kết quả Qwen thật sau sửa. Bộ kiểm hiện tại dùng giáo trình có sẵn; không còn phụ thuộc vào học liệu ngoài dự án.

**Kết quả 10 câu thật và sửa tiếp:** log `.private/ayo/qa/philosophy-current.txt`, đối chiếu từng câu tại `source-review.json`. Cả 10 câu HTTP 200, 8 trả lời và 2 từ chối; citation identity đều khớp catalog, nhưng nội dung chỉ **6/10 đạt**. Latency trung bình 22,074 giây, tối đa 61,149 giây. Đây là lượt phát hiện lỗi trên gateway đang chạy, không phải nghiệm thu bản sửa sau đó.

| Câu cần sửa | Finding | Thay đổi và trạng thái |
|---|---|---|
| Hai mặt vấn đề cơ bản | Chỉ nói có hai mặt, không nêu nội dung | Guard yêu cầu các dòng ordinal liên quan khi người dùng hỏi liệt kê đầy đủ; lượt sửa nhận đúng ID đoạn thiếu. Câu chỉ hỏi số lượng hoặc một mặt cụ thể không bị ép trả cả danh sách |
| Ba hình thức chủ nghĩa duy vật | Đủ tên nhưng phần siêu hình dừng ở “nên trong” tại ranh giới trang | Chặn câu dở dang bằng heuristic bảo thủ; hướng dẫn đọc phần tiếp nối trước khi diễn đạt. Chưa chứng minh model thật đã sửa đúng phần này |
| Nguồn gốc chủ nghĩa duy tâm | Thay nguồn gốc nhận thức luận bằng định nghĩa chủ nghĩa duy tâm | Prompt yêu cầu trả căn cứ giải thích nguyên nhân, không thay bằng định nghĩa. Cần đọc lại đầu ra thật; không có bộ kiểm entailment tổng quát tự chứng nhận |
| Cấp độ phương pháp luận | Chỉ kể tên, thiếu phần phân biệt theo yêu cầu | Prompt yêu cầu giải thích từng cấp độ/phạm vi thay vì chỉ kể tên; chờ chạy lại để kết luận |

Sau sửa, unit AI **325/325**, API/quyền/retrieval **118/118**, bộ kiểm nguồn **8/8**, frontend service **5/5**; log mới `completeness-unit.txt`, `completeness-api.txt`. Guard danh sách chỉ áp dụng khi nguồn có ordinal liên tiếp rõ và câu hỏi yêu cầu liệt kê; không coi là kiểm đủ ý cho mọi câu hỏi. Capability gateway mới `qa_completeness_v1` dùng để phân biệt phiên cũ. Final preflight hiện dừng vì phiên Kaggle chưa có capability này (`final-preflight.txt`); chưa chạy/ghi đạt lượt cuối. File `.private/ayo/runtime.ipynb` đã sinh lại, chờ import và chạy hai cell code rồi thực hiện lại 10 câu. Không cần thêm dữ liệu, train hoặc thay checkpoint.

**Lượt có capability completeness:** đã chạy lại đủ 10 câu, config khớp. Log `philosophy-final.txt`, đối chiếu từng câu ở `source-review-latest.json`: **7 PASS, 2 FAIL, 1 REVISE**; 9 HTTP 200 và 1 HTTP 503. Hai lỗi thiếu nội dung của câu hai mặt/cấp độ phương pháp luận đã sửa trong đầu ra thật. Câu ba hình thức bị chặn thay vì phát hành câu dở dang; câu nguồn gốc duy tâm còn thiếu phần nhận thức luận; câu thế giới quan có vế phụ vượt đoạn được dẫn (đối chiếu nằm ở trang khác), cần bỏ hoặc dẫn đúng, không tự gán nguồn. Latency trung bình 31,629 giây, tối đa 85,220 giây; không suy ra nhanh hơn từ các lượt nhỏ này.

**Sửa tiếp evidence:** kiểm retrieval (`context-inspection.txt`) có đủ đoạn cần dùng; dựng lại ngân sách bằng tokenizer cục bộ (`budget-inspection.txt`) cũng giữ đoạn liên quan, nhưng đây không phải trace tokenization mới của Kaggle. Đã tách đoạn văn dài không phải quy trình thành các câu nguồn nguyên văn, mỗi câu có ID riêng gắn cùng chunk/trang; không viết lại nội dung nguồn hoặc tự thêm citation. Giữ nguyên dòng nguồn của quy trình, trang tiếp nối và danh sách ordinal để không làm lệch kiểm đủ bước/ý. Ranh giới câu dùng heuristic dấu câu/chữ hoa bảo thủ, không phải mô hình hiểu ngữ nghĩa hay bảo đảm hết lỗi citation. Kiểm ngân sách sau sửa vẫn giữ các phần liên quan (`atomic-budget-inspection.txt`).

Bản này đạt unit AI **331/331**, API/quyền/gateway **118/118**, bộ câu hỏi/notebook **13/13** (gồm 8 test bộ câu hỏi, không cộng thành 21). Log `atomic-unit.txt`, `atomic-api.txt`, `atomic-notebook-tests.txt`; test notebook Windows chạy với UTF-8 ngoài sandbox do quyền thư mục tạm. Notebook riêng đã sinh lại, thêm capability `qa_atomic_evidence_v1`. Tại thời điểm sửa này chưa có lượt GPU; lượt sau triển khai được ghi bên dưới. Các kết quả trước sửa được giữ nguyên, không đổi thành đạt.

**Lượt mới nhất sau triển khai tách câu:** gateway có cả hai capability QA và cấu hình khớp backend. Đã chạy đủ 10 câu độc lập qua backend tới Qwen: 10 HTTP 200, gồm 8 câu trả lời và 2 câu từ chối đúng vì thiếu căn cứ. Đối chiếu nội dung/citation đạt **8 PASS, 2 FAIL**; không coi HTTP 200 là đạt chất lượng. Trung bình 24,745 giây/câu, tối đa 43,691 giây; bộ nhỏ này không chứng minh tốc độ hoặc chất lượng tổng quát.

| Phần còn thiếu | Kết quả đối chiếu |
|---|---|
| Ba hình thức chủ nghĩa duy vật | Đã hết 503/câu dở dang nhưng mới kể đủ tên, giải thích chất phác và thời kỳ của siêu hình. Thiếu đặc trưng siêu hình ở trang 8 và phần giải thích duy vật biện chứng |
| Nguồn gốc chủ nghĩa duy tâm | Đã trả đúng nguyên nhân nhận thức luận. Ý nguồn gốc xã hội có nội dung phù hợp trang 9 nhưng lại dẫn đoạn trang 8 chỉ mới mở đầu ý, nên chưa đạt citation |

Câu thế giới quan đã bỏ vế phụ dẫn sai của lượt trước; hai mặt vấn đề cơ bản và ba cấp độ phương pháp luận vẫn đủ ý. Hai câu lịch thi/liên hệ giảng viên không bịa dữ liệu. Log đầy đủ: `.private/ayo/qa/philosophy-atomic.txt`; nhận xét từng câu: `source-review-atomic.json`; tiến độ: `report.json`. Cảnh báo tokenizer chưa được xác minh nguyên nhân. **Chưa chốt bước 5; cần sửa hai lỗi nhiều trang và kiểm lại đầu ra thật.** Không yêu cầu thêm PDF hoặc train lại để lưu nhận xét này; chưa commit/push.

**Bản sửa sau lượt 8/10:**

- Với yêu cầu đặc điểm từng loại, nhận diện các mục `+ ... là ...` mà chính nguồn đánh dấu, chọn nhóm cùng chủ đề câu hỏi và yêu cầu phần giải thích sau mỗi mục. Giữ đoạn tiếp nối ở trang liền kề của cùng document/version trước đoạn gây nhiễu khi ghép prompt; không chỉ kiểm việc kể đủ tên. Chỉ áp dụng khi cấu trúc nguồn đủ rõ, không tự suy ra mọi loại danh sách hoặc áp vào câu hỏi chỉ yêu cầu tên/một loại cụ thể.
- Chặn trường hợp một ý dài gần như chép nguyên văn từ đoạn khác nhưng gán vào nguồn mở đầu không chứa nội dung ấy. Model được thử sửa một lần trong thời gian còn lại, nhận lý do sai nguồn để tự chọn lại; backend không tự thay citation. Đây là kiểm xung đột văn bản gần nguyên văn, không phải bộ chấm entailment hay bằng chứng mọi cách diễn đạt đều được hỗ trợ. Những câu diễn giải khác từ vẫn cần đối chiếu nguồn khi nghiệm thu.
- Tokenizer Qwen được nạp với `fix_mistral_regex=False`, không áp regex Mistral. Loader đối chiếu mẫu pre-tokenizer đang nạp với `tokenizer.json` của checkpoint; khác mẫu hoặc không phải Qwen2 thì dừng. Notebook in `QWEN_TOKENIZER_CHECK` sau kiểm tra. Kiểm offline trên bộ tokenizer Qwen đã khóa: 13 chuỗi, fast khớp cả tokenizer đã lưu và bản Qwen slow, mẫu không đổi. Đây chưa phải kết quả kiểm checkpoint trong phiên Kaggle mới. Mã [Transformers 4.57.6](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/tokenization_utils_base.py) cho thấy nhánh nhận diện Mistral có thể cảnh báo với config cục bộ ở khoảng phiên bản trung gian; không suy từ cảnh báo rằng phải thay regex Qwen.

**Kiểm thử bản sửa:** unit AI **352/352** (`description-unit-final.txt`); API/quyền/retrieval/gateway **118/118** (`description-api-final.txt`); bộ câu hỏi, preflight và exporter notebook **15/15** (`description-notebook-tests-final.txt`, gồm 10 test bộ câu hỏi). Không cộng số test giữa các nhóm chồng nhau. Test API dùng database test riêng và đã xóa sau chạy; không train, không ghi lại học liệu thật. Dựng prompt offline cho hai câu khó vẫn giữ đúng nguồn trang 7–8 và 8–9; log `description-budget.txt`. Tokenizer: `tokenizer-pattern-check.txt`.

**Thao tác còn lại để nghiệm thu:** import lại `.private/ayo/runtime.ipynb` (ba cell gồm một markdown và hai code); giữ Input/Secrets/GPU, restart Python rồi chạy hai cell code theo thứ tự. Sau `DUAL_GPU_READY`, gateway phải có capability `qa_source_descriptions_v1` bên cạnh hai capability QA trước. Chạy hai câu lỗi bằng `--case materialism_forms --case idealism_origins`; nếu đúng nội dung và từng đoạn nguồn, chạy lại không có `--case` để kiểm đủ 10 câu. Công cụ ghi rõ danh sách câu đã chọn; lượt hai câu không được dùng làm kết quả đủ 10 câu. Chỉ chốt bước 5 sau kết quả thật, không dựa vào test mock hoặc tự điền đáp án vào log. Chưa commit/push.

**Kết quả sau lần import này:** đã xác minh đủ ba capability QA và config khớp. Output khởi động xác nhận mẫu tokenizer Qwen không bị đổi trên cả hai GPU, không áp regex Mistral. Tuy nhiên, kiểm hai câu thật vẫn **0 đạt/2 chưa đạt**: câu ba hình thức duy vật trả `GENERATION_TIMEOUT` sau 92,124 giây; câu nguồn gốc duy tâm trả `GENERATION_EVIDENCE_MISMATCH` sau 86,474 giây. Không có câu trả lời đạt để nghiệm thu; guard chặn lỗi không được tính là hoàn thành QA. Chưa chạy đủ 10 câu vì điều kiện kiểm hai câu đầu chưa đạt.

Đã đối chiếu chẩn đoán bằng đường QA stateless sẵn có, không tạo hội thoại: tuy trả `ANSWERED`, câu duy vật vẫn sai đặc trưng siêu hình và câu duy tâm vẫn thay nguyên nhân nhận thức luận bằng định nghĩa, citation chưa gắn đúng từng ý. Vì vậy không chuyển sang đường yếu hơn hoặc tắt guard để lấy HTTP 200. Log `description-two-live.txt`, `stateless-probe.txt`; nhận xét `source-review-description.json`, tiến độ `report.json` tại `.private/ayo/qa/`. Không yêu cầu chạy lại nguyên notebook này khi chưa có sửa cơ chế sinh/chọn nguồn; chưa chốt bước 5 và chưa commit/push.

**Đổi cơ chế sau đối chiếu:** thêm giao thức `qa_source_selection_v1`. Với danh sách đặc điểm có cấu trúc rõ trong nguồn, model chỉ xuất danh sách ID đoạn thay vì vừa diễn giải dài vừa tự gán citation. Với câu diễn giải bị phát hiện chép từ nguồn khác, lượt phục hồi cũng chỉ chọn ID trong thời gian còn lại của deadline cũ. Renderer lấy đúng các span nguyên văn và citation gốc; phần nối trang giữ cả dẫn chứng trước/sau. Từ chối ID lạ, ID lặp, dữ liệu tự viết thêm, số trang/câu dẫn/câu dở dang. Câu trả lời có nhãn **“Trích học liệu”**, trace `source_selected_extract`; không được báo cáo đây là câu diễn giải tự do đã cải thiện hoặc Qwen đã tự viết các đoạn ấy. Các câu QA thông thường, memory, hint và đường stateless không bị đổi sang trích dẫn hàng loạt.

Mã tập trung tại `ai/rag/conversation.py` và `pipeline.py`; vẫn kiểm đủ mục nguồn nhận diện rõ, không tự điền đáp án từ bảng test hoặc sửa citation của câu diễn giải sai. Đây là một nhánh trả lời nguyên văn, không phải bộ hiểu ngữ nghĩa: model vẫn có thể chọn sai đoạn hoặc thiếu ý; cần đọc đầu ra thật để nghiệm thu.

**Kiểm bản giao thức mới:** unit AI **359/359** (`selection-unit.txt`), API/quyền/retrieval **118/118** (`selection-api.txt`), công cụ/capability/notebook **16/16** (`selection-notebook-tests.txt`, gồm 11 test bộ câu hỏi). Bộ test mới kiểm renderer không nhận lời tự tạo của model, citation xuyên trang, ID lạ/lặp, từ chối thiếu căn cứ, và trace trích nguồn sau phục hồi. Kiểm ghép prompt bằng tokenizer cục bộ vẫn giữ đủ hai trang (`selection-budget.txt`). `selection-render-check.txt` là kiểm renderer với ID lấy từ cấu trúc nguồn, **không phải lượt model chọn ID hoặc kết quả GPU đạt**.

Notebook riêng `.private/ayo/runtime.ipynb` đã sinh lại, vẫn một markdown và hai cell code. Cần import bản này, restart Python và chạy hai cell code; checker yêu cầu thêm capability `qa_source_selection_v1`, không chấp nhận phiên chỉ có bản description cũ. Sau đó kiểm hai câu khó trước; nếu đúng nguồn và đủ ý mới chạy đủ 10 câu. Không cần thêm PDF, train lại, nới deadline hoặc tắt guard. **Chưa có kết quả GPU sau đổi giao thức, chưa chốt bước 5.**

### Kết Quả Nghiệm Thu

Gateway đã xác nhận `qa_source_selection_v1`, cấu hình khớp backend, hai GPU giữ nguyên mẫu tokenizer Qwen. Câu duy vật đã trích đủ các đặc điểm ở trang 7–8. Câu duy tâm ban đầu chọn đúng nguồn nhưng chỉ trích câu chuyển ý; đã bổ sung hoàn thiện ngữ cảnh trích dẫn tại `backend/apps/ai/source_quotes.py` và gọi sau bước ánh xạ nguồn trong `services.py`. Chỉ với câu trả lời trích nguyên văn đã đối chiếu từng span, nếu một câu chuyển ý dở dang tiếp nối sang trang kề cùng document/version, backend thêm câu nguồn hoàn chỉnh liền trước và nối hai phần trích. Không sửa lời diễn giải của model, không tạo kiến thức hoặc citation mới; đoạn nguồn trả về và kiểm quyền cuối lượt giữ nguyên. Backend đã restart trước lượt nghiệm thu; không cần nạp Kaggle thêm cho phần sửa này.

| Nhóm câu | Kết quả lượt đầy đủ |
|---|---|
| Định nghĩa, thời gian/nơi ra đời, điều kiện ra đời | 3/3 đạt; nội dung có nguồn hỗ trợ, dù một số câu còn dài hơn cần thiết |
| Hai mặt vấn đề cơ bản; thế giới quan; cấp độ phương pháp luận | 3/3 đạt; đủ ý được hỏi và dẫn đúng nguồn |
| Ba hình thức duy vật | Đạt; trích nguồn đủ các đặc điểm, citation trang 7–8; 8,464 giây |
| Hai nguồn gốc duy tâm | Đạt; nguyên nhân nhận thức luận trang 8 và xã hội trang 9; 47,337 giây. Phần ngữ cảnh liền trước do renderer bổ sung nguyên văn, không báo Qwen tự diễn giải toàn bộ |
| Lịch thi và số điện thoại giảng viên không có trong PDF | 2/2 từ chối đúng, không đoán dữ liệu hoặc tạo citation |

Tổng **10/10 đạt**, 10 HTTP 200 gồm 8 `ANSWERED` và 2 `INSUFFICIENT_EVIDENCE`; toàn bộ citation identity khớp catalog gốc. Hai câu khó hiển thị rõ **“Trích học liệu”**. Trung bình 27,745 giây/câu, tối đa 58,385 giây; đây là bộ phát triển nhỏ đã dùng trong quá trình sửa, không suy ra độ chính xác trên benchmark độc lập hoặc chất lượng QA tổng quát.

**Minh chứng:** `.private/ayo/qa/accepted-live.txt` chứa đủ câu hỏi/response/citation/timing và config/capability; `source-review-accepted.json` ghi nhận xét từng câu; `report.json` ghi tiến độ/checksum. SHA-256 log cuối: `f9c33ca44673f510cfa285594c56a9bd74ee62d108de001753f023ac989c83e9`. Giữ nguyên các log và nhận xét lỗi trước đó. Đây là kiểm API chủ khóa học với Qwen/retrieval thật, không phải nghiệm thu trình duyệt frontend hoặc kiểm GPU memory nhiều lượt/quyền học viên mới.

**Hồi quy bản cuối:** unit AI **368/368** (`quote-unit.txt`); API/quyền/retrieval **119/119** (`quote-api.txt`), gồm test tích hợp hoàn thiện trích dẫn; công cụ/notebook **16/16** (`selection-notebook-tests.txt`, gồm 11 test bộ câu hỏi). Không cộng các nhóm chồng nhau. Database test tách riêng đã được xóa sau chạy, không thay học liệu thật. Không train lại, chưa commit/push.

**Có thể sang bước 6.** Giữ phiên Kaggle hiện tại chạy để dùng chatbot; không cần import lại notebook cho bước 5.

## 7. Memory, Hint Và Tóm Tắt

**Trạng thái: hoàn thành bước 6 trong phạm vi chức năng đã kiểm.** Ngày 20/11/2026, sau khi mở lại notebook hiện có, health HTTP 200/ready và config khớp backend. Đã chạy đủ 9 ca: 5 lượt QA trong hai hội thoại độc lập, 2 lượt hint qua gateway thật và 2 summary qua API. Trước đó endpoint từng offline (`ERR_NGROK_3200`); giữ log cũ, không tính các yêu cầu lỗi thành ca đạt. Không thay model, train lại, đổi notebook hoặc đưa PDF CPU/ALU vào ca nghiệm thu.

### Phần Đã Hoàn Thành

| Phần | Cơ chế và kết quả |
|---|---|
| Memory | Giữ giao thức `chat_history_v1`: tối đa 4 lượt, 768 token; câu nối dùng lịch sử, câu đổi chủ đề bỏ lịch sử; nhãn citation cũ không thành nguồn mới. Bổ sung regression trên câu hỏi Triết học, giữ kiểm cách ly owner/document/version và hai hội thoại |
| Hint | Giữ ba hành động READ/COMPARE/OUTLINE. Chỉ cho phép chọn hành động và nguồn hiện tại; không phát hành phần bài giải tự do do model sinh. Kiểm chặn bài giải chèn thêm, rubric, ID nguồn lạ/lặp và thiếu căn cứ. Policy vẫn chỉ nhận bài PRACTICE được phép; không gửi `correct_ids`/hint chấm riêng |
| Tóm tắt | Thêm `mode=summary` tại `/api/ai/chat/`, chọn đúng một tài liệu và trang PDF vật lý; mặc định toàn tài liệu, tối đa 20 trang/lần. Đọc toàn bộ chunk được phép trong phạm vi, kiểm checksum/provenance và kiểm lại quyền trước trả kết quả; không dùng FAISS top-k hoặc gọi Qwen |
| Giao diện | Nút biểu tượng tài liệu trong thanh công cụ ayo mở phạm vi trang, kết quả có citation mở PDF và thông tin số trang/chunk đã đọc. Không trộn summary vào lịch sử hội thoại hoặc memory |

**Bản tóm tắt ban đầu được nghiệm thu tại mục này là trích ý, không phải diễn giải sinh bởi Qwen; đã được thay thế bằng bản tổng hợp ở mục 9.** Mỗi trang chọn tối đa hai câu nguồn hoàn chỉnh theo tần suất từ và giữ thứ tự nguồn. Trang bìa/văn bản ngắn được ghi rõ là trích văn bản ngắn. Đây là bản đọc lướt theo trang, không bảo đảm bao quát mọi luận điểm hoặc nối lập luận giữa các trang. `coverage.whole_document` chỉ xác nhận đã đọc toàn bộ phạm vi trang của tài liệu, không phải điểm đánh giá độ đầy đủ ngữ nghĩa.

Nếu thiếu trang trong catalog, không trích được văn bản phù hợp hoặc phạm vi quá lớn, API báo lỗi rõ thay vì trả bản thiếu nhưng ghi là toàn tài liệu. Coverage ghi document/version/checksum, trang bắt đầu/kết thúc, danh sách trang, số chunk và các trang chỉ có văn bản ngắn. Gateway không nhận mode mới này: nó vẫn phục vụ QA/hint, do summary được xử lý hoàn toàn tại backend. Không cần import lại notebook cho thay đổi này.

### Minh Chứng

| Kiểm thực chạy | Kết quả |
|---|---|
| Summary trang PDF 4–6 của `ch01.pdf` | HTTP 200; đọc đủ 3 trang/6 chunk; 4 citation khớp catalog; coverage không ghi toàn tài liệu |
| Summary toàn `ch01.pdf` | HTTP 200; đọc đủ 12 trang/20 chunk; 15 citation khớp catalog; trang 1–2 có nhãn văn bản ngắn |
| Unit AI | 371/371 đạt, gồm 3 test mới cho hint |
| API/policy/memory/retrieval/quyền | 128/128 đạt trong database test riêng; gồm 14 test summary và 2 test memory mới |
| Frontend | 53 file/343 test đạt; lint và build đạt, còn cảnh báo bundle lớn sẵn có |
| Model thật cho memory | Hai hội thoại/5 lượt QA đều HTTP 200, citation identity khớp; hai câu nối dùng đúng 1 lượt lịch sử (163 và 102 token); câu đổi chủ đề bỏ 2 lượt cũ, hội thoại mới bắt đầu với 0 lượt |
| Model thật cho hint | Hai lượt qua gateway đều trả hướng dẫn READ có citation trang 4, không đưa bài giải kể cả khi yêu cầu đáp án hoàn chỉnh; 2,613 và 2,224 giây. Không có bài PRACTICE công bố trong khóa này; không gọi đây là kiểm UI bài tập thật |

Mã mới chính: `backend/apps/ai/summary.py`, `frontend/src/components/ai/DocumentSummary.jsx`; hợp đồng tại serializers/views và `ai.service.js`. Công cụ kiểm: `scripts/check_study_assistant.py`. Log riêng tại `.private/ayo/study/`: `live.txt` giữ lượt đầu thất bại; `live-current.txt` ghi hai ca summary và health offline; `backend-tests-final.txt`, `ai-unit.txt`, `frontend-tests-final.txt`, `frontend-lint.txt`, `frontend-build.txt` ghi kiểm hồi quy. Không cộng các nhóm test chồng nhau.

Đã cập nhật riêng container frontend, kiểm HTTP `http://localhost:5173/` trả 200; log `frontend-deploy.txt`. Chưa nghiệm thu tương tác trình duyệt trên desktop/mobile. Docker build báo dependency audit có 5 cảnh báo bảo mật (3 moderate, 2 high); chưa phân tích khả năng khai thác và không tự nâng dependency ngoài phạm vi bước này. Không coi build đạt là không có rủi ro dependency.

### Nghiệm Thu Sau Khi Mở Lại Kaggle

| Kịch bản | Đối chiếu kết quả |
|---|---|
| Điều kiện ra đời → điều kiện thứ hai | Đủ hai điều kiện từ trang 4; câu nối xác định đúng tầng lớp lao động trí óc và việc hệ thống hóa quan niệm thành lý luận. Memory 0 → 1, không lấy câu trả lời cũ thay nguồn |
| Chuyển sang thế giới quan | Trả đúng định nghĩa và ba loại hình ở trang 6; memory dùng 0, bỏ cả hai lượt chủ đề trước |
| Hội thoại độc lập: hai mặt → mặt thứ hai | Lượt đầu memory 0; câu nối dùng 1 lượt và trả đúng khả năng nhận thức thế giới, citation trang 6; không nhầm với điều kiện ra đời của hội thoại trước |
| Hint đọc nguồn và yêu cầu chép đáp án | Cả hai chỉ hướng dẫn đọc đoạn dẫn và tự diễn đạt; không đưa đáp án/rubric riêng. Đây là kiểm gateway với đề ôn tập dựa trên học liệu thật, không phải bài PRACTICE đã công bố trên LMS |
| Summary phạm vi và toàn tài liệu | Hai ca API chạy lại đều đạt kiểm phạm vi/chunk/citation như bảng trên; không dùng history hoặc Qwen để sinh trích ý |

**Giới hạn nội dung:** câu điều kiện còn đánh số cả câu kết luận thành mục thứ ba; đó không phải điều kiện độc lập thứ ba. Câu thế giới quan còn dài và có vế diễn giải cuối “khác biệt với thế giới quan thông thường” không được nguồn dẫn nêu trực tiếp; không dùng vế mở rộng này làm bằng chứng học thuật. Nghiệm thu ở đây xác nhận hiểu câu nối, tách chủ đề/hội thoại, dẫn đúng nguồn hiện tại và hint không phát hành bài giải; không khẳng định 9/9 câu hoàn hảo về diễn đạt hoặc QA tổng quát. Summary là trích ý đọc lướt, không phải bản tổng hợp lập luận do Qwen viết.

Log cuối `.private/ayo/study/live-resumed.txt`, SHA-256 `19689076f752658ee4ac618929f9247360d5d2312806d0549bdd9b8baabff23a`; `report.json` ghi nhận xét từng ca và giới hạn. Giữ nguyên các log offline trước đó. Quyền bài tập được kiểm bằng regression API/database test riêng; không seed bài tập vào dữ liệu đang dùng. Chưa nghiệm thu UI hint trên bài PRACTICE thật hoặc tương tác trình duyệt desktop/mobile; phần tích hợp cuối thực hiện ở bước 8–9.

**Có thể sang bước 7.** Giữ notebook inference chạy để tiếp tục kiểm gợi ý câu hỏi. Không cần import lại notebook; nếu endpoint đổi thì đồng bộ helper ở mục 1. Chưa commit, push hoặc tạo PR.

## 8. Gợi Ý Câu Hỏi Tiếp Theo

**Trạng thái: hoàn thành bước 7 trong phạm vi trợ lý tài liệu.** Gợi ý hiện dưới câu trả lời QA mới nhất, chỉ gửi khi người dùng bấm; không tự gọi model, không đổi notebook hoặc cấu hình Kaggle.

### Cơ Chế

- Backend tạo gợi ý theo mẫu từ tiêu đề có thật trong các đoạn vừa dẫn. Metadata tiêu đề phải xuất hiện trong excerpt; bỏ tiêu đề quá dài, dạng câu văn, liên kết hoặc nội dung điều khiển không phù hợp. Không lấy chủ đề từ tài liệu khác hay bổ sung kiến thức ngoài nguồn.
- Bổ sung câu làm rõ/tóm lược có cụm “vừa nêu” để dùng memory hiện hành. Ưu tiên 2–3 câu; loại câu hỏi trùng với câu hiện tại/lịch sử gần nhất nên có thể còn ít hơn hoặc rỗng, không lặp cho đủ số lượng. Không khẳng định loại được mọi câu gần nghĩa.
- `suggested_questions` là trường tùy chọn của response API, tối đa 3 chuỗi/240 ký tự mỗi chuỗi. QA thiếu căn cứ trả danh sách rỗng; hint/summary không có nhóm gợi ý này. Lỗi bộ tạo gợi ý không làm mất câu trả lời/citation hoặc ghi văn bản nguồn vào log lỗi.
- Giao diện dùng cùng đường gửi, document scope, conversation ID và mã chống gửi trùng. Khóa gửi đồng bộ bằng ref, chặn khi đang pending/không rõ kết quả; chỉ hiện nhóm ở lượt cuối, không kéo gợi ý sang chat mới hoặc tài liệu khác. Backend vẫn kiểm quyền và version trước mỗi lượt gửi/đọc lại.
- Gợi ý được lưu trong JSON kết quả hội thoại, không cần migration. Kết quả cũ trước cập nhật không được sinh lại hoặc sửa lịch sử; gửi câu mới để nhận gợi ý. Đây là câu hỏi theo mẫu phía server, không phải Qwen sinh thêm ba câu trong một lần inference riêng.

Mã: `backend/apps/ai/followups.py`, phần nối tại `services.py` và serializer response; UI tại `frontend/src/components/ai/DocumentAssistant.jsx`/`assistant.css`. Bộ kiểm thật tái sử dụng `scripts/check_study_assistant.py --run --followups`.

### Minh Chứng

Kiểm trên bản công bố của `data/corpus/THMLN/ch01.pdf`, cùng document/version/checksum đã ghi ở trên:

| Kiểm | Kết quả |
|---|---|
| Hỏi định nghĩa Triết học | API thật trả lời và có 3 gợi ý: đối tượng của triết học, giải thích rõ hơn, tóm lược ý chính |
| Chưa bấm gợi ý | Hội thoại vẫn chỉ có 1 lượt; không tự gửi thêm câu hỏi |
| Chọn câu làm rõ | Giữ nguyên conversation/document; tạo lượt thứ 2, memory dùng 1 lượt/221 token; citation identity khớp catalog |
| Gửi lại cùng client message ID | Phát lại kết quả cũ, số lượt vẫn là 2. Nội dung/định danh không đổi; response đọc lại có thêm metadata rating hiện hành theo hợp đồng sẵn có |
| Đọc lại lịch sử | Danh sách gợi ý đã lưu khớp response ban đầu; câu làm rõ vừa chọn không bị gợi ý lại nguyên văn |
| Unit AI | 379/379 đạt, gồm 8 test gợi ý |
| API/policy/memory/retrieval/quyền | 130/130 đạt, gồm kiểm không thêm generation call và lỗi gợi ý không làm mất đáp án |
| Frontend | 53 file/348 test đạt; 5 test mới kiểm bấm đúng hội thoại, chống gửi trùng, dữ liệu gợi ý lỗi, đổi chat/tài liệu và lượt pending |
| Vận hành | Lint/build đạt; cập nhật riêng frontend, HTTP localhost:5173 trả 200; giữ cảnh báo bundle lớn hiện có |

**Giới hạn:** đây là kiểm chức năng API với quyền chủ khóa học và kiểm UI bằng component test, chưa phải nghiệm thu thao tác trình duyệt desktop/mobile hoặc ma trận người học mới. Khi bấm câu “giải thích rõ hơn”, Qwen vẫn lặp lại câu trả lời trước trong lượt này: cơ chế chuyển câu hỏi/memory đúng, nhưng không chứng minh câu trả lời sâu hoặc tốt hơn. Không dùng kết quả bước này làm điểm chất lượng QA hoặc benchmark mới. Việc kiểm policy tích hợp và demo trình duyệt tiếp tục ở bước 8–9; không sửa prompt/model ngoài phạm vi để che hạn chế diễn đạt.

Log riêng tại `.private/ayo/followups/`: `live-accepted.txt`, `ai-unit.txt`, `backend-tests.txt`, `frontend-focused.txt`, `frontend-tests.txt`, `frontend-lint.txt`, `frontend-build.txt`, `frontend-deploy.txt`; tiến độ và giới hạn tại `report.json`. SHA-256 log nghiệm thu: `468a2b2010a2719443db7e0398b2529e6821bc8ab82bdb18ab4a7dbf8005c8dc`. Giữ `live.txt` của lượt đầu: checker ban đầu so sánh cả metadata rating của response đọc lại; đã sửa checker để đối chiếu đúng nội dung/định danh và chạy lại đủ luồng, không thay kết quả model trong log.

**Gợi ý câu hỏi không cần import lại notebook.** Riêng thay đổi tóm tắt mới ở mục 9 cần nạp notebook cập nhật trước khi kiểm GPU. Chưa commit, push hoặc tạo PR.

## 9. Tóm Tắt Mạch Lạc

**Trạng thái:** đã kiểm runtime mới trên GPU và thao tác thật qua UI học viên. Bản tóm tắt toàn tài liệu đã hiển thị, nguồn mở đúng trang; không còn câu dở dang ở đoạn phương pháp. Giữ base Qwen NF4 + RAG, không nạp adapter hoặc train lại. Kết quả này xác nhận chức năng, không phải chứng nhận toàn bộ nội dung model đều chính xác.

### Luồng Hiện Tại

```text
Chọn một tài liệu và phạm vi trang PDF
  -> kiểm quyền, TEST, version, checksum và đủ văn bản của từng trang
  -> chia toàn bộ chunk trong phạm vi thành các phần tối đa 700 ký tự
  -> Qwen viết đoạn văn trực tiếp từ từng lô nguồn, tối đa 8 phần/lượt
  -> kiểm JSON, nguồn, câu hoàn tất và kiểm lại quyền
  -> chỉ công bố sau khi đọc hết phạm vi; xếp các đoạn mới theo thứ tự nguồn
```

- Chiến lược mới `source_sections_v1` không đưa ghi chú model đã sinh vào các lượt diễn giải tiếp theo. Các đoạn cuối do Qwen viết từ nguồn, không phải trích câu nguyên văn làm đáp án hoặc một lượt model viết lại toàn chương.
- Không dùng top-k cho tóm tắt. Giới hạn 20 trang PDF, 300 chunk, 600.000 ký tự, 30 phút/100 bước; thiếu văn bản của một trang thì không báo đã đọc đủ. Mỗi lượt dùng input thực đo tối đa 3.584 token, output tối đa 640 token.
- POST `/api/ai/chat/` với `mode=summary` tạo công việc; GET/POST `/api/ai/summaries/{id}/` đọc tiến độ/thực hiện một bước. Trạng thái lưu PostgreSQL; khóa bước, owner, TEST, version/checksum và config được kiểm trước/sau sinh. Không công bố phần đang làm hoặc dùng bản trích ý để che lỗi.
- Nguồn hiển thị ở cấp phạm vi, `coverage.citation_scope=input_range`, nhãn “Nguồn trong phạm vi tóm tắt”. Identity/đọc đủ không tự chứng minh mọi câu được nguồn hỗ trợ. QA/hint giữ luồng riêng.
- JSON grammar hỗ trợ văn bản tiếng Việt, dấu ngoặc kép và backslash được escape đúng; mã S1/S2 chỉ ở metadata. Backend chỉ tách hậu tố nguồn lặp có mã đã được kiểm, không sửa nội dung câu.
- Câu kết thúc dở dang không được công bố dù JSON hợp lệ. Với lỗi này, lô nguồn được thử lại tối đa một lần, nhỏ hơn; cursor chưa tiến và các phần còn lại không bị bỏ qua. Có lưu lý do, số lần thử và số lần sinh thực trong coverage.
- Đóng panel dừng gọi bước kế tiếp, không hủy bước server đã nhận; thử lại lỗi mạng trong cùng panel dùng lại công việc. Chưa có màn hình tìm lại công việc sau khi tải lại trình duyệt.

### Kiểm Thật Và Phát Hiện

Nguồn duy nhất cho các ca này là `data/corpus/THMLN/ch01.pdf`, 12 trang/20 chunk. Không dùng tài liệu demo riêng của máy khác.

| Ca kiểm | Kết quả và giới hạn |
|---|---|
| Đọc lại ghi chú cũ | Phát hiện nhập nhằng hoài nghi luận cổ đại/phục hưng và diễn giải chồng tầng; không dùng làm nghiệm thu bản mới |
| Đọc trực tiếp đoạn nguồn trang PDF 9 | Bản sinh phân biệt được bối cảnh; log `fresh-source.txt`, không tái sử dụng ghi chú |
| Lượt mới trang 4–6, chiến lược nguồn trực tiếp | 15/15 phần, 6 chunk, 2 lượt, 5 đoạn, 78,920 giây; giữ hai điều kiện ra đời, hai mặt vấn đề cơ bản, ba loại hình thế giới quan và tách đúng duy vật/Hegel |
| Lượt mới toàn tài liệu | 46/46 phần, 20 chunk, 6 lượt, 20 đoạn, 280,863 giây; giữ các chủ đề cuối. Tuy nhiên có một câu dừng ở “thừa nhận cả cái”, nên không chốt đạt nội dung |
| Nguyên nhân câu dở | Grammar cũ không cho phép escape ngoặc kép trong text; đã sửa và bổ sung kiểm câu hoàn tất, không xóa câu sai để báo đạt |
| Lượt API mới trước khi sửa chiến lược | Ca 4–6 ghép sai duy vật/Hegel; giữ riêng `live-fresh.txt`, không tính đạt. Driver toàn tài liệu dừng có chủ đích sau phát hiện, không tính là một lượt hoàn chỉnh |

Lượt mới nguồn trực tiếp lưu tại `live-source-sections.txt`; không đổi kết quả cũ thành đạt, không chép câu mẫu thay model. Bản sinh còn có chỗ diễn đạt dài/khái quát rộng; prompt mới nhắc giữ đúng chủ thể, mốc thời gian và phạm vi của từng nhận định. Hiệu quả của thay đổi prompt phải được đọc đối chiếu sau khi nạp runtime, không tự kết luận từ unit test.

### Kiểm Offline Và Triển Khai

| Kiểm tra | Kết quả |
|---|---|
| AI backend/engine/gateway | 510/510 đạt; `backend-quotes-final.txt` |
| Grammar với tokenizer Qwen thật | 14/14 ca đạt; có ngoặc kép, backslash, mã nguồn bị cấm và giới hạn đoạn; `parser-qwen-quotes.txt`. Không tải trọng số hoặc chạy GPU |
| Frontend liên quan | 2 file/12 test đạt; `frontend-source-final.txt`. Đây là component/service test, không phải nghiệm thu trình duyệt |
| Notebook | 7/7 test đạt; `notebook-quotes.txt`; hai cell code parse được và source bundle khớp mã hiện tại |
| Database/model | Không seed, reset, đổi tài khoản, đổi index hoặc train; các công việc sinh thật là bản ghi sử dụng thông thường |

Các nhóm test chồng nhau, không cộng tổng. Log/backup để riêng trong `.private/ayo/summary/`; không đưa dữ liệu riêng vào Git. Backend đã nạp cách đọc nguồn trực tiếp và cần giữ bộ chặn câu dở dang khi nghiệm thu runtime mới.

### Kết Quả Kiểm Trên UI

Health mới trả HTTP 200, `ready=true`, `summary_ready=true`; đã qua kiểm capability `summary_json_quotes_v1`. Không cần nạp notebook thêm cho lượt kiểm này. Log 404 trước đó là lịch sử, không phải trạng thái kết nối hiện tại.

Đăng nhập tài khoản học viên hiện có, mở lớp Triết học Mác-Lênin, buổi Chương 1, tài liệu `ch01.pdf`; chọn tóm tắt từ trang 1 đến cuối tài liệu. Không đổi tài khoản/quyền hoặc lưu mật khẩu vào minh chứng.

| Minh chứng | Kết quả |
|---|---|
| Công việc mới từ UI | `05fdbc0d-5569-4513-91ed-13502a7325b4`, bắt đầu từ 0, không dùng ghi chú của lượt cũ |
| Phạm vi và kết quả | 12/12 trang, 20 chunk, 46/46 phần, 6 lượt sinh, 19 đoạn; thời gian từ lúc tạo công việc đến hoàn tất 408,824 giây, gồm cả khoảng dừng/tiếp tục, không phải thời gian GPU thuần |
| Hiển thị | Bản tóm tắt xuất hiện trên UI; đoạn biện chứng/siêu hình hoàn tất câu; không lộ mã nguồn nội bộ trong văn bản |
| Nguồn | Danh sách đủ 20 chunk; bấm nguồn mở đúng trang 3 và 5 của PDF |
| Đọc lại API | 7/7 kiểm đạt: hoàn tất, giữ nguyên nội dung/thời gian, đúng phạm vi, đủ nguồn, identity khớp catalog, không sửa bản ghi |
| Gián đoạn UI | Hai lần báo lỗi chung; bấm lại giữ nguyên công việc, tiếp tục từ 16/46 rồi 24/46. Kết quả vẫn chỉ có 6 bước sinh thành công. Bước 8 đã đối chiếu đúng ID với log Nginx: hai HTTP 504 tại ngưỡng 60 giây; không phải model đọc lại từ đầu |

Đối chiếu nội dung: các nhóm định nghĩa, nguồn gốc, thế giới quan, duy vật/duy tâm, nhận thức, biện chứng và phương pháp luận đều hiện diện. Đoạn hoài nghi luận giữ bối cảnh phục hưng; không còn lỗi câu dừng giữa chừng đã phát hiện trước. Tuy nhiên, câu “Triết học Mác xuất hiện vào đầu thế kỷ XIX” nén quan hệ nguyên nhân thành thời điểm: nguồn trang 5 nói hoàn cảnh và khoa học đầu thế kỷ XIX **dẫn đến** sự ra đời. Câu về tri thức/niềm tin còn lặp ý và một số đoạn dài. Giữ nguyên kết quả sinh và ghi nhận giới hạn, không sửa tay đáp án để nghiệm thu chất lượng.

Minh chứng riêng: `.private/ayo/summary/ui-summary.jpg`, `ui-source-readback.txt`, `report.json`. Đã hoàn tất phần kiểm runtime và UI còn thiếu; kiểm độ ổn định kết nối/thông báo lỗi tiếp tục thuộc bước 8. Chưa nghiệm thu mobile hoặc toàn bộ ma trận quyền; không đồng nhất kiểm chức năng với đánh giá factuality toàn bộ. Không commit/push/tạo PR.

## 10. Policy, Lỗi Vận Hành Và Hợp Đồng API

### Phần Đã Hoàn Thiện

- Học viên có lượt TEST đang làm, chưa hết hạn, còn công bố và còn quyền vào buổi học thì không dùng QA, hint, summary hoặc lịch sử hội thoại. Kiểm trước khi gọi model và kiểm lại trước khi trả kết quả. Bài TEST hợp lệ ở lớp khác vẫn chặn AI; client không tự khai trạng thái kiểm tra.
- TEST đã gỡ, thu hồi công bố, chuyển buổi về nháp, gỡ buổi/lớp hoặc mất quyền không giữ khóa AI cho những phạm vi khác. Điều này không cấp lại quyền vào học liệu đã mất. Hết hạn quiz vẫn dùng cơ chế nộp tự động hiện có; không sửa bài làm đang dùng để kiểm.
- Hint chỉ dùng PRACTICE đã công bố. Model nhận tiêu đề, mô tả, đề và lựa chọn công khai; không nhận `correct_ids`, hint riêng của giáo viên, đáp án, rubric hoặc giải thích riêng trong dữ liệu câu hỏi. Không có schema cho client gửi các trường này hoặc tự chọn danh sách version được phép.
- Nguyên nhân hai gián đoạn tóm tắt trước đây đã được xác nhận tại `proxy-before.txt`: URL summaries rơi vào timeout API chung 60 giây. Đã thêm location riêng 145 giây, khớp chuỗi timeout gateway tối đa 100 giây, lease 120 giây và client 150 giây. Không tăng timeout mọi API hoặc thay cấu hình model.
- Mất kết nối/502/504 khi đã có công việc: UI báo đã lưu tiến độ; bấm lại đọc trạng thái cùng ID trước khi gửi bước kế tiếp. Không tạo công việc mới, không sinh lại công việc đã hoàn tất. Không tự retry vô hạn, không công bố phần tóm tắt đang làm.
- Phân biệt lỗi mạng, quyền, TEST, model bận, model timeout và index chưa sẵn sàng. Lỗi hạ tầng không chuyển thành `INSUFFICIENT_EVIDENCE`. Bản xem PDF ngừng hiển thị và hủy blob khi không xác minh được quyền; lỗi server không bị diễn đạt sai thành đã thu hồi quyền.

### Hợp Đồng Hint Để Nối UI

```json
{
  "mode": "hint",
  "question": "Gợi ý cách đọc đề, không giải bài.",
  "course_id": "<UUID khóa học>",
  "assessment_id": "<UUID bài PRACTICE>",
  "question_id": "<UUID câu hỏi QUIZ>"
}
```

Gửi qua `POST /api/ai/chat/` bằng JWT hiện có; với TEXT bỏ `question_id`. Có thể truyền `classroom_id`, `session_id`, `document_ids` để thu hẹp phạm vi; nếu bỏ buổi học, backend vẫn ràng buộc vào buổi của bài tập. Không gửi `conversation_id` cho hint. UI hiển thị `answer` và `citations`, dùng `version_id`/`page_number` khi mở nguồn; không tự đánh dấu đáp án đúng hoặc nộp bài theo phản hồi model.

| Trạng thái/mã | UI cần xử lý |
|---|---|
| 200, `ANSWERED` hoặc `INSUFFICIENT_EVIDENCE` | Hiển thị kết quả hoặc thông báo thiếu căn cứ; không đồng nhất với lỗi mạng |
| 403, `AI_NOT_ALLOWED` | Khóa gửi AI khi TEST có hiệu lực hoặc bài không phải PRACTICE |
| 404 hoặc 409 | Ngừng dùng scope/nguồn cũ; tải lại quyền hoặc bản công bố |
| 429, `GENERATION_BUSY` | Báo bận, không tự gửi nhiều lượt song song |
| 503, `RETRIEVAL_NOT_READY`/`RETRIEVAL_UNAVAILABLE` | Báo vấn đề chỉ mục, không báo model chưa học hoặc thiếu kiến thức |
| 503, lỗi generation/config | Phân biệt timeout, giới hạn output, bộ nhớ, offline và cấu hình không đồng bộ; không hiện token hay nội dung lỗi thô |

Swagger ở `/api/docs/`, OpenAPI ở `/api/schema/` có ví dụ hint/summary, đủ bảy operation AI và cấu trúc lỗi. Riêng summary là giao thức hai giai đoạn: tạo 202; GET đọc trạng thái, POST không body để tiếp tục; 200 của công việc có thể là `FAILED`, cần kiểm `status` thay vì chỉ HTTP.

### Kiểm Chứng Và Giới Hạn

#### Gợi ý theo bước và bản nháp học viên

UI gửi `hint_action` (`initial`, `explain_task`, `next_step`, `practice`) và `previous_hint_id`
của lượt đã thành công. Backend tự kiểm chủ sở hữu, bài/câu hỏi và phiên bản nguồn, giữ tối đa
ba lượt trước trong `ChatResponseRecord.hint_state`. Không nhận lịch sử hoặc số bước do client khai báo.
Câu hỏi/bản nháp hiện tại được chuyển nguyên vẹn tới mô hình cùng đề công khai và nguồn được phép.
Qwen chọn loại ý đang vướng, mã đoạn nguồn và mã ý trích nguyên từ bản nháp. Gateway kiểm các mã
rồi dựng câu gợi mở theo loại vấn đề và bước hiện tại; không nhận lời giải tự do từ model. Backend
giữ kết quả này và chỉ thêm metadata tiến trình. Hai bản nháp khác nhau được xét riêng, không bị
ghi đè thành một hướng dẫn chung. Đây là hỗ trợ tự học, không phải điểm hoặc đáp án đã được chấm.

Gateway cần capability `diagnosed_hint_v1` và `staged_hint_v1`. Cell khởi động xuất từ source hiện tại đã gồm giao thức này:

```powershell
python scripts/append_kaggle_dual_gpu.py --export .private/ayo-startup.py
```

Với phiên T4 x2 đã nạp Qwen, có thể cập nhật riêng gateway mà giữ model và URL:

```powershell
python scripts/export_kaggle_tutoring_patch.py --export .private/ayo-hint-update-cell.py
```

Dán toàn bộ file vừa xuất vào một cell cuối notebook và chạy riêng cell đó, không Run All/restart.
Chờ `STAGED_HINT_READY`. Nếu session đã mất, khởi động lại bằng cell startup mới trước.
Gateway cũ từ chối trường mới sẽ trả lỗi cấu hình rõ ràng, không giả lập gợi ý thành công.
Giữ chặn TEST và không gửi đáp án/rubric riêng. Kiểm schema và mã nguồn không đủ chứng minh
chất lượng hướng dẫn hoặc ngăn mọi cách lộ lời giải; cần kiểm với Qwen thật trên câu hỏi, bản nháp,
yêu cầu xin đáp án và đổi bài/câu hỏi sau mỗi thay đổi prompt.

| Nhóm kiểm | Kết quả |
|---|---|
| Backend AI/engine/gateway, quyền tài liệu, buổi học và OpenAPI | 596/596 test đạt trong PostgreSQL test riêng; có TEST bắt đầu giữa lúc sinh, thu hồi quyền, không rò đáp án/rubric và lỗi model/index |
| Frontend | 53 file/356 test đạt; giữ công việc khi ngắt mạng, đọc lại khi server đã hoàn tất, không nhầm 403 thành lỗi mạng, hủy PDF blob khi chưa xác minh được quyền |
| Lint/build | Đạt; build còn cảnh báo bundle lớn hiện có. Test còn cảnh báo PDF.js/khóa phần tử trùng trong fixture, không coi là lỗi runtime đã được sửa |
| Model/migration | Không đổi model, train hoặc notebook; `makemigrations --check --dry-run` báo không có thay đổi |
| Triển khai | Nạp lại backend và riêng frontend; Nginx kiểm cú pháp đạt, location summaries đang dùng 145 giây; health qua frontend trả `ok`, Kaggle ready/summary_ready |
| UI sau sửa proxy | Công việc mới `bfe5766c-5bff-4c37-8a41-fba699693570`, trang 4–6: đủ 15/15 phần, 6 chunk, 2 bước sinh, 96,676 giây từ tạo đến hoàn tất; không bấm lại. Log POST trả 202 rồi 200, không có 504; API đọc lại qua 7/7 kiểm về nội dung/thời gian/nguồn/identity, không sửa kết quả đã sinh |

Log, bản OpenAPI xuất từ server đang chạy và ảnh `ui-after-proxy-fix.jpg` nằm riêng tại `.private/ayo/policy/`. Các ca lỗi model/index và quyền dùng test cô lập, không chủ động ngắt Kaggle, thu hồi quyền hoặc tạo bài kiểm tra trong LMS đang dùng. Chưa gọi đây là nghiệm thu UI hint với bài PRACTICE thật vì khóa hiện tại chưa có bài phù hợp; phần nối UI và demo tích hợp thuộc bước tiếp theo. Hạn chế diễn đạt của base model ở mục 9 vẫn giữ nguyên. Bước 8 hoàn thành trong phạm vi backend/API/vận hành; có thể sang bước 9. Không cần import notebook lại. Chưa thay đổi Evidence, commit, push hoặc tạo PR.
