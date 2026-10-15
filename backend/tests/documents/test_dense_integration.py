"""Real FAISS + Django authorization; deterministic vectors only (no model download)."""
from dataclasses import asdict, replace
from unittest.mock import patch
from uuid import uuid4

import numpy as np

from apps.ai.embeddings.base import EmbeddedChunks, EmbeddingConfig
from apps.ai.retrieval.index import DenseIndex
from apps.documents.exceptions import DocumentError
from apps.documents.retrieval_contracts import Chunk
from apps.documents.retrieval_scope import resolve_scope
from tests.documents.test_retrieval_scope import ScopeFixture


class DenseIntegrationTests(ScopeFixture):
    def setUp(self):
        super().setUp()
        self.config = EmbeddingConfig(max_tokens=514)
        self.chunk = Chunk('1.0', 'chunk-1', str(self.course.pk), str(self.doc.pk),
                           str(self.version.pk), 'PDF', 1, None, 0, 'Trusted text',
                           3, 0, 12, 'a'*64, 'b'*64)
        self.catalog = {self.chunk.chunk_id: self.chunk}
        self.vector = np.zeros(1024, dtype=np.float32)
        self.vector[0] = 1
        from apps.ai.embeddings.service import EmbeddingService
        self.embedding = EmbeddingService(self.config)
        self.scope = resolve_scope(self.student, self.course.pk, session_id=self.session.pk)

    def build(self, chunks=None):
        records = [asdict(self.chunk)] if chunks is None else chunks
        vectors = np.repeat(self.vector[None, :], len(records), axis=0)
        embedded = EmbeddedChunks(tuple(c['chunk_id'] for c in records), vectors,
                                  (5,)*len(records), self.config.fingerprint())
        return DenseIndex(records, embedded, self.config)

    def retrieve(self, index=None, **kwargs):
        from apps.documents.dense_retrieval import retrieve_dense_authorized
        return retrieve_dense_authorized(self.student, 'Question', self.scope,
            index or self.build(), self.embedding, catalog=self.catalog, **kwargs)

    def test_real_dense_provider_returns_trusted_sources(self):
        with patch.object(self.embedding, 'embed_query', return_value=self.vector):
            hits = self.retrieve()
        self.assertEqual(hits[0]['chunk_id'], 'chunk-1')
        self.assertEqual(hits[0]['text'], self.chunk.text)
        self.assertEqual(hits[0]['source']['version_id'], str(self.version.pk))
        self.assertEqual(hits[0]['rank'], 1)

    def test_index_catalog_drift_rejected_before_embedding(self):
        for change in ({'text': 'Wrong'}, {'source_checksum': 'c'*64}, {'page_number': 2}):
            with self.subTest(change=change), patch.object(self.embedding, 'embed_query') as encode:
                record = {**asdict(self.chunk), **change}
                with self.assertRaises(DocumentError) as caught:
                    self.retrieve(self.build([record]))
                self.assertEqual(caught.exception.code, 'INDEX_CATALOG_MISMATCH')
                encode.assert_not_called()

    def test_extra_foreign_rows_cannot_fill_top_k(self):
        foreign = {**asdict(self.chunk), 'chunk_id': 'foreign', 'course_id': str(uuid4()),
                   'document_id': str(uuid4()), 'version_id': str(uuid4())}
        self.catalog['foreign'] = Chunk(**foreign)
        with patch.object(self.embedding, 'embed_query', return_value=self.vector):
            hits = self.retrieve(self.build([foreign, asdict(self.chunk)]), top_k=1)
        self.assertEqual([hit['chunk_id'] for hit in hits], ['chunk-1'])

    def test_revocation_during_embedding_is_blocked(self):
        def revoke(query):
            self.enrollment.status = 'WITHDRAWN'
            self.enrollment.save()
            return self.vector
        with patch.object(self.embedding, 'embed_query', side_effect=revoke):
            with self.assertRaises(DocumentError):
                self.retrieve()

    def test_unpublish_during_faiss_search_is_blocked(self):
        index = self.build()
        search = index.search
        def unpublish(*args, **kwargs):
            result = search(*args, **kwargs)
            self.doc.is_published = False
            self.doc.save()
            return result
        with patch.object(self.embedding, 'embed_query', return_value=self.vector), \
                patch.object(index, 'search', side_effect=unpublish):
            with self.assertRaises(DocumentError):
                self.retrieve(index)

    def test_empty_scope_and_spoofed_user_do_not_encode(self):
        with patch.object(self.embedding, 'embed_query') as encode:
            self.scope = resolve_scope(self.student, self.course.pk, document_ids=[])
            self.assertEqual(self.retrieve(), [])
            self.scope = replace(self.scope, user_id=str(self.owner.pk))
            with self.assertRaises(DocumentError):
                self.retrieve()
        encode.assert_not_called()

    def test_owner_preview_survives_scope_conversion(self):
        from apps.documents.dense_retrieval import retrieve_dense_authorized
        self.doc.is_published = False
        self.doc.active_version = self.version
        self.doc.save()
        scope = resolve_scope(self.owner, self.course.pk, preview=True)
        with patch.object(self.embedding, 'embed_query', return_value=self.vector):
            hits = retrieve_dense_authorized(self.owner, 'Q', scope, self.build(),
                                             self.embedding, catalog=self.catalog)
        self.assertEqual(len(hits), 1)
