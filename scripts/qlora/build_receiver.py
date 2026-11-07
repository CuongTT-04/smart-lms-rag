"""Prepare a receiver-only Kaggle bootstrap, keeping the reviewed GPU logic intact."""
import argparse
import copy
import io
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from .data import require, sha_file
from .runtime import write_json, inventory

PILOT_BUNDLE_SHA='2b44e35f7386b506955e9fad29541490c052129a8af6ae0eef7e4f0b7f7c0707'

def receiver_notebook(original, tools_sha):
    result=copy.deepcopy(original)
    cell=''.join(result['cells'][1]['source'])
    cell=cell.replace('7fd1a989602f72951e3e7626f605d6509234183e04ef165f21e8eca35fc15b55',tools_sha)
    cell=cell.replace('/kaggle/working/qlora-preparation','/kaggle/working/qlora-cuong-verification')
    cell=cell.replace("assert len(candidates) == 1, f'{name}: can dung 1 Input khop checksum, tim thay {len(candidates)}'",
        "assert candidates, f'{name}: khong co Input khop checksum'")
    result['cells'][1]['source']=cell.splitlines(keepends=True)
    cell=''.join(result['cells'][2]['source']).replace('/kaggle/working/qlora-env','/kaggle/working/qlora-cuong-env')
    cell=cell.replace("'--environment-only', '--output'", "'--environment-only', '--environment', str(VENV), '--output'")
    result['cells'][2]['source']=cell.splitlines(keepends=True)
    result['cells'][0]['source']=['# W6 — Cường kiểm chứng độc lập trên Kaggle\n',
        'Gắn Input riêng tư gồm qlora-environment-input.zip và ZIP pilot gốc. Bật GPU T4 x2 và Internet.\n',
        'Chạy 6 code cell theo thứ tự. Chỉ dùng GPU 0; GPU 1 không cần cho bài kiểm này. Dừng server chatbot trước.\n',
        'Lần đầu có thể tải base model khoảng 15 GB. Không tải cache/weights lên Git.\n',
        'Nạp adapter và so sánh 20 ca, sau đó resume đúng 1 update (25 → 26), không train lại 50 bước.\n',
        'Cell cuối xuất ZIP, receipt và audit: tải về để kiểm checksum và ghi bằng chứng riêng của Cường.\n',
        'Notebook được chuẩn bị sẵn; chỉ kết quả thực chạy mới chứng minh GPU reload/resume.\n']
    for i,c in enumerate(result['cells']):
        if c['cell_type']=='code':
            c['outputs']=[];c['execution_count']=None
            compile(''.join(c['source']),f'receiver-cell-{i}','exec')
    result['metadata']['ohayo_receiver']=dict(member='B',name='Trần Tuấn Cường',gpu_executed=False,
        frozen_gpu_cells_unchanged=[4,5,6],purpose='INDEPENDENT_RELOAD_RESUME_PENDING_EXECUTION')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    root=Path(__file__).resolve().parents[2]
    require(args.output.resolve().is_relative_to(root/'.private') and not args.output.exists(),'NEW_PRIVATE_OUTPUT_REQUIRED')
    require(sha_file(args.bundle)==PILOT_BUNDLE_SHA,'PILOT_BUNDLE_IDENTITY')
    args.output.mkdir(parents=True)
    buffer=io.BytesIO()
    # Current CPU/environment tools are separate from the frozen trainer embedded
    # in GPU cell 4. Resume therefore retains the original source identity.
    with ZipFile(buffer,'w',compression=ZIP_DEFLATED) as zipped:
        for path in sorted((root/'scripts/qlora').glob('*')):
            if path.is_file() and path.suffix in ('.py','.txt'):
                zipped.write(path,path.relative_to(root).as_posix())
        zipped.write(root/'configs/qlora-pilot.json','configs/qlora-pilot.json')
    import hashlib
    raw=buffer.getvalue();tool_sha=hashlib.sha256(raw).hexdigest()
    with ZipFile(args.output/'qlora-environment-input.zip','x',compression=ZIP_DEFLATED) as zipped:
        zipped.writestr('tools.bundle',raw)
        zipped.writestr('pilot.bundle',args.bundle.read_bytes())
    notebook=receiver_notebook(json.loads((root/'notebooks/qlora_verification.ipynb').read_text(encoding='utf8')),tool_sha)
    write_json(args.output/'qlora_cuong_verification.ipynb',notebook)
    write_json(args.output/'receipt.json',dict(files=inventory(args.output),tools_bundle_sha256=tool_sha,
        pilot_bundle_sha256=PILOT_BUNDLE_SHA,gpu_executed=False))
    print('RECEIVER_KAGGLE_INPUT_PREPARED: '+str(args.output))

if __name__=='__main__':main()
