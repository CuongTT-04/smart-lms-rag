# W05 — bằng chứng tiến độ B,28/10/2026

Đây là công cụ và250 draft B, chưa nghiệm thu toàn bộ W5. Xem docs/weekly/W5/quality-report.md và scripts/w5/README.md. Tests27; kiểm nguồn/citation/hash/leakage và tokenizer thật cho250 draft; không có Qwen generation/training trong bước này.

Human review=0, eligible=0, train=0. Chưa có A candidate/exporter hoặc full split/release. Chuẩn bị draft trước peer review là staging theo yêu cầu tiếp tục của người dùng, không thay gate A. Không tạo PR/tag/commit giả. HEAD trong manifest chỉ là base trước working-tree W5.

Report hiện hành member-b-draft-*.json, profile và tokenization-report.json. Report pilot cũ giữ cho lịch sử, không làm chứng cứ250. Findings CSV chỉ có header khi lần kiểm hiện hành không có findings; không có nghĩa con người đã phê duyệt. Character5-gram không bao quát mọi paraphrase, CPU mask reference không thay trainer W6.

Gói .private/w5/handoff/member-b-drafts-v0.2.zip chứa trích đoạn nội bộ; không commit lên kho công khai. HTML để đọc, CSV để review. Test-results/metrics/manifest ghi số liệu và checksum thực.

## Tiếp nhận A ngày29/10/2026

Đã nhận250 draft A, kiểm ZIP163 file và tái kiểm CPU gói SFT250 mẫu. Kết quả rà soát sơ bộ bằng công cụ đề nghị sửa3 mẫu; human peer approval vẫn chờ. Xem docs/weekly/W5/tiep-nhan-member-a.md và Evidence/W05/intake-a. Các câu “chưa có A” ở phần28/10 là lịch sử. Chưa ghép split/release500 hoặc train.

## Bộ chung đã chuẩn bị

Evidence/W05/group có báo cáo500 candidate, source/group split/token readback và tests77/36/125. Xem docs/weekly/W5/ket-qua-tich-hop-w5.md; peer acceptance chưa được cấp. Không đưa ZIP/token IDs/PDF/candidate riêng tư lên GitHub công khai.

## Kiểm lại30/10/2026

Đã sửa ràng buộc ID theo từng file split trong CLI audit; test tráo file và tráo mẫu kèm sidecar bị chặn. Kết quả mới:77 test A,40 test B,125 test runtime (242 tổng), exit0. Xem group/tests.json và các log group/*.txt; log tiếp nhận cũ được giữ nguyên nội dung dưới tên intake-a/*.txt để Git theo dõi. Không thay gói dữ liệu đóng băng.
