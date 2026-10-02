# Dataset card cho hệ thống quản lý học tập thông minh tích hợp mô hình ngôn ngữ lớn tinh chỉnh và kỹ thuật RAG

## 1. Tổng quan về dataset

| Loại | Thông tin |
|---|---|
| Tên dataset | SmartLMS AI-RAG Course Corpus |
| Phiên bản | v1.0 |
| Ngày tạo | 2026-10-01 |
| Mục đích | Cung cấp nguồn tài liệu môn học cho hệ thống LMS tích hợp trợ lý AI |
| Ngôn ngữ | Tiếng Việt |
| Định dạng file | PDF |
| Số lượng môn học | 3 |
| Số lượng tài liệu | 27 |

---

## 2. Mục đích sử dụng

Dataset này được xây dựng nhằm cung cấp nguồn tài liệu môn học cho hệ thống LMS tích hợp AI Assistant.

Corpus được sử dụng cho:

- Document ingestion (tích hợp tài liệu)
- Text extraction (trích xuất văn bản)
- Chunking (chia nhỏ văn bản)
- Embedding (tạo vector biểu diễn)
- Vector retrieval (tìm kiếm vector)
- RAG-based question answering (hệ thống trả lời câu hỏi dựa trên RAG)
- Evaluation of answer correctness (đánh giá độ chính xác của câu trả lời)
- Evaluation of citation accuracy (đánh giá độ chính xác của trích dẫn)

---

## 3. Danh sách môn học và số lượng tài liệu

| ID môn học | Tên môn học | Số lượng tài liệu | Ngôn ngữ |
|---|---|---:|---|
| CNXHKH | Chủ nghĩa xã hội khoa học | 7 | Tiếng Việt |
| KTCTMLN | Kinh tế chính trị Mác-Lênin | 6 | Tiếng Việt |
| THMLN | Triết học Mác-Lênin | 14 | Tiếng Việt |
| **Tổng cộng** | | **27** | |

---

## 4. Nguồn dữ liệu và quyền sử dụng

Tài liệu thuộc về các môn học được thu thập từ các nguồn chia sẻ mang tính chất không chính thức, do vậy:
- Bản quyền nội dung hoàn toàn thuộc về các tác giả hoặc nhà xuất bản gốc.
- Tập dữ liệu này được cung cấp **cam kết chỉ sử dụng cho mục đích nghiên cứu và học tập phi thương mại**.

---

## 5. Cấu trúc thư mục dữ liệu

Corpus được tổ chức theo từng môn học:

```text
data/
└── corpus/
    │
    ├── CNXHKH/
    │   ├── ch01.pdf
    │   ├── ch02.pdf
    │   ├── ch03.pdf
    │   ├── ch04.pdf
    │   ├── ch05.pdf
    │   ├── ch06.pdf
    │   ├── ch07.pdf
    │
    ├── KTCTMLN/
    │   ├── ch01.pdf
    │   ├── ch02.pdf
    │   ├── ch03.pdf
    │   ├── ch04.pdf
    │   ├── ch05.pdf
    │   ├── ch06.pdf
    │
    └── THMLN/
        ├── ch01.pdf
        ├── ch02.pdf
        ├── ...
        ├── ch14.pdf
```

### Quy ước đặt tên

| Pattern           | Ý nghĩa                     |
| ----------------- | --------------------------- |
| `ch01.pdf`        | Chương 1                    |
| `ch02.pdf`        | Chương 2                    |
| `...`             | Các chương tiếp theo        |

Tên môn học đầy đủ được lưu trong metadata thay vì sử dụng tên dài trong tên file.

---

## 6. Document Metadata

Mỗi tài liệu được định danh bằng các metadata:

| Loại metadata | Mô tả                    |
| ------------- | ------------------------ |
| `course_id`   | ID môn học               |
| `course_name` | Tên môn học              |
| `chapter_id`  | Số chương                |
| `document_id` | ID duy nhất của tài liệu |
| `file_name`   | Tên file                 |
| `file_type`   | PDF/DOCX/PPTX...         |
| `source`      | Nguồn tài liệu           |
| `page_count`  | Số trang                 |
| `license`     | Quyền sử dụng            |
| `checksum`    | SHA-256 của file         |
| `title`       | Tiêu đề của chương       |
| `generated_at`| Thời gian tạo metadata   |

Ví dụ:
```json
{
  "course_id": "CNXHKH",
  "course_name": "Chủ nghĩa xã hội khoa học",
  "chapter_id": 1,
  "document_id": "CNXHKH-ch01-abcdxyz",
  "file_name": "ch01.pdf",
  "file_type": "PDF",
  "source": "Private shared drive (Bộ GD&ĐT materials, restricted)",
  "page_count": 24,
  "license": "All rights reserved by authors; owned by Bộ Giáo dục và Đào tạo; permission for internal research only",
  "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "title": "NHẬP MÔN CHỦ NGHĨA XÃ HỘI KHOA HỌC",
  "generated_at": "2026-10-01T12:00:00Z"
}
```
Các metadata phục vụ cho việc quản lý, tìm kiếm và tích hợp tài liệu vào hệ thống LMS. Chúng cũng được sử dụng để kiểm tra chất lượng dữ liệu và đảm bảo tính nhất quán của corpus. Mỗi file PDF đi kèm với một file JSON metadata có cùng tên (ví dụ: `ch01.pdf` và `ch01.json`), tất cả được lưu trong cùng thư mục môn học.

---

## 7. Chất lượng dữ liệu

Việc kiểm tra chất lượng dữ liệu nhằm đảm bảo các tài liệu trong corpus đáp ứng các tiêu chuẩn về khả năng trích xuất văn bản, tính nhất quán của metadata và độ chính xác của nội dung.

### Các yêu cầu kiểm tra

- Kiểm tra file có thể mở được (không bị lỗi PDF)
- Kiểm tra PDF có text layer (text extraction khả dụng)
- Kiểm tra số trang (so khớp với metadata)
- Kiểm tra thứ tự chương (chuỗi chương trong mỗi môn học đúng)
- Loại bỏ file trùng lặp (theo SHA-256)
- Kiểm tra metadata (file `.json` tồn tại và các trường bắt buộc khớp)
- Kiểm tra encoding tiếng Việt (không phát hiện lỗi mã hoá lớn)
- Kiểm tra OCR đối với tài liệu scan (không cần OCR cho các file hiện có)

### Tóm tắt kết quả kiểm tra 

| Tiêu chí | Số lượng |
|---|---:|
| Tổng số file PDF | 27 |
| File mở được | 27 |
| File đạt chuẩn | 27 |
| File cần sửa | 0 |
| File loại bỏ | 0 |
| File trùng lặp | 0 |
| File cần OCR | 0 |
| File có vấn đề metadata | 0 |

### Kết quả theo môn học (trình tự chương)

- CNXHKH: Đúng chuỗi chương
- KTCTMLN: Đúng chuỗi chương
- THMLN: Đúng chuỗi chương

### Các vấn đề phát hiện được

Không phát hiện vấn đề cần xử lý trong dataset gốc sau khi cập nhật metadata; tất cả 27 file đều đạt tiêu chuẩn.

### Chi tiết kết quả kiểm tra

Dự án sử dụng script kiểm tra chất lượng dữ liệu tự động check_dataset_quality.py tại `scripts/` để kiểm tra các tiêu chí trên. Kết quả chi tiết được lưu trong 1 file báo cáo dạng csv tại thư mục `data/reports/`.

---

## 8. QA pilot

QA pilot được sử dụng để kiểm tra chất lượng dữ liệu học liệu và đánh giá sơ bộ khả năng trả lời câu hỏi của hệ thống AI trước khi triển khai rộng rãi. Hiện tại, có tổng cộng 50 câu hỏi thử nghiệm được tạo ra dựa trên nội dung của 3 môn học, mỗi câu hỏi bao gồm các trường liên quan sau:

| Trường           | Ý nghĩa              |
| ---------------- | -------------------- |
| `qa_id`          | ID của câu hỏi       |
| `course_id`      | ID của môn học       |
| `question`       | Câu hỏi              |
| `question_type`  | Loại câu hỏi         |
| `ground_truth`   | Đáp án chuẩn         |
| `source_doc`     | Tài liệu chứa đáp án |
| `source_page`    | Trang chứa thông tin |
| `source_section` | Chương/section       |
| `difficulty`     | Độ khó               |
| `notes`          | Ghi chú              |

Các trường này giúp hệ thống AI sau này có thể đánh giá độ chính xác của câu trả lời và khả năng trích dẫn thông tin từ tài liệu gốc. Dữ liệu QA pilot được lưu trong file csv `qa_pilot_v1.0.csv` trong thư mục `data/qa/`.

---

## 9. Hạn chế sử dụng

Dataset **không được sử dụng** cho:

* Huấn luyện mô hình ngôn ngữ từ đầu.
* Phân tích hoặc suy luận về người học.
* Các mục đích ngoài phạm vi đồ án nếu không có quyền sử dụng phù hợp.

---

## 10. Hạn chế dataset

* Corpus hiện chỉ bao gồm 3 môn học.
* Số lượng tài liệu còn hạn chế.
* Chất lượng text phụ thuộc vào chất lượng PDF gốc.

---

## 11. Thông tin dự án

**Project:** smartlms-ai-rag

**Thành viên tham gia:**

* Trần Tuấn Cường - MSV: B22DCVT073
* Vũ Nam Dương - MSV: B22DCVT119

**Repository:** https://github.com/CuongTT-04/smart-lms-rag.git




