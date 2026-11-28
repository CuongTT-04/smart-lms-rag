# Báo cáo W09 — 28/11/2026

**Mục tiêu:** Guardrails, quyền truy cập tài liệu, chống lộ nội dung/citation sai. Nền Admin/xác minh email là Chặng 2, chốt độc lập. Đây là W9 thực tế theo yêu cầu giảng viên.

**Trạng thái: ĐẠT TOÀN BỘ CỔNG TỰ ĐỘNG & 36 CA LIVE — CHỜ DUYỆT THÀNH VIÊN (READY_FOR_REVIEW).** Sau bản vá bật structured QA protocol cho API stateless và chuẩn hóa thứ tự trang cùng tài liệu, lượt chạy lại trọn bộ 36 ca live trên `tuned_rag` đạt **36/36**, Chat QA đạt **17/17 (100%)** cả accuracy lẫn coverage (trước vá là 34/36, 57,14% / 47,06%). Còn chờ thành viên đối chiếu ký duyệt, chạy demo UI thu hồi→mở lại citation và kiểm SMTP thật.

| Planned | Done | Evidence | Problems | Next week / việc tiếp theo |
| --- | --- | --- | --- | --- |
| Kiểm quyền và thu hồi xuyên suốt LMS | Chặn toàn bộ 17 ca trái lớp/khóa, nguồn gỡ/nháp, phiên bản cũ, thu hồi trước/sau model & lịch sử; 0 lộ dữ liệu | checks.json; GR-04, 07–17, 22, 32; 1.055 test backend | Demo thu hồi rồi mở lại citation trên UI thật chưa quay ở lượt này | Kiểm tay trên trình duyệt với dữ liệu thử; giữ kiểm quyền server ở mọi đường đọc |
| Kiểm guardrails và citation | Chạy lại trọn bộ 36/36 ca đạt; chấm 17/17 nhận định chat đạt (100% ≥ 90%), 17/17 nhận định summary có căn cứ | citation-review.csv; GR-01–36 (`live-post-patch`) | Summary chỉ có nguồn theo phạm vi (`input_range`); review do trợ lý thực hiện, chờ thành viên ký duyệt | Thành viên kiểm chéo ledger; tiến tới W10 thanh toán & bảo mật nâng cao |
| Tích hợp Admin và bảo mật phiên | Ghép PR #27 (`f04c7df`), giữ 401/403 sau model, kiểm toàn bộ luồng auth/email/duyệt/LEGACY/Admin cuối; smoke 4 tab Admin | 1.055 backend đạt + 5 skip; 413 frontend; ảnh Admin | SMTP thật chưa chạy (mới test locmem) | Chạy thử SMTP thật cho hộp thư thường và `.edu.vn` |
| Đóng gói bằng chứng | Metrics, ma trận 36/36, review từng ý, ảnh, manifest, lệnh tái chạy và giữ nguyên lịch sử lượt trước vá | README; metrics.csv; test-results.txt; manifest.json | Chưa commit/push/PR sau lượt cập nhật cuối | Review chéo PR, merge `main` và đóng Issue #23–#26 |

Kết quả citation chat (`live-post-patch`): **accuracy 17/17 (100%)**, **coverage 17/17 (100%)**, vượt mục tiêu ≥ 90% của `NFR-29`. Trong 4 câu chat có đáp án (`GR-01`, `GR-02`, `GR-18`, `GR-31`), 4/4 trả lời đúng nguồn, 0 lỗi, 0 từ chối sai; 2 câu thiếu căn cứ (`GR-03`, `GR-11`) đều trả `INSUFFICIENT_EVIDENCE`. Summary có 17/17 ý có căn cứ trong phạm vi đầu vào nhưng chưa có liên kết từng ý–nguồn nên không cộng vào tỷ lệ chat. Thử nghiệm đối chứng ngoài fixture (5 trang Mạng máy tính mới) đạt 12/12 citation đúng trang và 31/35 (88,6%) ý ngữ nghĩa trên nguồn không dấu, xác nhận bản vá không overfit vào fixture.

Không quan sát lộ dữ liệu trái quyền trong 17 ca từ chối tổng hợp. Tín hiệu health tại lượt chạy cuối xác nhận hai replica `tuned_rag` khớp 392 tensor adapter đã khóa, config và source gateway khớp.

Kiểm bổ sung: backend **1.055 PASS / 1.060** (5 skip parser tùy chọn), upload/worker **27/27**, công cụ preflight/so sánh **28/28**, frontend **413/413** (lint/build đạt, cảnh báo chunk lớn), `makemigrations --check` và `manage.py check` sạch.

Nguồn số liệu: [checks.json](logs/checks.json), [ledger nhận định](logs/citation-review.csv), [test-results](test-results.txt). Không huấn luyện lại model, không sửa benchmark/holdout cũ và chưa commit/push.
