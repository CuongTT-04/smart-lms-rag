from copy import deepcopy
import unittest
from scripts.instruction.combine import bind_rows
from scripts.qlora.data import digest


class CombineTests(unittest.TestCase):
    def rows(self):
        payload = dict(prompt=[{'role':'user','content':'fixture'}], completion=[{'role':'assistant','content':'fixture'}])
        return [dict(payload=payload, metadata=dict(record_id='W5_A_00001', split='train',
            source_group_ids=['doc-1'], variant_family_id='family-1', sft_sha256=digest(payload))) ]

    def test_preserves_authenticated_payload_and_physical_split(self):
        row = self.rows()[0]
        result = bind_rows(self.rows(), [])
        self.assertEqual(result['train'][0]['payload'], row['payload'])
        self.assertEqual(result['train'][0]['metadata']['record_id'], 'W5_A_00001')

    def test_rejects_new_source_group_crossing_an_inherited_split(self):
        old = self.rows()
        other = deepcopy(old[0])
        other['metadata'].update(record_id='W6_B_00001', split='validation', variant_family_id='new-family')
        with self.assertRaisesRegex(ValueError, 'GROUP_SPLIT_LEAKAGE'):
            bind_rows(old, [other])

    def test_rejects_duplicate_id_and_forged_payload_hash(self):
        old = self.rows()
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_ID'):
            bind_rows(old, deepcopy(old))
        old[0]['payload']['completion'][0]['content'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'PAYLOAD_BINDING'):
            bind_rows(old, [])
