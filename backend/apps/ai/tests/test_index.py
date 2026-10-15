from copy import deepcopy
from dataclasses import replace
import unittest

import numpy as np

from apps.ai.embeddings.base import EmbeddedChunks, EmbeddingConfig
from apps.ai.retrieval.index import DenseIndex, IndexError


class DenseIndexTests(unittest.TestCase):
    def setUp(self):
        self.config = EmbeddingConfig()
        self.chunks = [
            {
                "chunk_id": f"chunk-{row}", "text": f"text-{row}",
                "course_id": "00000000-0000-4000-8000-000000000001",
                "document_id": "00000000-0000-4000-8000-000000000101",
                "version_id": "00000000-0000-4000-8000-000000001001",
                "document_title": "Fixture", "page_number": row + 1,
            }
            for row in range(3)
        ]
        self.vectors = np.zeros((3, 1024), dtype=np.float32)
        for row in range(3):
            self.vectors[row, row] = 1
        self.embeddings = EmbeddedChunks(tuple(c["chunk_id"] for c in self.chunks), self.vectors, (3, 3, 3), self.config.fingerprint())

    def build(self, chunks=None, embeddings=None):
        return DenseIndex(self.chunks if chunks is None else chunks, self.embeddings if embeddings is None else embeddings, self.config)

    def assert_build_error(self, code, chunks=None, embeddings=None):
        with self.assertRaises(IndexError) as ctx:
            self.build(chunks, embeddings)
        self.assertEqual(ctx.exception.code, code)

    def test_self_search_returns_exact_source(self):
        index = self.build()
        self.assertEqual(index.count, 3)
        for row in range(3):
            result = index.search(self.vectors[row], 1)[0]
            self.assertEqual(result["chunk_id"], f"chunk-{row}")
            self.assertEqual(result["source"]["page_number"], row + 1)
            self.assertAlmostEqual(result["score"], 1)

    def test_ranking_matches_numpy_inner_product(self):
        query = np.zeros(1024, dtype=np.float32)
        query[:3] = [0.2, 0.9, 0.4]
        query /= np.linalg.norm(query)
        results = self.build().search(query, 3)
        scores = self.vectors @ query
        expected = np.argsort(-scores)
        self.assertEqual([r["chunk_id"] for r in results], [f"chunk-{i}" for i in expected])
        np.testing.assert_allclose([r["score"] for r in results], scores[expected], atol=1e-6)
        self.assertEqual([r["rank"] for r in results], [1, 2, 3])

    def test_top_k_larger_than_index_returns_only_real_rows(self):
        self.assertEqual(len(self.build().search(self.vectors[0], 10)), 3)

    def test_metadata_is_not_mutated_or_shared(self):
        index = self.build()
        self.chunks[0]["page_number"] = 99
        first = index.search(self.vectors[0], 1)[0]
        self.assertEqual(first["source"]["page_number"], 1)
        first["source"]["page_number"] = 50
        self.assertEqual(index.search(self.vectors[0], 1)[0]["source"]["page_number"], 1)
        manifest = index.manifest()
        manifest["vector_mapping"][0]["source"]["page_number"] = 42
        self.assertEqual(index.manifest()["vector_mapping"][0]["source"]["page_number"], 1)

    def test_manifest_describes_index_and_config(self):
        manifest = self.build().manifest()
        self.assertEqual(manifest["index_type"], "IndexFlatIP")
        self.assertEqual(manifest["vector_count"], 3)
        self.assertEqual(manifest["embedding_config_hash"], self.config.fingerprint())
        self.assertEqual([r["chunk_id"] for r in manifest["vector_mapping"]], list(self.embeddings.chunk_ids))
        changed = deepcopy(self.chunks)
        changed[0]["text"] = "different text"
        self.assertNotEqual(manifest["chunks_sha256"], self.build(changed).manifest()["chunks_sha256"])
        self.assertIsInstance(self.build().serialize(), bytes)

    def test_building_again_does_not_append_duplicates(self):
        self.assertEqual(self.build().count, 3)
        self.assertEqual(self.build().count, 3)

    def test_empty_or_invalid_chunks(self):
        for chunks in ([], "bad", [None]):
            with self.subTest(chunks=chunks):
                self.assert_build_error("INVALID_CHUNKS", chunks=chunks)

    def test_invalid_ids_or_text(self):
        for key, value, code in (("chunk_id", " ", "INVALID_CHUNK_ID"), ("text", "", "EMPTY_TEXT")):
            chunks = deepcopy(self.chunks)
            chunks[0][key] = value
            self.assert_build_error(code, chunks=chunks)

    def test_duplicate_ids(self):
        chunks = deepcopy(self.chunks)
        chunks[1]["chunk_id"] = chunks[0]["chunk_id"]
        self.assert_build_error("DUPLICATE_CHUNK_ID", chunks=chunks)

    def test_source_uuid_and_page_validation(self):
        for key, value in (("version_id", "wrong"), ("document_id", None), ("page_number", 0), ("page_number", True)):
            with self.subTest(key=key, value=value):
                chunks = deepcopy(self.chunks)
                chunks[0][key] = value
                self.assert_build_error("INVALID_SOURCE", chunks=chunks)

    def test_wrong_mapping_order(self):
        self.assert_build_error("MAPPING_MISMATCH", embeddings=replace(self.embeddings, chunk_ids=self.embeddings.chunk_ids[::-1]))

    def test_wrong_embedding_configuration(self):
        self.assert_build_error("CONFIG_MISMATCH", embeddings=replace(self.embeddings, config_hash="wrong"))

    def test_wrong_vector_shape(self):
        self.assert_build_error("INVALID_VECTOR_SHAPE", embeddings=replace(self.embeddings, vectors=np.ones((3, 512), dtype=np.float32)))

    def test_wrong_dtype_and_nonfinite_vectors(self):
        for vectors in (self.vectors.astype(np.float64), np.full((3, 1024), np.nan, dtype=np.float32)):
            with self.subTest(dtype=vectors.dtype):
                self.assert_build_error("INVALID_VECTORS", embeddings=replace(self.embeddings, vectors=vectors))

    def test_unnormalized_vectors(self):
        self.assert_build_error("INVALID_VECTOR_NORM", embeddings=replace(self.embeddings, vectors=self.vectors * 2))

    def test_non_json_metadata_rejected(self):
        chunks = deepcopy(self.chunks)
        chunks[0]["extra"] = object()
        self.assert_build_error("INVALID_METADATA", chunks=chunks)

    def test_query_validation(self):
        index = self.build()
        for query in (np.zeros(1024, dtype=np.float32), self.vectors[0].astype(np.float64), np.full(1024, np.nan, dtype=np.float32), np.ones(512, dtype=np.float32)):
            with self.subTest(shape=query.shape), self.assertRaises(IndexError) as ctx:
                index.search(query, 1)
            self.assertEqual(ctx.exception.code, "INVALID_QUERY")
        for k in (0, -1, True, 1.5):
            with self.subTest(k=k), self.assertRaises(IndexError) as ctx:
                index.search(self.vectors[0], k)
            self.assertEqual(ctx.exception.code, "INVALID_TOP_K")
