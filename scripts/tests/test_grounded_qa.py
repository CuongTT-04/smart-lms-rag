import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from scripts.check_grounded_qa import CASES, SOURCE_PROFILE, check_gateway


class GroundedQuestionSetTests(unittest.TestCase):
    def test_exactly_ten_distinct_cases(self):
        self.assertEqual(len(CASES), 10)
        self.assertEqual(len({case[0] for case in CASES}), 10)
        self.assertEqual(len({case[1] for case in CASES}), 10)

    def test_source_is_the_existing_project_pdf(self):
        root = Path(__file__).resolve().parents[2]
        source = root / SOURCE_PROFILE['path']
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), SOURCE_PROFILE['sha256'])

    def test_two_negative_and_two_multi_page_cases(self):
        cases = {case[0]: case for case in CASES}
        self.assertEqual(sum(name.startswith('missing_') for name in cases), 2)
        self.assertIn('7–8', cases['materialism_forms'][2])
        self.assertIn('8–9', cases['idealism_origins'][2])

    def test_replacement_questions_are_about_the_selected_subject(self):
        text = json.dumps(CASES, ensure_ascii=False)
        self.assertIn('triết học', text)
        for term in ('CPU', 'ALU', 'thanh ghi', 'chu kỳ lệnh'):
            self.assertNotIn(term, text)

    def test_preview_does_not_need_django_or_inference(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable, '-B', 'scripts/check_grounded_qa.py',
                                 '--document', '3724aa92-4a4a-4c61-9063-df2ce124540e'],
                                cwd=root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [list(case) for case in CASES])

    def test_two_case_preview_preserves_questions_and_does_not_claim_full_run(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable, '-B', 'scripts/check_grounded_qa.py',
                                 '--document', '3724aa92-4a4a-4c61-9063-df2ce124540e',
                                 '--case', 'materialism_forms', '--case', 'idealism_origins'],
                                cwd=root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([row[0] for row in json.loads(result.stdout)], ['materialism_forms', 'idealism_origins'])

    def gateway(self, health):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(health).encode()
        opener = MagicMock()
        opener.open.return_value = response
        with patch.dict(os.environ, {'AI_INFERENCE_URL': 'https://example.test', 'AI_INFERENCE_TOKEN': 'x'*40}), \
                patch('scripts.check_grounded_qa.build_opener', return_value=opener):
            return check_gateway({'model': 'test'})

    def test_final_check_rejects_gateway_missing_current_capability(self):
        with self.assertRaisesRegex(RuntimeError, 'Gateway update required'):
            self.gateway({'ready': True, 'config': {'model': 'test'}, 'capabilities': []})

    def test_final_check_rejects_config_drift(self):
        with self.assertRaisesRegex(RuntimeError, 'config differs'):
            self.gateway({'ready': True, 'config': {'model': 'other'}, 'capabilities': ['qa_completeness_v1']})

    def test_final_check_records_matching_gateway_capability(self):
        result = self.gateway({'ready': True, 'config': {'model': 'test'}, 'capabilities': ['qa_completeness_v1', 'qa_atomic_evidence_v1', 'qa_source_descriptions_v1', 'qa_source_selection_v1']})
        self.assertTrue(result['config_matches'])

    def test_atomic_gateway_without_description_fix_is_not_final_acceptance(self):
        with self.assertRaisesRegex(RuntimeError, 'Gateway update required'):
            self.gateway({'ready': True, 'config': {'model': 'test'},
                          'capabilities': ['qa_completeness_v1', 'qa_atomic_evidence_v1']})

    def test_description_gateway_without_selection_protocol_is_not_current(self):
        with self.assertRaisesRegex(RuntimeError, 'Gateway update required'):
            self.gateway({'ready': True, 'config': {'model': 'test'}, 'capabilities':
                          ['qa_completeness_v1', 'qa_atomic_evidence_v1', 'qa_source_descriptions_v1']})


if __name__ == '__main__':
    unittest.main()
