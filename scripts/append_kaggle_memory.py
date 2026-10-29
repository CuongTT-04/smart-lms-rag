"""Append a memory-capable startup cell without changing old notebook evidence."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def startup_source():
    spec = importlib.util.spec_from_file_location('ohayo_dual_export', ROOT/'scripts/append_kaggle_dual_gpu.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.startup_source()


def append(path):
    path = Path(path)
    notebook = json.loads(path.read_text(encoding='utf-8'))
    if any(c.get('id') == 'ohayo-chat-memory-startup' for c in notebook['cells']):
        raise ValueError('Memory startup already appended; refusing to overwrite evidence')
    notebook['cells'].extend([
        dict(cell_type='markdown', id='ohayo-chat-memory-guide', metadata={}, source=[
            '# Phiên chat và context nhiều lượt\n',
            'Chọn **Restart & Clear Cell Outputs**, rồi chỉ chạy cell cuối mới này. '
            'Giữ GPU T4 x2, Internet, Input checkpoint và hai Secrets cũ. Không Run All.\n\n',
            'Gateway mới hỗ trợ `chat_history_v1`; lịch sử do backend xác minh và gửi vào, '
            'không được lưu thành bộ nhớ toàn cục trên GPU. Sau SAN SANG/DUAL_GPU_READY, '
            'đồng bộ backend bằng `configure_kaggle_inference.py --dual-gpu --chat-memory`.\n',
            'Mỗi câu hỏi vẫn dùng một GPU; không thay baseline, tạo checkpoint hay chạy lại bộ QA.\n']),
        dict(cell_type='code', id='ohayo-chat-memory-startup', metadata={}, execution_count=None,
             outputs=[], source=startup_source().splitlines(keepends=True)),
    ])
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1)+'\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('notebooks', nargs='*', type=Path)
    parser.add_argument('--export', type=Path)
    args = parser.parse_args()
    for path in args.notebooks:
        append(path)
        print('Appended memory startup:', path)
    if args.export:
        args.export.write_text(startup_source(), encoding='utf-8')
        print('Exported memory startup:', args.export)
