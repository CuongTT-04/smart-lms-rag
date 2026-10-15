"""Offline dense index. Access control must be resolved before production retrieval."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from uuid import UUID

import faiss
import numpy as np

from ..embeddings.base import EmbeddedChunks, EmbeddingConfig


class IndexError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class DenseIndex:
    """One fresh IndexFlatIP snapshot, with immutable-by-caller row/source mapping."""

    def __init__(self, chunks: Sequence[Mapping], embeddings: EmbeddedChunks, config: EmbeddingConfig):
        if isinstance(chunks, (str, bytes)) or not isinstance(chunks, Sequence) or not chunks:
            raise IndexError("INVALID_CHUNKS", "A nonempty list or tuple of chunks is required.")
        records = []
        for chunk in chunks:
            if not isinstance(chunk, Mapping):
                raise IndexError("INVALID_CHUNKS", "Each chunk must be a record.")
            record = deepcopy(dict(chunk))
            chunk_id, text = record.get("chunk_id"), record.get("text")
            if not isinstance(chunk_id, str) or not chunk_id.strip() or chunk_id != chunk_id.strip():
                raise IndexError("INVALID_CHUNK_ID", "Chunk IDs must be nonblank strings without outer whitespace.")
            if not isinstance(text, str) or not text.strip():
                raise IndexError("EMPTY_TEXT", "Chunk text must be nonblank.")
            try:
                for key in ("course_id", "document_id", "version_id"):
                    UUID(record[key])
            except (KeyError, ValueError, TypeError, AttributeError) as exc:
                raise IndexError("INVALID_SOURCE", "Source must include valid course/document/version UUIDs.") from exc
            page = record.get("page_number")
            if type(page) is not int or page < 1:
                raise IndexError("INVALID_SOURCE", "Source page number must be a positive integer.")
            records.append(record)
        ids = tuple(record["chunk_id"] for record in records)
        if len(set(ids)) != len(ids):
            raise IndexError("DUPLICATE_CHUNK_ID", "Cannot index duplicate chunk IDs.")
        if embeddings.chunk_ids != ids:
            raise IndexError("MAPPING_MISMATCH", "Embedding row IDs must match chunk order exactly.")
        if embeddings.config_hash != config.fingerprint():
            raise IndexError("CONFIG_MISMATCH", "Embeddings were created with a different configuration.")
        vectors = embeddings.vectors
        if not isinstance(vectors, np.ndarray) or vectors.shape != (len(records), config.dimension):
            raise IndexError("INVALID_VECTOR_SHAPE", "Vector count/dimension must match chunks and config.")
        if vectors.dtype != np.float32 or not np.isfinite(vectors).all():
            raise IndexError("INVALID_VECTORS", "Vectors must be finite float32 values.")
        if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4, rtol=0):
            raise IndexError("INVALID_VECTOR_NORM", "IndexFlatIP baseline requires L2-normalized vectors.")
        try:
            payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise IndexError("INVALID_METADATA", "Chunk metadata must contain JSON-safe values.") from exc
        self._chunks = tuple(records)
        self._config = config
        self._chunks_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self._index = faiss.IndexFlatIP(config.dimension)
        self._index.add(np.ascontiguousarray(vectors))

    @property
    def count(self):
        return self._index.ntotal

    @property
    def embedding_config(self):
        return self._config

    def search(self, query_vector: np.ndarray, top_k: int = 5, *, row_ids: Sequence[int] | None = None) -> list[dict]:
        """Search this offline snapshot; this is not a user-authorized API."""
        if type(top_k) is not int or top_k < 1:
            raise IndexError("INVALID_TOP_K", "top_k must be a positive integer.")
        if not isinstance(query_vector, np.ndarray) or query_vector.shape != (self._config.dimension,):
            raise IndexError("INVALID_QUERY", "Query vector has the wrong shape.")
        if query_vector.dtype != np.float32 or not np.isfinite(query_vector).all():
            raise IndexError("INVALID_QUERY", "Query vector must contain finite float32 values.")
        if not np.isclose(np.linalg.norm(query_vector), 1, atol=1e-4, rtol=0):
            raise IndexError("INVALID_QUERY", "Query vector must be L2-normalized.")
        search_index = self._index
        source_rows = list(range(self.count))
        if row_ids is not None:
            if isinstance(row_ids, (str, bytes)) or not isinstance(row_ids, Sequence):
                raise IndexError("INVALID_ROWS", "Allowed rows must be a sequence of unique integer positions.")
            source_rows = list(row_ids)
            if any(type(row) is not int or not 0 <= row < self.count for row in source_rows) or len(set(source_rows)) != len(source_rows):
                raise IndexError("INVALID_ROWS", "Allowed row positions are duplicated or out of range.")
            if not source_rows:
                return []
            # Exact search inside the allowed subset; never filter a global top-k.
            vectors = np.stack([self._index.reconstruct(row) for row in source_rows])
            search_index = faiss.IndexFlatIP(self._config.dimension)
            search_index.add(np.ascontiguousarray(vectors, dtype=np.float32))
        scores, rows = search_index.search(np.ascontiguousarray(query_vector.reshape(1, -1)), min(top_k, len(source_rows)))
        results = []
        for rank, (row, score) in enumerate(zip(rows[0], scores[0]), 1):
            chunk = self._chunks[source_rows[int(row)]]
            results.append({
                "rank": rank,
                "chunk_id": chunk["chunk_id"],
                "score": float(score),
                "text": chunk["text"],
                "source": deepcopy({key: value for key, value in chunk.items() if key not in ("chunk_id", "text")}),
            })
        return results

    def serialize(self) -> bytes:
        """Export raw FAISS bytes; use storage.save_index for a complete snapshot."""
        return faiss.serialize_index(self._index).tobytes()

    def export_chunks(self) -> list[dict]:
        return deepcopy(list(self._chunks))

    def manifest(self) -> dict:
        return {
            "schema_version": "1.0",
            "index_type": "IndexFlatIP",
            "metric": "inner_product",
            "normalized": True,
            "dimension": self._config.dimension,
            "dtype": "float32",
            "vector_count": self.count,
            "embedding_config": asdict(self._config),
            "embedding_config_hash": self._config.fingerprint(),
            "chunks_sha256": self._chunks_hash,
            "vector_mapping": [
                {"row": row, "chunk_id": chunk["chunk_id"], "source": deepcopy({key: value for key, value in chunk.items() if key not in ("chunk_id", "text")})}
                for row, chunk in enumerate(self._chunks)
            ],
        }
