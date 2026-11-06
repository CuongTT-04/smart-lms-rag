from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

from scripts.qlora.data import (authenticate, digest, loads, read_rows, sha_file,
                                tokenize_payload, within)
from scripts.qlora.runtime import write_json


class Tokenizer:
    eos_token_id = 2
    prompt = [4, 5]
    completion = [6, 7, 2, 8]

    def apply_chat_template(self, messages, **options):
        return self.prompt[:] if options['add_generation_prompt'] else self.prompt + self.completion

    def encode(self, text, **options):
        return [8]


class DataTests(unittest.TestCase):
    def test_canonical_unicode_matches_contract(self):
        self.assertEqual(digest({'x': '\u00e9'}), digest({'x': 'e\u0301'}))

    def test_duplicate_keys_and_nonfinite_rejected(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError):
                loads(text)

    def test_paths_confined(self):
        root = Path.cwd()
        for name in ('../outside', '/outside', 'C:/outside', '..\\outside'):
            with self.assertRaises(ValueError):
                within(root, name)

    def test_exact_prompt_eos_and_post_format_mask(self):
        result = self.tokenize(Tokenizer())
        self.assertEqual(result['labels'], [-100, -100, 6, 7, 2, -100])
        self.assertEqual(result['supervised_tokens'], 3)
        self.assertEqual(result['completion_tokens'], 4)

    def tokenize(self, tokenizer, **limits):
        return tokenize_payload({'prompt': [{}], 'completion': [{}]}, tokenizer,
                                dict(max_prompt_tokens=2, max_completion_tokens=4,
                                     max_sequence_tokens=6, **limits))

    def test_budget_boundary_and_no_truncation(self):
        tok = Tokenizer()
        self.tokenize(tok)
        tok.completion = [6, 7, 7, 2, 8]
        with self.assertRaisesRegex(ValueError, 'TOKEN_BUDGET'):
            self.tokenize(tok)

    def test_missing_or_duplicate_eos_rejected(self):
        for completion in ([6, 7, 8], [6, 2, 2, 8]):
            tok = Tokenizer()
            tok.completion = completion
            with self.assertRaisesRegex(ValueError, 'COMPLETION_EOS'):
                self.tokenize(tok)

    def test_empty_target_and_post_eos_content_rejected(self):
        for completion in ([2, 8], [6, 2, 99]):
            tok = Tokenizer()
            tok.completion = completion
            with self.assertRaises(ValueError):
                self.tokenize(tok)

    def test_hash_and_split_authentication(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            contract = {'model': {'model_id': 'model', 'revision': 'rev', 'tokenizer_revision': 'rev'}}
            selection = {'splits': {'train': ['a'], 'validation': ['b']}, 'excluded_holdout_ids': ['h']}
            write_json(folder / 'training-contract.json', contract)
            write_json(folder / 'selection.json', selection)
            files = {p.name: {'sha256': sha_file(p), 'size_bytes': p.stat().st_size}
                     for p in folder.iterdir()}
            manifest = dict(files=files, contract_sha256=digest(contract),
                            counts={'train': 128, 'validation': 32}, holdout_payload_included=False)
            write_json(folder / 'manifest.json', manifest)
            config = dict(data_manifest_sha256=sha_file(folder / 'manifest.json'),
                          contract_sha256=digest(contract), model_id='model', revision='rev')
            authenticate(folder, config)
            (folder / 'selection.json').write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'DATA_INTEGRITY'):
                authenticate(folder, config)
            with self.assertRaisesRegex(ValueError, 'MANIFEST_HASH'):
                authenticate(folder, dict(config, data_manifest_sha256='0' * 64))

    def test_jsonl_does_not_accept_blanks_or_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'rows.jsonl'
            for text in ('{}\n\n', '{"a":1,"a":2}\n'):
                path.write_text(text, encoding='utf-8')
                with self.assertRaises(ValueError):
                    read_rows(path)
