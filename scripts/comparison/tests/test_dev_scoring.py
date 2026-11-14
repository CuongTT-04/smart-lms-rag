from copy import deepcopy
import json
import unittest

from scripts.comparison.dev_scoring import validate
from scripts.comparison.protocol import digest


class DevScoringTests(unittest.TestCase):
    def setUp(self):
        raw=json.dumps(dict(items=[dict(text='A statement',evidence_id='E1.1')]))
        self.case=dict(blind_id='J001',raw_output=raw,raw_output_sha256=digest(raw),
            reference_sha256='a'*64,contexts=[dict(evidence_id='E1.1',text='A source passage')])
        self.review=dict(blind_id='J001',raw_output_sha256=digest(raw),reference_sha256='a'*64,
            correctness=2,reason='Fixture semantic decision',missing_points=[],claims=[dict(
                item_index=0,claim='A statement',status='supported',citation_supported=True,
                support_quote='source passage',reason='Fixture support mapping')])

    def test_explicit_semantic_review_accepted(self):
        self.assertEqual(len(validate(self.case,self.review)['items']),1)

    def test_wrong_output_hash_rejected(self):
        self.review['raw_output_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'BINDING'):
            validate(self.case,self.review)

    def test_wrong_reference_hash_rejected(self):
        self.review['reference_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'BINDING'):
            validate(self.case,self.review)

    def test_valid_id_does_not_replace_support_quote(self):
        self.review['claims'][0]['support_quote']='not in source'
        with self.assertRaisesRegex(ValueError,'SUPPORT_QUOTE'):
            validate(self.case,self.review)

    def test_missing_item_claim_rejected(self):
        self.review['claims']=[]
        with self.assertRaisesRegex(ValueError,'COVERAGE'):
            validate(self.case,self.review)

    def test_wrong_citation_can_have_support_elsewhere(self):
        self.case['contexts'].append(dict(evidence_id='E2.1',text='Another proof'))
        claim=self.review['claims'][0]
        claim.update(citation_supported=False,support_quote='Another proof')
        validate(self.case,self.review)

    def test_contradicted_claim_needs_counter_evidence(self):
        claim=self.review['claims'][0]
        claim.update(status='contradicted',citation_supported=False,support_quote='')
        with self.assertRaisesRegex(ValueError,'CONTRADICTION_QUOTE'):
            validate(self.case,self.review)
        claim['counter_quote']='A source passage'
        validate(self.case,self.review)

    def test_raw_newline_keeps_content_score_for_separate_renderer(self):
        value=json.loads(self.case['raw_output'])
        value['items'][0]['text']='First\nSecond'
        self.case['raw_output']=json.dumps(value)
        self.case['raw_output_sha256']=digest(self.case['raw_output'])
        self.review['raw_output_sha256']=self.case['raw_output_sha256']
        self.assertIn('\n',validate(self.case,self.review)['items'][0]['text'])

    def test_score_range_rejected(self):
        self.review['correctness']=3
        with self.assertRaisesRegex(ValueError,'JUDGMENT_SCORE'):
            validate(self.case,self.review)


if __name__=='__main__':
    unittest.main()
