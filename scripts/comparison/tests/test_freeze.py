import tempfile
from copy import deepcopy
from pathlib import Path
import unittest

from scripts.comparison.freeze import SELECTED, decide, verify_locked
from scripts.comparison.protocol import file_hash
from scripts.comparison.runner import LIMITS, MODEL, REVISION


class FreezeTests(unittest.TestCase):
    def config(self):
        return dict(model_id=MODEL, model_revision=REVISION, generation=dict(LIMITS),
                    adapter_sha256=SELECTED, stage='DEV_ONLY', attempts=1, warmup_calls_per_arm=2,
                    history=False, response_cache=False, repair=False, retries=False)

    def recommendation(self):
        return dict(recommended_adapter_sha256=SELECTED, new_correctness_total=50, old_correctness_total=47)

    def test_select_and_disclose_regression(self):
        result = decide(self.recommendation(), self.config())
        self.assertFalse(result['chatbot_adapter_changed'])
        self.assertIn('THMLN', result['limitations'][0])

    def test_reject_wrong_adapter(self):
        config = self.config()
        config['adapter_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            decide(self.recommendation(), config)

    def test_reject_wrong_recommendation(self):
        recommendation = self.recommendation()
        recommendation['recommended_adapter_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            decide(recommendation, self.config())

    def test_reject_changed_generation(self):
        config = deepcopy(self.config())
        config['generation']['max_new_tokens'] = 256
        with self.assertRaises(ValueError):
            decide(self.recommendation(), config)

    def test_reject_no_selection_advantage(self):
        recommendation = self.recommendation()
        recommendation['new_correctness_total'] = 46
        with self.assertRaises(ValueError):
            decide(recommendation, self.config())

    def test_lock_checks_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / 'input'
            file.write_bytes(b'locked')
            files = {'input': dict(sha256=file_hash(file), size_bytes=6)}
            verify_locked(root, files)
            file.write_bytes(b'edited')
            with self.assertRaises(ValueError):
                verify_locked(root, files)

    def test_lock_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                verify_locked(Path(tmp), {'../outside': dict(sha256='0'*64, size_bytes=0)})
