from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.comparison.holdout import ADAPTER_SHA, ARMS, audit, score, summarize
from scripts.comparison.package_holdout import make_evaluation_notebook
from scripts.comparison.protocol import digest, write_bundle, write_json, write_rows


def messages(hint=False):
    evidence = [{'source_id': 'S1', 'citation_label': 1, 'text': 'Source'}] if hint else [
        {'evidence_id': 'E1.1', 'citation_label': 1, 'text': 'Source'}]
    return [{'role': 'system', 'content': 'System'}, {'role': 'user', 'content': json.dumps(dict(evidence=evidence))}]


GOLD = '{"items":[{"text":"Supported claim","evidence_id":"E1.1"}]}'


class HoldoutScores(unittest.TestCase):
    def test_exact_structured_answer(self):
        result = score(GOLD, GOLD, 'qa', messages())
        self.assertTrue(result['format_valid'] and result['evidence_ids_valid'] and result['reference_exact'])
        self.assertEqual(result['reference_item_recall'], 1)

    def test_unknown_evidence_is_not_valid(self):
        self.assertFalse(score(GOLD.replace('E1.1', 'E9.1'), GOLD, 'qa', messages())['evidence_ids_valid'])

    def test_empty_refusal_does_not_get_citation_credit(self):
        result = score('{"items":[]}', GOLD, 'qa', messages())
        self.assertTrue(result['refused'])
        self.assertFalse(result['evidence_ids_valid'])

    def test_malformed_json(self):
        self.assertFalse(score('bad', GOLD, 'qa', messages())['format_valid'])

    def test_duplicate_json_key(self):
        self.assertFalse(score('{"items":[],"items":[]}', GOLD, 'qa', messages())['format_valid'])

    def test_extra_field_rejected(self):
        self.assertFalse(score('{"items":[],"quote":"bad"}', GOLD, 'qa', messages())['format_valid'])

    def test_truncated_generation_not_scored_as_success(self):
        result = score(GOLD, GOLD, 'qa', messages(), completed=False)
        self.assertFalse(result['reference_exact'] or result['format_valid'])

    def test_hint_valid_label(self):
        self.assertTrue(score('READ [1]', 'READ [1]', 'hint', messages(True))['evidence_ids_valid'])

    def test_hint_unknown_label(self):
        self.assertFalse(score('READ [2]', 'READ [1]', 'hint', messages(True))['evidence_ids_valid'])

    def test_compare_requires_two_distinct_sources(self):
        self.assertFalse(score('COMPARE [1] [1]', 'READ [1]', 'hint', messages(True))['format_valid'])

    def test_paraphrase_is_not_claimed_semantically_wrong(self):
        result = score(GOLD.replace('Supported claim', 'Equivalent wording'), GOLD, 'qa', messages())
        self.assertTrue(result['format_valid'])
        self.assertFalse(result['reference_exact'])

    def test_partial_answer_reference_item_recall(self):
        gold = json.dumps({'items': [{'text': 'Supported claim', 'evidence_id': 'E1.1'},
                                     {'text': 'Another claim', 'evidence_id': 'E1.1'}]})
        self.assertEqual(score(GOLD, gold, 'summary', messages())['reference_item_recall'], .5)

    def test_weighted_loss_and_refusal_denominators(self):
        rows = []
        for arm in ARMS:
            for task, nll, tokens, refusal in [('qa', 2, 2, True), ('insufficient_evidence', 12, 4, True)]:
                rows.append(dict(arm=arm, task_type=task, nll_sum=nll, supervised_tokens=tokens,
                    status='completed', generation_seconds=1, measurements={'peak_allocated_bytes': 10},
                    scores=dict(format_valid=True, evidence_ids_valid=False, reference_exact=False,
                                reference_item_recall=0, refused=refusal)))
        result = summarize(rows)['tuned_rag']
        self.assertAlmostEqual(result['completion_token_weighted_loss'], 14/6)
        self.assertEqual(result['refusal_precision'], .5)
        self.assertEqual(result['refusal_recall'], 1)
        self.assertEqual(result['false_refusals'], 1)
        self.assertEqual(result['valid_citation_rate_answerable'], 0)

    def audit_fixture(self, root):
        source = dict(record_id='one', task_type='qa', payload={'prompt': messages(), 'completion': [{'content': GOLD}]})
        source['payload_sha256'] = digest(source['payload'])
        rows = [dict(record_id='one', task_type='qa', arm=arm, payload_sha256=source['payload_sha256'],
                     prompt_sha256=digest(messages()), supervised_tokens=2, nll_sum=2,
                     adapter_sha256=ADAPTER_SHA if arm == 'tuned_rag' else None,
                     raw_output=GOLD, status='completed', generation_seconds=1,
                     scores=score(GOLD, GOLD, 'qa', messages()),
                     measurements=dict(peak_allocated_bytes=100, adapter_state=dict(enabled=arm == 'tuned_rag',
                         layers=196, disabled_layers=0 if arm == 'tuned_rag' else 196, merged=False))) for arm in ARMS]
        write_json(root / 'manifest.json', {})
        return source, rows

    def test_audit_rejects_duplicate_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, rows = self.audit_fixture(root)
            write_rows(root / 'outputs.jsonl', [rows[0], rows[0]])
            with patch('scripts.comparison.holdout.load', return_value=(dict(adapter_sha256=ADAPTER_SHA), [source], [dict(supervised_tokens=2)], {})):
                with self.assertRaisesRegex(ValueError, 'HOLDOUT_OUTPUT_ID'):
                    audit(root, root, 'smoke')

    def test_audit_recomputes_scores_and_loss(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, rows = self.audit_fixture(root)
            write_rows(root / 'outputs.jsonl', rows)
            with patch('scripts.comparison.holdout.load', return_value=(dict(adapter_sha256=ADAPTER_SHA), [source], [dict(supervised_tokens=2)], {})):
                report = audit(root, root, 'smoke')
                self.assertEqual(report['metrics']['rag']['completion_token_weighted_loss'], 1)
                rows[-1]['scores']['reference_exact'] = False
                write_rows(root / 'outputs.jsonl', rows)
                with self.assertRaisesRegex(ValueError, 'HOLDOUT_SCORE_DRIFT'):
                    audit(root, root, 'smoke')

    def test_audit_rejects_adapter_disabled_in_tuned_arm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, rows = self.audit_fixture(root)
            rows[-1]['measurements']['adapter_state']['enabled'] = False
            write_rows(root / 'outputs.jsonl', rows)
            with patch('scripts.comparison.holdout.load', return_value=(dict(adapter_sha256=ADAPTER_SHA), [source], [dict(supervised_tokens=2)], {})):
                with self.assertRaisesRegex(ValueError, 'HOLDOUT_ADAPTER_STATE'):
                    audit(root, root, 'smoke')

    def test_notebook_runs_holdout_module_not_training(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'source').mkdir()
            (root / 'source/a.txt').write_text('fixture')
            receipt = write_bundle(root / 'source', root / 'holdout-evaluation.zip')
            notebook = make_evaluation_notebook(root / 'holdout-evaluation.zip', receipt)
        source = '\n'.join(''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code')
        self.assertIn('scripts.comparison.holdout', source)
        self.assertIn("'--split', mode", source)
        self.assertIn("execute('holdout')", source)
        self.assertIn("SMOKE_AUDIT['rows'] == 8", source)
        self.assertNotIn('scripts.comparison.training', source)
        self.assertNotIn('scripts.comparison.runner', source)
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code':
                compile(''.join(cell['source']), '<notebook>', 'exec')


if __name__ == '__main__':
    unittest.main()
