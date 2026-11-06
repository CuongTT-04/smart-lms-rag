# W6 — bằng chứng tiếp nhận của Cường

Kết quả ngày 06/11/2026, cập nhật GPU ngày 07/11/2026; đây là phần evidence bổ sung, không ghi đè bằng chứng chuẩn bị đầu vào hoặc artifact của Dương. Xem `docs/qlora-receiver-report.md` để đọc kết luận và phân công.

- **Planned:** tiếp nhận QLoRA, kiểm config/checkpoint/log, bổ sung 250 mẫu B, ghép bộ 1.000, kiểm reload/resume và so sánh development.
- **Done:** kiểm receipt/manifest tất cả ZIP, tensor/state pilot 50 update; dựng lại 250 A từ PDF; xuất 250 B; kiểm lại 1.000 dòng, tokenizer và split; tái tính 40 output; kiểm gói GPU mới của Cường, đủ reload/resume và byte identity 40/40 output. Có báo cáo PDF hai trang và đồ thị nhận từ run thực đã xác thực.
- **Evidence:** `training-artifact-audit.json`, `member-a-audit.json`, `member-b-audit.json`, `group-audit.json`, `group-readback.json`, `cuong-gpu-result.json`, `cuong-gpu-artifact-audit.json`, `cuong-gpu-intake.json`, `cuong-output-identity.json`, `metrics.csv`, `training-metrics.csv`, `loss-curve.png`, `weekly-report.pdf`, `tests.json`, hai transcript `.txt`, `manifest.json`.
- **Problems:** máy kiểm không có CUDA. Cường đã chạy GPU riêng trên Kaggle và gói tải về đã được kiểm độc lập trên CPU; không ghi thành lần chạy CUDA tại máy kiểm. Data 1.000 còn review nội dung và đang hỗn hợp format; quyền nguồn chưa xác minh. Chất lượng adapter chưa chứng minh tăng; review hỗ trợ không phải chữ ký peer review.
- **Next week / phần chốt:** review theo ID/hash, thống nhất format trước W7, tổng hợp Evidence và PR/Issue khi nhóm xác nhận.

103 test QLoRA/receiver và 105 test instruction đạt trong lần kiểm CPU ghi tại đây. Một số integration test dùng Qwen ngẫu nhiên rất nhỏ trên CPU; không thay thế smoke/huấn luyện QLoRA 7B trên GPU. Artifact data/log thực được kiểm riêng, không suy từ mock.

Không đưa PDF nguồn, raw output, prompt/token IDs, dữ liệu train hay trọng số lên thư mục evidence công khai. Những file đó được chuyển riêng với checksum. Code hiện chưa được commit/push trong lần tiếp nhận; không tạo đường dẫn PR/Issue giả.
