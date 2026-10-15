from pathlib import Path
import unittest


class W3PackageTests(unittest.TestCase):
    def test_qa_regeneration_inputs_are_packaged(self):
        root = Path(__file__).resolve().parents[4]
        package = (root/'scripts/package_kaggle.ps1').read_text(encoding='utf-8')
        self.assertIn("'scripts/package_kaggle.ps1'", package)
        for name in ('qa_pilot_v2.0.csv', 'qa_w3_cuong_v1.0.csv', 'qa_pilot_v2.0_review.csv',
                     'qa_w3_source_checks.json', 'qa_w3_source_audit.csv'):
            with self.subTest(name=name):
                self.assertIn("'data/qa/"+name+"'", package)
