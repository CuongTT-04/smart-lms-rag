from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.comparison.benchmark import (atomic_points, content_digest, normalized_question,
    duplicate_audit, revise, split_audit, validate_reviews, write_package)
from scripts.comparison.prepare_data import source_repairs


def case():
    row = dict(qa_id='q1', question='A question?', scope_id='scope', course_code='course',
               question_type='factual', answerable=True,
               reference=dict(required_points=['A; B'], evidence=[dict(source_group_id='main')]))
    row['content_sha256'] = content_digest(row)
    return row


def review(row):
    return dict(qa_id=row['qa_id'], content_sha256=row['content_sha256'], review_kind='AGENT_REVIEW',
                reviewer='tester', agent_run_id='test-run', question_valid='YES',
                reference_correct_complete='YES', pages_support='YES', nonduplicate='YES',
                absence_checked_full_scope='NOT_APPLICABLE', decision='APPROVE',
                reason='Reviewed', source_check='Page checked', duplicate_check='Checked', absence_check='')


def training(group='train', split='train', family='f1'):
    return [dict(record_id='r1', split=split, source_group_ids=[group], variant_family_id=family)], [dict(prompt=[dict(content=json.dumps(dict(question='Different')))])]


class BenchmarkTests(unittest.TestCase):
    def test_atomic_clauses(self):
        self.assertEqual(atomic_points(['A; B; C']), ['A', 'B', 'C'])

    def test_negative_clause_keeps_reason(self):
        self.assertEqual(atomic_points(['Không; vì A; còn B']), ['Không; vì A', 'còn B'])

    def test_unicode_question_normalization(self):
        self.assertEqual(normalized_question('  CÓ, không?'), 'có không')

    def test_revision_preserves_original_and_identity(self):
        original = case()
        saved = deepcopy(original)
        rows, changes = revise([original], {})
        self.assertEqual(original, saved)
        self.assertEqual(rows[0]['qa_id'], original['qa_id'])
        self.assertFalse(changes[0]['question_changed'])
        self.assertNotEqual(rows[0]['content_sha256'], original['content_sha256'])

    def test_unknown_replacement_rejected(self):
        with self.assertRaises(ValueError):
            revise([case()], {'unknown': {}})

    def test_altered_original_rejected(self):
        row = case()
        row['question'] = 'Edited'
        with self.assertRaises(ValueError):
            revise([row], {})

    def test_complete_review(self):
        row = case()
        validate_reviews([row], [review(row)])

    def test_missing_review_rejected(self):
        with self.assertRaises(ValueError):
            validate_reviews([case()], [])

    def test_stale_review_rejected(self):
        row = case()
        record = review(row)
        record['content_sha256'] = 'stale'
        with self.assertRaises(ValueError):
            validate_reviews([row], [record])

    def test_duplicate_review_rejected(self):
        row = case()
        with self.assertRaises(ValueError):
            validate_reviews([row], [review(row), review(row)])

    def test_revision_cannot_pass_acceptance(self):
        row = case()
        record = review(row)
        record.update(decision='REVISE', nonduplicate='NO')
        validate_reviews([row], [record], require_approval=False)
        with self.assertRaises(ValueError):
            validate_reviews([row], [record])

    def test_approve_with_failed_criterion_rejected(self):
        row = case()
        record = review(row)
        record['nonduplicate'] = 'NO'
        with self.assertRaises(ValueError):
            validate_reviews([row], [record], require_approval=False)

    def test_insufficient_requires_scope_evidence(self):
        row = case()
        row['answerable'] = False
        row['content_sha256'] = content_digest(row)
        with self.assertRaises(ValueError):
            validate_reviews([row], [review(row)])

    def test_main_group_cannot_be_in_train(self):
        metas, payloads = training('main')
        with self.assertRaises(ValueError):
            split_audit([case()], metas, payloads)

    def test_main_group_can_remain_in_holdout(self):
        metas, payloads = training('main', 'instruction_holdout')
        self.assertFalse(split_audit([case()], metas, payloads)['train_validation_source_overlap'])

    def test_group_cannot_cross_splits(self):
        metas, payloads = training()
        metas.append(dict(record_id='r2', split='validation', source_group_ids=['train'], variant_family_id='f2'))
        with self.assertRaises(ValueError):
            split_audit([case()], metas, payloads * 2)

    def test_family_cannot_cross_splits(self):
        metas, payloads = training()
        metas.append(dict(record_id='r2', split='validation', source_group_ids=['other'], variant_family_id='f1'))
        with self.assertRaises(ValueError):
            split_audit([case()], metas, payloads * 2)

    def test_exact_training_question_blocked(self):
        metas, payloads = training()
        payloads[0]['prompt'][0]['content'] = json.dumps(dict(question='a question'))
        with self.assertRaises(ValueError):
            split_audit([case()], metas, payloads)

    def test_package_with_findings_never_authorizes_main(self):
        row = case()
        record = review(row)
        record.update(decision='REVISE', nonduplicate='NO')
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'new'
            write_package(folder, [row], [record], [], {}, {})
            readiness = json.loads((folder / 'readiness.json').read_text())
            self.assertFalse(readiness['main_authorized'])
            self.assertEqual(readiness['unresolved_review_ids'], ['q1'])
            with self.assertRaises(ValueError):
                write_package(folder, [row], [record], [], {}, {})


class RepairTests(unittest.TestCase):
    def test_unknown_record_unchanged(self):
        row = dict(prompt=[dict(content='{}')], completion=[dict(content='answer')])
        result, meta, changes = source_repairs(row, dict(record_id='other'), {})
        self.assertEqual(row, result)
        self.assertFalse(changes)

    def test_summary_uses_existing_single_source(self):
        row = dict(prompt=[dict(content=json.dumps(dict(evidence=[dict(text='source')])) )],
                   completion=[dict(content='- First\n- Second\n- Third [1].')])
        saved = deepcopy(row)
        result, meta, changes = source_repairs(row, dict(record_id='W5_B_00008'), {})
        self.assertEqual(row, saved)
        self.assertEqual(result['completion'][0]['content'].count('[1]'), 3)
        self.assertTrue(changes)

    def test_formula_correction_requires_original_condition(self):
        row = dict(prompt=[dict(content=json.dumps(dict(evidence=[dict(text='other')])) )],
                   completion=[dict(content='claim [2] [3]')])
        with self.assertRaises(ValueError):
            source_repairs(row, dict(record_id='W5_A_00146'), {})

    def test_formula_correction_changes_only_citation(self):
        row = dict(prompt=[dict(content=json.dumps(dict(evidence=[dict(text='p = G - k')])) )],
                   completion=[dict(content='claim [2] [3]; other [4]')])
        result, _, _ = source_repairs(row, dict(record_id='W5_A_00146'), {})
        self.assertEqual(result['completion'][0]['content'], 'claim [1]; other [4]')


class DuplicateTests(unittest.TestCase):
    def rows(self, question='Different', target='READ [1]'):
        return dict(prompt=[dict(content=json.dumps(dict(question=question)))],
                    completion=[dict(content=target)])

    def test_exact_questions_are_flagged(self):
        metas = [dict(record_id='a', split='train'), dict(record_id='b', split='validation')]
        result = duplicate_audit([], metas, [self.rows(), self.rows()])
        self.assertEqual(result['internal_findings'][0]['kind'], 'QUESTION')
        self.assertNotEqual(result['internal_findings'][0]['left_split'], result['internal_findings'][0]['right_split'])

    def test_short_action_targets_are_not_duplicate_answers(self):
        metas = [dict(record_id='a', split='train'), dict(record_id='b', split='train')]
        result = duplicate_audit([], metas, [self.rows('Alpha'), self.rows('Beta')])
        self.assertFalse(result['internal_findings'])

    def test_long_structured_answer_is_compared(self):
        metas = [dict(record_id='a', split='train'), dict(record_id='b', split='train')]
        target = json.dumps(dict(items=[dict(text='A long answer with enough words to exceed the eighty character limit for duplicate target screening.', evidence_id='E1.1')]))
        result = duplicate_audit([], metas, [self.rows('Alpha', target), self.rows('Beta', target)])
        self.assertEqual(result['internal_findings'][0]['kind'], 'TARGET')

    def test_benchmark_training_question_overlap(self):
        result = duplicate_audit([case()], [dict(record_id='a', split='train')], [self.rows('A question?')])
        self.assertEqual(result['benchmark_findings'][0]['qa_id'], 'q1')
        self.assertEqual(result['benchmark_findings'][0]['kind'], 'QUESTION')


if __name__ == '__main__':
    unittest.main()
