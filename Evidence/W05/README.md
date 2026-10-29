# Minh chứng tuần 05: phần A và kết quả tích hợp

## Kết quả theo phạm vi

| Phạm vi | Kết quả | Căn cứ |
| --- | --- | --- |
| A, trước tích hợp | 250 mẫu tự review; SFT 193/32/25; 14 component; audit tokenizer thật 250/250 đạt | `history/member-a/`, gói bàn giao riêng tư A |
| B, giai đoạn draft | 250 mẫu; kiểm nguồn/citation/tokenizer; chưa peer acceptance | `history/member-b/`, báo cáo chất lượng B |
| Nhóm, theo báo cáo B ngày 29/10/2026 | 500 candidate; split 385/57/58; 27 component; cả ba môn và bốn task trong từng tập | `group/group-report.json`, `group/verification.json` |
| Test trong báo cáo tích hợp B | 77 công cụ A, 36 công cụ B, 125 hồi quy runtime đạt | `group/tests.json`; log được tham chiếu nhưng không có trong checkout nếu Git bỏ qua |
| Huấn luyện / peer acceptance | Chưa huấn luyện; chưa nghiệm thu theo từng mẫu của hai thành viên | Contract và báo cáo nhóm |

Kết quả 500 mẫu là báo cáo tích hợp do B bàn giao, không phải tự động coi đã tái kiểm gói dữ liệu riêng tư trên máy A sau merge. Ba bản sửa A được ghi nhận cho `W5_A_00116`, `W5_A_00139`, `W5_A_00146`; không ghi đè bản A đã audit hoặc tự cấp review trên hash mới.

## Đọc và đối chiếu

- [Dataset card v2.0](../../docs/dataset-card-v2.0.md): phần A và cập nhật tiếp nhận.
- [Dataset card bộ chung](../../docs/dataset-card-v2.1-group-candidate.md): candidate 500 mẫu.
- [Quy trình và hướng dẫn bàn giao A](../../docs/instruction-input-review.md).
- [Kết quả tích hợp của B](../../docs/weekly/W5/ket-qua-tich-hop-w5.md) và [tiếp nhận A](../../docs/weekly/W5/tiep-nhan-member-a.md).

`metrics.csv` gộp số đo với scope riêng cho A, B và nhóm. `test-results.json` giữ báo cáo nhóm B cùng kết quả phần A trước tích hợp. `manifest.json` đối chiếu file hiện có sau giải quyết xung đột; các manifest gốc được giữ nguyên nội dung trong `history/` và chỉ có giá trị cho snapshot tương ứng.

## Giới hạn và tiếp nhận tiếp

Kiểm hồi quy sau gộp trên máy A: **77 test công cụ A, 36 test công cụ B, 125 test runtime và 338 test giao diện đạt**. Chi tiết tại `merge-validation.json`. Test B dùng pypdf 6.10.0 trong môi trường riêng; chưa chạy DB integration hoặc tái audit gói nhóm riêng tư của B.

- Gói A: `.private/instruction/handoff/member-a-handoff.zip`, checksum trong receipt; không đi theo Git. Gói nhóm của B ở `.private/w5/group-v0.2/package` trên máy B, không suy ra đã có trên máy A khi merge.
- Gói A giữ nguyên split cũ: validation thiếu KTCTMLN, holdout chỉ KTCTMLN. Báo cáo bộ chung của B có độ phủ ba môn tốt hơn; hai phạm vi không thay thế lịch sử của nhau.
- Quyền nguồn vẫn chưa được xác minh độc lập; chỉ nghiên cứu nội bộ, không phát hành PDF/candidate/token IDs/adapter công khai.
- Code chatbot của B cũng được merge; audit nguồn đã khóa trong gói A là lịch sử, không tự áp dụng cho runtime mới. Dùng bản đóng băng trong ZIP để kiểm lại gói A; bộ chung cần đúng artifact/hash B đã bàn giao.
- Chưa tạo merge commit, push hoặc tag trong lượt giải quyết xung đột. Merge không thay cho peer review hay nghiệm thu nhóm.
