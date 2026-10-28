from copy import deepcopy
import json
import csv
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.instruction.common import (ROOT, InstructionError, canonical, content_hash, digest,
    check_text_checksum, load_resources, loads, project_sft, read_pdf_pages, read_reviews, validate_record, validate_records, validate_reviews)
from scripts.instruction.tests.support import production_resource, record, rehash, resources, reviews


class CandidateValidationTests(unittest.TestCase):
    def test_all_four_task_types_validate(self):
        for number,task in enumerate(['qa','summary','hint','insufficient_evidence'],1):
            with self.subTest(task=task):
                validate_record(record(number,task),resources(),preview=True)

    def test_hash_is_nfc_canonical_and_binds_provenance(self):
        import unicodedata
        row=record(); other=deepcopy(row)
        other['question']=unicodedata.normalize('NFD',row['question'])
        self.assertEqual(content_hash(row),content_hash(other))
        other['provenance']['created_at']='2026-10-29T09:00:00+07:00'
        self.assertNotEqual(content_hash(row),content_hash(other))
        with self.assertRaisesRegex(InstructionError,'CONTENT_HASH_MISMATCH'):
            validate_record(other,resources(),preview=True)

    def test_array_order_is_bound_to_hash(self):
        row=record(); row['source_group_ids'].append('FIXTURE:other')
        first=content_hash(row); row['source_group_ids'].reverse()
        self.assertNotEqual(first,content_hash(row))

    def test_duplicate_json_keys_and_nonfinite_values_fail(self):
        for value in ['{"a":1,"a":2}','{"a":NaN}']:
            with self.subTest(value=value),self.assertRaises(InstructionError): loads(value)
        with self.assertRaises(ValueError): canonical({'number':float('inf')})

    def test_benchmark_checksum_allows_only_recorded_line_ending_conversion(self):
        data=b'{"question":"example"}\n'
        self.assertEqual(check_text_checksum(data,digest(data)),'EXACT_BYTES')
        self.assertEqual(check_text_checksum(data.replace(b'\n',b'\r\n'),digest(data)),'CRLF_TO_LF_EQUIVALENT')
        with self.assertRaisesRegex(InstructionError,'BENCHMARK_CHANGED'):
            check_text_checksum(data.replace(b'example',b'changed'),digest(data))

    def test_unknown_fields_private_exercise_and_invalid_types_fail(self):
        for field,value in [('ground_truth','secret'),('page_number',True),('document_id','bad-uuid')]:
            row=record()
            if field=='ground_truth': row[field]=value
            else: row['contexts'][0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(InstructionError,'INVALID_SCHEMA'):
                validate_record(rehash(row),resources(),preview=True)
        row=record(3,'hint');row['exercise']={'exercise_id':'x','question':'x','choices':[],'answer_key':'secret'}
        with self.assertRaisesRegex(InstructionError,'INVALID_SCHEMA'):
            validate_record(rehash(row),resources(),preview=True)

    def test_unknown_citation_mixed_refusal_cjk_and_wrong_hint_fail(self):
        for task,target in [('qa','Một câu trả lời [9].'),('qa','INSUFFICIENT_EVIDENCE [1]'),
                            ('qa','中文 [1]'),('hint','Hãy xem nguồn [1].'),('hint','COMPARE [1] [1]')]:
            row=record(3 if task=='hint' else 1,task);row['target_text']=target
            with self.subTest(target=target),self.assertRaises(ValueError):
                validate_record(rehash(row),resources(),preview=True)

    def test_qa_sentinel_and_api_json_are_not_targets(self):
        for target in ['INSUFFICIENT_EVIDENCE','{"answer":"test [1]"}']:
            row=record();row['target_text']=target
            with self.subTest(target=target),self.assertRaises(ValueError):
                validate_record(rehash(row),resources(),preview=True)

    def test_summary_and_hint_are_projected_using_runtime_builder(self):
        for number,task in [(2,'summary'),(3,'hint')]:
            row=record(number,task); before=deepcopy(row)
            result=project_sft(row,resources(),preview=True)
            self.assertEqual(row,before)
            self.assertEqual([x['role'] for x in result['prompt']],['system','user'])
            self.assertEqual(result['completion'],[{'role':'assistant','content':row['target_text']}])
            payload=json.loads(result['prompt'][1]['content'])
            self.assertEqual(set(payload),{'question','mode','evidence','exercise'})
            self.assertEqual(set(payload['evidence'][0]),{'source_id','chunk_id','text','document_id',
                'version_id','document_title','page_number','section_title','citation_label'})
            self.assertEqual(payload['evidence'][0]['citation_label'],1)

    def test_citation_uses_position_not_source_id(self):
        row=record();row['contexts'][0]['source_id']='S8'
        result=project_sft(rehash(row),resources(),preview=True)
        self.assertEqual(json.loads(result['prompt'][1]['content'])['evidence'][0]['citation_label'],1)
        self.assertEqual(result['completion'][0]['content'],row['target_text'])

    def test_fixture_cannot_pass_as_real_data(self):
        with self.assertRaisesRegex(InstructionError,'FIXTURE_SCOPE_MISMATCH'):
            validate_record(record(),resources(),preview=False)

    def test_empty_evidence_and_duplicate_sources_fail(self):
        row=record();row['contexts']=[]
        with self.assertRaises(ValueError): validate_record(rehash(row),resources(),preview=True)
        row=record();row['contexts'].append(deepcopy(row['contexts'][0]))
        with self.assertRaisesRegex(InstructionError,'DUPLICATE_SOURCE_ID'):
            validate_record(rehash(row),resources(),preview=True)

    def test_exact_benchmark_and_parent_seed_fail(self):
        res=resources(); row=record()
        res.protected_hashes.add(digest(' '.join(row['question'].casefold().split()).encode('utf-8')))
        with self.assertRaisesRegex(InstructionError,'BENCHMARK_QUESTION'):
            validate_record(row,res,preview=True)
        res=resources();res.protected_ids.add('THMLN_QA_001');row['parent_record_id']='THMLN_QA_001'
        with self.assertRaisesRegex(InstructionError,'BENCHMARK_SEED'):
            validate_record(rehash(row),res,preview=True)

    def test_near_benchmark_is_flagged_not_auto_approved(self):
        row=record();res=resources();res.protected_questions=[row['question']+' ']
        with self.assertRaisesRegex(InstructionError,'BENCHMARK_NEAR_DUPLICATE'):
            validate_record(row,res,preview=True)

    def test_common_target_alone_is_not_benchmark_leakage(self):
        validate_records([record(1),record(5)],resources(),preview=True)

    def test_duplicate_records_and_questions_fail(self):
        with self.assertRaisesRegex(InstructionError,'DUPLICATE_RECORD_ID'):
            validate_records([record(),record()],resources(),preview=True)
        second=record(2);second['question']=record()['question']
        with self.assertRaisesRegex(InstructionError,'DUPLICATE_QUESTION'):
            validate_records([record(),rehash(second)],resources(),preview=True)

    def test_near_duplicate_questions_fail(self):
        second=record(2);second['question']=record()['question']+' '
        with self.assertRaises(InstructionError):
            validate_records([record(),rehash(second)],resources(),preview=True)

    def test_pdf_rights_gate_and_page_evidence_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            row,res=production_resource(tmp)
            with patch('scripts.instruction.common.read_pdf_pages',return_value=[row['contexts'][0]['text']]):
                validate_record(row,res)
            res.catalog[next(iter(res.catalog))]['generation_authorized']=False
            with self.assertRaisesRegex(InstructionError,'SOURCE_RIGHTS_UNVERIFIED'):
                validate_record(row,res)

    def test_pdf_source_text_and_page_tampering_fail(self):
        for change in ['pdf','text','page','group','course']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                row,res=production_resource(tmp)
                if change=='pdf': (res.root/'source.pdf').write_bytes(b'tampered')
                if change=='text': row['contexts'][0]['text']='không có trong nguồn';row['contexts'][0]['text_sha256']=digest(row['contexts'][0]['text'].encode())
                if change=='page': row['contexts'][0]['page_number']=2
                if change=='group': row['source_group_ids']=['THMLN:ch03.pdf']
                if change=='course': row['course_code']='KTCTMLN'
                with patch('scripts.instruction.common.read_pdf_pages',return_value=[record()['contexts'][0]['text']]),self.assertRaises(ValueError):
                    validate_record(rehash(row),res)

    def test_native_pdf_extraction_without_model(self):
        from pathlib import Path
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'authored.pdf';writer=PdfWriter();page=writer.add_blank_page(width=300,height=200)
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),
                NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):
                DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 10 100 Td (Self authored fixture source.) Tj ET')
            page[NameObject('/Contents')]=writer._add_object(stream)
            writer.write(path)
            self.assertEqual(len(read_pdf_pages(path)),1)
            self.assertIn('Self authored fixture source.',read_pdf_pages(path)[0])

    def test_reviews_bind_identity_score_hash_and_decision(self):
        row=record();good=reviews([row]);validate_reviews([row],good,resources())
        for key,value in [('content_sha256','0'*64),('reviewer_member','B'),('review_kind','PEER_REVIEW'),
                          ('decision','REVISE'),('content_correctness',1),('language_and_format',0),
                          ('instruction_clarity',True),('reason',''),('reviewed_at','not-a-date')]:
            wrong=deepcopy(good);wrong[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): validate_reviews([row],wrong,resources())

    def test_missing_duplicate_and_unresolved_reviews_fail(self):
        row=record();good=reviews([row])
        for values in [[],good+good]:
            with self.assertRaises(ValueError): validate_reviews([row],values,resources())
        peer=deepcopy(good[0]);peer.update(reviewer_member='B',review_kind='PEER_REVIEW',decision='REVISE')
        with self.assertRaisesRegex(InstructionError,'UNRESOLVED_REVIEW_FINDING'):
            validate_reviews([row],good+[peer],resources())

    def test_preview_resources_do_not_need_private_bundle(self):
        self.assertEqual(load_resources(preview=True).contract['status'],'TECHNICAL_INPUT_AGREED')

    def test_csv_review_roundtrip_and_malformed_scores(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'reviews.csv';rows=reviews([record()])
            with path.open('w',encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            self.assertEqual(read_reviews(path),rows)
            validate_reviews([record()],read_reviews(path),resources())
            path.write_text(path.read_text().replace(',2,2,2,2,2,',',True,2,2,2,2,'),encoding='utf-8')
            with self.assertRaisesRegex(InstructionError,'INVALID_REVIEW_SCORE'):read_reviews(path)

    def test_csv_duplicate_header_is_rejected(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'reviews.csv';path.write_text('record_id,record_id\na,b\n')
            with self.assertRaisesRegex(InstructionError,'INVALID_REVIEW_HEADER'):read_reviews(path)

    def test_import_does_not_load_gpu_or_embedding_libraries(self):
        code='import sys; import scripts.instruction.common; assert not any(x in sys.modules for x in ["torch","transformers","sentence_transformers"])'
        result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__': unittest.main()
