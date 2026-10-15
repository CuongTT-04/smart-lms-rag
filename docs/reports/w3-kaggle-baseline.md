# Baseline corpus W3 trên Kaggle

Ngày nhận kết quả: 15/10/2026. Ban đầu nhận aggregate qua chat. Sau đó đã đọc trực tiếp metrics.json/retrieval_results.csv và metadata/chunks/index bytes trong gói `D:/Downloads/ohayo-baseline-results-v1.0/w3-integrated`; kiểm tra checksum, dataset parity và tính độc lập Recall/Hit đều khớp. Chưa chạy model/reuse lại hoặc nhận notebook đã lưu để kiểm chứng tuần tự. Chi tiết: [w3-retrieval-error-analysis.md](w3-retrieval-error-analysis.md).

## Phạm vi và trạng thái

Đã chạy model thật trên snapshot 27 PDF, 1.048 chunk và 100 QA development. Theo output, đủ 100 prediction, 100 QA có nhãn để chấm, không thiếu prediction, không lỗi nhãn hoặc truy xuất. Đây là baseline nháp vì review_status vẫn pending_human_peer. Không phải phép đánh giá chất lượng câu trả lời LLM hoặc nghiệm thu quyền Django.

| k (chunk) | Macro Page Recall@k | Hit@k |
|---|---:|---:|
| 1 | 0,73 | 0,73 |
| 3 | 0,94 | 0,94 |
| 5 | 0,97 | 0,97 |
| 10 | 0,98 | 0,98 |

Recall@5 của lượt đo này cao hơn mục tiêu 0,80; chưa coi là nghiệm thu cuối khi peer review và tái lập chưa hoàn tất. Tập QA hiện có một gold page mỗi câu nên Recall và Hit trùng nhau; không diễn giải thành 97% câu trả lời AI đúng. Các câu miss phải lấy từ retrieval_results.csv, không suy đoán QA ID từ aggregate.

## Thời gian và cấu hình

- model_load_build_reload_seconds: 2330,135 giây, khoảng 38 phút 50 giây; là tổng phạm vi nạp model/build/reload do runner ghi, không phải latency mỗi câu.
- Mean query latency: 0,3239985 giây/QA, theo trường latency của runner. Không coi đây là thời gian build toàn corpus hoặc phép đo phục vụ đồng thời nhiều người.
- BGE-M3 revision: 5617a9f61b028005a4858fdac845db406aefb181; CPU, batch 2, max_tokens 514, dense 1.024 chiều, float32, L2, FAISS inner product.
- Python 3.13.15; torch 2.11.0+cpu; sentence-transformers 5.7.0; transformers 5.16.1; numpy 2.1.3; huggingface-hub 1.29.0; psutil 7.2.2, theo output.
- reload_checks: 3. Đây là kiểm tra reload trong lượt runner, chưa phải xác nhận một lượt notebook độc lập từ kernel mới.
- authorization_verified=false; rag_ready=false; parser=pypdf; validation_only=false.

## Truy vết

| Artifact/config | SHA-256 hoặc revision do output báo |
|---|---|
| Dataset JSON | 2f7f9e0880630e39eb18e5ba30f2fde391be8deed87321a16402b3eb2044a45b |
| Corpus manifest | 0ce8cd4aff3b35c4515c4a3eac59006f81dd875dcec1e5012cb1aa09dab3351f |
| Embedding config | cb64865324751eb5726329917a349887a33142e51f8114a4500d50e822902466 |
| Chunking config | 184dc29844666d63f6948ed4c4e191580cfb686a9d829dc84065cf072ad9f6d6 |
| Index revision | 5d1f070cda659dfe8fb9a3dc8945ee69badea453aaa02a44cf65f104e43afd1b |
| retrieval_results.csv | 2bfcc0f995f733820bfb2ce8f254d926fe1e2a9ce9fc30bf55a2a6c071b87995 |

## Công việc tiếp theo

### Cập nhật reuse sau session reset - 16/10/2026

Theo output Dương gửi, lượt reuse dùng lại đúng index revision `5d1f070cda659dfe8fb9a3dc8945ee69badea453aaa02a44cf65f104e43afd1b`, dataset/config hashes giữ nguyên; đủ 100 prediction, không lỗi. Recall/Hit@1/3/5/10 vẫn 0,73/0,94/0,97/0,98; reload_checks=3. Thời gian model_load_build_reload_seconds=47,519 giây (lượt này load/reload index, không embedding corpus); mean query latency=0,341467 giây. Không coi 47,519 giây là toàn bộ runtime gồm cả 100 query.

Corpus manifest hash mới `a50711b0d43d2652c24c20b983eac4995980ab44987564f760b89b8431bf856d`; CSV hash mới `2cb9550700de4741afc7334ce11051dee8bb34b8042413550fb64e3540818dd2`. Generator manifest có elapsed_seconds, CSV có latency nên checksum thay đổi không tự chứng minh nội dung nguồn/ranking thay đổi. Chưa có hai file lượt reuse để đối chiếu metadata trực tiếp. Runner reuse đã kiểm tra catalog records khớp export_chunks của snapshot trước khi query. Aggregate bằng nhau chưa chứng minh 100 danh sách top-k giống nhau; cần đối chiếu chunk ID/rank/source từng QA giữa hai lượt và ghi riêng sai khác score nếu có.

Phần kiểm chứng reuse và aggregate đã đạt theo output; vẫn cần lưu notebook, môi trường, output reuse, đối chiếu từng QA và xác nhận review người. Chưa cập nhật human peer approval hoặc xác nhận quyền DB.

1. Giữ phiên Kaggle đang có index; lưu/download output data/processed/w3-integrated gồm đầy đủ index/current.json và generation, predictions.json, retrieval_results.csv, metrics.json, preflight.json. Không chỉ lưu pointer hoặc cell output.
2. Lưu notebook có outputs và môi trường pip freeze. Tránh chạy lại run(*COMMON) chỉ để lưu kết quả vì lệnh đó build lại corpus.
3. Kiểm tra riêng việc reuse index với cùng snapshot/config/device/offline flag; dùng run(*COMMON, '--reuse-index') sau khi đã bảo toàn output lần đầu. Lệnh này vẫn có thể nạp model và chạy query, không hứa tức thì. Muốn giữ hai lượt, sao lưu thư mục output trước khi runner ghi lại metric.
4. Đọc CSV để xác định ba QA miss@5 và hai QA miss@10, đối chiếu trang nguồn và phân loại lỗi; không sửa gold theo ranking để tăng điểm.
5. Dương/Cường xác nhận review chéo. Nếu nhãn thay đổi, chạy đánh giá lại; chỉ reuse corpus index khi các kiểm tra config/catalog cho phép.
6. Hoàn thiện minh chứng tái lập và bàn giao. Chưa đánh dấu toàn bộ W3 hoàn thành chỉ từ aggregate metrics.
