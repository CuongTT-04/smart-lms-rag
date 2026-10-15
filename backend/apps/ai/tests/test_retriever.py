from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

import numpy as np

from apps.ai.embeddings.base import EmbeddedChunks, EmbeddingConfig, EmbeddingError
from apps.ai.retrieval.index import DenseIndex
from apps.ai.retrieval.retriever import RetrievalError, RetrievalScope, RetrievalService


COURSE_A = "00000000-0000-4000-8000-000000000001"
COURSE_B = "00000000-0000-4000-8000-000000000002"
VERSION_A = "00000000-0000-4000-8000-000000001001"
VERSION_B = "00000000-0000-4000-8000-000000001002"
USER = "00000000-0000-4000-8000-000000000999"
DOC = "00000000-0000-4000-8000-000000000101"


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.config = EmbeddingConfig()
        self.chunks = [{"chunk_id": f"chunk-{i}", "text": f"fixture-{i}",
                        "course_id": COURSE_B if i < 2 else COURSE_A,
                        "document_id": DOC, "version_id": VERSION_B if i < 2 else VERSION_A,
                        "page_number": i + 1, "original_storage_key": "private/do-not-expose"} for i in range(4)]
        vectors = np.zeros((4, 1024), dtype=np.float32)
        vectors[np.arange(4), np.arange(4)] = 1
        self.index = DenseIndex(self.chunks, EmbeddedChunks(tuple(c["chunk_id"] for c in self.chunks), vectors, (), self.config.fingerprint()), self.config)
        # Global top-2 are both forbidden; allowed rows 2 and 3 must still be found.
        self.query = np.zeros(1024, dtype=np.float32)
        self.query[:4] = [0.8, 0.5, 0.2, 0.1]
        self.query /= np.linalg.norm(self.query)
        self.embedding = SimpleNamespace(config=self.config, embed_query=MagicMock(return_value=self.query))
        self.scope = RetrievalScope(USER, COURSE_A, frozenset({VERSION_A}))
        self.resolver = MagicMock(side_effect=lambda request: self.scope)
        self.service = RetrievalService(self.index, self.embedding, self.resolver)

    def test_searches_allowed_subset_before_top_k(self):
        result = self.service.retrieve("question", self.scope, 2)
        self.assertEqual([r["chunk_id"] for r in result["results"]], ["chunk-2", "chunk-3"])
        self.assertEqual(result["returned_count"], 2)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(self.resolver.call_count, 3)
        self.assertEqual([r["rank"] for r in result["results"]], [1, 2])

    def test_smaller_scope_returns_fewer_results_without_foreign_sources(self):
        result = self.service.retrieve("question", self.scope, 10)
        self.assertEqual(result["returned_count"], 2)
        self.assertTrue(all(r["source"]["course_id"] == COURSE_A for r in result["results"]))

    def test_storage_fields_are_not_exposed(self):
        result = self.service.retrieve("question", self.scope)
        self.assertNotIn("original_storage_key", result["results"][0]["source"])
        self.assertIn("version_id", result["results"][0]["source"])

    def test_empty_scope_does_not_embed_or_fallback(self):
        self.resolver.side_effect = lambda request: replace(request, allowed_version_ids=frozenset())
        result = self.service.retrieve("question", self.scope)
        self.assertEqual(result["status"], "EMPTY_SCOPE")
        self.assertEqual(result["results"], [])
        self.embedding.embed_query.assert_not_called()

    def test_missing_indexed_sources_is_distinct(self):
        scope = replace(self.scope, allowed_version_ids=frozenset({"00000000-0000-4000-8000-000000008888"}))
        self.resolver.side_effect = lambda request: request
        result = self.service.retrieve("question", scope)
        self.assertEqual(result["status"], "NO_INDEXED_SOURCES")
        self.embedding.embed_query.assert_not_called()

    def test_foreign_version_cannot_cross_course(self):
        self.resolver.side_effect = lambda request: replace(request, allowed_version_ids=frozenset({VERSION_B}))
        self.assertEqual(self.service.retrieve("question", self.scope)["results"], [])

    def test_unapproved_version_in_same_course_is_not_retrieved(self):
        chunks = deepcopy(self.chunks)
        for chunk in chunks:
            chunk["course_id"] = COURSE_A
        vectors = np.eye(4, 1024, dtype=np.float32)
        index = DenseIndex(chunks, EmbeddedChunks(tuple(c["chunk_id"] for c in chunks), vectors, (), self.config.fingerprint()), self.config)
        service = RetrievalService(index, self.embedding, self.resolver)
        results = service.retrieve("question", self.scope, 2)["results"]
        self.assertEqual([r["chunk_id"] for r in results], ["chunk-2", "chunk-3"])
        self.assertTrue(all(r["source"]["version_id"] == VERSION_A for r in results))

    def test_explicit_empty_document_filter_does_not_broaden_scope(self):
        scope = replace(self.scope, document_ids=frozenset())
        self.resolver.side_effect = lambda request: request
        self.assertEqual(self.service.retrieve("question", scope)["status"], "EMPTY_SCOPE")

    def test_document_selection_only_narrows(self):
        scope = replace(self.scope, document_ids=frozenset({"00000000-0000-4000-8000-000000000555"}))
        self.resolver.side_effect = lambda request: request
        self.assertEqual(self.service.retrieve("question", scope)["status"], "NO_INDEXED_SOURCES")

    def test_removed_or_unpublished_version_is_excluded_by_resolver(self):
        self.resolver.side_effect = lambda request: replace(request, allowed_version_ids=frozenset({VERSION_A}))
        scope = replace(self.scope, allowed_version_ids=frozenset({VERSION_A, VERSION_B}))
        result = self.service.retrieve("question", scope)
        self.assertTrue(all(r["source"]["version_id"] == VERSION_A for r in result["results"]))

    def test_revocation_during_embedding_returns_no_sources(self):
        self.resolver.side_effect = [self.scope, replace(self.scope, allowed_version_ids=frozenset())]
        self.assertEqual(self.service.retrieve("question", self.scope)["status"], "EMPTY_SCOPE")

    def test_revocation_after_search_fails_without_returning_content(self):
        self.resolver.side_effect = [self.scope, self.scope, replace(self.scope, allowed_version_ids=frozenset())]
        with self.assertRaises(RetrievalError) as ctx:
            self.service.retrieve("question", self.scope)
        self.assertEqual(ctx.exception.code, "SCOPE_CHANGED")

    def test_new_grants_during_query_do_not_widen_initial_scope(self):
        expanded = replace(self.scope, allowed_version_ids=frozenset({VERSION_A, VERSION_B}))
        self.resolver.side_effect = [self.scope, expanded, expanded]
        result = self.service.retrieve("question", self.scope)
        self.assertTrue(all(r["source"]["version_id"] == VERSION_A for r in result["results"]))

    def test_scope_not_cached_between_calls(self):
        self.service.retrieve("question", self.scope)
        self.resolver.side_effect = lambda request: replace(request, allowed_version_ids=frozenset())
        self.assertEqual(self.service.retrieve("question", self.scope)["status"], "EMPTY_SCOPE")

    def test_forbidden_scope_is_distinct_from_empty(self):
        self.resolver.side_effect = RetrievalError("SCOPE_FORBIDDEN", "Access denied.")
        with self.assertRaises(RetrievalError) as ctx:
            self.service.retrieve("question", self.scope)
        self.assertEqual(ctx.exception.code, "SCOPE_FORBIDDEN")
        self.embedding.embed_query.assert_not_called()

    def test_resolver_failure_is_not_hidden_as_no_results(self):
        self.resolver.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(RetrievalError) as ctx:
            self.service.retrieve("question", self.scope)
        self.assertEqual(ctx.exception.code, "SCOPE_RESOLUTION_FAILED")

    def test_resolver_cannot_change_identity_or_selectors(self):
        self.resolver.side_effect = lambda request: replace(request, course_id=COURSE_B)
        with self.assertRaises(RetrievalError) as ctx:
            self.service.retrieve("question", self.scope)
        self.assertEqual(ctx.exception.code, "INVALID_SCOPE")

    def test_resolver_required_and_config_must_match(self):
        for resolver, embedding, code in ((None, self.embedding, "INVALID_RESOLVER"), (self.resolver, SimpleNamespace(config=replace(self.config, batch_size=4)), "CONFIG_MISMATCH")):
            with self.subTest(code=code), self.assertRaises(RetrievalError) as ctx:
                RetrievalService(self.index, embedding, resolver)
            self.assertEqual(ctx.exception.code, code)

    def test_embedding_errors_are_preserved(self):
        self.embedding.embed_query.side_effect = EmbeddingError("TOKEN_LIMIT_EXCEEDED", "Query too long.")
        with self.assertRaises(RetrievalError) as ctx:
            self.service.retrieve("question", self.scope)
        self.assertEqual(ctx.exception.code, "TOKEN_LIMIT_EXCEEDED")

    def test_invalid_request(self):
        for query, scope, k, code in ((" ", self.scope, 5, "INVALID_QUERY"), ("query", {}, 5, "INVALID_SCOPE"), ("query", self.scope, True, "INVALID_TOP_K"), ("query", self.scope, 0, "INVALID_TOP_K")):
            with self.subTest(code=code), self.assertRaises(RetrievalError) as ctx:
                self.service.retrieve(query, scope, k)
            self.assertEqual(ctx.exception.code, code)

    def test_scope_validation_and_hint_mode(self):
        with self.assertRaises(RetrievalError):
            RetrievalScope(USER, COURSE_A, "not-a-set")
        with self.assertRaises(RetrievalError):
            replace(self.scope, mode="other")
        scope = replace(self.scope, mode="hint")
        self.resolver.side_effect = lambda request: request
        self.assertEqual(self.service.retrieve("question", scope)["mode"], "hint")

    def test_raw_index_row_validation(self):
        self.assertEqual(self.index.search(self.query, 5, row_ids=[]), [])
        for rows in ([0, 0], [-1], [99], [True], "bad"):
            with self.subTest(rows=rows):
                from apps.ai.retrieval.index import IndexError
                with self.assertRaises(IndexError):
                    self.index.search(self.query, row_ids=rows)
