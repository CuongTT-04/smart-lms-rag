# W6 — cách tiếp nhận kết quả của Cường

Đọc trước `docs/qlora-receiver-report.md` và `docs/dataset-card-w6.md`. Gói riêng của Cường nằm tại `.private/qlora/delivery/`, không đưa lên Git công khai.

## Dương tiếp nhận

1. Nhận ZIP bàn giao và receipt cùng tên. Kiểm SHA-256/kích thước trước, sau đó giải nén vào thư mục mới; không ghi đè gói pilot hoặc dữ liệu đã audit.
2. Trong `data/`, kiểm ZIP 250 B và ZIP ứng viên 1.000 theo receipt riêng. Trong `reports/`, đọc kiểm tiếp nhận A, checkpoint/log, review 40 output và kết quả test. `manifest.json` của gói liệt kê tất cả file với hash/kích thước.
3. Review B theo `candidates.jsonl`, context/page và `content_sha256`. Ghi quyết định riêng của A; không sửa bản nhận rồi vẫn dùng receipt cũ. Chú ý các hạn chế của recipe trong dataset card. Owner B cần đọc và xác nhận phần của mình trước khi nhóm nghiệm thu.
4. Đối chiếu finding review 40 output. Đặc biệt `W5_B_00120` có khác rubric giữa owner review và review tiếp nhận; giữ cả hai hồ sơ, chốt lý do nếu thay đổi kết luận.
5. Bộ 1.000 là ứng viên hỗn hợp format. Không chạy thẳng vào trainer pilot hoặc nối hai split tùy ý. Trước W7 xuất phiên bản đồng nhất, review/hash/audit lại. Pilot đã chạy dùng 128/32 riêng.
6. Kết quả GPU của Cường đã được tiếp nhận và kiểm độc lập, nằm trong phần `gpu/` của gói bàn giao v2. Dùng receipt/manifest và report mới để tổng hợp Evidence W06 và PR/Issue. Chỉ ghi tên người xác nhận khi người đó thực sự xác nhận. Không đóng milestone bằng kết quả CPU thay GPU.

## Cường chạy GPU bằng một cell ở notebook đang có

Không cần upload notebook khác. Thêm một code cell **cuối** notebook Dương; giữ nguyên cell cũ. Dán toàn bộ `.private/qlora/receiver-work/append-verification-cell.py` vào cell mới.

Gắn Input Private: `.private/qlora/kaggle-cuong-v1/qlora-environment-input.zip` và ZIP pilot gốc `pilot-20261104T180615021055Z.zip` trong gói Dương. Có thể dùng lại Input cũ; các bản bundle trùng hệt hash được chấp nhận. Bật T4 x2 và Internet; dừng chatbot để giải phóng GPU. Không cần ngrok/token chatbot. Lần đầu có thể tải base model khoảng 15 GB.

Chỉ chạy cell mới. Cell dùng thư mục output riêng, môi trường Python riêng, một GPU; code GPU reload/resume đóng băng của Dương giữ nguyên. Chạy so sánh 20 ca đã khóa, tiếp tục checkpoint 25 đúng một update tới 26 với lịch max_steps=50, rồi xuất ZIP/receipt/audit. Nếu lỗi, giữ log và gửi traceback; không xóa checkpoint gốc hoặc reset khi chưa lấy được bằng chứng.

Khi thành công, tải ZIP verification mới cùng `-receipt.json` và `-audit.json` về máy. Đây mới là đầu vào để ghi Cường đã tự chạy GPU; notebook/cell được chuẩn bị sẵn không chứng minh đã chạy.

## Chạy kiểm artifact trên CPU

Tạo môi trường riêng theo `scripts/qlora/requirements.txt`; dùng PyTorch CPU phù hợp và `jsonschema`, `pypdf` cho kiểm dữ liệu. Không đổi môi trường phục vụ backend. Đặt `USE_TF=0`, `USE_FLAX=0`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` khi đã có tokenizer trong bundle.

Các lệnh sau dùng `python` của môi trường kiểm; thay đường dẫn artifact theo máy nhận:

```powershell
python -B -m scripts.qlora.receive --archive <zip> --receipt <receipt.json> --output <thu-muc-moi> --report <bao-cao.json>
# Với smoke/pilot dùng thêm --manifest-name run-manifest.json.

python -B -m scripts.qlora.receive_training --smoke <smoke-dir> --pilot <pilot-dir> --verification <verification-dir> --bundle <pilot-bundle-dir> --report <bao-cao-moi.json>

python -B -m scripts.qlora.check --output <thu-muc-ket-qua-moi>
python -B -m unittest discover -s scripts/instruction/tests -t .

python -B -m scripts.instruction.expand --spec <B-authored-specs.json> --handoff <pilot-bundle-dir> --old-compact <ohayo-instruction.zip> --member B --audit-only --output <B-package-dir>

python -B -m scripts.instruction.combine --old-compact <ohayo-instruction.zip> --member-a <A-package-dir> --member-b <B-package-dir> --handoff <pilot-bundle-dir> --output .private/instruction/group-new/package
```

Từ đầu source checkout Cường hiện tại cần thêm source registry/PDF nội bộ được contract tham chiếu nếu kiểm lại dữ liệu. Môi trường CPU không thể thay kiểm QLoRA 7B trên CUDA. `receive_training` đọc lại tensor/state của run đã xác thực; không chạy train hay inference mới. Không sửa `context.json` hoặc source đóng băng để ép audit vượt qua.


## Kết quả đã có — không cần chạy lại để hoàn thành bước GPU W6

Ngày 07/11 đã nhận và kiểm gói `verification-20261106T194045367524Z.zip` (190.438.481 byte; SHA-256 `85760688ed358d1b8dc4ff6dc7f26ce3dad96f7558bac4e9a3d88ad4c2f0f38b`). Gói bàn giao v2 chứa ZIP này cùng receipt/audit, kết quả kiểm tensor/state và so 40 raw output. Các hướng dẫn chạy phía trên phục vụ tái lập sau này; không yêu cầu Cường lặp lại lần đã đạt.

Nếu cây Output Kaggle lỗi, dùng `kaggle/download-verification-files.py` để tạo liên kết tải ba file ngay trong cell. Tải về ngay và lưu Version có Output trước khi kết thúc session. Không coi dòng Draft saved là bằng chứng đã lưu ZIP/checkpoint.
