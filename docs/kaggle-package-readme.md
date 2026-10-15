# Gói chạy W3 OHAYO

Gói source chứa cả sample A và luồng corpus A/B. Không chứa weights, dữ liệu DB, index, chunk text hoặc corpus PDF riêng tư. Mặc định embedding offline; lần đầu cần `--allow-download` và Internet để tải đúng revision.

Mở `notebooks/w3_retrieval_baseline.ipynb`, chỉnh đường dẫn gói source và input corpus/chunks; Run All từ kernel sạch. Notebook không vá source test và không dùng prediction fixture cho kết quả corpus.

Cài `pip install -r backend/requirements-w3.txt`. Nếu chỉ có PDF, chạy `backend/scripts/verify_w3_chunks.py` để tạo probe pypdf 27 PDF (số lượng thực phụ thuộc corpus); nếu dùng extraction runtime Docling, operator cung cấp manifest/catalog của đúng UUID DB. Hai loại snapshot khác nhau và không được ghép lẫn.

Xem `docs/reports/w3-ab-reproduce.md` và `docs/reports/w3-ban-giao-duong.md` trong repository để biết điều kiện nghiệm thu, lệnh chạy và phần việc còn lại. Sample 12 chunk không phải kết quả 100 QA. Đo offline không thay thế kiểm thử quyền Django.
