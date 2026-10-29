# Minh chứng phần A

Ngày 28/10/2026. Người thực hiện/tự review: Vũ Nam Dương (A). B chưa duyệt cuối.

| Nội dung | Kết quả |
| --- | --- |
| Mẫu A | 250: 150 QA, 50 summary, 25 hint, 25 thiếu căn cứ |
| Môn | 100 THMLN, 75 KTCTMLN, 75 CNXHKH |
| Split nguyên nhóm | 193 train / 32 validation / 25 holdout; 14 component |
| Audit tokenizer thật | 250/250 đạt; không cắt ngầm; kiểm EOS/loss mask/padding |
| Test | 77 công cụ + 125 hồi quy đạt |
| GPU / model / training | Không dùng / không nạp / chưa chạy |
| B duyệt / review dữ liệu B | Chờ duyệt / chờ đầu vào |

**Đọc đầy đủ:** [dataset card v2.0](../../docs/dataset-card-v2.0.md) và [quy trình, hướng dẫn bàn giao](../../docs/instruction-input-review.md#11-bàn-giao-phần-a).

**Minh chứng:** `metrics.csv` lưu số đo; `test-results.json` lưu tổng hợp test/demo và hash log riêng tư; `manifest.json` lưu hash/kích thước các file minh chứng, mã nguồn và checksum ZIP riêng tư. Không chứa mẫu hoặc đoạn PDF. Demo là kiểm lại dữ liệu/tokenizer, không phải suy luận model.

ZIP tại `.private/instruction/handoff/member-a-handoff.zip` không đi theo Git, phải chuyển qua kênh riêng; hướng dẫn máy mới ở tài liệu tổng hợp. Không phát hành dữ liệu/adapter công khai. Quyền nguồn vẫn `DECLARED_NOT_VERIFIED`, tự review không thay B nghiệm thu.

**Giới hạn:** validation không có KTCTMLN; holdout chỉ KTCTMLN. Gộp A/B phải chia nhóm và audit lại; không dùng số liệu này để kết luận model trả lời tốt hơn. Chưa gửi file cho B, tạo/review PR, chốt tag hoặc nghiệm thu nhóm.
