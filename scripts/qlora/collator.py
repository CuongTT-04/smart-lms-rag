"""Strict right padding for already-audited, unshifted completion-only labels."""
from dataclasses import dataclass
from .data import require


@dataclass(frozen=True)
class CompletionCollator:
    pad_token_id: int = 151643
    eos_token_id: int = 151645
    max_sequence_tokens: int = 2048
    pad_to_multiple_of: int = 8

    def pad(self, features):
        require(bool(features), 'EMPTY_BATCH')
        require(type(self.pad_to_multiple_of) is int and self.pad_to_multiple_of > 0,
                'PADDING_MULTIPLE')
        batch = {k: [] for k in ('input_ids', 'attention_mask', 'labels')}
        for row in features:
            require(set(row) == set(batch), 'MODEL_INPUT_FIELDS')
            ids, mask, labels = (row[k] for k in batch)
            require(all(isinstance(v, list) for v in (ids, mask, labels))
                    and len(ids) == len(mask) == len(labels) > 0, 'TOKEN_SHAPES')
            require(all(type(n) is int and n >= 0 for n in ids)
                    and all(type(n) is int and n == 1 for n in mask)
                    and all(type(n) is int for n in labels), 'TOKEN_TYPES_OR_PREPADDING')
            positions = [i for i, n in enumerate(labels) if n != -100]
            require(len(positions) >= 2 and positions[0] > 0
                    and positions == list(range(positions[0], positions[-1] + 1)),
                    'COMPLETION_MASK')
            require(all(labels[i] == ids[i] for i in positions)
                    and labels[positions[-1]] == self.eos_token_id
                    and sum(labels[i] == self.eos_token_id for i in positions) == 1,
                    'LABEL_IDS_OR_EOS')
        size = max(len(row['input_ids']) for row in features)
        size = ((size + self.pad_to_multiple_of - 1) // self.pad_to_multiple_of) * self.pad_to_multiple_of
        require(size <= self.max_sequence_tokens, 'PADDED_TOKEN_LIMIT')
        for row in features:
            missing = size - len(row['input_ids'])
            for key, padding in (('input_ids', self.pad_token_id), ('attention_mask', 0), ('labels', -100)):
                batch[key].append(row[key][:] + [padding] * missing)
        return batch

    def __call__(self, features):
        import torch
        return {key: torch.tensor(values, dtype=torch.long) for key, values in self.pad(features).items()}
