"""Bundle the current comparison evidence for private teammate review."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

from scripts.comparison.protocol import verify_bundle, write_bundle, write_json
from scripts.qlora.data import read_json, require, sha_file
from scripts.qlora.runtime import inventory, verify_inventory

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'.private/comparison'

VERIFY = '''"""Verify an extracted private handoff; Python standard library only."""
import hashlib, json
from pathlib import Path
root=Path(__file__).resolve().parent
manifest=json.loads((root/'bundle-manifest.json').read_text(encoding='utf-8'))
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
assert actual == set(manifest) | {'bundle-manifest.json'}, 'Unexpected or missing files'
for name,info in manifest.items():
    p=(root/name).resolve()
    assert p.is_relative_to(root) and not (root/name).is_symlink(), 'Unsafe path'
    h=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''): h.update(chunk)
    assert p.stat().st_size==info['bytes'] and h.hexdigest()==info['sha256'], name
print('HANDOFF_BYTE_INTEGRITY_PASSED:',len(manifest),'files')
print('No training, main generation, semantic approval or repository changes performed.')
'''


def build(output):
    output=output.resolve()
    require(output.is_relative_to(ROOT/'.private') and not output.exists(),'NEW_PRIVATE_HANDOFF_REQUIRED')
    state=read_json(BASE/'experiment-readiness.json')
    require(state['main_completed'] and state['A_primary_review_count']==450 and
            state['A_secondary_review_count']==45,'HANDOFF_CURRENT_PROGRESS')
    for folder in (BASE/'assessment/main',BASE/'assessment/dev-v2',BASE/'runs/main-intake',
                   BASE/'prepared/benchmark-v3',BASE/'prepared/training-v2',BASE/'prepared/frozen-experiment'):
        verify_inventory(folder,read_json(folder/'manifest.json')['files'])
    for name in ('full-20261112T192034516377Z',):
        receipt=read_json(BASE/'runs'/(name+'-receipt.json'))
        archive=BASE/'runs'/(name+'.zip')
        require(sha_file(archive)==receipt['sha256'] and archive.stat().st_size==receipt['size_bytes'],
                'HANDOFF_TRAINING_ARCHIVE_PIN')
    output.mkdir(parents=True)
    contents=output/'contents'
    mapping=[]
    origins={}
    def add(source,name):
        source=Path(source)
        require(source.resolve().is_relative_to(ROOT) and not source.is_symlink(),'HANDOFF_SOURCE_PATH')
        target=contents/name
        require(not target.exists() and target.resolve().is_relative_to(contents),'HANDOFF_OVERWRITE_OR_PATH')
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        require(sha_file(source)==sha_file(target),'HANDOFF_COPY_HASH')
        origins[name]=source.relative_to(ROOT).as_posix()
    def tree(source,destination):
        for p in sorted(source.rglob('*')):
            require(not p.is_symlink(),'HANDOFF_SYMLINK')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':
                add(p,destination+'/'+p.relative_to(source).as_posix())
        mapping.append(dict(archive_path=destination,project_path=source.relative_to(ROOT).as_posix(),
                            action='Compare and integrate; never overwrite differing shared files blindly.'))
    for name in ('scripts/comparison','scripts/qlora','data/comparison'):
        tree(ROOT/name,'code/'+name)
    for name in ('comparison.ipynb','comparison_training.ipynb','comparison_main.ipynb'):
        add(ROOT/'notebooks'/name,'code/notebooks/'+name)
    add(ROOT/'docs/comparison.md','code/docs/comparison.md')
    add(ROOT/'backend/apps/ai/rag/conversation.py','code/backend/apps/ai/rag/conversation.py')
    mapping.append(dict(archive_path='code',project_path='.',action='Merge into the existing repository; not a complete application checkout.'))
    for source,destination in (
        ('prepared/benchmark-v3','inputs/benchmark'),('prepared/training-v2','inputs/training'),
        ('prepared/retrieval-v2','inputs/retrieval'),('prepared/frozen-experiment','inputs/frozen'),
        ('assessment/main','assessment/main'),('assessment/dev-v2','assessment/dev'),
        ('runs/main-intake','generation/main'),('prepared/training-runner-v3/baseline','generation/dev-old'),
        ('review-workbench','verification/benchmark-review')):
        tree(BASE/source,destination)
    add(BASE/'inputs/instruction/package.zip','inputs/instruction/package.zip')
    for source,destination in (
        ('prepared/main-runner-fixed','generation/runner'),
        ('prepared/training-runner-v3','training/runner')):
        for p in sorted((BASE/source).glob('*')):
            if p.is_file():add(p,destination+'/'+p.name)
        mapping.append(dict(archive_path=destination,project_path='.private/comparison/'+source,
                            action='Nested ZIP is the original immutable Kaggle Input; extract contents separately only if needed.'))
    for suffix in ('.zip','-receipt.json','-audit.json','-assessment.json','-verification.json'):
        name='full-20261112T192034516377Z'+suffix
        add(BASE/'runs'/name,'training/'+name)
    mapping.append(dict(archive_path='training/full-20261112T192034516377Z.zip',
        project_path='.private/comparison/runs/full-20261112T192034516377Z',
        action='Keep original ZIP and receipt in runs; extract ZIP to this new folder if reading checkpoints/logs.'))
    for suffix in ('.zip','-receipt.json'):
        name='dev-20261112T203002043135Z'+suffix
        add(BASE/'runs'/name,'generation/dev-new/'+name)
    mapping.append(dict(archive_path='generation/dev-new',project_path='.private/comparison/runs',
        action='Keep original ZIP and receipt unchanged.'))
    for name in ('rubric.md','source-manifest.json'):
        add(BASE/'inputs/v3/evaluator/main'/name,'inputs/evaluator/'+name)
    mapping.append(dict(archive_path='inputs/evaluator',project_path='.private/comparison/inputs/v3/evaluator/main',
        action='Scorer-only source registry/rubric; do not mount as generator Input.'))
    for name in ('dev.references.jsonl','rubric.md'):
        add(BASE/'inputs/v3/evaluator/dev'/name,'inputs/dev-evaluator/'+name)
    mapping.append(dict(archive_path='inputs/dev-evaluator',project_path='.private/comparison/inputs/v3/evaluator/dev',action='Scorer only.'))
    add(BASE/'prepared/semantic-review.json','verification/semantic-review.json')
    add(BASE/'prepared/input-readback.json','verification/input-readback.json')
    for name in ('data-review-report.json','group-intake-report.json','training-readback-1000.json',
                 'main-scoring-tests.json','main-scoring-validation.json','main-intake-tests.json',
                 'main-package-fix-tests.json','training-recovery-tests.json','freeze-tests.json','handoff-tests.json'):
        add(BASE/name,'verification/'+name)
    add(BASE/'experiment-readiness.json','verification/experiment-readiness.json')
    (contents/'verify.py').write_text(VERIFY,encoding='utf-8')
    write_json(contents/'restore-map.json',dict(folders=mapping,files=origins,
        note='Restore in the existing repository using these mappings. This verifier does not copy or overwrite repository files. '
             'Historical source-lock paths include old working copies intentionally not duplicated; replay the frozen runner ZIP, not a new freeze.'))
    write_json(contents/'handoff.json',dict(status='A_WORK_COMPLETE_PENDING_B_REVIEW_AND_GROUP_AGGREGATION',
        selected_adapter_sha256=state['selected_adapter_sha256'],freeze_sha256=state['freeze_sha256'],
        main_package_sha256=state['main_package_sha256'],training=dict(train=770,validation=114,holdout=116,updates=193),
        main=dict(questions=300,outputs=900,completed=897,output_limit=3),
        assessment=dict(A_primary=450,A_secondary=45,B_primary_completed=0,B_secondary_completed=0,
            group_adjudication='PENDING',semantic_scores_scope='A_PRIMARY_150_QUESTIONS_PER_ARM'),
        excluded=['Qwen base weights','Virtual environments and package/model caches','PDF originals already held by the team',
            'Legacy failed downloads and obsolete runner revisions','Old pilot adapter weights previously handed over',
            'Private credentials','.git','comparison-handoff.md'],
        dependencies=['Existing project checkout for backend imports/tests','27 matching source PDFs for new source verification',
            'Pinned Python packages in recipes; base model download/cache only if fresh GPU inference is required'],
        rights='PRIVATE_INTERNAL_RESEARCH_NO_PUBLIC_REDISTRIBUTION',chatbot_changed=False))
    archive=output/'comparison-handoff.zip'
    receipt=write_bundle(contents,archive)
    verify_bundle(archive)
    extracted=output/'readback'
    with ZipFile(archive) as zipped:
        require(zipped.testzip() is None,'HANDOFF_CRC')
        require(not any(n.endswith('comparison-handoff.md') for n in zipped.namelist()),'HANDOFF_NOTE_MUST_BE_SEPARATE')
        zipped.extractall(extracted)
    verified=subprocess.run([sys.executable,'-X','utf8','-B',str(extracted/'verify.py')],
        capture_output=True,text=True,encoding='utf-8',errors='replace')
    require(verified.returncode==0,'HANDOFF_EXTRACTED_READBACK:'+verified.stderr)
    write_json(output/'readback.json',{**receipt,'status':'HANDOFF_EXTRACTED_INTEGRITY_PASSED',
        'verifier_stdout':verified.stdout,'md_included':False,'source_artifacts_unchanged':True,
        'no_training_or_generation':True,'group_semantic_acceptance':'PENDING_B_REVIEW'})
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(parser.parse_args().output),indent=2))
