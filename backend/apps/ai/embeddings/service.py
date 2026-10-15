"""Lazy dense embedding service, usable without Django or a database."""

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import platform
from threading import Lock

import numpy as np

from .base import EmbeddedChunks, EmbeddingConfig, EmbeddingError


class EmbeddingService:
    def __init__(self, config: EmbeddingConfig | None = None):
        self.config = config or EmbeddingConfig.from_file(Path(__file__).with_name("config.json"))
        self._model = None
        self._lock = Lock()

    def _load_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        from sentence_transformers import SentenceTransformer

                        model = SentenceTransformer(
                            self.config.model_id,
                            revision=self.config.revision,
                            device=self.config.device,
                            local_files_only=self.config.local_files_only,
                            trust_remote_code=False,
                        )
                        model.float()
                        dimension_getter = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
                        if dimension_getter() != self.config.dimension:
                            raise EmbeddingError("INVALID_DIMENSION", "Model dimension does not match config.")
                        model.max_seq_length = self.config.max_tokens
                        self._model = model
                    except EmbeddingError:
                        raise
                    except Exception as exc:
                        raise EmbeddingError("MODEL_LOAD_FAILED", "Cannot load the pinned embedding model.") from exc
        return self._model

    def embed_chunks(self, chunks: Sequence[Mapping]) -> EmbeddedChunks:
        if isinstance(chunks, (str, bytes)) or not isinstance(chunks, Sequence):
            raise EmbeddingError("INVALID_INPUT", "Chunks must be a list or tuple of records.")
        ids, texts = [], []
        for chunk in chunks:
            if not isinstance(chunk, Mapping):
                raise EmbeddingError("INVALID_INPUT", "Each chunk must be a record with chunk_id and text.")
            chunk_id, text = chunk.get("chunk_id"), chunk.get("text")
            if not isinstance(chunk_id, str) or not chunk_id.strip() or chunk_id != chunk_id.strip():
                raise EmbeddingError("INVALID_CHUNK_ID", "Chunk IDs must be nonblank strings without outer whitespace.")
            if not isinstance(text, str) or not text.strip():
                raise EmbeddingError("EMPTY_TEXT", "Chunk text must be a nonblank string.")
            ids.append(chunk_id)
            texts.append(text)
        if len(set(ids)) != len(ids):
            raise EmbeddingError("DUPLICATE_CHUNK_ID", "Chunk IDs must be unique within a call.")
        if not texts:
            return EmbeddedChunks((), np.empty((0, self.config.dimension), dtype=np.float32), (), self.config.fingerprint())

        model = self._load_model()
        try:
            # Count untruncated input, including special tokens, before encode can truncate.
            counts = tuple(len(model.tokenizer.encode(text, add_special_tokens=True, truncation=False, verbose=False)) for text in texts)
            for chunk_id, count in zip(ids, counts):
                if count > self.config.max_tokens:
                    raise EmbeddingError("TOKEN_LIMIT_EXCEEDED", f"Chunk {chunk_id} has {count} tokens; limit is {self.config.max_tokens}.")
            vectors = np.asarray(model.encode(
                texts,
                batch_size=self.config.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
                prompt="",
            ))
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError("ENCODING_FAILED", "Embedding inference failed.") from exc
        if vectors.shape != (len(ids), self.config.dimension):
            raise EmbeddingError("INVALID_VECTOR_SHAPE", "Vector count or dimension does not match the chunks.")
        if not np.issubdtype(vectors.dtype, np.floating):
            raise EmbeddingError("INVALID_VECTOR_DTYPE", "Vectors must contain floating-point values.")
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        if not np.isfinite(vectors).all():
            raise EmbeddingError("NONFINITE_VECTOR", "Vectors contain NaN or infinite values.")
        if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4, rtol=0):
            raise EmbeddingError("INVALID_VECTOR_NORM", "Vectors must have L2 norm approximately equal to one.")
        return EmbeddedChunks(tuple(ids), vectors, counts, self.config.fingerprint())

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_chunks([{"chunk_id": "query", "text": text}]).vectors[0]

    def runtime_info(self) -> dict:
        packages = {}
        for package in ("torch", "sentence-transformers", "transformers", "huggingface-hub", "numpy", "psutil"):
            try:
                packages[package] = version(package)
            except PackageNotFoundError:
                packages[package] = None
        return {
            "config": asdict(self.config),
            "config_hash": self.config.fingerprint(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": packages,
            "hf_home": os.environ.get("HF_HOME"),
        }
