# Review nội dung và nguồn QA của Cường và Dương

Ngày review: **17/10/2026**. Người review: **Codex — trợ lý AI**. Phạm vi: 100 QA của `origin/main` tại commit `c981655eff3fa7e163d47ed3d0b731ceab7841b9`, không phải bộ QA cũ trên nhánh Cường đang mở.

## Kết quả

| Phần phụ trách | Số câu đã review | Có nguồn hỗ trợ | Câu bắt buộc sửa nhãn |
|---|---:|---:|---:|
| Dương | 50 | 50 | 0 |
| Cường | 50 | 50 | 0 |
| Tổng | **100** | **100** | **0** |

Phân phần: 50 ID trong bộ Cường là phần Cường; 49 THMLN và pilot `KTCTMLN_QA_001` còn lại tính phần Dương. Cột phân phần không phải tên người ký review.

Đã đọc câu hỏi/đáp án và đối chiếu bằng chứng trên trang PDF vật lý; kiểm tra câu đúng/sai có đảo chiều/phủ định, lựa chọn trắc nghiệm, phép tính và phạm vi gợi ý. Đã trích lại nguồn từ PDF, xác nhận checksum và nội dung trích khớp audit hiện có. Đã xem ảnh trực tiếp ba trang cần làm rõ công thức/bố cục. Mỗi câu có nhận xét nội dung riêng trong [qa_assistant_review.csv](../../data/qa/qa_assistant_review.csv).

Không chỉnh câu hỏi, đáp án hoặc gold theo retrieval; lượt review này không dùng predictions để sửa dataset và không tính lại baseline trên nhãn mới. Đây không phải đánh giá mù vì các lượt kiểm tra trước đã biết kết quả baseline. Nội dung review không làm thay đổi bộ QA/metric đã bàn giao.

## Các câu cần chú ý

- **KTCTMLN_QA_001:** đã đọc và xem trực quan KTCTMLN/ch01.pdf trang 20; đối tượng sản xuất/trao đổi và quan hệ với lực lượng sản xuất/kiến trúc thượng tầng đúng. Không còn thiếu kiểm tra nguồn trong bản main này.
- **KTCTMLN_QA_005:** giữ gold trang 10 như main. Quan hệ tỷ lệ nghịch hỗ trợ phép tính giả định `10/2=5`; 10 và 5 là số của tình huống, không phải số trích từ giáo trình. Bản cũ gold trang 9 không phải bản được review ở đây.
- **CUONG_W3_QA_015:** đã xem KTCTMLN/ch03.pdf trang 13, CH ở tử và ch ở mẫu; `n=CH/ch` đúng. Hai thời gian cần cùng đơn vị khi vận dụng.
- **CUONG_W3_QA_023:** bản main đã giới hạn đúng đối tượng xóa bỏ là tư hữu tư bản chủ nghĩa về tư liệu sản xuất, không suy rộng thành mọi sở hữu cá nhân.
- **CUONG_W3_QA_008:** trang 10 đủ làm điểm mở đầu cho hint về cường độ. Định nghĩa đầy đủ năng suất ở trang 9; nếu sau này mở rộng thành câu so sánh hoàn chỉnh cần đối chiếu thêm trang đó. Chưa cần tự thêm/sửa gold của câu hint hiện tại.

## Hạn chế cần ghi trong báo cáo

Năm nhóm kiến thức gần nhau, không phải câu trùng nguyên văn: `THMLN_QA_011/020`, `THMLN_QA_006/007`, `THMLN_QA_022/041`, `THMLN_QA_023/038`, `KTCTMLN_QA_004/005`. Chúng có thể giữ trong tập development để kiểm tra cách hỏi khác nhau, nhưng 100 câu không đại diện 100 kiến thức độc lập hay held-out test cuối đồ án.

Bảy mẫu hint có bằng chứng phù hợp mục đích truy xuất. Chưa đánh giá hành vi sinh gợi ý của chatbot hoặc mức độ tiết lộ đáp án; phần này cần policy và phép đo riêng khi triển khai sinh phản hồi.

## File kết quả và trạng thái review

- `data/qa/qa_assistant_review.csv`: 100 dòng, gồm QA ID, người phụ trách, câu hỏi/đáp án đã review, nguồn/checksum, kết luận và nhận xét riêng. `reviewer=Codex`, `reviewer_kind=ai_assistant`.
- `docs/reports/w3-qa-assistant-review.json`: bản tổng hợp máy đọc, commit/dataset hash và checksum CSV.
- Dataset hash của nội dung JSON Git dùng LF: `44037180cde5d328bdda98573e303bfee6cb5f89968cbce1df15f32d91327fe9`. Hash bản CRLF trong artifacts Kaggle khác dù nội dung giống nhau, như đã kiểm tra ngày 16/10.

**Review nội dung bằng trợ lý đã hoàn tất cho cả hai phần.** Không điền tên Dương/Cường vào ô reviewer thay họ; human peer confirmation vẫn cần hai thành viên xác nhận nếu tiêu chí nghiệm thu yêu cầu. Log review người và `pending_human_peer` của dataset không bị sửa. Review này không xác nhận demo quyền DB.
