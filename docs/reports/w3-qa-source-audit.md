# Rà soát nguồn 100 QA W3

Ngày: 15/10/2026. Người thực hiện kiểm tra hỗ trợ: Codex. Đây không phải chữ ký phê duyệt peer của Dương hoặc Cường.

## Quy trình

1. Đọc dữ liệu A75/B50, CSV/JSON tích hợp và review log; kiểm tra cách hợp nhất 25 ID pilot chung thành 100 QA.
2. Đọc câu hỏi/đáp án, đối chiếu nguồn PDF vật lý; kiểm lại anchor/thuật ngữ của 49 QA Triết học và lập đặc tả bằng chứng cho 51 QA còn lại. Đọc các trang lân cận khi nội dung bị ngắt trang.
3. Kiểm tra trực quan trang PDF 20 của KTCTMLN/ch01.pdf và công thức tốc độ chu chuyển ở trang PDF 13 của KTCTMLN/ch03.pdf. Không suy ra công thức chỉ từ vị trí tử/mẫu trong text extraction.
4. Lưu đặc tả rà soát/chỉnh sửa ở `data/qa/qa_w3_source_checks.json`; giữ nguyên các file pilot A/B, áp dụng bản chỉnh rõ ràng khi hợp nhất để không mất thay đổi khi tái tạo.
5. Tái tạo CSV, JSON, review log và file minh chứng `qa_w3_source_audit.csv`. Kiểm tra đủ 100 ID/câu hỏi không trùng chính xác, loại câu và đáp án, trang/UUID/checksum, CSV/JSON parity và chạy lại không đổi output.
6. Kiểm thử ngoại lệ bằng chứng thiếu, trang sai, đổi trường ngoài phạm vi, Unicode tiếng Việt và chống ghi đè review của người. Hồi quy cuối đạt 118/118, không skip. Venv local ban đầu thiếu pypdf/Django/requests; đã bổ sung các dependency W3 và bật UTF-8 cho tiến trình con Windows trước lượt kiểm tra cuối. Không migrate database hoặc chạy phép đo model thật.

## Kết quả

| Nội dung | Kết quả |
|---|---|
| Tổng QA / phân bố môn | 100: THMLN 49, KTCTMLN 31, CNXHKH 20 |
| Chế độ | 93 qa, 7 hint |
| ID và câu hỏi trùng chính xác sau chuẩn hóa | Không |
| Trang nguồn, UUID, checksum, minh chứng anchor/thuật ngữ | Đạt 100/100 trong lượt kiểm tra |
| CSV/JSON | Đồng nhất câu hỏi, đáp án, mode, document/version/page |
| Source review required | 0, trước đó còn KTCTMLN_QA_001 |
| Tái tạo và input A/B | Output ổn định, pilot A/B không thay đổi |
| Human peer approval | 0/100; giữ pending_human_peer |

## Các xử lý cụ thể

### KTCTMLN_QA_001

Đã đọc trang PDF 19-21 và kiểm tra trực quan trang 20 của `KTCTMLN/ch01.pdf`. Đoạn mở đầu trang 20 xác nhận đối tượng nghiên cứu là quan hệ xã hội của sản xuất và trao đổi, trong liên hệ biện chứng với lực lượng sản xuất và kiến trúc thượng tầng tương ứng. Câu hỏi/đáp án và gold trang 20 hiện có đúng; giữ nguyên, bổ sung minh chứng và đổi trạng thái thiếu rà soát nguồn sang source_checked_pending_peer. Không đổi đáp án để khớp dự đoán hoặc tự gán human peer approval.

### KTCTMLN_QA_005

Chuyển gold từ trang PDF 9 sang 10 của ch02.pdf: trang 9 nêu chiều biến đổi, còn trang 10 có quan hệ tỷ lệ nghịch hỗ trợ lập luận năng suất gấp đôi thì giá trị một đơn vị giảm một nửa. Giữ câu hỏi/đáp án, cập nhật source_page, source_pages và ghi chú. Các số 10 và 5 là tình huống vận dụng, không được ghi là số liệu trích từ PDF. Một trang 10 đủ hỗ trợ nguyên lý áp dụng nên không tăng gold thành hai trang bắt buộc chỉ vì có trang dẫn nhập.

### CUONG_W3_QA_023

Giữ câu hỏi và nguồn ch02.pdf trang PDF 7 của CNXHKH; làm rõ trong đáp án đối tượng xóa bỏ là tư hữu tư bản chủ nghĩa về tư liệu sản xuất, theo câu giải thích ngay sau đoạn định nghĩa. Không mở rộng thành phủ nhận mọi sở hữu cá nhân.

## Giới hạn và việc tiếp theo

- Source audit gồm đọc đối chiếu của trợ lý và kiểm tra bằng chứng bằng script, không tự thay thế review chéo của hai thành viên. Các cột agent_reviewer/agent_review_status tách biệt peer_reviewer/peer_review_status.
- Câu hỏi không trùng nguyên văn không đồng nghĩa độc lập ngữ nghĩa: THMLN_QA_011/020 kiểm tra cùng quan hệ vật chất-tinh thần bằng dạng câu khác nhau; KTCTMLN_QA_004/005 dùng cùng nguyên lý với câu khái niệm và vận dụng. Giữ nhãn development và ghi hạn chế khi báo cáo, không coi đây là held-out test.
- Việc khớp anchor/thuật ngữ không tự chứng minh mọi suy luận đúng; vẫn cần nhóm duyệt nội dung/nguồn, đặc biệt hai chỉnh sửa và KTCTMLN_QA_001. Không sử dụng predictions trong lần rà soát này.
- JSON QA đổi hash thành `2f7f9e0880630e39eb18e5ba30f2fde391be8deed87321a16402b3eb2044a45b`. Phải cập nhật Dataset source trên Kaggle và chạy lại preflight trước khi đo; output preflight cũ không đại diện dataset mới.
- Chưa thay PDF, chunking config hay embedding config; chưa chạy baseline corpus. ZIP source cập nhật không chứa PDF/model/index/database và không tự cập nhật Kaggle.

## Tái tạo

```powershell
python scripts/merge_w3_qa.py
python scripts/check_w3_qa_audit.py
```

Lệnh kiểm tra ghi `docs/reports/w3-qa-source-audit.json`. Script merge từ chối ghi đè review log khi đã có reviewer/quyết định peer, để nhóm đối chiếu rõ thay đổi thay vì mất phê duyệt. Khi nhóm bắt đầu duyệt, không chạy merge vào thư mục final một cách máy móc.
