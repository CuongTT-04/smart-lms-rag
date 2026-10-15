import importlib.util
from pathlib import Path
import unittest


class QAMergeTests(unittest.TestCase):
    def test_merge_shared_ids_and_reject_label_conflicts_or_duplicate_questions(self):
        path = Path(__file__).resolve().parents[4]/'scripts/merge_w3_qa.py'
        spec = importlib.util.spec_from_file_location('merge_w3_qa', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        a = {'qa_id': 'A', 'course_id': 'C', 'question': 'Question one', 'ground_truth': 'Answer',
             'source_doc': 'ch01.pdf', 'source_page': '1'}
        b = {**a, 'qa_id': 'B', 'question': 'Question two'}
        self.assertEqual(len(module.merge_rows([a], [a, b])), 2)
        with self.assertRaises(ValueError):
            module.merge_rows([a], [{**a, 'source_page': '2'}])
        with self.assertRaises(ValueError):
            module.merge_rows([a], [{**b, 'question': ' Question   ONE '}])
