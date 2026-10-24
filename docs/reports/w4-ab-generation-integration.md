# W4 — Tích hợp LLM sinh câu trả lời có citation

Cập nhật: 24/10/2026. Báo cáo tổng hợp tích hợp, bằng chứng kiểm chứng và phần còn thiếu; các số đo dưới đây thuộc những lần chạy đã ghi nhận, không phải lần chạy mới khi dọn tài liệu.

## Phạm vi và kiến trúc

- Backend dùng PostgreSQL; unit test dùng mock/dummy DB, integration test dùng PostgreSQL test riêng.
- Upload PDF → EXTRACT → INDEX tự động → BGE-M3 CPU → snapshot FAISS. Snapshot được chuyển nguyên tử; backend tự nhận chỉ mục mới. Chỉ mục không tự công bố học liệu hoặc cấp quyền đọc.
- API kiểm tra phạm vi học liệu và quyền trong PostgreSQL trước truy xuất và sau generation. Citation ràng buộc document/version/trang; đoạn trích lấy từ chunk có quyền. PDF nguồn được mở với `expected_version_id`.
- `GenerationBridge` chuyển context đã whitelist sang contract generation và kiểm tra references thuộc nguồn thực sự đưa vào prompt sau cắt token. Backend gọi Qwen trên Kaggle qua HTTPS có token bằng `apps.ai.remote.generate_answer`; cấu hình dùng tiền tố `AI_*`.
- Chế độ kiểm tra chặn trợ lý theo policy server; gợi ý bài ôn tập chỉ nhận context đề bài được phép. Test double kiểm logic không thay đánh giá chất lượng model thật.

## Phục vụ model và giao diện

Profile online hiện dùng hai bản Qwen2.5-7B NF4 trên GPU 0/1, luân phiên tối đa hai lượt sinh đồng thời; yêu cầu thứ ba nhận trạng thái bận. Mỗi câu hỏi dùng một GPU. CPU PyTorch intra-op tối đa 2 thread, inter-op 1 khi đặt được; tokenizer parallelism tắt.

Profile có context 6144, input 3584, output tối đa 1024 token và timeout generation 90 giây. HTTP backend tối đa 100 giây, proxy chat 145 giây, frontend 150 giây. Lỗi hết output hoặc đầu ra chưa hợp lệ không được phát hành như câu trả lời hoàn chỉnh. Chưa có số đo chứng minh tăng tốc một yêu cầu.

Trợ lý hiển thị từng lượt hỏi/đáp, trạng thái chờ và hiệu ứng hiện từ sau khi HTTP hoàn tất. Hover/focus citation mở đoạn trích; nguồn phía dưới vẫn mở PDF để đối chiếu. Like/dislike có thể đổi hoặc bỏ, chỉ chủ câu trả lời được đánh giá; PostgreSQL lưu request ID, owner và rating, không lưu nội dung hội thoại trong bảng feedback. Hội thoại hiện giữ trong bộ nhớ giao diện, chưa có lịch sử phiên bền vững hoặc memory nhiều lượt đưa vào LLM.

## Bằng chứng tích hợp đã ghi nhận

| Kiểm chứng | Kết quả và giới hạn |
| --- | --- |
| Upload tự lập chỉ mục | PDF thử qua JWT HTTP: EXTRACT/INDEX đến READY trong 61,32 giây. Đã soft-remove PDF thử; không đổi công bố nguồn gốc. Hai phiên bản ban đầu có 12 chunk, preflight không lệch provenance. |
| RAG tài liệu DATA-17 | API thật HTTP 200/ANSWERED, citation trang 11 và 1 đúng published version; PDF nguồn HTTP 200. Probe 39,16 giây gồm mở PDF. Còn lẫn tiếng Anh/lỗi đầu từ; chưa nghiệm thu factuality hoặc ngôn ngữ. |
| Citation và feedback | Hai excerpt dài 1673 và 1818 ký tự; PDF HTTP 200. LIKE → DISLIKE → null đều HTTP 200 và đọc lại PostgreSQL khớp. |
| Health Kaggle sau chuyển profile | HTTP 200, ready=true, replicas=2, profile input/output/timeout 3584/1024/90. Backend kích hoạt `kaggle-dual-gpu.json`. |
| Câu “Chu kì xử lý lệnh CPU là gì?” | Qua frontend Nginx → backend → PostgreSQL/BGE/FAISS → Qwen thật: HTTP 200/ANSWERED, citation trang 7, 8, 9; PDF HTTP 200. Lượt đầu 58,75 giây có cold load retrieval sau restart backend. |
| Hai câu khác nhau đồng thời | max in_flight=2; câu CPU gốc HTTP 200 sau 46,95 giây; câu biến thể bị HTTP 503/INVALID_GENERATION sau 31,09 giây. Wall time 48,17 giây. Lỗi đầu ra này chưa được sửa. |
| Hai lượt cùng câu CPU đồng thời | Cả hai HTTP 200/ANSWERED, citation trang 7, 8, 9; thời gian 60,56 và 60,43 giây, wall time 61,39 giây, max in_flight=2. Đây là kiểm concurrency, không thay bộ đánh giá chất lượng. |

Artifact kiểm chứng riêng tư trong `backend/.private/` gồm `auto-index-live-result.json`, `chat-ux-live-result.json`, `dual-gpu-cpu-answer.json`, `dual-gpu-live-varied-questions.json` và `dual-gpu-live-same-question.json`. Không đưa token hoặc nội dung riêng tư lên Git. Chưa đo trực tiếp phần trăm sử dụng GPU; không suy ra mọi câu hỏi đều đạt từ health hoặc concurrency.

Các lượt kiểm thử kỹ thuật gần nhất trước khi tổng hợp: 42 test backend AI trên PostgreSQL test riêng; 45 test script/notebook/helper/CLI; frontend 328 test/51 file khi giới hạn `--maxWorkers=2`, lint và Docker build đạt. Lượt frontend mặc định worker trước đó có hai timeout 5 giây ở ClassroomNavigation/VideoQuestionDialog trong lúc các kiểm thử khác dùng CPU; toàn suite chạy lại với hai worker đạt, chưa kết luận tuyệt đối nguyên nhân timing.

## Tái lập và vận hành

Dùng các hướng dẫn hiện hành để cấu hình và khởi động:

- [Tự lập chỉ mục học liệu](../automatic-document-indexing.md).
- [Khởi động inference Kaggle](../kaggle-inference-startup.md).
- [Phục vụ hai GPU và đồng bộ endpoint](../kaggle-dual-gpu-serving.md).

Preflight kiểm DB/index và provenance, không tự chứng minh model đang online:

```powershell
docker compose exec -T backend python manage.py check_w4_chat_runtime
```

Smoke HTTP dùng UUID và tài khoản có quyền thật. Copy [fixture mẫu](../../data/fixtures/w4-chat-smoke.example.json) ra thư mục riêng tư rồi chỉnh case; đặt access token trong biến môi trường `W4_SMOKE_TOKEN`:

```powershell
.\.venv\Scripts\python.exe scripts/check_w4_chat_integration.py --base-url http://localhost:8000 --cases .private/w4-smoke-cases.json --output .private/w4-smoke-results
```

Các lệnh kiểm tra kỹ thuật liên quan:

```powershell
docker compose exec -T backend python manage.py test tests.ai --noinput
docker compose exec -T backend python manage.py test tests.documents.test_upload tests.documents.test_worker --settings=tests.documents_settings --noinput
npm --prefix frontend test -- --maxWorkers=2
npm --prefix frontend run lint
npm --prefix frontend run build
```

Kịch bản nghiệm thu cần gồm câu hỏi có căn cứ và mở citation đúng phiên bản/trang; hỏi ngoài nguồn; gợi ý bài PRACTICE; chặn AI trong TEST; thu hồi nguồn/đổi quyền giữa generation. Ghi rõ ca dùng model thật, test double hoặc thao tác browser; HTTP thành công không tự chứng minh factuality. Chưa có screenshot/video nghiệm thu UI trong các probe trên.

## Dữ liệu và tiêu chí W4 còn thiếu

Source generation bàn giao từ nhánh Dương tại commit `0e08a08`. Bộ canonical gồm `qa_baseline.json` 100 câu và `qa_additions.json` 50 câu. Không cộng thêm bộ 25 câu nháp Cường thành 175 câu. Đóng góp và review người phải đối chiếu metadata bàn giao; source notebook hoặc cấu hình `FULL_BASELINE=True` không chứng minh đã có predictions.

Để kết luận hoàn tất tiêu chí “Tích hợp LLM sinh câu trả lời có citation; bộ test factuality”, còn cần:

1. Nhận/kiểm ZIP baseline `20261023T105403Z-bac2de31.zip` và `factuality-results` thật, kiểm checksum và đủ 150 ID; chấm lại từ predictions thực.
2. Hoàn tất human peer review và scores có người chấm. Lexical screening, source audit và mock provider không thay xác nhận factuality.
3. Phân tích/sửa hoặc ghi nhận giới hạn INVALID_GENERATION của câu CPU biến thể; đánh giá thêm chất lượng tiếng Việt và độ đúng citation trên nhiều câu hỏi.
4. Thực hiện và lưu minh chứng demo UI đầy đủ với model thật, học liệu đúng quyền và các tình huống policy.

Checkpoint phải được lưu và gắn Input; Kaggle cần session GPU đang chạy để có endpoint. Khởi động lại session không yêu cầu tạo lại chỉ mục FAISS. Chưa xác nhận toàn bộ W4 hoàn tất từ những probe riêng lẻ trên.
