import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts.w5.common import content_hash, digest, load_contract, parse_json, read_jsonl, within
from scripts.w5.quality import validate_records

ROOT=Path(__file__).resolve().parents[3]


class IOTests(unittest.TestCase):
    def test_duplicate_keys_nonfinite_and_path_escape_fail(self):
        for text in ['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}']:
            with self.assertRaises(ValueError):parse_json(text)
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):within(root,'../foreign.pdf')

    def test_hash_normalizes_values_but_preserves_array_order(self):
        self.assertEqual(digest({'a':'é'}),digest({'a':'e\u0301'}))
        self.assertNotEqual(digest([1,2]),digest([2,1]))
        self.assertEqual(content_hash({'x':1,'content_sha256':'bad'}),content_hash({'x':1}))


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.c=load_contract(ROOT/'data/instruction/w5/contract');self.c['exclusion']['protected_inputs']=[]
        self.row=read_jsonl(ROOT/'data/fixtures/w5-instruction-contract.jsonl')[0]
        self.row.update(record_id='W5_B_00001',course_code='THMLN',source_identity_scope='offline_corpus',source_group_ids=['THMLN:unit.pdf'])
        p=self.root/'unit.pdf';p.write_bytes(b'unit PDF stub, not a real corpus source')
        sha=hashlib.sha256(p.read_bytes()).hexdigest()
        ctx=self.row['contexts'][0];ctx.update(source_checksum=sha,rights_reference='unit-permission')
        source=dict(document_id=ctx['document_id'],version_id=ctx['version_id'],course_code='THMLN',source_group_id='THMLN:unit.pdf',
            relative_path='unit.pdf',source_checksum=sha,page_count=2,generation_authorized=True,rights_evidence_reference='unit-permission')
        self.c['sources']['sources']=[source]
        self.c['allocation']=[dict(source_group_id=source['source_group_id'],primary_author_member='B',page_start='1',page_end='2')]
        pages=[SimpleNamespace(extract_text=lambda:ctx['text']),SimpleNamespace(extract_text=lambda:'Different physical page')]
        self.mock=patch('pypdf.PdfReader',return_value=SimpleNamespace(pages=pages)).start();self.addCleanup(patch.stopall)
        self.row['content_sha256']=content_hash(self.row)

    def call(self,**kwargs):
        self.row['content_sha256']=content_hash(self.row)
        return validate_records([self.row],self.c,self.root,**kwargs)

    def test_actual_file_hash_page_and_text_checks(self):
        self.assertTrue(self.call()['passed'])
        self.row['contexts'][0]['page_number']=2
        self.assertFalse(self.call()['passed'])
        self.row['contexts'][0]['page_number']=1
        (self.root/'unit.pdf').write_bytes(b'tampered')
        self.assertFalse(self.call()['passed'])

    def test_permission_and_allocation_are_enforced(self):
        self.c['sources']['sources'][0]['generation_authorized']=False
        self.assertFalse(self.call()['passed'])
        self.c['sources']['sources'][0]['generation_authorized']=True
        self.c['allocation'][0]['primary_author_member']='A'
        self.assertFalse(self.call()['passed'])

    def test_valid_peer_review_can_make_candidate_eligible_but_not_full_release(self):
        review=dict(record_id=self.row['record_id'],content_sha256=self.row['content_sha256'],reviewer_member='A',
            reviewed_at='2026-10-28T00:00:00+07:00',decision='ACCEPT',reason='unit test review, not real human evidence')
        review.update({k:'2' for k in self.c['quality']['rubric']['criteria']})
        self.assertEqual(self.call(reviews=[review])['eligible_ids'],[self.row['record_id']])
        self.assertFalse(self.call(reviews=[review],stage='release')['passed'])
        review['reviewed_at']='2099-01-01T00:00:00Z'
        self.assertFalse(self.call(reviews=[review])['passed'])

    def test_qa_cannot_smuggle_exercise_fields(self):
        self.row['exercise']=dict(exercise_id='x',question='question',choices=[])
        self.assertFalse(self.call()['passed'])
