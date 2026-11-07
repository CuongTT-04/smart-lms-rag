"""Build a private, self-verifying pre-training handoff. Never sends or uploads it."""
import argparse
import inspect
import json
from pathlib import Path
import sys
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.w6 import contracts
from scripts.w6.contracts import ROOT,require,read_json,sha_file,write_once,write_json,within


def verify_tree(root,expected_manifest_sha256=None):
    root=Path(root).resolve();path=root/'package-manifest.json'
    if expected_manifest_sha256:require(sha_file(path)==expected_manifest_sha256,'PACKAGE_MANIFEST_HASH')
    manifest=read_json(path)
    entries=list(root.rglob('*'))
    require(not any(p.is_symlink() for p in entries),'PACKAGE_SYMLINK')
    actual={p.relative_to(root).as_posix() for p in entries if p.is_file()}
    require(actual==set(manifest['files'])|{'package-manifest.json','SHA256SUMS.txt'},'PACKAGE_FILE_SET')
    for name,info in manifest['files'].items():
        member=within(root,name)
        require(member.is_file() and member.stat().st_size==info['size_bytes'] and sha_file(member)==info['sha256'],'PACKAGE_MEMBER_INTEGRITY:'+name)
    sums={}
    for line in (root/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        digest,name=line.split('  ',1);require(name not in sums,'DUPLICATE_PACKAGE_SUM');sums[name]=digest
    require(set(sums)==set(manifest['files'])|{'package-manifest.json'},'PACKAGE_SUM_SET')
    require(all(sha_file(within(root,name))==value for name,value in sums.items()),'PACKAGE_SUM_INTEGRITY')
    return {'passed':True,'files_checked':len(manifest['files']),'package_manifest_sha256':sha_file(path)}


def verifier_source():
    header='''# Standalone bootstrap verifies code/data bytes before importing bundled code.
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
'''
    helpers='\n\n'.join(inspect.getsource(f) for f in [contracts.require,contracts.sha_bytes,contracts.sha_file,
        contracts.loads,contracts.read_json,contracts.within,verify_tree])
    body='''
def main():
    p=argparse.ArgumentParser(description='Verify the private W6 handoff without model weights or GPU.')
    p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--archive',type=Path)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--source-root',type=Path)
    p.add_argument('--run-tests',action='store_true')
    args=p.parse_args();here=Path(__file__).resolve().parent
    receipt=read_json(args.receipt)
    if args.archive:require(sha_file(args.archive)==receipt['zip_sha256'],'ZIP_RECEIPT_MISMATCH')
    tree=verify_tree(here,receipt['package_manifest_sha256'])
    source=here/'source';sys.path.insert(0,str(source))
    from scripts.w6.contracts import write_json
    from scripts.w6.tokenizer import load_tokenizer
    from scripts.w6.validate_dataset import validate
    folder=here/'data/pilot-v2';contract=read_json(folder/'training-contract.json')
    tokenizer=load_tokenizer(here/'tokenizer',contract,read_json(folder/'tokenizer-reference.json'))
    data=validate(folder/'manifest.json',tokenizer,expected_manifest_sha256=receipt['pilot_manifest_sha256'],
                  source_root=args.source_root)
    tests='NOT_REQUESTED'
    if args.run_tests:
        env=dict(os.environ,PYTHONPATH=str(source),PYTHONDONTWRITEBYTECODE='1')
        result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(source/'scripts/w6/tests')],
                              cwd=here,env=env,capture_output=True,text=True)
        print(result.stdout[-2000:]);print(result.stderr[-3000:])
        require(result.returncode==0,'BUNDLED_TESTS_FAILED');tests='PASSED'
    require(not args.report.resolve().is_relative_to(here),'SAVE_REPORT_OUTSIDE_IMMUTABLE_HANDOFF')
    write_json(args.report,{'passed':True,'package':tree,'pilot':data,'tests':tests,
                          'training':'NOT_RUN','gpu_used':False,'human_peer_approval_created':False})
    print('W6_HANDOFF_VERIFIED: 160 records; no holdout; tokenizer/masks/provenance recomputed; training NOT_RUN.')

if __name__=='__main__':main()
'''
    source=header+helpers+'\n'+body
    compile(source,'verify_handoff.py','exec');return source


def archive_path(output):
    return Path(str(output)+'.zip')


def build(pilot,tokenizer,output,guide,verification_report):
    pilot=Path(pilot);tokenizer=Path(tokenizer);output=Path(output)
    data=read_json(pilot/'manifest.json');contract=read_json(pilot/'training-contract.json')
    verified=read_json(verification_report)
    require(verified.get('passed') is True and verified['manifest_sha256']==sha_file(pilot/'manifest.json'),'UNVERIFIED_PILOT')
    files={}
    def put(name,raw):
        path=within(output,name);write_once(path,raw)
        files[name]=dict(sha256=sha_file(path),size_bytes=path.stat().st_size)
    put('README.md',Path(guide).read_bytes())
    put('docs/weekly/W6/phan-cong-w6.md',(ROOT/'docs/weekly/W6/phan-cong-w6.md').read_bytes())
    put('verify_handoff.py',verifier_source().encode('utf-8'))
    for name in [*data['files'],'manifest.json','SHA256SUMS.txt']:
        put('data/pilot-v2/'+name,(pilot/name).read_bytes())
    for name,info in read_json(pilot/'tokenizer-reference.json')['files'].items():
        require(sha_file(tokenizer/name)==info['sha256'],'TOKENIZER_COPY_HASH')
        put('tokenizer/'+name,(tokenizer/name).read_bytes())
    for name,expected in contract['source_code_sha256'].items():
        raw=(ROOT/name).read_bytes()
        require(contracts.sha_bytes(raw.replace(b'\r\n',b'\n'))==expected,'CODE_SNAPSHOT_MISMATCH')
        put('source/'+name,raw)
    for path in sorted((ROOT/'scripts/w6').rglob('*')):
        if path.is_file() and path.suffix in ('.py','.md','.txt') and '__pycache__' not in path.parts:
            put('source/'+path.relative_to(ROOT).as_posix(),path.read_bytes())
    for name in ['data/w6/training-contract.json','data/w6/source-allocation.json','data/w6/record-allocation.csv',contract['source_manifest']['path']]:
        put('source/'+name,(ROOT/name).read_bytes())
    put('reports/preparation-verification.json',Path(verification_report).read_bytes())
    manifest=dict(schema_version='w6-private-handoff-v1',status='TECHNICAL_HANDOFF_READY_TRAINING_NOT_RUN',
        sender_responsible_member='Trần Tuấn Cường',recipient='Vũ Nam Dương',files=files,
        pilot_manifest_sha256=sha_file(pilot/'manifest.json'),source_archive_sha256=data['source_archive_sha256'],
        contract_sha256=contracts.digest(contract),counts=data['counts'],new_samples_authored=0,
        public_redistribution_allowed=False,model_weights_included=False,holdout_payload_included=False,
        human_peer_approval_created=False,training='NOT_RUN')
    write_json(output/'package-manifest.json',manifest)
    sums={**files,'package-manifest.json':dict(sha256=sha_file(output/'package-manifest.json'))}
    write_once(output/'SHA256SUMS.txt',''.join(f'{v["sha256"]}  {name}\n' for name,v in sorted(sums.items())).encode())
    verify_tree(output)
    stream=__import__('io').BytesIO()
    with ZipFile(stream,'w',compression=ZIP_DEFLATED,compresslevel=9) as z:
        for path in sorted(p for p in output.rglob('*') if p.is_file()):
            info=ZipInfo(path.relative_to(output).as_posix(),date_time=(2026,11,1,0,0,0))
            info.compress_type=ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,path.read_bytes())
    archive=archive_path(output);write_once(archive,stream.getvalue())
    receipt=dict(schema_version='w6-handoff-receipt-v1',archive=archive.name,
        zip_sha256=sha_file(archive),size_bytes=archive.stat().st_size,
        package_manifest_sha256=sha_file(output/'package-manifest.json'),
        pilot_manifest_sha256=sha_file(pilot/'manifest.json'),contract_sha256=contracts.digest(contract),
        counts=data['counts'],training='NOT_RUN',public_redistribution_allowed=False)
    write_json(output.parent/(output.name+'.receipt.json'),receipt)
    return archive,receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pilot',type=Path,required=True);p.add_argument('--tokenizer',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--guide',type=Path,required=True)
    p.add_argument('--verification-report',type=Path,required=True)
    args=p.parse_args();archive,receipt=build(args.pilot,args.tokenizer,args.output,args.guide,args.verification_report)
    print('PRIVATE_HANDOFF_BUILT:',archive,'sha256='+receipt['zip_sha256'])
