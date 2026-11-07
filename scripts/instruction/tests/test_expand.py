"""CPU regressions for the private member-addition compiler, not quality scores."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.instruction.expand import addition_schema, audit_package, check_slots, excerpt, scan_duplicates, source_split_map
from scripts.qlora.runtime import inventory, write_json


def allocated_fixture():
    tasks = ['qa'] * 150 + ['summary'] * 50 + ['hint'] * 25 + ['insufficient_evidence'] * 25
    courses = ['THMLN'] * 100 + ['KTCTMLN'] * 75 + ['CNXHKH'] * 75
    records, slots = [], []
    for n, (task, course) in enumerate(zip(tasks, courses), 1):
        rid, group = f'W6_A_{n:05}', course + ':ch01.pdf'
        records.append(dict(record_id=rid, author_member='A', task_type=task, course_code=course,
                            source_group_ids=[group], contexts=[dict(page_number=2, source_checksum='a' * 64)]))
        slots.append(dict(record_id=rid, owner_member='A', task_type=task, course_code=course,
                          source_group_id=group, page_start='1', page_end='3', source_checksum='a' * 64))
    return records, slots


class AdditionTests(unittest.TestCase):
    def test_excerpt_matches_spacing_without_rewriting_original_words(self):
        self.assertEqual(excerpt('Heading\nStart text.\nEnd here. Footer', 'Starttext.', 'End here.'), 'Start text. End here.')

    def test_excerpt_unicode_is_normalized(self):
        self.assertEqual(excerpt('Cafe\u0301 finish.', 'Caf\u00e9', 'finish.'), 'Caf\u00e9 finish.')

    def test_repeated_start_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_START_NOT_UNIQUE'):
            excerpt('start x start end', 'start', 'end')

    def test_empty_anchors_rejected(self):
        for start, end in [('', 'end'), ('start', ' '), (' ', '')]:
            with self.subTest(start=start, end=end), self.assertRaisesRegex(ValueError, 'EMPTY_SOURCE_ANCHOR'):
                excerpt('start end', start, end)

    def test_missing_end_rejected(self):
        with self.assertRaises(ValueError):
            excerpt('start no ending', 'start', 'absent')

    def test_schema_extension_does_not_modify_original(self):
        original = {'properties': {'record_id': {'pattern': '^W5_[AB]_[0-9]{5}$'}, 'schema_version': {'const':'w5-instruction-v1'}}}
        before = deepcopy(original)
        updated = addition_schema(original)
        self.assertEqual(original, before)
        self.assertEqual(updated['properties']['record_id']['pattern'], '^W6_[AB]_[0-9]{5}$')
        self.assertEqual(updated['properties']['schema_version'], before['properties']['schema_version'])

    def test_locked_250_slots_pass(self):
        check_slots(*allocated_fixture())

    def test_member_b_uses_only_b_slots_and_record_namespace(self):
        records, slots = allocated_fixture()
        for row, slot in zip(records, slots):
            row.update(record_id=row['record_id'].replace('W6_A_', 'W6_B_'), author_member='B')
            slot.update(record_id=row['record_id'], owner_member='B')
        check_slots(records, slots, member='B')
        with self.assertRaises(ValueError):
            check_slots(records, slots)

    def test_old_nested_and_new_flat_metadata_split(self):
        self.assertEqual(source_split_map([
            dict(record=dict(source_group_ids=['one']),split='train'),
            dict(source_group_ids=['two'],split='instruction_holdout')]),
            {'one':'train','two':'instruction_holdout'})

    def test_source_group_cannot_cross_split(self):
        with self.assertRaisesRegex(ValueError, 'OLD_SOURCE_SPLIT'):
            source_split_map([dict(source_group_ids=['one'],split=s) for s in ('train','validation')])

    def test_incomplete_249_fails(self):
        records, slots = allocated_fixture()
        with self.assertRaisesRegex(ValueError, 'MEMBER_QUOTA'):
            check_slots(records[:-1], slots)

    def test_duplicate_id_fails(self):
        records, slots = allocated_fixture()
        records[0]['record_id'] = records[1]['record_id']
        with self.assertRaisesRegex(ValueError, 'SLOT_IDS'):
            check_slots(records, slots)

    def test_author_course_task_and_group_cannot_change(self):
        for field, value in [('author_member','B'),('course_code','CNXHKH'),('task_type','hint'),('source_group_ids',['other'])]:
            records, slots = allocated_fixture()
            records[0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'SLOT_BINDING'):
                check_slots(records, slots)

    def test_page_and_checksum_are_bound(self):
        for field, value in [('page_number',4),('source_checksum','b' * 64)]:
            records, slots = allocated_fixture()
            records[0]['contexts'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'SLOT_PAGE_OR_CHECKSUM'):
                check_slots(records, slots)

    def test_wrong_task_total_fails_even_if_slots_match(self):
        records, slots = allocated_fixture()
        records[0]['task_type'] = slots[0]['task_type'] = 'hint'
        with self.assertRaisesRegex(ValueError, 'TASK_QUOTA'):
            check_slots(records, slots)

    @patch('scripts.w5.quality.benchmark_inputs', return_value=(set(), [], set(), set(), []))
    def test_duplicate_new_questions_and_long_targets(self, mock):
        text = 'An independently written long explanation with concrete claims rather than an action or refusal. ' * 2
        rows = [dict(record_id='A1',question='A very specific question about a process?',target_text=text),
                dict(record_id='A2',question='A very specific question about a process?',target_text=text)]
        issues, _ = scan_duplicates(rows, [], {})
        self.assertTrue({'EXACT_QUESTION_REUSE','NEW_QUESTION_NEAR','NEW_TARGET_NEAR'} <= {r['code'] for r in issues})

    @patch('scripts.w5.quality.benchmark_inputs', return_value=(set(), [], set(), set(), []))
    def test_old_question_is_not_a_new_sample(self, mock):
        row = dict(record_id='old', question='Which exact mechanism is responsible?', target_text='Distinct short answer.')
        issues, nearest = scan_duplicates([dict(row,record_id='new')], [row], {})
        self.assertIn('OLD_QUESTION_NEAR', {r['code'] for r in issues})
        self.assertEqual(nearest[0]['closest_old_id'], 'old')

    def test_protected_question_and_id_are_excluded(self):
        question = 'Which source establishes this rule?'
        row = dict(record_id='protected',question=question,target_text='A short answer.')
        with patch('scripts.w5.quality.benchmark_inputs',return_value=(set(),[question],{'protected'},set(),[])):
            issues, _ = scan_duplicates([row], [], {})
        self.assertTrue({'EXACT_QUESTION_REUSE','BENCHMARK_NEAR'} <= {r['code'] for r in issues})

    def test_long_benchmark_target_rejected(self):
        text = 'Reference statement with enough detail to exceed the minimum target length and detect reuse safely.'
        row = dict(record_id='new',question='An unrelated question?',target_text=text)
        with patch('scripts.w5.quality.benchmark_inputs',return_value=(set(),[],set(),set(),[text])):
            issues, _ = scan_duplicates([row], [], {})
        self.assertIn('BENCHMARK_TARGET_NEAR', {r['code'] for r in issues})

    def test_integrity_rejects_changed_file_before_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / 'candidates.jsonl'
            path.write_text('{}\n', encoding='utf8')
            write_json(folder / 'manifest.json', dict(files=inventory(folder)))
            path.write_text('{"tampered":true}\n', encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'ARTIFACT_INTEGRITY'):
                audit_package(folder, None, {}, [], [])

    def test_unlisted_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_json(folder / 'manifest.json', dict(files={}))
            (folder / 'unexpected.json').write_text('{}', encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'PACKAGE_FILE_SET'):
                audit_package(folder, None, {}, [], [])


if __name__ == '__main__':
    unittest.main()
