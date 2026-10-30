# W5 — kết quả tích hợp kỹ thuật bộ instruction chung

> Kết luận sau tích hợp bản sửa B `2c142a3`: phần kỹ thuật được A chấp nhận sau review theo ủy quyền; không chờ thêm B để hoàn tất phần việc A. 77/46/125 test đạt. Xem `Evidence/W05/manifest.json#integration_review` và mục 13 tài liệu tổng hợp. Không tạo chữ ký/điểm PEER_REVIEW B hoặc đổi cờ nghiệm thu của package đã đóng băng.

> Cập nhật hiện hành 30/10/2026: A đã tiếp nhận và tái audit gói 500 mẫu, review 250 mẫu B, xác nhận ba bản sửa A và biên tập thêm 9 mẫu B trong bản mới. Manifest hiện hành `843b450ead5bc43958f60c146352f4f1b2f93b863eb46fc7f162ee2531b89bc5`, split 385/57/58; kiểm lại 500/500 đạt. Gói B ban đầu ở phần dưới được giữ làm lịch sử. B chưa review/chốt bản mới; group_release_ready và training_ready vẫn false. Xem mục 12 của `docs/instruction-input-review.md` và `Evidence/W05/manifest.json`.

Cập nhật29/10/2026. Đã hoàn thành các đầu ra kỹ thuật trước nghiệm thu:500 candidate, sửa đề xuất3 mẫu A, thống nhất kiểm nguồn/OCR, chia lại nguyên component, xuất SFT/tokenized/metadata và audit CPU từ file đã lưu. Gói A/B gốc và SELF_REVIEW giữ nguyên. Không công khai dữ liệu học liệu.

## Người phụ trách

- Vũ Nam Dương:250 mẫu A, công cụ biên soạn/xuất SFT và gói bàn giao A.
- Trần Tuấn Cường:250 mẫu B, hợp đồng/validator, tiếp nhận và kiểm định gói A, tích hợp/chia tập/audit bộ500 mẫu và tổng hợp evidence.
- Review chéo: Dương review phần B; Cường review phần A. Chỉ ghi hoàn thành khi có xác nhận trên đúng hash. Công cụ hỗ trợ không được tính là xác nhận của thành viên.

## Kết quả

| Hạng mục | Kết quả |
|---|---|
| Số mẫu |500, mỗi người250 |
| Task |300 QA,100 summary,50 hint,50 thiếu căn cứ |
| Môn |200 THMLN,150 KTCTMLN,150 CNXHKH |
| Split chung |385 train /57 validation /58 instruction holdout |
| Component nguồn/họ |27, không bị tách qua các tập |
| Phân bố môn | Cả ba tập có đủ ba môn và đủ bốn task |
| Kiểm máy | Schema/hash/source/page/excerpt/citation/benchmark/duplicate:0 finding |
| Tokenizer thật |500/500; prompt tối đa1533, completion kể format91, chuỗi1602 token |
| Readback |12 checksum payload + manifest, metadata/payload/token IDs/labels/padding/source checks tái tính đạt |
| Test |77 A +40 B +125 hồi quy đạt (kiểm lại30/10/2026) |
| Weights/GPU/training |Không tải weights, không dùng GPU, chưa train |

Tỷ lệ77%/11,4%/11,6% là phương án ứng viên giữ nguyên nhóm nguồn và đảm bảo đủ môn ở cả ba tập; không tuyên bố80/10/10 chính xác hoặc tối ưu toàn cục. Không nối hai split riêng của A/B. Holdout không dùng chỉnh cấu hình, không thay benchmark QA độc lập.

## Chỉnh sửa và tính tái lập

A00116 bỏ ý so sánh chưa có evidence; A00139 thêm context trang26 để khôi phục điều kiện; A00146 giữ riêng các trích đoạn/page, điều chỉnh citation và câu hỏi tương ứng ba context. Có revision-log gồm hash cũ/mới và provenance B hỗ trợ chỉnh. Giữ tác giả gốc A, nhưng chưa có A xác nhận bản chỉnh; SELF_REVIEW hash cũ không chuyển sang hash mới.

Normalizer nhóm dùng NFC rồi bỏ whitespace để chấp nhận khoảng trắng OCR, không bỏ/thay ký tự khác. Catalog tương thích giữ trạng thái dùng nội bộ, không tự xác nhận giấy phép. Snapshot hợp đồng nằm trong gói; tokenizer/library/revision/limits được suy ra từ snapshot W5. Sau rà soát độc lập đã sửa việc phụ thuộc cấu hình A đang thay đổi; regression tests từRED sangGREEN.

## Gói hoàn chỉnh về kỹ thuật

.private/w5/group-v0.2/package chứa candidates, ba split prompt/completion, ba split tokenized, metadata, plan, quality/tokenization reports, contract snapshot và manifest. verification.json ghi checksum manifest và kết quả mở lại. Gói nén .private/w5/group-v0.2/W5-group-technical-candidate.zip có checksum và biểu mẫu chốt review. Chỉ chuyển nội bộ, không đính kèm PR công khai.

## Hồ sơ review trên từng mẫu

1. Đã ghi nhận Dương xác nhận kết quả kỹ thuật chung theo thông tin Cường cung cấp. Cần lưu chi tiết review phần B và3 bản chỉnh A theo từng ID/hash vào biểu mẫu.
2. Cường xác nhận peer review phần A trên hash đang dùng. Điền peer-review-required.csv; mỗi tiêu chí0–2, tổng>=9, không0, correctness/grounding/behavior đều2. Nếu sửa dữ liệu, cần hash/review/audit mới.

acceptance.json để trống các xác nhận. Human peer accepted=0, group_release_ready=false, training_ready=false. Đây là cách ghi đúng trạng thái, không phải lỗi kiểm kỹ thuật. Kết quả rà soát bằng công cụ không thay cho xác nhận review của Dương. Chỉ sau các xác nhận thực tế và review PR mới chốt tag w05 hoặc ghi W5 nghiệm thu toàn bộ.

Minh chứng W5 được tổng hợp trong báo cáo này và Evidence/W05/. Issue và PR cho nhiệm vụ dataset cần gắn milestone Tuan5; không dùng Issue7/PR8 về Ayo thay cho nhiệm vụ dataset.

## Quyết định kỹ thuật của Trần Tuấn Cường

Trần Tuấn Cường xác nhận chọn bộ đã audit làm baseline nghiên cứu nội bộ để chuẩn bị W6. Xem docs/weekly/W5/quyet-dinh-chot-ky-thuat.md và data/instruction/w5/project-owner-decision.json. Việc chọn baseline và xác nhận kết quả kỹ thuật của Dương được ghi nhận riêng với hồ sơ review từng mẫu và nghiệm thu học thuật. Artifact gốc giữ nguyên, không phát hành công khai.

## Xác nhận của Vũ Nam Dương — cập nhật29/10/2026

Theo thông tin Trần Tuấn Cường cung cấp, Vũ Nam Dương đã xác nhận kết quả thực hiện phù hợp. Người xác nhận: Vũ Nam Dương; người chuyển thông tin xác nhận: Trần Tuấn Cường. Xác nhận được ghi nhận ở mức kết quả kỹ thuật chung, không thay đổi người thực hiện theo phân công. Chưa có bảng điểm review theo từng ID/hash kèm theo xác nhận này; các biểu mẫu đó và trạng thái nghiệm thu trong gói đóng băng được theo dõi riêng.

## Sửa audit split — 30/10/2026

Checker release kiểm riêng ba cặp payload/sidecar theo tên split, số dòng và toàn bộ ID trong split plan; chặn tráo nguyên file hoặc từng mẫu kèm sidecar. Bổ sung4 test, bộ B đạt40 test. Log kiểm lại ở Evidence/W05/test-results.txt; gói dữ liệu đã bàn giao giữ nguyên.
