import copy
import unittest
from pathlib import Path

from scripts.w5.common import load_contract, read_jsonl, content_hash
from scripts.w5.quality import validate_records

ROOT = Path(__file__).resolve().parents[3]


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_contract(ROOT/'data/instruction/w5/contract')
        self.rows = read_jsonl(ROOT/'data/fixtures/w5-instruction-contract.jsonl')

    def validate(self, rows=None, **kwargs):
        return validate_records(self.rows if rows is None else rows, self.contract, ROOT, fixture_mode=True, **kwargs)

    def codes(self, report):
        return {f['code'] for f in report['findings']}

    def test_fixture_checks_are_not_release_approval(self):
        r=self.validate()
        self.assertTrue(r['passed'], r)
        self.assertEqual(len(r['valid_ids']), 4)
        self.assertEqual(r['eligible_ids'], [])
        self.assertFalse(self.validate(stage='release')['passed'])

    def test_bad_schema_hash_and_unknown_citation(self):
        for mutation, code in [(lambda r:r.update(extra='secret'), 'SCHEMA'),
                               (lambda r:r.update(content_sha256='0'*64), 'CONTENT_HASH'),
                               (lambda r:r.update(target_text='Answer [9]'), 'TARGET_FORMAT')]:
            row=copy.deepcopy(self.rows[0]);mutation(row)
            if code!='CONTENT_HASH':row['content_sha256']=content_hash(row)
            self.assertIn(code,self.codes(self.validate([row])))

    def test_source_text_identity_page_group_are_bound(self):
        for field, value in [('text','invented source'),('page_number',2),('document_id','00000000-0000-0000-0000-000000000000')]:
            row=copy.deepcopy(self.rows[0]);row['contexts'][0][field]=value;row['content_sha256']=content_hash(row)
            self.assertIn('SOURCE',self.codes(self.validate([row])))
        row=copy.deepcopy(self.rows[0]);row['source_group_ids']=['foreign'];row['content_sha256']=content_hash(row)
        self.assertIn('SOURCE_GROUP',self.codes(self.validate([row])))

    def test_hint_must_not_disclose_answer_and_compare_needs_distinct_sources(self):
        row=copy.deepcopy(self.rows[2]);row.update(task_type='hint',mode='hint',target_text='COMPARE [1] [1]');row['content_sha256']=content_hash(row)
        self.assertIn('TARGET_FORMAT',self.codes(self.validate([row])))

    def test_duplicate_questions_and_ids_are_not_eligible(self):
        row=copy.deepcopy(self.rows[0]);row['record_id']='FX_W5_00009';row['content_sha256']=content_hash(row)
        self.assertIn('EXACT_DUPLICATE',self.codes(self.validate([self.rows[0],row])))
        self.assertIn('DUPLICATE_ID',self.codes(self.validate([self.rows[0],self.rows[0]])))

    def test_protected_question_rejected_even_with_different_target(self):
        import json
        row=copy.deepcopy(self.rows[0]);row['question']=json.loads((ROOT/'data/qa/qa_baseline.json').read_text())['cases'][0]['question']
        row['content_sha256']=content_hash(row)
        self.assertIn('BENCHMARK_EXACT',self.codes(self.validate([row])))

    def test_self_review_stale_hash_and_bad_scores_do_not_approve(self):
        row=self.rows[0]
        for reviewer, sha, score in [('B',row['content_sha256'],'2'),('A','0'*64,'2'),('A',row['content_sha256'],'0')]:
            review=dict(record_id=row['record_id'],content_sha256=sha,reviewer_member=reviewer,reviewed_at='2026-10-28T00:00:00+07:00',decision='ACCEPT',reason='checked',re_review_of='')
            review.update({key:score for key in self.contract['quality']['rubric']['criteria']})
            self.assertIn('REVIEW',self.codes(self.validate([row],reviews=[review],stage='release')))

    def test_changed_protected_file_fails_closed(self):
        contract=copy.deepcopy(self.contract);contract['exclusion']['protected_inputs'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):validate_records(self.rows,contract,ROOT,fixture_mode=True)

    def test_long_target_duplicates_require_adjudication_even_for_different_questions(self):
        a=copy.deepcopy(self.rows[0]);b=copy.deepcopy(a)
        b['record_id']='FX_W5_00009';b['question']='Hãy ghi lại các nội dung có trong tình huống này.'
        a['target_text']=a['contexts'][0]['text']+' [1]';b['target_text']=a['target_text']
        for r in [a,b]:r['content_sha256']=content_hash(r)
        report=self.validate([a,b])
        self.assertIn('TARGET_NEAR_DUPLICATE',self.codes(report))
        adjudication=dict(record_id=a['record_id'],other_id=b['record_id'],content_sha256=a['content_sha256'],other_sha256=b['content_sha256'],reviewer_member='A',reason='unit family adjudication',reviewed_at='2026-10-28T00:00:00+07:00',decision='SAME_FAMILY')
        resolved=self.validate([a,b],adjudications=[adjudication])
        self.assertNotIn('TARGET_NEAR_DUPLICATE',self.codes(resolved))
        self.assertEqual(resolved['confirmed_pairs'],[(a['record_id'],b['record_id'])])
