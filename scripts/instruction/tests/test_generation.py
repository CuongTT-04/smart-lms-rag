from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.instruction.common import ROOT, InstructionError, jsonl_bytes, read_jsonl
from scripts.instruction.generate_candidates import generate
from scripts.instruction.tests.support import draft, record, resources


class GeneratorTests(unittest.TestCase):
    def test_stable_ids_restart_and_no_duplicate_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'records.jsonl';one=draft(record())
            result=generate([one],path,resources(),preview=True)
            self.assertEqual(result['added_count'],1)
            before=path.read_bytes()
            result=generate([one],path,resources(),preview=True)
            self.assertEqual(result['added_count'],0);self.assertEqual(path.read_bytes(),before)
            generate([one,draft(record(2,'summary'))],path,resources(),preview=True)
            self.assertEqual([row['record_id'] for row in read_jsonl(path)],['FX_W5_00001','FX_W5_00002'])

    def test_changed_draft_never_overwrites_old_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'records.jsonl';one=draft(record());generate([one],path,resources(),preview=True)
            before=path.read_bytes();one['target_text']='Nội dung khác [1].'
            with self.assertRaisesRegex(InstructionError,'EXISTING_DRAFT_CHANGED'):
                generate([one],path,resources(),preview=True)
            self.assertEqual(path.read_bytes(),before)

    def test_invalid_batch_is_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'records.jsonl';one=draft(record());generate([one],path,resources(),preview=True)
            before=path.read_bytes();bad=draft(record(3,'hint'));bad['target_text']='COMPARE [1] [1]'
            with self.assertRaises(ValueError):
                generate([draft(record(2,'summary')),bad],path,resources(),preview=True)
            self.assertEqual(path.read_bytes(),before)

    def test_drafts_cannot_supply_review_gold_or_ids(self):
        for key,value in [('record_id','FX_W5_00077'),('review','ACCEPT'),('ground_truth','answer')]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                bad=draft(record());bad[key]=value
                with self.assertRaisesRegex(InstructionError,'INVALID_DRAFT_FIELDS'):
                    generate([bad],Path(tmp)/'records.jsonl',resources(),preview=True)

    def test_wrong_author_and_nonstring_question_are_rejected(self):
        for key,value in [('author_member','B'),('question',42)]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                bad=draft(record());bad[key]=value
                with self.assertRaises(InstructionError):
                    generate([bad],Path(tmp)/'records.jsonl',resources(),preview=True)

    def test_generator_does_not_mutate_input_or_create_approvals(self):
        with tempfile.TemporaryDirectory() as tmp:
            one=draft(record());before=deepcopy(one);path=Path(tmp)/'records.jsonl'
            result=generate([one],path,resources(),preview=True)
            self.assertEqual(one,before);self.assertEqual(result['model_calls'],0)
            self.assertNotIn('review',read_jsonl(path)[0])

    def test_benchmark_draft_rejected(self):
        from scripts.instruction.common import digest,question_key
        with tempfile.TemporaryDirectory() as tmp:
            res=resources();one=draft(record());res.protected_hashes.add(digest(question_key(one['question']).encode()))
            with self.assertRaisesRegex(InstructionError,'BENCHMARK_QUESTION'):
                generate([one],Path(tmp)/'records.jsonl',res,preview=True)

    def test_cli_preview_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'drafts.jsonl';source.write_bytes(jsonl_bytes([draft(record())]))
            output=Path(tmp)/'records.jsonl'
            cmd=[sys.executable,'scripts/instruction/generate_candidates.py','--drafts',str(source),'--output',str(output),'--preview']
            for _ in range(2):
                result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(len(read_jsonl(output)),1)

    def test_cli_does_not_overwrite_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'drafts.jsonl';before=jsonl_bytes([draft(record())]);source.write_bytes(before)
            result=subprocess.run([sys.executable,'scripts/instruction/generate_candidates.py','--drafts',str(source),
                '--output',str(source),'--preview'],cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertEqual(source.read_bytes(),before)

    def test_resuming_an_earlier_batch_preserves_later_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'records.jsonl'
            rows=[draft(record()),draft(record(2,'summary')),draft(record(3,'hint'))]
            generate(rows,output,resources(),preview=True)
            before=output.read_bytes()
            result=generate(rows[:1],output,resources(),preview=True)
            self.assertEqual(result['added_count'],0)
            self.assertEqual(result['record_count'],3)
            self.assertEqual(output.read_bytes(),before)


if __name__=='__main__': unittest.main()
