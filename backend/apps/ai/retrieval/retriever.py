"""Top-k retrieval with server-resolved source scope and live revalidation."""

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from uuid import UUID

from ..embeddings.base import EmbeddingError
from ..embeddings.service import EmbeddingService
from .index import DenseIndex, IndexError as DenseIndexError


class RetrievalError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _uuid(value):
    if not isinstance(value, str):
        raise ValueError("Scope identifiers must be UUID strings.")
    return str(UUID(value))


@dataclass(frozen=True)
class RetrievalScope:
    """Selectors plus a resolver-computed allowlist; constructing this is not authorization."""

    user_id: str
    course_id: str
    allowed_version_ids: frozenset[str]
    mode: str = "qa"
    classroom_id: str | None = None
    session_id: str | None = None
    document_ids: frozenset[str] | None = None

    def __post_init__(self):
        try:
            for name in ("user_id", "course_id", "classroom_id", "session_id"):
                value = getattr(self, name)
                if value is not None or name in ("user_id", "course_id"):
                    object.__setattr__(self, name, _uuid(value))
            for name in ("allowed_version_ids", "document_ids"):
                value = getattr(self, name)
                if name == "document_ids" and value is None:
                    continue
                if not isinstance(value, (set, frozenset, tuple, list)):
                    raise ValueError("Version/document selectors must be collections of UUIDs.")
                object.__setattr__(self, name, frozenset(_uuid(item) for item in value))
            if self.mode not in ("qa", "hint"):
                raise ValueError("Supported modes are qa and hint.")
        except (TypeError, ValueError, AttributeError) as exc:
            raise RetrievalError("INVALID_SCOPE", "Scope identifiers or mode are invalid.") from exc

    def selectors(self):
        return (self.user_id, self.course_id, self.mode, self.classroom_id, self.session_id, self.document_ids)


class RetrievalService:
    def __init__(self, index: DenseIndex, embedding: EmbeddingService, scope_resolver: Callable[[RetrievalScope], RetrievalScope]):
        if not callable(scope_resolver):
            raise RetrievalError("INVALID_RESOLVER", "A server-side scope resolver is required.")
        if index.embedding_config != embedding.config:
            raise RetrievalError("CONFIG_MISMATCH", "Query embedding and index configurations must match.")
        self.index = index
        self.embedding = embedding
        self.scope_resolver = scope_resolver
        self._chunks = index.export_chunks()
        identity = {"manifest": index.manifest(), "index_sha256": hashlib.sha256(index.serialize()).hexdigest()}
        self.index_revision = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

    def _resolve(self, requested: RetrievalScope) -> RetrievalScope:
        try:
            resolved = self.scope_resolver(requested)
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError("SCOPE_RESOLUTION_FAILED", "Cannot resolve current source permissions.") from exc
        if not isinstance(resolved, RetrievalScope) or resolved.selectors() != requested.selectors():
            raise RetrievalError("INVALID_SCOPE", "Resolver must preserve the requested identity and selectors.")
        return resolved

    def _rows(self, scope: RetrievalScope):
        return [row for row, chunk in enumerate(self._chunks)
                if _uuid(chunk["course_id"]) == scope.course_id
                and _uuid(chunk["version_id"]) in scope.allowed_version_ids
                and (scope.document_ids is None or _uuid(chunk["document_id"]) in scope.document_ids)]

    def _response(self, query, scope, results, status):
        return {"query": query, "mode": scope.mode, "index_revision": self.index_revision,
                "status": status, "results": results, "returned_count": len(results)}

    def retrieve(self, query: str, scope: RetrievalScope, top_k: int = 5) -> dict:
        if not isinstance(query, str) or not query.strip():
            raise RetrievalError("INVALID_QUERY", "Query must be a nonblank string.")
        if not isinstance(scope, RetrievalScope):
            raise RetrievalError("INVALID_SCOPE", "A typed scope from the server integration is required.")
        if type(top_k) is not int or top_k < 1:
            raise RetrievalError("INVALID_TOP_K", "top_k must be a positive integer.")
        initial = self._resolve(scope)
        if not initial.allowed_version_ids or initial.document_ids == frozenset():
            return self._response(query, initial, [], "EMPTY_SCOPE")
        initial_rows = self._rows(initial)
        if not initial_rows:
            return self._response(query, initial, [], "NO_INDEXED_SOURCES")
        try:
            vector = self.embedding.embed_query(query)
        except EmbeddingError as exc:
            raise RetrievalError(exc.code, str(exc)) from exc
        current = self._resolve(scope)
        current_rows = set(self._rows(current))
        rows = [row for row in initial_rows if row in current_rows]
        if not rows:
            return self._response(query, current, [], "EMPTY_SCOPE" if not current.allowed_version_ids or current.document_ids == frozenset() else "NO_INDEXED_SOURCES")
        try:
            results = self.index.search(vector, top_k, row_ids=rows)
        except DenseIndexError as exc:
            raise RetrievalError(exc.code, str(exc)) from exc
        final = self._resolve(scope)
        final_rows = set(self._rows(final))
        if any(row not in final_rows for row in rows):
            raise RetrievalError("SCOPE_CHANGED", "Source permissions changed during search; retry with current permissions.")
        source_fields = {"course_id", "document_id", "version_id", "document_title", "page_number", "section_title"}
        for result in results:
            result["source"] = {key: value for key, value in result["source"].items() if key in source_fields}
        return self._response(query, final, results, "OK")
