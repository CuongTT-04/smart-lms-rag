import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from scripts.w5.common import ROOT, content_hash, read_jsonl


class CLITests(unittest.TestCase):
    def command(self,*args):
        return subprocess.run([sys.executable,'-B',str(ROOT/'scripts/w5/validate_instruction_dataset.py'),*map(str,args)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')

    def test_fixture_smoke_cli_is_not_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'report.json'
            result=self.command('--input','data/fixtures/w5-instruction-contract.jsonl','--fixture-mode','--report',report)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(data['eligible_ids'],[])
            result=self.command('--input','data/fixtures/w5-instruction-contract.jsonl','--fixture-mode','--stage','release','--report',report)
            self.assertEqual(result.returncode,1,result.stderr)

    def test_invalid_target_exits_nonzero_with_findings(self):
        row=read_jsonl(ROOT/'data/fixtures/w5-instruction-contract.jsonl')[0]
        row['target_text']='Answer [9]';row['content_sha256']=content_hash(row)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.jsonl';path.write_text(json.dumps(row,ensure_ascii=False)+'\n',encoding='utf-8')
            report=Path(tmp)/'report.json'
            result=self.command('--input',path,'--fixture-mode','--report',report)
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertIn('TARGET_FORMAT',{f['code'] for f in json.loads(report.read_text(encoding='utf-8'))['findings']})

    def test_report_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'records.jsonl';before=(ROOT/'data/fixtures/w5-instruction-contract.jsonl').read_bytes();path.write_bytes(before)
            result=self.command('--input',path,'--fixture-mode','--report',path)
            self.assertEqual(result.returncode,2)
            self.assertEqual(path.read_bytes(),before)


class ReleaseSplitBindingTests(unittest.TestCase):
    """Exercise the CLI boundary; source/review validation has its own suite."""
    def setUp(self):
        import copy
        from scripts.w5.common import load_contract, digest
        from scripts.w5.splitting import build_split_plan
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.contract=load_contract(ROOT/'data/instruction/w5/contract')
        self.contract['training']['source_hashes']={}
        self.rows=[]
        fixture=read_jsonl(ROOT/'data/fixtures/w5-instruction-contract.jsonl')[0]
        for i in range(6):
            row=copy.deepcopy(fixture)
            row.update(record_id=f'TEST_{i}',source_group_ids=[f'SOURCE_{i}'],variant_family_id=f'FAMILY_{i}')
            row['content_sha256']=content_hash(row)
            self.rows.append(row)
        self.quality=dict(passed=True,eligible_ids=[r['record_id'] for r in self.rows],confirmed_pairs=[])
        self.plan=build_split_plan(self.rows,self.quality['eligible_ids'],[],42)
        self.plan['contract_fingerprint']=self.contract['fingerprint']
        self.plan_path=self.folder/'split-plan.json'
        self.plan_path.write_text(json.dumps(self.plan),encoding='utf-8')
        self.files={}
        for split,ids in self.plan['splits'].items():
            payload=[{'test_record_id':rid} for rid in ids]
            sidecar=[dict(record_id=rid,content_sha256=next(r['content_sha256'] for r in self.rows if r['record_id']==rid),split=split,sft_sha256=digest(item)) for rid,item in zip(ids,payload)]
            self.files[split]=(self.folder/(split+'.jsonl'),self.folder/(split+'.metadata.jsonl'))
            for path,items in zip(self.files[split],(payload,sidecar)):
                self.write_rows(path,items)

    def write_rows(self,path,rows):
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')

    def audit(self,order=None):
        from unittest.mock import patch
        from scripts.w5 import cli
        order=order or list(self.files)
        args=['audit','--input','unused.jsonl','--payload',*[str(self.files[s][0]) for s in order],
              '--sidecar',*[str(self.files[s][1]) for s in order],
              '--split-plan',str(self.plan_path),'--report',str(self.folder/'report.json')]
        # Stop at the real download boundary: these tests need no network/model.
        with patch.object(sys,'argv',args), patch.object(cli,'inputs',return_value=(self.contract,self.rows,self.quality)), patch('huggingface_hub.snapshot_download',side_effect=RuntimeError('TOKENIZER_BOUNDARY')):
            return cli.training_main()

    def test_valid_split_files_reach_tokenizer_even_in_different_argument_order(self):
        with self.assertRaisesRegex(RuntimeError,'TOKENIZER_BOUNDARY'):
            self.audit(list(reversed(self.files)))

    def test_swapped_train_holdout_files_with_matching_sidecars_are_rejected(self):
        for i in (0,1):
            train=self.files['train'][i];hold=self.files['instruction_holdout'][i]
            a,b=train.read_bytes(),hold.read_bytes();train.write_bytes(b);hold.write_bytes(a)
        with self.assertRaisesRegex(ValueError,'split|Split'):
            self.audit()

    def test_swapped_single_rows_with_matching_sidecars_are_rejected(self):
        for i in (0,1):
            train=self.files['train'][i];hold=self.files['instruction_holdout'][i]
            a,b=read_jsonl(train),read_jsonl(hold);a[0],b[0]=b[0],a[0]
            self.write_rows(train,a);self.write_rows(hold,b)
        with self.assertRaisesRegex(ValueError,'split|Split'):
            self.audit()

    def test_shifted_sidecar_file_boundaries_are_rejected(self):
        train=self.files['train'][1];hold=self.files['instruction_holdout'][1]
        a,b=read_jsonl(train),read_jsonl(hold);b.insert(0,a.pop())
        self.write_rows(train,a);self.write_rows(hold,b)
        with self.assertRaisesRegex(ValueError,'count|split|Split'):
            self.audit()
