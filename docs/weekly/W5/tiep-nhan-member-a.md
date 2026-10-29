# Tiếp nhận phần A — 29/10/2026

Commit bàn giao ce431c5, ZIP khớp SHA256 trong receipt: 8ec51ffbbb80f810d0fe64ac9366d0dfa9862c2a6f8b3ff4a937ee53ab0d8a6a. 163 file payload khớp manifest. Giữ nguyên ZIP/receipt/candidate/SELF_REVIEW và gói SFT; chạy kiểm trên bản giải nén mới trong .private/w5/intake-a/ce431c5/received.

Kiểm CPU tái tính 250 mẫu: 10 checksum SFT, nguồn/trang, hash review, split, tokenizer/template/EOS, labels và padding đều đạt. Candidate/review gốc khớp đầy đủ với metadata SFT. Import công cụ từ gói đã đối chiếu với Git; trên workspace hiện tại77 test A,27 test B và125 hồi quy đều đạt. Không dùng GPU/weights, chưa train.

Phần tiếp nhận do Trần Tuấn Cường phụ trách đã được hỗ trợ rà soát bằng công cụ trên250 mẫu, gồm50 summary,25 hint,25 refusal. Đề nghị sửa3 mẫu, không xác nhận247 mẫu còn lại đã được con người ACCEPT:

| ID | Hash hiện tại | Đề nghị |
|---|---|---|
| W5_A_00116 | 2165b8832c3972980560887a837d3711d85b5845f5377a1cd1a6877965e495bc | Bổ sung evidence về trọng thương hoặc bỏ ý so sánh chưa có căn cứ kèm theo |
| W5_A_00139 | 84662dc7c820dc442e0258ab21c8729dbdf54dfbd73b5a9ae84f9dae93c34810 | Khôi phục đầy đủ điều kiện của câu bị ngắt giữa trang PDF26–27 |
| W5_A_00146 | 3c9a16310ed06987ca4e00b95be7fb3915fd0a2ac84438d370dfa56ac3f5e7ec | Bổ sung phần điều kiện còn thiếu hoặc chuyển citation về evidence thực sự hỗ trợ |

Trang được nhắc là trang vật lý1-based. Không tự ghép hai trang rồi gán một page_number; giữ riêng context/page và citation đúng. Mẫu đổi phải tính hash, SELF_REVIEW lại, xuất gói mới và audit lại; không sửa bản đã đóng gói.

62 mẫu/66 context không qua phép so nguồn của B do khoảng trắng OCR; tất cả khớp chính xác sau NFC và bỏ whitespace như validator A. Đây là khác biệt quy tắc so sánh, không phải62 lỗi kiến thức hoặc text bịa. Giữ cả strict report và source-normalization-audit riêng tư để thống nhất normalizer trước audit500.

Validation A vẫn thiếu KTCTMLN; holdout chỉ KTCTMLN. Không nối split A/B. Hiện có500 draft trên máy B, nhưng chưa có review A cho B và human peer acceptance chung; chưa khóa split hoặc tag/release nhóm.

Gói trả nhận xét: .private/w5/intake-a/ce431c5/member-a-review-return.zip. Nhận xét sơ bộ bằng công cụ được lưu riêng trong nhật ký kỹ thuật (loại `AI_REVIEW`), peer-review-template.csv để B xác nhận/điền điểm thật, không đưa template trống vào exporter. Chưa ghi PEER_REVIEW ACCEPT, không sửa SELF_REVIEW của A. Nguồn chỉ nghiên cứu nội bộ theo quyết định đã ghi, không phát hành công khai. ZIP riêng tư; bản nhận xét không gửi ra ngoài tự động.

## Cập nhật bộ chung29/10/2026

Đã tạo và audit CPU500 candidate, split385/57/58 đủ ba môn trong từng tập,3 bản sửa A có hash mới. Xem docs/weekly/W5/ket-qua-tich-hop-w5.md. Gói gốc giữ nguyên; peer confirmations vẫn cần thật, chưa train hoặc nghiệm thu nhóm.

## Xác nhận của Vũ Nam Dương — cập nhật29/10/2026

Theo thông tin Trần Tuấn Cường cung cấp, Vũ Nam Dương đã xác nhận kết quả thực hiện phù hợp. Người xác nhận: Vũ Nam Dương; người chuyển thông tin xác nhận: Trần Tuấn Cường. Xác nhận được ghi nhận ở mức kết quả kỹ thuật chung, không thay đổi người thực hiện theo phân công. Chưa có bảng điểm review theo từng ID/hash kèm theo xác nhận này; các biểu mẫu đó và trạng thái nghiệm thu trong gói đóng băng được theo dõi riêng.
