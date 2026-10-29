# W5 — tiến độ phần việc của Trần Tuấn Cường

Ngày 28/10/2026. Contract v0.2 ghi nhận A đồng ý theo xác nhận của Cường. Nguồn PDF dùng cho nghiên cứu nội bộ theo chỉ dẫn của Cường; không khai giấy phép đã được xác minh độc lập hoặc quyền phát hành công khai.

## Trạng thái

| Task | Đã thực hiện | Còn phụ thuộc review/đầu vào |
|---|---|---|
| B1 | Schema/quota/rubric, phân nguồn, benchmark exclusions, pin prompt/parser/tokenizer | Review hợp đồng nếu có thay đổi |
| B2 | Validator source/page/checksum/excerpt, citation/parser, trùng và leakage, peer gates | Adjudication thật nếu có finding mới |
| B3 | Sửa pilot, chuẩn bị 250 draft đúng quota task/môn/13 nhóm nguồn B | A review; hiệu chỉnh rubric trên pilot hai người; sửa trước ACCEPT |
| B4 | Splitter theo component, seed 42 và tests | Chưa có candidate A để review; chưa đủ 500 mẫu được duyệt để khóa split |
| B5 | Checker tokenizer/template/EOS/reference mask, demo, báo cáo, gói review | Chưa có exporter/sidecar/manifest/card A để audit release; trainer W6 chưa chạy |

Theo yêu cầu tiếp tục của người dùng, chuẩn bị 250 draft trước review pilot thật để giảm thời gian chờ. Đây là staging có thể sửa lại, không bỏ qua calibration/peer review trong điều kiện nghiệm thu. Không ghi điểm hoặc ACCEPT thay Dương.

## Dữ liệu thực tế

- 250 draft: 150 QA, 50 summary, 25 hint, 25 insufficient_evidence.
- Theo môn: THMLN 100, KTCTMLN 75, CNXHKH 75; đúng số lượng theo từng nguồn B trong allocation.
- Trần Tuấn Cường phụ trách biên soạn câu hỏi từ đoạn nguồn đã chọn, sử dụng công cụ hỗ trợ; nhiều QA target là trích xuất/chỉnh chính tả OCR, summary được diễn đạt lại. Không phải 250 output do Qwen sinh.
- Hint có READ/OUTLINE/COMPARE; COMPARE có hai context với ID riêng. Nhiều negative yêu cầu dữ kiện không có trong đoạn, thường là số liệu thực tế; cần A kiểm tính tự nhiên/độ khó, không xem là coverage đầy đủ của hard negatives.
- Pilot v0.1 giữ nguyên trong .private/w5/pilot/v0.1; bản sửa ở pilot/v0.2. Nội dung thay đổi phải review hash mới.

## Kiểm chứng

Report hiện hành: data/instruction/w5/quality/member-b-draft-validation.json và member-b-draft-tokenization.json. Kiểm máy gồm nguồn/trang/trích đoạn, format/parser, quyền theo chỉ dẫn, phân nguồn, checksum, trùng, benchmark và special-token injection. Tokenizer thật theo revision/template đã pin, không tải weights.

27 unit tests đã qua. Demo kiểm cả fixture tốt và từ chối fixture/dữ liệu chưa review khi tạo release. Evidence/W05 ghi số liệu/hash lần chạy cuối. Report pilot chỉ kiểm 10 mẫu, không dùng làm bằng chứng cho 250 draft; bản v0.1 giữ trong archive.

Human peer reviews=0; release-eligible=0; training runs=0. Kiểm máy và rà soát sơ bộ bằng công cụ không chứng minh mọi claim/citation đã được con người duyệt. Character5-gram không phát hiện mọi paraphrase; mask CPU reference không thay integration trainer/collator W6.

## Bàn giao

Gói nội bộ: .private/w5/handoff/member-b-drafts-v0.2.zip. Có candidate, SFT preview, HTML đọc được, CSV trống điểm, source index, contract/report/checksum. Không kèm PDF/weights/secret/bài nộp/hội thoại học viên. Không đưa gói lên GitHub công khai.

1. Dương review pilot đã sửa, gửi pilot A để hiệu chỉnh rubric; sau đó review batch 25–50 của B.
2. Cường sửa B theo feedback; nhận candidate A để review thật vào CSV B sở hữu.
3. Đủ500 mẫu được duyệt mới xử lý/khóa split; A export release/card/manifest, B audit đúng hash artifact.

Chạy demo theo scripts/w5/README.md. Kết quả tích hợp và gói bàn giao hiện tại được tổng hợp tại [báo cáo bộ500 mẫu](ket-qua-tich-hop-w5.md).

## Cập nhật29/10/2026

Đã nhận250 mẫu A và kiểm lại ZIP/SFT trên CPU. Kết quả rà soát sơ bộ bằng công cụ đề nghị sửa3 mẫu; human peer acceptance vẫn chờ. Phần “chưa nhận A” ở trên là lịch sử28/10. Xem [tiếp nhận A](tiep-nhan-member-a.md).

## Cập nhật bộ chung29/10/2026

Đã tạo và audit CPU500 candidate, split385/57/58 đủ ba môn trong từng tập,3 bản sửa A có hash mới. Xem docs/weekly/W5/ket-qua-tich-hop-w5.md. Gói gốc giữ nguyên; peer confirmations vẫn cần thật, chưa train hoặc nghiệm thu nhóm.
