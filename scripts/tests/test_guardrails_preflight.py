import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.guardrails_preflight import ROOT, PLAN, sha256, validate_plan, candidate_identity, capture


class GuardrailsPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT / PLAN).read_bytes())

    def test_all_cases_and_shared_contract_are_present(self):
        self.assertEqual(validate_plan(self.plan), 36)

    def test_duplicate_ids_fail(self):
        self.plan['cases'].append(copy.deepcopy(self.plan['cases'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            validate_plan(self.plan)

    def test_missing_shared_case_fails(self):
        self.plan['cases'][0].pop('shared_id')
        with self.assertRaisesRegex(ValueError, 'Shared fixture'):
            validate_plan(self.plan)

    def test_missing_mode_fails(self):
        self.plan['cases'] = [case for case in self.plan['cases'] if case['mode'] != 'summary']
        with self.assertRaisesRegex(ValueError, 'coverage'):
            validate_plan(self.plan)

    def test_unexecuted_cases_cannot_claim_passed(self):
        self.plan['cases'][0]['passed'] = True
        with self.assertRaisesRegex(ValueError, 'acceptance results'):
            validate_plan(self.plan)

    def test_both_arms_required(self):
        self.plan['arms'] = ['tuned_rag']
        with self.assertRaisesRegex(ValueError, 'Both'):
            validate_plan(self.plan)

    def test_controls_cannot_drop_fixed_context(self):
        self.plan['comparison']['same_for_both_arms'].remove('retrieved_contexts_and_order')
        with self.assertRaisesRegex(ValueError, 'controls'):
            validate_plan(self.plan)

    def test_security_gates_cannot_be_relaxed(self):
        self.plan['acceptance']['unauthorized_disclosures'] = 1
        with self.assertRaisesRegex(ValueError, 'Safety'):
            validate_plan(self.plan)

    def test_holdout_remains_untouched(self):
        self.plan['comparison']['do_not_modify_previous_benchmarks_or_holdout'] = False
        with self.assertRaisesRegex(ValueError, 'Historical'):
            validate_plan(self.plan)

    def test_candidate_rejects_wrong_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.plan['candidate']['directory'] = 'adapter'
            adapter = root / 'adapter'
            adapter.mkdir()
            (adapter / 'adapter_config.json').write_text('{}')
            (adapter / 'adapter_model.safetensors').write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                candidate_identity(self.plan, root)

    def test_baseline_rejects_public_destination(self):
        with self.assertRaisesRegex(ValueError, 'child of'):
            capture(ROOT / 'data/qa/public-baseline', Path('unused.json'))

    def test_baseline_cannot_overwrite_existing_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / '.private/guardrails/baseline'
            destination.mkdir(parents=True)
            with self.assertRaises(FileExistsError):
                capture(destination, root / 'unused.json', root)

    def test_checksum_detects_content_change(self):
        self.assertNotEqual(sha256(b'original'), sha256(b'changed'))


if __name__ == '__main__':
    unittest.main()
