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
