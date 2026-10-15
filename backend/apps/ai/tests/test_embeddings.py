import json
from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import numpy as np

from apps.ai.embeddings.base import EmbeddingConfig, EmbeddingError
from apps.ai.embeddings.service import EmbeddingService


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.service = EmbeddingService(EmbeddingConfig(max_tokens=8))
        self.model = MagicMock()
        self.model.tokenizer.encode.side_effect = lambda text, **kwargs: [0] * (len(text.split()) + 2)
        self.model.encode.side_effect = self.encode
        self.model.get_sentence_embedding_dimension.return_value = 1024
        self.model.get_embedding_dimension.return_value = 1024
        self.records = [{"chunk_id": "b", "text": "second", "page_number": 2}, {"chunk_id": "a", "text": "first", "page_number": 1}]

    @staticmethod
    def encode(texts, **kwargs):
        vectors = np.zeros((len(texts), 1024), dtype=np.float64)
        for row, text in enumerate(texts):
            vectors[row, sum(map(ord, text)) % 1024] = 1
        return vectors

    def assert_code(self, code, records):
        with patch.object(self.service, "_load_model", return_value=self.model):
            with self.assertRaises(EmbeddingError) as ctx:
                self.service.embed_chunks(records)
        self.assertEqual(ctx.exception.code, code)

    def test_ids_rows_and_metadata_are_preserved(self):
        before = json.dumps(self.records)
        with patch.object(self.service, "_load_model", return_value=self.model):
            result = self.service.embed_chunks(self.records)
            reverse = self.service.embed_chunks(self.records[::-1])
        self.assertEqual(result.chunk_ids, ("b", "a"))
        np.testing.assert_array_equal(reverse.vectors, result.vectors[::-1])
        self.assertEqual(json.dumps(self.records), before)
        self.assertEqual(result.token_counts, (3, 3))
        self.assertEqual(result.vectors.dtype, np.float32)
        self.assertTrue(result.vectors.flags.c_contiguous)
        self.assertEqual(result.config_hash, self.service.config.fingerprint())
        kwargs = self.model.encode.call_args.kwargs
        self.assertTrue(kwargs["normalize_embeddings"])
        self.assertEqual(kwargs["prompt"], "")

    def test_empty_input_does_not_load_model(self):
        with patch.object(self.service, "_load_model") as load:
            result = self.service.embed_chunks([])
        load.assert_not_called()
        self.assertEqual(result.vectors.shape, (0, 1024))

    def test_invalid_records(self):
        for records in ("text", None, [{}], ["text"]):
            with self.subTest(records=records):
                code = "INVALID_CHUNK_ID" if records == [{}] else "INVALID_INPUT"
                self.assert_code(code, records)

    def test_invalid_ids(self):
        for chunk_id in (None, "", " ", " padded ", 123):
            with self.subTest(chunk_id=chunk_id):
                self.assert_code("INVALID_CHUNK_ID", [{"chunk_id": chunk_id, "text": "valid"}])

    def test_empty_or_nonstring_text(self):
        for text in (None, "", " \n", 123):
            with self.subTest(text=text):
                self.assert_code("EMPTY_TEXT", [{"chunk_id": "a", "text": text}])

    def test_duplicate_ids_rejected_before_model_load(self):
        with patch.object(self.service, "_load_model") as load:
            with self.assertRaises(EmbeddingError) as ctx:
                self.service.embed_chunks([self.records[0], self.records[0]])
        self.assertEqual(ctx.exception.code, "DUPLICATE_CHUNK_ID")
        load.assert_not_called()

    def test_overlong_input_rejected_without_encoding(self):
        self.assert_code("TOKEN_LIMIT_EXCEEDED", [{"chunk_id": "a", "text": "word " * 7}])
        self.model.encode.assert_not_called()
        self.model.tokenizer.encode.assert_called_with("word " * 7, add_special_tokens=True, truncation=False, verbose=False)

    def test_exact_token_boundary_is_accepted(self):
        with patch.object(self.service, "_load_model", return_value=self.model):
            result = self.service.embed_chunks([{"chunk_id": "a", "text": "word " * 6}])
        self.assertEqual(result.token_counts, (8,))

    def test_inference_failure_has_explicit_code(self):
        self.model.encode.side_effect = RuntimeError("out of memory")
        self.assert_code("ENCODING_FAILED", self.records)

    def test_shape_mismatch(self):
        self.model.encode.side_effect = None
        for shape in ((1, 1024), (2, 512)):
            with self.subTest(shape=shape):
                self.model.encode.return_value = np.ones(shape)
                self.assert_code("INVALID_VECTOR_SHAPE", self.records)

    def test_nonfinite_vector(self):
        self.model.encode.side_effect = None
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                self.model.encode.return_value = np.full((2, 1024), value)
                self.assert_code("NONFINITE_VECTOR", self.records)

    def test_invalid_norm(self):
        self.model.encode.side_effect = None
        for value in (0.0, 1.0):
            with self.subTest(value=value):
                self.model.encode.return_value = np.full((2, 1024), value)
                self.assert_code("INVALID_VECTOR_NORM", self.records)

    def test_integer_vectors_rejected(self):
        self.model.encode.side_effect = None
        self.model.encode.return_value = np.ones((2, 1024), dtype=np.int32)
        self.assert_code("INVALID_VECTOR_DTYPE", self.records)

    def test_query_uses_same_contract(self):
        with patch.object(self.service, "_load_model", return_value=self.model):
            vector = self.service.embed_query("question")
        self.assertEqual(vector.shape, (1024,))
        self.assertEqual(vector.dtype, np.float32)

    def test_model_loads_once_and_revision_is_pinned(self):
        constructor = MagicMock(return_value=self.model)
        with patch.dict("sys.modules", {"sentence_transformers": SimpleNamespace(SentenceTransformer=constructor)}):
            self.service.embed_chunks(self.records)
            self.service.embed_query("question")
        constructor.assert_called_once_with(
            "BAAI/bge-m3", revision=self.service.config.revision, device="cpu",
            local_files_only=True, trust_remote_code=False,
        )
        self.model.float.assert_called_once()
        self.assertEqual(self.model.max_seq_length, 8)

    def test_load_failure_can_retry(self):
        constructor = MagicMock(side_effect=[RuntimeError("missing cache"), self.model])
        with patch.dict("sys.modules", {"sentence_transformers": SimpleNamespace(SentenceTransformer=constructor)}):
            with self.assertRaises(EmbeddingError) as ctx:
                self.service.embed_chunks(self.records)
            self.assertEqual(ctx.exception.code, "MODEL_LOAD_FAILED")
            self.service.embed_chunks(self.records)
        self.assertEqual(constructor.call_count, 2)

    def test_model_dimension_mismatch(self):
        self.model.get_sentence_embedding_dimension.return_value = 512
        self.model.get_embedding_dimension.return_value = 512
        constructor = MagicMock(return_value=self.model)
        with patch.dict("sys.modules", {"sentence_transformers": SimpleNamespace(SentenceTransformer=constructor)}):
            with self.assertRaises(EmbeddingError) as ctx:
                self.service.embed_chunks(self.records)
        self.assertEqual(ctx.exception.code, "INVALID_DIMENSION")
        self.assertIsNone(self.service._model)

    def test_config_roundtrip_and_fingerprint(self):
        fingerprints = []
        for offline in (True, False):
            with self.subTest(local_files_only=offline):
                expected = EmbeddingConfig(local_files_only=offline)
                payload = json.dumps(asdict(expected))
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "fixture-config.json"
                    path.write_text(payload, encoding="utf-8")
                    config = EmbeddingConfig.from_file(path)
                self.assertEqual(config, expected)
                self.assertEqual(config.fingerprint(), expected.fingerprint())
                self.assertEqual(len(config.fingerprint()), 64)
                self.assertNotEqual(config.fingerprint(), replace(config, batch_size=4).fingerprint())
                fingerprints.append(config.fingerprint())
        self.assertNotEqual(*fingerprints)

    def test_invalid_config(self):
        for settings in ({"revision": "main"}, {"batch_size": 0}, {"batch_size": True}, {"max_tokens": 8193}, {"max_tokens": 0}, {"normalize_embeddings": False}, {"dimension": 768}, {"device": "auto"}, {"dtype": "float16"}, {"local_files_only": "true"}, {"model_id": "other"}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                EmbeddingConfig(**settings)
