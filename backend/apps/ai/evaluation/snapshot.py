"""Reuse a checksummed dense snapshot for offline evaluation, never live authorization."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
from uuid import NAMESPACE_URL, uuid5


def read_snapshot(index_dir, source_map):
    root = Path(index_dir).resolve()
    pointer = json.loads((root / "current.json").read_text(encoding="utf-8"))
    generation = pointer.get("generation")
    if pointer.get("storage_schema_version") != "1.0" or not isinstance(generation, str) or not re.fullmatch(r"snapshot-[0-9a-f]{32}", generation):
        raise ValueError("Invalid snapshot pointer.")
    folder = (root / generation).resolve()
    if not folder.is_relative_to(root):
        raise ValueError("Snapshot path escaped index directory.")
    raw = (folder / "manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer["manifest_sha256"]:
        raise ValueError("Snapshot manifest checksum mismatch.")
    manifest = json.loads(raw)
    if manifest.get("index_file") != "index.faiss" or manifest.get("chunks_file") != "chunks.jsonl":
        raise ValueError("Unsupported snapshot filenames.")
    from ..embeddings.base import EmbeddingConfig
    config = EmbeddingConfig(**manifest["embedding_config"])
    if (config.fingerprint() != manifest.get("embedding_config_hash") or manifest.get("index_type") != "IndexFlatIP"
            or manifest.get("metric") != "inner_product" or manifest.get("normalized") is not True):
        raise ValueError("Incompatible dense snapshot configuration.")
    for name, key in (("chunks.jsonl", "chunks_file_sha256"), ("index.faiss", "index_sha256")):
        file = (folder / name).resolve()
        if not file.is_relative_to(root) or hashlib.sha256(file.read_bytes()).hexdigest() != manifest[key]:
            raise ValueError("Snapshot artifact checksum mismatch.")
    chunks = [json.loads(line) for line in (folder / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    sources = {}
    for source in source_map["sources"]:
        key = (source["course_id"], source["document_id"], source["version_id"])
        if key in sources:
            raise ValueError("Duplicate snapshot source identity.")
        sources[key] = source
    ids = [chunk["chunk_id"] for chunk in chunks]
    if not chunks or len(ids) != len(set(ids)) or len(chunks) != manifest["vector_count"]:
        raise ValueError("Snapshot chunk inventory mismatch.")
    for chunk in chunks:
        source = sources[(chunk["course_id"], chunk["document_id"], chunk["version_id"])]
        if (chunk["source_checksum"] != source["source_checksum"]
                or type(chunk["page_number"]) is not int or not 1 <= chunk["page_number"] <= source["page_count"]
                or not isinstance(chunk.get("text"), str) or not chunk["text"].strip()):
            raise ValueError("Snapshot source identity/page/checksum mismatch.")
    return manifest, chunks


def label_cases(cases, source_map):
    sources = {(s["course_id"], s["document_id"], s["version_id"]): s for s in source_map["sources"]}
    result = []
    for original in cases:
        case = dict(original)
        try:
            for gold in case["gold_sources"]:
                source = sources[(case["course_id"], gold["document_id"], gold["version_id"])]
                if type(gold["page_number"]) is not int or not 1 <= gold["page_number"] <= source["page_count"]:
                    raise ValueError("Out-of-range gold page.")
        except (KeyError, TypeError, ValueError):
            case["label_error"] = "GOLD_SOURCE_NOT_IN_PINNED_SNAPSHOT"
        result.append(case)
    return result


class OfflineSnapshotRetriever:
    def __init__(self, index_dir, source_map, *, allow_embedding_download=False):
        from ..embeddings.base import EmbeddingConfig
        from ..embeddings.service import EmbeddingService
        from ..retrieval.storage import load_index
        from ..retrieval.retriever import RetrievalService

        manifest, chunks = read_snapshot(index_dir, source_map)
        stored_config = EmbeddingConfig(**manifest["embedding_config"])
        self.index = load_index(index_dir, stored_config)
        if self.index.export_chunks() != chunks:
            raise ValueError("Loaded FAISS mapping differs from the pinned corpus.")
        # Download permission is transport policy, not a change to the vector model/budget/device.
        self.embedding = EmbeddingService(replace(stored_config, local_files_only=not allow_embedding_download))

        class QueryEmbedding:
            config = stored_config

            def embed_query(inner, text):
                return self.embedding.embed_query(text)

        self.retriever = RetrievalService(self.index, QueryEmbedding(), scope_resolver=lambda scope: scope)
        self.chunks = chunks
        self.provenance = {
            "index_revision": self.retriever.index_revision,
            "index_sha256": manifest["index_sha256"], "chunks_sha256": manifest["chunks_sha256"],
            "chunking_revision": sorted({c["chunking_config_hash"] for c in chunks}),
            "embedding_config": manifest["embedding_config"],
            "query_runtime_config": self.embedding.runtime_info()["config"],
            "scope_resolver": "offline_course_allowlist_not_database_permissions",
            "authorization_verified": False, "reembedding_performed": False,
        }

    def __call__(self, request, *, top_k):
        from ..retrieval.retriever import RetrievalScope

        scope = RetrievalScope(str(uuid5(NAMESPACE_URL, "offline-generation-evaluator")), request["course_id"],
                               frozenset(c["version_id"] for c in self.chunks if c["course_id"] == request["course_id"]),
                               mode=request["mode"])
        return self.retriever.retrieve(request["question"], scope, top_k=top_k)
