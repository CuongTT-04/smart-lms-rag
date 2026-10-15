# Phân tích lỗi baseline W3 v1.0

Ngày kiểm tra: 15/10/2026. Đầu vào thực tế: `D:/Downloads/ohayo-baseline-results-v1.0/w3-integrated/metrics.json` và `retrieval_results.csv`. Đã đọc thêm metadata/chunks trong snapshot index cùng thư mục và các trang PDF nguồn trong repository. Không thay đổi input, gold, config, index hoặc metric để cải thiện điểm.

## Kiểm chứng kết quả

- CSV có đủ 100 ID duy nhất, khớp câu hỏi/đáp án/gold của JSON QA có SHA-256 `2f7f9e0880630e39eb18e5ba30f2fde391be8deed87321a16402b3eb2044a45b`.
- SHA-256 CSV thực tế khớp `results_sha256`: `2bfcc0f995f733820bfb2ce8f254d926fe1e2a9ce9fc30bf55a2a6c071b87995`.
- Tính độc lập từ danh sách chunk/source: cắt top-k trước rồi bỏ trùng trang theo document/version/page. Recall và Hit đều lần lượt 0,73 / 0,94 / 0,97 / 0,98 cho k=1/3/5/10, khớp từng dòng CSV và aggregate JSON.
- 100 status OK, không error/missing/invalid label trong báo cáo. Rank liên tiếp và course ID khớp dataset; không coi điều này là xác minh quyền database.
- Pointer, manifest, checksum binary/chunks và 1.048 bản ghi chunk khớp nhau; toàn bộ chunk ID/source trong 100 dòng kết quả ánh xạ đúng metadata snapshot. Chỉ kiểm tra bytes/hash và JSON, không deserialize FAISS hoặc chạy model lại.
- Mọi QA có một trang gold nên Page Recall và Hit trùng nhau; không phải hai phép đo chất lượng độc lập.

## Ba trường hợp miss@5

| QA | Gold (trang PDF vật lý) | Kết quả thực tế | Nhận định |
|---|---|---|---|
| THMLN_QA_004 | THMLN/ch05.pdf, 16 | Top-1: cùng tài liệu trang 5, score 0,71932286; gold không có trong top-10 | Có chunk gold trong index, không phải mất nguồn. Trang 5 có luận điểm vật chất là tính thứ nhất và ý thức là phản ánh, nhưng không phải trang gold đã chốt. |
| THMLN_QA_010 | THMLN/ch12.pdf, 2 | Top-1: cùng tài liệu trang 1, score 0,68103510; top-2 trang 3; gold không có trong top-10 | Top đầu nghiêng về nguồn gốc/chức năng nhà nước, trong khi trang 2 giải thích trực tiếp bản chất giai cấp và bộ máy cưỡng chế. Chunk chứa đoạn này vẫn có trong index. |
| CNXHKH_QA_006 | CNXHKH/ch03.pdf, 14 | Top-1: cùng tài liệu trang 13, score 0,74026960; gold ở rank 7, score 0,67553937 | Truy xuất gần nguồn nhưng thứ hạng trang gold thấp. Trang 13 đã nêu tiếp thu khoa học/công nghệ, trang 14 nêu đầy đủ cả quản lý. Miss@5 nhưng hit@10. |

### THMLN_QA_004 - Câu đúng/sai về ý thức quyết định vật chất

Gold trang 16 trực tiếp xác định vật chất có trước, quyết định ý thức và ý thức tác động trở lại qua thực tiễn; đáp án False được hỗ trợ. Chunk gold `7ea37dd8-8544-5fef-bae3-b334e85d17f6` có đoạn này nhưng còn trộn với nội dung vô thức ở phần đầu. Top-1 `3379b2a7-9a9c-5f61-b3e4-bd0425a8e769` trang 5 cũng chứa nội dung liên quan về vật chất và ý thức.

Suy luận cần kiểm chứng thêm: dense embedding có thể ưu tiên nội dung tổng quát và gặp khó với mệnh đề đảo chiều/đúng-sai; ngữ cảnh lẫn trong chunk có thể làm giảm mức tập trung của vector. Không kết luận chắc chắn nguyên nhân chỉ từ một ranking, không coi score là xác suất đúng. Không gán rank cụ thể của gold ngoài top-10 khi chưa có kết quả sâu hơn.

### THMLN_QA_010 - Bản chất giai cấp của nhà nước

Gold trang 2 là bằng chứng trực tiếp, chứa trong chunk `e8a637f8-03c4-5eb2-820b-f7663bfbdc67`. Top-1 `34514172-09e4-5953-8ff1-971eb7608fa6` trang 1 chủ yếu nêu lịch sử xuất hiện và mâu thuẫn giai cấp; top-2 trang 3 nêu bộ máy cưỡng chế/chức năng giai cấp. Những trang đó liên quan nhưng không bao phủ đầy đủ đáp án đã chốt như trang 2. Có nhiều chunk cùng trang/tài liệu chiếm vị trí; k đếm chunk, không đếm trang duy nhất.

Suy luận: baseline chưa phân biệt đủ tốt nguồn gốc, bản chất và chức năng nhà nước khi nội dung dùng chung nhiều khái niệm. Không thấy dấu hiệu thiếu chunk gold hoặc metadata sai trong các kiểm tra đã thực hiện. Chưa chứng minh toàn bộ vector đều đúng bằng việc embedding lại corpus.

### CNXHKH_QA_006 - Bỏ qua chế độ tư bản và kế thừa thành tựu

Gold trang 14 có đủ khoa học, công nghệ và quản lý; được tìm ở rank 7, chunk `821fcfb2-3e1b-5f87-964c-18d093631150`. Top-1 trang 13, chunk `d81c4cb0-f4ce-5784-9444-ca247d2732a0`, đã có luận điểm kế thừa thành tựu và khoa học/công nghệ nhưng không nêu quản lý như trang 14. Đây không phải retrieval hoàn toàn lạc chủ đề.

Không đổi gold sang trang 13 hoặc bổ sung gold chỉ để tăng điểm sau khi xem predictions. Nếu nhóm cần đánh giá các nguồn thay thế tương đương, phải review độc lập, định nghĩa rõ protocol/dataset phiên bản mới và đánh giá lại; không tự gộp mọi trang thay thế thành nhiều trang bắt buộc.

## Kết luận và việc tiếp theo

1. Giữ nguyên baseline hiện tại: Recall@5=0,97, Recall@10=0,98; ba miss@5, hai miss@10 đều thuộc nhãn gold hợp lệ đã kiểm tra. Điểm vượt mục tiêu 0,80 trên development này, chưa chứng nhận chất lượng phản hồi AI.
2. Không cần embedding lại corpus để phân tích lỗi này. Đã có đầy đủ index bytes/manifests trong gói tải về; giữ nguyên bản đầu trước khi chạy reuse vì runner có thể ghi lại predictions/metrics.
3. Cần một lượt reuse/tái lập cùng config và đối chiếu top-k/metric. Ba reload_checks trong runner không thay thế bằng chứng notebook Run All từ kernel mới. Chưa chạy reuse trong lần kiểm tra này.
4. A/B xác nhận review chéo và các hạn chế nguồn thay thế; review_status hiện vẫn pending_human_peer. Source audit của trợ lý không phải chữ ký peer review.
5. Chuyển cải tiến query/negation, cấu trúc chunk theo mục và hybrid/reranker sang đợt thử nghiệm phù hợp (W5 theo kế hoạch); không thay baseline W3 hoặc gold ngầm. Mọi thử nghiệm cần khóa config/dataset và báo riêng.

Đánh giá này dùng corpus offline pypdf, UUID probe và lọc theo khóa học; authorization_verified=false, không phải nghiệm thu bridge quyền DB. Cần bổ sung notebook đã lưu, log môi trường đầy đủ và proof tái lập để chốt gói bàn giao.
