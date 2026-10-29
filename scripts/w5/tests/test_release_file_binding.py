from copy import deepcopy
from pathlib import Path
import unittest

from scripts.w5.cli import bind_release_files
from scripts.w5.common import digest


class ReleaseFileBindingTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(record_id=rid, content_sha256=rid) for rid in ('A', 'B', 'C')]
        self.plan = {'splits': dict(zip(('train', 'validation', 'instruction_holdout'), [['A'], ['B'], ['C']]))}
        self.payloads = [Path(split + '.jsonl') for split in self.plan['splits']]
        self.sidecars = [Path(split + '.metadata.jsonl') for split in self.plan['splits']]
        self.files = {}
        for payload, sidecar, row in zip(self.payloads, self.sidecars, self.rows):
            content = dict(prompt=[dict(role='user', content=row['record_id'])],
                           completion=[dict(role='assistant', content='answer')])
            self.files[payload] = [content]
            self.files[sidecar] = [dict(record_id=row['record_id'], content_sha256=row['content_sha256'],
                sft_sha256=digest(content), split=payload.stem, row_index=0)]

    def call(self):
        return bind_release_files(self.rows, self.plan, self.payloads, self.sidecars,
                                  load_rows=lambda path: self.files[path])

    def test_valid_three_split_files(self):
        rows, payload = self.call()
        self.assertEqual(rows, self.rows)
        self.assertEqual(len(payload), 3)

    def test_swapped_train_holdout_with_matching_sidecars_rejected(self):
        for paths in (self.payloads, self.sidecars):
            a, b = paths[0], paths[2]
            self.files[a], self.files[b] = self.files[b], self.files[a]
        with self.assertRaisesRegex(ValueError, 'Physical split IDs'):
            self.call()

    def test_file_boundary_shift_rejected(self):
        for paths in (self.payloads, self.sidecars):
            self.files[paths[0]].extend(self.files[paths[1]])
            self.files[paths[1]] = []
        with self.assertRaisesRegex(ValueError, 'Physical split IDs'):
            self.call()

    def test_declared_split_and_row_index_are_checked(self):
        original = deepcopy(self.files[self.sidecars[0]][0])
        for key, value, message in [('split', 'instruction_holdout', 'declared split'),
                                     ('row_index', 4, 'row position')]:
            self.files[self.sidecars[0]][0] = {**original, key: value}
            with self.assertRaisesRegex(ValueError, message):
                self.call()

    def test_missing_duplicate_and_mispaired_files_rejected(self):
        for payloads, sidecars in [(self.payloads[:2], self.sidecars[:2]),
                                  ([self.payloads[0]] * 3, [self.sidecars[0]] * 3),
                                  (self.payloads, list(reversed(self.sidecars)))]:
            with self.assertRaises(ValueError):
                bind_release_files(self.rows, self.plan, payloads, sidecars,
                                   load_rows=lambda path: self.files[path])

    def test_payload_hash_mismatch_rejected(self):
        self.files[self.payloads[0]][0]['completion'][0]['content'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.call()
