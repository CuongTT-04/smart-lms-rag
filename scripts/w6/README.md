# W6: chuẩn bị đầu vào pilot QLoRA

Chỉ chuẩn bị, kiểm và đóng gói dữ liệu. Chưa có trainer hoặc huấn luyện GPU trong thư mục này. Người phụ trách dữ liệu: Trần Tuấn Cường; trainer/GPU: Vũ Nam Dương. Hướng dẫn bàn giao: `docs/weekly/W6/ban-giao-duong.md`.

## Thực hiện từ checkout đầy đủ

Lệnh chạy ở root repo. Các đường dẫn dưới là ví dụ lần chuẩn bị thực tế; chọn thư mục output **mới** khi nội dung thay đổi. Công cụ chỉ cho ghi mới hoặc ghi lại bytes giống hệt, không ghi đè artifact đã khóa.

```powershell
python -B -m scripts.w6.bootstrap
python -B scripts/w6/intake.py --contract data/w6/training-contract.json --archive D:/ohayo-instruction.zip --output .private/w6/inputs/w5-compact --report Evidence/W06/intake-report.json
python -B scripts/w6/allocation.py --contract data/w6/training-contract.json --archive D:/ohayo-instruction.zip --output data/w6
```

Các lệnh tiếp theo cần môi trường có đúng `requirements-data.txt` (tokenizer CPU, không cần torch) và tokenizer local đúng revision. Ví dụ trên máy chuẩn bị:

```powershell
.private/w5/tokenizer-runtime/Scripts/python.exe -B scripts/w6/prepare_pilot.py --contract data/w6/training-contract.json --source-package D:/ohayo-instruction.zip --tokenizer .private/w5/intake-a/ce431c5/received/.private/instruction/tokenizer --output .private/w6/datasets/pilot-v2
```

Lấy SHA-256 thật của `manifest.json`, không dùng giá trị mẫu. Sau đó:

```powershell
python -B scripts/w6/validate_dataset.py --manifest <pilot>/manifest.json --tokenizer <tokenizer-local> --contract data/w6/training-contract.json --expected-manifest-sha256 <SHA256-thật> --source-root . --report <báo-cáo-ngoài-pilot>.json
python -B scripts/w6/handoff.py --pilot <pilot> --tokenizer <tokenizer-local> --output .private/w6/handoff/W6-Cuong-to-Duong-v1.0 --guide docs/weekly/W6/ban-giao-duong.md --verification-report <báo-cáo-đã-pass>.json
python -B -m unittest discover -s scripts/w6/tests
```

`bootstrap` chỉ dành cho checkout đầy đủ có Evidence W5 và code snapshot khớp; người nhận gói riêng dùng `verify_handoff.py` và contract có sẵn, không chạy bootstrap lại. ZIP/receipt/tokenized/raw payload chỉ lưu riêng. Public evidence chỉ lưu số đếm, trạng thái và checksum.

## Phạm vi kiểm

- ZIP raw hash, exact member set, manifest/member bytes; không extract path tùy ý.
- Bind ID/hash/split với từng dòng file vật lý, chặn tráo train/holdout kể cả sidecar.
- Giữ nguồn/family split; kiểm checksum PDF và đoạn text trên trang thật theo NFC bỏ whitespace, không bỏ dấu hoặc đổi nội dung.
- Chuyển citation bằng nhãn đã chỉ rõ và unit duy nhất; bỏ mẫu mơ hồ, không tự suy đoán source.
- Quota đồng thời môn/task bằng flow, deterministic seed; không bù bằng bản sao.
- Tokenizer thật kiểm template/prefix/EOS/loss mask/giới hạn; validator tính lại payload/token thay vì chỉ tin hash nội bộ.
- Package whitelist và kiểm exact file set trước khi import code, có test gói giải nén và môi trường CPU.

Unit tests dùng fixture/fake tokenizer để kiểm các ca lỗi. Kết quả tokenizer Qwen thật và PDF thật nằm trong báo cáo riêng; không gọi unit tests là kết quả huấn luyện hoặc nghiệm thu nội dung của hai thành viên.
