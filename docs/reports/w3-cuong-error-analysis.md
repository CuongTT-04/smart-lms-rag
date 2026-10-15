# Lỗi và giới hạn phần W3 của Cường

## Các lỗi đã bắt và xử lý

| Lỗi/điều kiện | Hành vi đã kiểm chứng |
|---|---|
| Unicode tổ hợp, newline khác nhau, câu dài không dấu cách | NFC/LF, giữ offsets và coverage; giới hạn token và tiến vị trí |
| UUID/checksum/page count extraction lệch DB, nguồn gỡ | Không build artifact gắn sai nguồn |
| Chạy lại cùng input/config | ID/chunks/checksum không trùng và ổn định |
| JSONL bị thay nội dung sau ghi manifest | load_catalog từ chối checksum sai |
| Scope rỗng, tài liệu/classroom khác khóa, enrollment thu hồi | Không mở rộng quyền; không gọi provider khi scope rỗng |
| Source draft/unpublished/removed hoặc latest chưa công bố | Student không nhận nguồn; owner preview phải explicit |
| Quyền hoặc trạng thái công bố đổi trong lúc search | Revalidate và chặn kết quả cũ |
| Provider trả unknown/duplicate ID, NaN, ID list/dict hoặc int score quá lớn | DocumentError kiểm soát, không TypeError/OverflowError không xử lý |
| Tokenizer revision mutable | Command bắt SHA commit 40 ký tự trước tải model |
| Test W2 cũ chặn owner tải gốc | Cập nhật test theo hành vi đã được người dùng chốt: owner tải gốc, protected student bị chặn |

## Giới hạn chưa được loại bỏ

- Chưa nhận real embedding/index/retriever A, vì vậy không có top-k thực hoặc Recall. Provider fixture chỉ kiểm chứng ranh giới quyền và output.
- Chưa có peer review dataset, chưa ghép thành 100 QA nhóm và chưa kiểm chứng toàn bộ nhãn Dương. 50 QA phần B vẫn pending review.
- Probe 27 corpus dùng pypdf; probe Docling runtime riêng có một PDF. Hai số chunk không được coi là cùng parser/cùng generation.
- Chưa tự nối indexing vào background worker hoặc thêm persistent indexing receipt; không mark READY giả.
- Bốn test concurrency PostgreSQL chưa chạy; SQLite không chứng minh race ở mọi mức isolation.
- Chưa có video demo query top-k thật hoặc báo cáo Recall cuối. Cần phần Dương trước khi ghi các output này là Done.

## Bước tiếp theo

Nhận interface/index và manifest A; đối chiếu catalog/model/config; chạy query có scope trên hai khóa; đo Page Recall theo từng QA và phân tích miss thật. Review chéo và frozen snapshot trước báo cáo 17/10. Các lỗi tokenizer/chunk/quyền đã có regression test để giữ behavior khi tích hợp.
