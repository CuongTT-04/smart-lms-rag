# Kiểm kê Corpus v1 — W2, ngày 07/10/2026

Kiểm tra tự động, chỉ đọc PDF/metadata gốc. PASS chỉ xác nhận tiêu chí kỹ thuật được kiểm tra, không xác nhận quyền sử dụng/phát hành tài liệu.

- PDF: 27; metadata JSON: 27.
- PASS: 27; FAIL: 0; metadata không có PDF: 0.
- Kiểm tra checksum, số trang, cặp file/định danh, giới hạn 20 MiB/100 trang, dấu hiệu PDF cần OCR/lỗi ký tự và thông tin nguồn/license.
- Source/license hiện là khai báo trong metadata, chưa có bằng chứng độc lập xác nhận cấp phép. Cần nhóm/giảng viên xác nhận phạm vi nghiên cứu nội bộ trước khi chia sẻ công khai.

| Môn | PDF | PASS | FAIL |
|---|---:|---:|---:|
| CNXHKH | 7 | 7 | 0 |
| KTCTMLN | 6 | 6 | 0 |
| THMLN | 14 | 14 | 0 |

## Các vấn đề phát hiện

Không phát hiện lỗi theo các tiêu chí tự động trên. Vẫn cần đối chiếu extraction với PDF gốc; không coi đây là đánh giá chất lượng OCR/Docling hoặc kiểm chứng nội dung học thuật.

## Bàn giao

Manifest dùng đường dẫn tương đối repo, checksum SHA-256 tính lại. Nhãn môn trong corpus không phải khóa UUID runtime của LMS. Không sửa PDF/metadata để làm kết quả kiểm kê đạt.
