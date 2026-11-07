from copy import deepcopy
import unittest
import torch

from scripts.qlora.collator import CompletionCollator


def row():
    return {'input_ids': [10, 11, 12, 13, 2, 14], 'attention_mask': [1] * 6,
            'labels': [-100, -100, 12, 13, 2, -100]}


class CollatorTests(unittest.TestCase):
    def setUp(self):
        self.collator = CompletionCollator(pad_token_id=0, eos_token_id=2)

    def test_right_padding_dtype_and_input_immutability(self):
        original = row()
        saved = deepcopy(original)
        batch = self.collator([original])
        self.assertEqual(original, saved)
        self.assertEqual(set(batch), {'input_ids', 'attention_mask', 'labels'})
        self.assertTrue(all(t.dtype == torch.long and t.shape == (1, 8) for t in batch.values()))
        self.assertEqual(batch['input_ids'][0].tolist(), original['input_ids'] + [0, 0])
        self.assertEqual(batch['attention_mask'][0].tolist(), [1] * 6 + [0, 0])
        self.assertEqual(batch['labels'][0].tolist(), original['labels'] + [-100, -100])

    def test_variable_length_batch_stable_multiple(self):
        short = row()
        longer = {k: [10] * 4 + v if k == 'input_ids' else
                  ([1] * 4 + v if k == 'attention_mask' else [-100] * 4 + v)
                  for k, v in row().items()}
        self.assertEqual(self.collator([short, longer])['input_ids'].shape, (2, 16))

    def test_does_not_double_shift_labels(self):
        labels = self.collator([row()])['labels'][0].tolist()
        self.assertEqual(labels[2:5], [12, 13, 2])

    def test_rejects_metadata(self):
        sample = dict(row(), record_id='private-id')
        with self.assertRaisesRegex(ValueError, 'MODEL_INPUT_FIELDS'):
            self.collator([sample])

    def test_rejects_bad_shapes(self):
        sample = row()
        sample['attention_mask'].pop()
        with self.assertRaisesRegex(ValueError, 'TOKEN_SHAPES'):
            self.collator([sample])

    def test_rejects_prepadded_rows(self):
        sample = row()
        sample['attention_mask'][-1] = 0
        with self.assertRaisesRegex(ValueError, 'PREPADDING'):
            self.collator([sample])

    def test_rejects_bool_tokens(self):
        sample = row()
        sample['input_ids'][0] = True
        with self.assertRaisesRegex(ValueError, 'TOKEN_TYPES'):
            self.collator([sample])

    def test_rejects_empty_batch(self):
        with self.assertRaisesRegex(ValueError, 'EMPTY_BATCH'):
            self.collator([])

    def test_rejects_all_masked_or_prompt_loss(self):
        for labels in ([-100] * 6, row()['input_ids'][:5] + [-100]):
            sample = dict(row(), labels=labels)
            with self.assertRaisesRegex(ValueError, 'COMPLETION_MASK'):
                self.collator([sample])

    def test_rejects_label_mismatch_and_multiple_eos(self):
        for labels in ([-100, -100, 99, 13, 2, -100], [-100, -100, 2, 13, 2, -100]):
            with self.assertRaisesRegex(ValueError, 'LABEL_IDS_OR_EOS'):
                self.collator([dict(row(), labels=labels)])

    def test_rejects_mask_holes_and_missing_eos(self):
        for labels in ([-100, -100, 12, -100, 2, -100], [-100, -100, 12, 13, -100, -100]):
            with self.assertRaises(ValueError):
                self.collator([dict(row(), labels=labels)])

    def test_rejects_padding_that_exceeds_limit(self):
        with self.assertRaisesRegex(ValueError, 'PADDED_TOKEN_LIMIT'):
            CompletionCollator(pad_token_id=0, eos_token_id=2, max_sequence_tokens=7)([row()])
