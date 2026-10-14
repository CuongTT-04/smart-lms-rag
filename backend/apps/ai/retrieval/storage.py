"""Checksummed local FAISS snapshots with atomic publication of the current pointer."""

from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

import faiss
import numpy as np

from ..embeddings.base import EmbeddedChunks, EmbeddingConfig
from .index import DenseIndex, IndexError as DenseIndexError


class IndexStorageError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _write_file(path: Path, data: bytes):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _checked_path(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise IndexStorageError("INVALID_PATH", "Snapshot files must remain inside the selected directory.")
    return resolved


def save_index(index: DenseIndex, directory: str | Path, metadata: dict | None = None) -> Path:
    """Write a new generation, then atomically publish current.json; retain old generations."""
    root = Path(directory).resolve()
    corpus = Path(__file__).resolve().parents[4] / "data/corpus"
    if root.is_relative_to(corpus.resolve()):
        raise IndexStorageError("INVALID_PATH", "Corpus originals and metadata are read-only.")
    if metadata is not None and not isinstance(metadata, dict):
        raise IndexStorageError("INVALID_METADATA", "Snapshot metadata must be a dictionary.")
    index_bytes = index.serialize()
    try:
        chunks_bytes = "".join(json.dumps(chunk, ensure_ascii=False, allow_nan=False) + "\n" for chunk in index.export_chunks()).encode("utf-8")
        manifest = {
            **index.manifest(),
            "storage_schema_version": "1.0",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "faiss_version": version("faiss-cpu"),
            "index_file": "index.faiss",
            "chunks_file": "chunks.jsonl",
            "index_sha256": _hash(index_bytes),
            "chunks_file_sha256": _hash(chunks_bytes),
            "metadata": metadata or {},
        }
        manifest_bytes = _json_bytes(manifest)
    except (TypeError, ValueError) as exc:
        raise IndexStorageError("INVALID_METADATA", "Snapshot metadata must be JSON-safe.") from exc
    pointer_temp = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        generation = "snapshot-" + uuid4().hex
        snapshot = _checked_path(root, root / generation)
        snapshot.mkdir()
        _write_file(snapshot / "index.faiss", index_bytes)
        _write_file(snapshot / "chunks.jsonl", chunks_bytes)
        _write_file(snapshot / "manifest.json", manifest_bytes)
        pointer_bytes = _json_bytes({"storage_schema_version": "1.0", "generation": generation, "manifest_sha256": _hash(manifest_bytes)})
        with tempfile.NamedTemporaryFile(dir=root, prefix=".current-", suffix=".tmp", delete=False) as stream:
            pointer_temp = Path(stream.name)
            stream.write(pointer_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pointer_temp, root / "current.json")
        return snapshot
    except OSError as exc:
        raise IndexStorageError("SAVE_FAILED", "Snapshot could not be published; the previous pointer is retained.") from exc
    finally:
        if pointer_temp is not None and pointer_temp.exists():
            pointer_temp.unlink()


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise IndexStorageError("SNAPSHOT_NOT_FOUND", "A required snapshot file is missing or unreadable.") from exc


def _parse(data: bytes, code: str):
    try:
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("Expected a JSON object")
        return result
    except (ValueError, UnicodeDecodeError) as exc:
        raise IndexStorageError(code, "Snapshot JSON is invalid.") from exc


def load_index(directory: str | Path, expected_config: EmbeddingConfig) -> DenseIndex:
    """Load trusted local artifacts only; checksums detect corruption, not malicious authorship."""
    root = Path(directory).resolve()
    pointer = _parse(_read(_checked_path(root, root / "current.json")), "INVALID_POINTER")
    generation = pointer.get("generation")
    if pointer.get("storage_schema_version") != "1.0" or not isinstance(generation, str) or not re.fullmatch(r"snapshot-[0-9a-f]{32}", generation):
        raise IndexStorageError("INVALID_POINTER", "Unsupported pointer schema or snapshot name.")
    snapshot = _checked_path(root, root / generation)
    manifest_bytes = _read(_checked_path(root, snapshot / "manifest.json"))
    if _hash(manifest_bytes) != pointer.get("manifest_sha256"):
        raise IndexStorageError("CHECKSUM_MISMATCH", "Manifest checksum does not match the published pointer.")
    manifest = _parse(manifest_bytes, "INVALID_MANIFEST")
    if manifest.get("storage_schema_version") != "1.0" or manifest.get("index_file") != "index.faiss" or manifest.get("chunks_file") != "chunks.jsonl":
        raise IndexStorageError("INVALID_MANIFEST", "Unsupported snapshot schema or file names.")
    try:
        config = EmbeddingConfig(**manifest["embedding_config"])
    except (KeyError, ValueError, TypeError) as exc:
        raise IndexStorageError("CONFIG_MISMATCH", "Stored embedding configuration is invalid.") from exc
    if config.fingerprint() != manifest.get("embedding_config_hash") or config != expected_config:
        raise IndexStorageError("CONFIG_MISMATCH", "Snapshot and expected embedding configurations differ.")
    index_bytes = _read(_checked_path(root, snapshot / "index.faiss"))
    chunks_bytes = _read(_checked_path(root, snapshot / "chunks.jsonl"))
    if _hash(index_bytes) != manifest.get("index_sha256") or _hash(chunks_bytes) != manifest.get("chunks_file_sha256"):
        raise IndexStorageError("CHECKSUM_MISMATCH", "Index or chunk file checksum is invalid.")
    try:
        chunks = [json.loads(line) for line in chunks_bytes.decode("utf-8").splitlines()]
    except (ValueError, UnicodeDecodeError) as exc:
        raise IndexStorageError("INVALID_CHUNKS", "Stored chunk records are invalid JSONL.") from exc
    count = manifest.get("vector_count")
    if type(count) is not int or count < 1 or len(chunks) != count:
        raise IndexStorageError("COUNT_MISMATCH", "Chunk count differs from the snapshot manifest.")
    try:
        loaded = faiss.deserialize_index(np.frombuffer(index_bytes, dtype=np.uint8).copy())
    except Exception as exc:
        raise IndexStorageError("INVALID_INDEX", "FAISS cannot deserialize the stored index.") from exc
    if not isinstance(loaded, faiss.IndexFlatIP) or loaded.metric_type != faiss.METRIC_INNER_PRODUCT or loaded.d != config.dimension:
        raise IndexStorageError("INVALID_INDEX", "Index type, metric or dimension is incompatible.")
    if loaded.ntotal != count:
        raise IndexStorageError("COUNT_MISMATCH", "FAISS vector count differs from metadata.")
    try:
        vectors = loaded.reconstruct_n(0, loaded.ntotal)
        ids = tuple(chunk["chunk_id"] for chunk in chunks)
        result = DenseIndex(chunks, EmbeddedChunks(ids, vectors, (), config.fingerprint()), config)
    except DenseIndexError as exc:
        raise IndexStorageError(exc.code, str(exc)) from exc
    except (KeyError, TypeError, RuntimeError) as exc:
        raise IndexStorageError("INVALID_INDEX", "Stored vectors or chunk records are invalid.") from exc
    # Compare derived source mapping and all base manifest fields, not just IDs/count.
    if any(manifest.get(key) != value for key, value in result.manifest().items()):
        raise IndexStorageError("MAPPING_MISMATCH", "Stored mapping or metadata differs from the validated chunks/index.")
    result._index = loaded
    return result
