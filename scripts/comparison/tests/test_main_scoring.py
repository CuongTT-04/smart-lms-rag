from collections import Counter
import unittest

from scripts.comparison.main_scoring import assignment, literal_support, paired, parse, quantile, semantic_metrics


class MainScoringTests(unittest.TestCase):
    def test_base_null_citation_protocol(self):
        self.assertTrue(parse('{"items":[{"text":"Answer","evidence_id":null}]}')['schema_valid'])

    def test_duplicate_json_keys_rejected(self):
        self.assertFalse(parse('{"items":[],"items":[]}')['json_valid'])

    def test_trailing_markdown_not_repaired(self):
        self.assertFalse(parse('{"items":[]}```')['json_valid'])

    def test_empty_valid_but_not_semantic_score(self):
        value=parse('{"items":[]}')
        self.assertTrue(value['schema_valid'])
        self.assertEqual(value['items'], [])
        self.assertNotIn('correctness',value)

    def test_wrong_item_shape_rejected(self):
        self.assertFalse(parse('{"items":[{"text":"A"}]}')['schema_valid'])

    def test_literal_source_identity_not_keyword_overlap(self):
        contexts={'E1.1':{'text':'Production and consumption occur simultaneously.'}}
        self.assertEqual(literal_support('Production and consumption occur simultaneously.',contexts),['E1.1'])
        self.assertEqual(literal_support('Production and consumption never occur simultaneously.',contexts),[])

    def test_balanced_reproducible_assignments(self):
        refs=[]
        for course in ('A','B','C'):
            for kind,n in (('factual',40),('explanation',30),('multi_page',10),('insufficient',20)):
                refs.extend(dict(qa_id=f'{course}-{kind}-{i}',course_code=course,question_type=kind) for i in range(n))
        owners,secondary=assignment(refs)
        self.assertEqual(Counter(owners.values()),{'A':150,'B':150})
        self.assertEqual(len(secondary),15)
        self.assertTrue(all(owners[rid]=='B' for rid in secondary))
        self.assertEqual((owners,secondary),assignment(list(reversed(refs))))

    def row(self,*,answerable=True,score=0,claims=None,abstain=False):
        return dict(correctness=score,claims=claims or [],answerable=answerable,
            protocol_abstention=abstain,schema_valid=True,displayed_correctness=score)

    def test_empty_answerable_not_rewarded_for_no_claims(self):
        metrics=semantic_metrics([self.row(abstain=True)])
        self.assertEqual(metrics['correctness_percent'],0)
        self.assertEqual(metrics['false_protocol_abstentions'],1)
        self.assertIsNone(metrics['faithfulness_item_micro'])

    def test_insufficient_denominator_separate(self):
        rows=[self.row(score=1),self.row(answerable=False,score=2,abstain=True)]
        metrics=semantic_metrics(rows)
        self.assertEqual(metrics['answerable_outputs'],1)
        self.assertEqual(metrics['correct_abstention_rate'],1)
        self.assertEqual(metrics['false_protocol_abstentions'],0)

    def test_source_support_not_citation_id_validity(self):
        claims=[dict(status='supported',citation_id='E1.1',citation_supported=False),
                dict(status='unsupported',citation_id='E2.1',citation_supported=False)]
        metrics=semantic_metrics([self.row(claims=claims)])
        self.assertEqual(metrics['faithfulness_item_micro'],.5)
        self.assertEqual(metrics['citation_precision_item_micro'],0)
        self.assertEqual(metrics['citation_coverage_item_micro'],0)

    def test_paired_bootstrap_identical_outputs(self):
        rows=[dict(qa_id=str(i),arm=arm,correctness=i%3) for i in range(6) for arm in ('rag','tuned_rag')]
        result=paired(rows,'rag','tuned_rag')
        self.assertEqual(result['ties'],6)
        self.assertEqual(result['paired_case_bootstrap_95_ci'],[0,0])

    def test_latency_quantile_interpolation(self):
        self.assertEqual(quantile([3,1,2,4],.5),2.5)
        self.assertIsNone(quantile([],.95))
