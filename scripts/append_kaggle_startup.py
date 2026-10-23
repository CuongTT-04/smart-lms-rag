"""Append one independent startup cell; never change earlier notebook cells."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def startup_source():
    gateway = (ROOT / 'backend/apps/ai/inference_gateway.py').read_text(encoding='utf-8')
    bootstrap = (ROOT / 'scripts/kaggle_startup_cell.py').read_text(encoding='utf-8')
    return 'OHAYO_GATEWAY_SOURCE = ' + repr(gateway) + '\n\n' + bootstrap


def append(path):
    original = path.read_bytes()
    notebook = json.loads(original)
    if any(cell.get('id') == 'ohayo-independent-startup' for cell in notebook['cells']):
        raise ValueError('Startup cell already present; refusing to replace notebook cells')
    previous = json.loads(original)['cells']
    source = startup_source()
    compile(source, 'ohayo-independent-startup', 'exec')
    notebook['cells'].extend([
        {'cell_type': 'markdown', 'id': 'ohayo-independent-startup-guide', 'metadata': {}, 'source': [
            '# Khởi động chatbot độc lập — chỉ chạy cell cuối mỗi phiên\n',
            'Giữ nguyên các mục trên để làm bằng chứng. Không cần chạy lại mục 1–14.\n\n',
            '**Thiết lập một lần:** bật GPU + Internet; gắn Output chứa `ohayo-model` và Input '
            '**OHAYO Generation Provider**. Trong Add-ons → Secrets, thêm và bật quyền '
            '`NGROK_AUTHTOKEN` (tài khoản ngrok) và `OHAYO_INFERENCE_TOKEN` '
            '(token ngẫu nhiên ASCII ít nhất 32 ký tự; backend dùng cùng giá trị). Không đưa token vào code/output.\n\n',
            '**Mỗi phiên:** chạy cell cuối. Nếu cần cài thư viện và phát hiện kernel còn bản cũ, '
            'chỉ Restart & Clear Cell Outputs rồi chạy lại cell cuối; không Factory Reset. '
            'Chờ SAN SANG, tải `w4-generation-kaggle.json` và cập nhật URL ở backend nếu URL đổi.\n\n',
            'Model còn trong phiên sẽ được dùng lại; phiên mới chỉ nạp checkpoint từ Input, không tải lại '
            'model gốc, không xuất checkpoint hoặc đánh giá 150 QA. API chỉ phục vụ sinh câu trả lời; '
            'backend vẫn phải kiểm tra quyền và truy xuất học liệu. Ngrok là kết nối HTTPS qua bên thứ ba; '
            'không có dịch vụ thường trực khi session Kaggle đã dừng.\n\n',
            'Nếu có nhiều source/checkpoint, đặt `os.environ["OHAYO_SOURCE_PACKAGE"]` hoặc '
            '`os.environ["OHAYO_CHECKPOINT"]` trong một cell nhỏ trước cell cuối.\n']},
        {'cell_type': 'code', 'id': 'ohayo-independent-startup', 'metadata': {},
         'execution_count': None, 'outputs': [], 'source': source.splitlines(keepends=True)},
    ])
    assert notebook['cells'][:len(previous)] == previous
    backup = path.with_name(path.stem + '.before-startup.ipynb')
    if backup.exists():
        raise FileExistsError(backup)
    backup.write_bytes(original)
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    assert json.loads(path.read_text(encoding='utf-8'))['cells'][:len(previous)] == previous
    return len(previous)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('notebook', type=Path)
    args = parser.parse_args()
    print('Preserved original cells:', append(args.notebook))
