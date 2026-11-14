import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts.comparison.group_scoring import build_review, validate_reviews, agreement, resolve_reviews, validate_renderers, verify_b_lock
from scripts.comparison.main_scoring import parse
from scripts.comparison.protocol import write_json, file_hash


class GroupScoringTests(unittest.TestCase):
    def case(self):
        return dict(blind_id='M1',qa_id='Q1',content_sha256='content',raw_output_sha256='raw',reference_sha256='ref',
            answerable=True,generation_status='completed',reference={'required_points':['A']},
            parsed={'schema_valid':True,'items':[{'text':'A','evidence_id':'E1.1'}]},
            contexts={'E1.1':dict(text='A',document_id='doc',version_id='v',page_number=1,char_start=0,char_end=1,source_checksum='pdf')})

    def note(self):
        return dict(blind_id='M1',raw_content_score=2,reason='Fully supports the requested fact',
                    verdicts=['E1.1'],claim_reasons=['Page one states the asserted fact'])

    def test_failure_and_invalid_abstention_are_zero_but_raw_score_preserved(self):
        case=self.case();case['generation_status']='output_limit'
        review=build_review(case,self.note(),'B')
        self.assertEqual((review['correctness'],review['raw_content_score']),(0,2))
        case.update(generation_status='completed',answerable=False,parsed={'schema_valid':False,'items':[]})
        note=self.note();note.update(verdicts=[],claim_reasons=[])
        self.assertEqual(build_review(case,note,'B')['correctness'],0)

    def test_empty_answerable_response_scores_zero(self):
        case = self.case()
        case['parsed'] = parse('{"items":[]}')
        for raw_score in (0, 1, 2):
            note = {**self.note(), 'raw_content_score': raw_score, 'verdicts': [], 'claim_reasons': []}
            with self.subTest(raw_score=raw_score):
                review = build_review(case, note, 'B')
                self.assertEqual(review['correctness'], 0)
                validate_reviews({'M1': case}, [review], {'M1'}, 'B')
                for forced_score in (1, 2):
                    with self.subTest(forced_score=forced_score), self.assertRaisesRegex(ValueError, 'GROUP_FAILURE_SCORE_POLICY'):
                        validate_reviews({'M1': case}, [{**review, 'correctness': forced_score}], {'M1'}, 'B')

    def test_valid_insufficient_abstention_keeps_full_credit(self):
        case = self.case()
        case.update(answerable=False, parsed=parse('{"items":[]}'))
        note = {**self.note(), 'verdicts': [], 'claim_reasons': []}
        review = build_review(case, note, 'B')
        self.assertEqual(review['correctness'], 2)
        validate_reviews({'M1': case}, [review], {'M1'}, 'B')

    def test_unparseable_answerable_content_is_still_scored_semantically(self):
        case = self.case()
        case['parsed'] = parse('A meaningful answer outside the JSON protocol')
        note = {**self.note(), 'verdicts': [], 'claim_reasons': []}
        review = build_review(case, note, 'B')
        self.assertEqual(review['correctness'], 2)
        validate_reviews({'M1': case}, [review], {'M1'}, 'B')

    def test_support_and_citation_are_separate_and_exact_source_is_bound(self):
        case=self.case();case['parsed']['items'][0]['evidence_id']='E9.1'
        review=build_review(case,self.note(),'B')
        self.assertEqual(review['claims'][0]['status'],'supported')
        self.assertFalse(review['claims'][0]['citation_supported'])
        self.assertEqual(review['claims'][0]['sources'][0]['quote'],'A')
        validate_reviews({'M1':case},[review],{'M1'},'B')
        bad=copy.deepcopy(review);bad['claims'][0]['sources'][0]['quote']='invented'
        with self.assertRaises(ValueError):validate_reviews({'M1':case},[bad],{'M1'},'B')

    def test_missing_duplicate_stale_unknown_source_and_unreviewed_item_rejected(self):
        case=self.case();note=self.note();review=build_review(case,note,'B')
        for rows in ([],[review,review],[{**review,'content_sha256':'stale'}]):
            with self.assertRaises(ValueError):validate_reviews({'M1':case},rows,{'M1'},'B')
        for verdicts in ([],['E9.1']):
            with self.assertRaises(ValueError):build_review(case,{**note,'verdicts':verdicts},'B')

    def test_multiple_sources_needed_do_not_make_one_citation_sufficient(self):
        case=self.case()
        case['contexts']['E2.1']={**case['contexts']['E1.1'],'text':'B'}
        note={**self.note(),'verdicts':['E1.1+E2.1']}
        claim=build_review(case,note,'B')['claims'][0]
        self.assertEqual(claim['status'],'supported')
        self.assertFalse(claim['citation_supported'])

    def test_secondary_not_averaged_into_primary_and_disagreement_requires_decision(self):
        primary=build_review(self.case(),self.note(),'B')
        secondary=build_review(self.case(),{**self.note(),'raw_content_score':0,'reason':'Disagrees'},'A')
        with self.assertRaises(ValueError):resolve_reviews({'M1':primary},{'M1':secondary},{})
        decision=build_review(self.case(),{**self.note(),'raw_content_score':1,'reason':'Source-grounded adjudication'},'ADJUDICATOR')
        final,log=resolve_reviews({'M1':primary},{'M1':secondary},{'M1':decision})
        self.assertEqual(len(final),1)
        self.assertEqual(final[0]['correctness'],1)
        self.assertEqual(primary['correctness'],2)
        self.assertEqual(log[0]['primary_correctness'],2)

    def test_agreement_uses_only_paired_independent_rows(self):
        a={'x':{'correctness':0},'y':{'correctness':1},'z':{'correctness':2}}
        b={'x':{'correctness':0},'y':{'correctness':2},'z':{'correctness':2}}
        result=agreement(a,b)
        self.assertEqual(result['pairs'],3)
        self.assertAlmostEqual(result['exact_correctness_agreement'],2/3)
        self.assertEqual(result['confusion_matrix'],[[1,0,0],[0,0,1],[0,0,1]])
        with self.assertRaises(ValueError):agreement(a,{'x':{'correctness':0}})

    def test_renderer_requires_exactly_one_bound_row_per_case(self):
        case=self.case()
        row=dict(blind_id='M1',raw_output_sha256='raw',status='RENDERED',backend_renderer_applied=True)
        self.assertEqual(validate_renderers({'M1':case},[row])['M1']['status'],'RENDERED')
        for rows in ([],[row,row],[{**row,'raw_output_sha256':'changed'}],
                     [{**row,'blind_id':'M2'}],[{**row,'status':'PROTOCOL_VALID'}]):
            with self.assertRaises(ValueError):validate_renderers({'M1':case},rows)

    def test_b_lock_rejects_other_a_revision_or_changed_rubric(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=root/'a';b=root/'b';a.mkdir();b.mkdir()
            judge=dict(rubric_sha256='rubric',claim_unit='item',failure_policy='zero',locked_raw_sha256='raw',references_sha256='ref')
            write_json(a/'judge-config.json',judge)
            write_json(a/'reviews-lock.json',{'version':'A1'})
            (b/'reviews-b.jsonl').write_text('',encoding='utf-8')
            write_json(b/'judge-config.json',judge)
            lock=dict(reviews_sha256=file_hash(b/'reviews-b.jsonl'),judge_config_sha256=file_hash(b/'judge-config.json'),
                      source_a_reviews_lock_sha256=file_hash(a/'reviews-lock.json'))
            write_json(b/'reviews-lock.json',lock)
            with patch('scripts.comparison.group_scoring.SOURCE',a):
                verify_b_lock(b)
                write_json(b/'reviews-lock.json',{**lock,'source_a_reviews_lock_sha256':'different'})
                with self.assertRaises(ValueError):verify_b_lock(b)
                write_json(b/'reviews-lock.json',lock)
                write_json(b/'judge-config.json',{**judge,'claim_unit':'different'})
                write_json(b/'reviews-lock.json',{**lock,'judge_config_sha256':file_hash(b/'judge-config.json')})
                with self.assertRaises(ValueError):verify_b_lock(b)


if __name__=='__main__':unittest.main()
