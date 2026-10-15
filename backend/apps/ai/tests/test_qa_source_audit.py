import csv
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class SourceAuditTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[4]/'scripts/merge_w3_qa.py'
        spec = importlib.util.spec_from_file_location('qa_source_audit_merge', path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_normalization_handles_decomposed_vietnamese_and_pdf_spacing(self):
        self.assertEqual(self.module.compact('chủ nghĩa'), self.module.compact('chủ nghĩa'))
        self.assertEqual(self.module.compact('ph ản ánh'), self.module.compact('phản ánh'))

    def run_audit(self, changes=None, terms=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file in ('qa_pilot_v2.0_additions.json', 'qa_pilot_v2.0_corrections.json'):
                (root/file).write_text(json.dumps({'rows': []}), encoding='utf-8')
            check = {'qa_id': 'q1', 'anchor': 'Bằng chứng', 'terms': terms or ['nội dung'], 'changes': changes or {}}
            (root/'qa_w3_source_checks.json').write_text(json.dumps({'checks': [check]}), encoding='utf-8')
            row = {'qa_id': 'q1', 'course_id': 'C', 'source_doc': 'ch01.pdf', 'source_page': '1',
                   'source_pages': '[1]', 'ground_truth': 'old'}
            reader = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: 'Bằng chứng nội dung')])
            with patch.object(self.module, 'PdfReader', return_value=reader):
                return self.module.audit_rows([row], {('C', 'ch01.pdf'): {'source_checksum': 'hash'}}, root, root)

    def test_explicit_correction_and_agent_status(self):
        rows, audit = self.run_audit({'ground_truth': 'new'})
        self.assertEqual(rows[0]['ground_truth'], 'new')
        self.assertEqual(json.loads(audit[0]['changes'])['ground_truth'], {'before': 'old', 'after': 'new'})
        self.assertEqual(audit[0]['agent_reviewer'], 'Codex')
        self.assertEqual(audit[0]['audit_status'], 'agent_source_checked_pending_human_peer')

    def test_missing_evidence_fails_before_export(self):
        with self.assertRaisesRegex(ValueError, 'Missing source evidence'):
            self.run_audit(terms=['not present'])

    def test_out_of_range_or_inconsistent_page_rejected(self):
        for changes in ({'source_pages': '[2]'}, {'source_page': '2'}, {'source_pages': '[true]'}, {'source_pages': '[1,1]'}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'Invalid gold pages'):
                self.run_audit(changes)

    def test_cannot_change_owner_or_fake_human_approval(self):
        for key in ('owner', 'peer_review_status', 'document_id'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Unsupported editorial'):
                self.run_audit({key: 'fake'})

    def test_human_review_log_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'qa_review_log.csv'
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=['qa_id', 'peer_reviewer', 'peer_review_status'])
                writer.writeheader()
                writer.writerow({'qa_id': 'q1', 'peer_reviewer': 'Human', 'peer_review_status': 'approved'})
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'Existing human review'):
                self.module.build('unused', directory)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
