"""Append a standalone two-GPU serving profile; never rewrite an earlier cell."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def startup_source():
    gateway = (ROOT/'backend/apps/ai/inference_gateway.py').read_text(encoding='utf-8')
    path = ROOT/'scripts/kaggle_startup_cell.py'
    bootstrap = path.read_text(encoding='utf-8')
    tree = ast.parse(bootstrap)
    bootstrap = '\n\n'.join(ast.get_source_segment(bootstrap, n) for n in tree.body if isinstance(n, ast.FunctionDef))
    profile = (ROOT/'scripts/kaggle_dual_gpu_cell.py').read_text(encoding='utf-8')
    files = [ROOT/'backend/apps/__init__.py', ROOT/'backend/apps/ai/__init__.py']
    for directory in ('providers', 'prompts', 'rag'):
        files.extend(sorted((ROOT/'backend/apps/ai'/directory).glob('*.py')))
    payloads = {p.relative_to(ROOT).as_posix():p.read_text(encoding='utf-8') for p in files}
    manifest = {'schema_version':1,'purpose':'local_generation_provider_source',
        'files':{name:hashlib.sha256(content.encode()).hexdigest() for name,content in payloads.items()}}
    bundle = {'manifest':manifest,'files':payloads}
    signature = 'dual-v1-' + hashlib.sha256((gateway+bootstrap+profile+json.dumps(manifest,sort_keys=True)).encode()).hexdigest()
    source = ('# OHAYO: only run this last cell after restarting Python.\n'
        + 'OHAYO_GATEWAY_SOURCE = ' + repr(gateway) + '\n'
        + 'OHAYO_PROVIDER_BUNDLE = ' + repr(bundle) + '\n'
        + 'OHAYO_DUAL_SIGNATURE = ' + repr(signature) + '\n\n' + bootstrap + '\n\n' + profile)
    compile(source,'ohayo-dual-gpu-startup','exec')
    return source


def append(path):
    path = Path(path)
    original = path.read_bytes()
    notebook = json.loads(original)
    if any(cell.get('id') == 'ohayo-dual-gpu-startup' for cell in notebook['cells']):
        raise ValueError('Dual GPU cell already appended; refusing to overwrite evidence')
    backup = path.with_name(path.stem+'.before-dual-gpu.ipynb')
    if backup.exists():
        raise FileExistsError(backup)
    before = notebook['cells'][:]
    notebook['cells'].extend([
        {'cell_type':'markdown','id':'ohayo-dual-gpu-guide','metadata':{},'source':[
            '# Khởi động phục vụ Qwen trên hai GPU\n',
            'Lần chuyển từ cell cũ: chọn **Restart & Clear Cell Outputs**, không Factory Reset. '
            'Sau đó chỉ chạy cell cuối mới này; không Run All và không chạy cell startup cũ.\n\n',
            'Bật GPU T4 x2 + Internet, gắn checkpoint NF4 đã lưu vào Input, bật hai Secrets '
            '`NGROK_AUTHTOKEN` và `OHAYO_INFERENCE_TOKEN`. Mã Provider đã nhúng trong cell; '
            'không cần chọn giữa các Input Provider trùng nhau.\n\n',
            'Mỗi GPU giữ một bản model, tối đa hai yêu cầu đồng thời; một câu hỏi chỉ chạy '
            'trên một GPU. Giới hạn đầu ra 1024 token, input 3584, timeout sinh 90 giây. '
            'Không chạy lại baseline hoặc tạo checkpoint.\n\n',
            'Chờ `DUAL_GPU_READY`, cập nhật URL nếu đổi và đồng bộ cấu hình backend theo '
            '`docs/kaggle-dual-gpu-serving.md`. Không dán token vào output/chat.\n']},
        {'cell_type':'code','id':'ohayo-dual-gpu-startup','metadata':{},'execution_count':None,
         'outputs':[],'source':startup_source().splitlines(keepends=True)},
    ])
    assert notebook['cells'][:-2] == before
    backup.write_bytes(original)
    path.write_text(json.dumps(notebook,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('notebooks',nargs='*',type=Path)
    parser.add_argument('--export',type=Path)
    args=parser.parse_args()
    for path in args.notebooks:
        append(path)
        print('Appended dual GPU cells:',path)
    if args.export:
        args.export.write_text(startup_source(),encoding='utf-8')
        print('Exported standalone cell:',args.export)
