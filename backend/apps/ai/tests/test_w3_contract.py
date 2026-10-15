import unittest
from dataclasses import replace
from apps.ai.embeddings.base import EmbeddingConfig
from apps.documents.retrieval_contracts import ChunkingConfig


class W3ContractTests(unittest.TestCase):
    def test_512_content_plus_two_specials_requires_514_encoder(self):
        from apps.ai.retrieval.w3_contract import validate_token_budget
        chunking = ChunkingConfig(tokenizer_revision=EmbeddingConfig().revision)
        validate_token_budget(chunking, EmbeddingConfig(max_tokens=514), special_tokens=2)
        for config, special in ((EmbeddingConfig(), 2),
                                 (EmbeddingConfig(max_tokens=514), 3),
                                 (replace(EmbeddingConfig(max_tokens=514), revision='a'*40), 2)):
            with self.subTest(config=config, special=special), self.assertRaises(ValueError):
                validate_token_budget(chunking, config, special_tokens=special)
