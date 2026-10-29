from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.instruction.common import ROOT,InstructionError,digest,json_bytes,jsonl_bytes,read_json,read_jsonl
from scripts.instruction.export_sft_dataset import export,validate_plan
from scripts.instruction.tests.support import plan,record,rehash,resources,reviews,production_resource


class ExportTests(unittest.TestCase):
    def rows(self):
        return [record(),record(2,'summary'),record(3,'hint')]

    def test_deterministic_payload_manifest_and_metadata_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.rows();scores=reviews(rows);splits=plan(rows);original=deepcopy((rows,scores,splits))
            first=Path(tmp)/'first';second=Path(tmp)/'second'
            result=export(rows,scores,splits,first,resources(),preview=True)
            export(list(reversed(rows)),scores,splits,second,resources(),preview=True)
            self.assertEqual((rows,scores,splits),original)
            self.assertEqual(result['status'],'FIXTURE_PREVIEW_NOT_DATASET')
            self.assertEqual(result['real_dataset_record_count'],0)
            self.assertEqual(result['validation']['tokenizer_eos_loss_mask'],'NOT_RUN')
            self.assertFalse(result['quality_verified'])
            self.assertNotIn('manifest.json',result['files'])
            for name in ['manifest.json',*result['files']]:
                self.assertEqual((first/name).read_bytes(),(second/name).read_bytes())
            for name,entry in result['files'].items():
                self.assertEqual(digest((first/name).read_bytes()),entry['sha256'])
                self.assertEqual((first/name).stat().st_size,entry['size_bytes'])
            for meta in read_jsonl(first/'metadata.jsonl'):
                sft=read_jsonl(first/(meta['split']+'.jsonl'))[meta['row_index']]
                self.assertEqual(set(sft),{'prompt','completion'})
                self.assertEqual(sft['completion'][0]['content'],meta['record']['target_text'])
                self.assertNotIn('self_review',json.loads(sft['prompt'][1]['content']))

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out';out.mkdir();(out/'keep').write_text('unchanged')
            rows=self.rows()
            with self.assertRaisesRegex(InstructionError,'OUTPUT_ALREADY_EXISTS'):
                export(rows,reviews(rows),plan(rows),out,resources(),preview=True)
            self.assertEqual((out/'keep').read_text(),'unchanged')

    def test_all_real_exports_reject_fixture_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.rows()
            with self.assertRaisesRegex(InstructionError,'FIXTURE_SCOPE_MISMATCH'):
                export(rows,reviews(rows),plan(rows),Path(tmp)/'out',resources())

    def test_production_path_remains_candidate_pending_final_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            first,res=production_resource(tmp);rows=[first]
            for number,chapter in [(2,'ch03.pdf'),(3,'ch05.pdf')]:
                row=record(number);context=row['contexts'][0]
                row.update(record_id=f'W5_A_{number:05d}',course_code='THMLN',
                    source_identity_scope='offline_corpus',source_group_ids=['THMLN:'+chapter])
                context.update(source_checksum=first['contexts'][0]['source_checksum'],
                    rights_reference=first['contexts'][0]['rights_reference'])
                source=deepcopy(res.sources[0]);source.update(document_id=context['document_id'],
                    version_id=context['version_id'],source_group_id='THMLN:'+chapter,source_doc=chapter)
                res.sources.append(source);rows.append(rehash(row))
            res.__post_init__()
            with patch('scripts.instruction.common.read_pdf_pages',return_value=[first['contexts'][0]['text']]):
                result=export(rows,reviews(rows),plan(rows),Path(tmp)/'out',res)
            self.assertEqual(result['status'],'CANDIDATE_PENDING_B_REVIEW')
            self.assertEqual(result['real_dataset_record_count'],3)
            self.assertEqual(result['validation']['final_b_review'],'PENDING')
            self.assertFalse(result['full_target_peer_accepted'])

    def test_stale_reviews_and_plan_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.rows();scores=reviews(rows);splits=plan(rows)
            rows[0]['target_text']='Một đáp án đã thay đổi [1].';rehash(rows[0])
            out=Path(tmp)/'out'
            with self.assertRaisesRegex(InstructionError,'SELF_REVIEW_MISSING_OR_STALE'):
                export(rows,scores,splits,out,resources(),preview=True)
            self.assertFalse(out.exists())
            with self.assertRaisesRegex(InstructionError,'STALE_SPLIT_HASH'):
                export(rows,reviews(rows),splits,out,resources(),preview=True)

    def test_group_leakage_source_document_variant_parent_and_multi_source(self):
        for kind in ['group','document','variant','parent','multi']:
            with self.subTest(kind=kind):
                rows=self.rows()
                if kind=='group':rows[1]['source_group_ids']=rows[0]['source_group_ids'][:]
                if kind=='document':rows[1]['contexts'][0]['document_id']=rows[0]['contexts'][0]['document_id']
                if kind=='variant':rows[1]['variant_family_id']=rows[0]['variant_family_id']
                if kind=='parent':rows[1]['parent_record_id']=rows[0]['record_id']
                if kind=='multi':rows[1]['source_group_ids']+=rows[0]['source_group_ids']
                rehash(rows[1])
                with self.assertRaisesRegex(InstructionError,'SPLIT_GROUP_LEAKAGE'):
                    validate_plan(rows,plan(rows),resources().contract)

    def test_split_seed_missing_ids_unknown_and_empty_split_fail(self):
        rows=self.rows()
        for kind in ['seed','missing','unknown','empty']:
            with self.subTest(kind=kind):
                splits=plan(rows)
                if kind=='seed':splits['seed']=17
                if kind=='missing':splits['assignments'].pop(rows[0]['record_id'])
                if kind=='unknown':splits['assignments'][rows[0]['record_id']]='test'
                if kind=='empty':splits['assignments']={row['record_id']:'train' for row in rows}
                with self.assertRaises(InstructionError):validate_plan(rows,splits,resources().contract)

    def test_write_failure_does_not_publish_partial_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out';rows=self.rows()
            with patch('scripts.instruction.export_sft_dataset.os.rename',side_effect=OSError('simulated')):
                with self.assertRaises(OSError):export(rows,reviews(rows),plan(rows),out,resources(),preview=True)
            self.assertFalse(out.exists())
            self.assertEqual([p for p in Path(tmp).iterdir() if p.is_dir()],[])

    def test_output_cannot_contain_an_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.rows();inside=Path(tmp)/'records.jsonl';inside.write_bytes(jsonl_bytes(rows))
            with self.assertRaisesRegex(InstructionError,'OUTPUT_OVERLAPS_INPUT'):
                export(rows,reviews(rows),plan(rows),Path(tmp),resources(),preview=True,input_paths=[inside])

    def test_cli_smoke_produces_five_files_without_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.rows();root=Path(tmp)
            (root/'rows.jsonl').write_bytes(jsonl_bytes(rows));(root/'reviews.jsonl').write_bytes(jsonl_bytes(reviews(rows)))
            (root/'split.json').write_bytes(json_bytes(plan(rows)))
            command=[sys.executable,'scripts/instruction/export_sft_dataset.py','--inputs',str(root/'rows.jsonl'),
                '--reviews',str(root/'reviews.jsonl'),'--split-plan',str(root/'split.json'),
                '--output',str(root/'out'),'--preview']
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(len(list((root/'out').iterdir())),5)
            self.assertEqual(read_json(root/'out/manifest.json')['model_calls'],0)

    def test_no_final_release_mode_is_silently_available(self):
        result=subprocess.run([sys.executable,'scripts/instruction/export_sft_dataset.py','--final'],
                              cwd=ROOT,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)


if __name__=='__main__': unittest.main()
