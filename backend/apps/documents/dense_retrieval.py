"""Server-only bridge between W3 Django permissions and A's dense retriever."""
from dataclasses import asdict

from apps.ai.retrieval.retriever import (
    RetrievalError, RetrievalScope as DenseScope, RetrievalService,
)
from .exceptions import DocumentError
from .retrieval_adapter import live_scope, retrieve_authorized
from .retrieval_contracts import Chunk


def _dense_scope(scope):
    return DenseScope(user_id=scope.user_id, course_id=scope.course_id,
        allowed_version_ids=frozenset(scope.allowed_version_ids), mode=scope.mode,
        classroom_id=scope.classroom_id, session_id=scope.session_id,
        document_ids=None if scope.document_ids is None else frozenset(scope.document_ids))


def retrieve_dense_authorized(user, query, scope, index, embedding, *, catalog, top_k=5):
    """Use only an authenticated user and operator-loaded index/catalog.

    Keep B's preview flag on the captured scope; A receives no client allowlist.
    Exact catalog equality prevents drift between embedding text and returned text.
    This function does not publish a source or mark an ingestion job READY.
    """
    live_scope(user, scope)
    records = index.export_chunks()
    if (len(records) != len(catalog) or any(
            not isinstance(catalog.get(row['chunk_id']), Chunk)
            or asdict(catalog[row['chunk_id']]) != row for row in records)):
        raise DocumentError('INDEX_CATALOG_MISMATCH', 'Index and trusted chunk catalog differ.', 503)
    requested = _dense_scope(scope)

    def resolve(candidate):
        if candidate != requested:
            raise DocumentError('INVALID_SCOPE', 'Scope selectors must remain server-owned.', 400)
        return _dense_scope(live_scope(user, scope))

    service = RetrievalService(index, embedding, scope_resolver=resolve)

    class BoundProvider:
        def search(self, *, query, allowed_version_ids, top_k):
            if frozenset(allowed_version_ids) != requested.allowed_version_ids:
                raise DocumentError('INVALID_SCOPE', 'Scope allowlist changed.', 400)
            try:
                return service.retrieve(query, requested, top_k)['results']
            except RetrievalError as exc:
                if isinstance(exc.__cause__, DocumentError):
                    raise exc.__cause__
                raise

    return retrieve_authorized(user, query, scope, BoundProvider(), top_k, catalog=catalog)
