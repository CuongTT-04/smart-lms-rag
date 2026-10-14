"""Build and query a real FAISS index from explicitly synthetic W3 sample chunks."""

import argparse
from datetime import datetime, timezone
import hashlib
import io
from importlib.metadata import version
import json
from pathlib import Path
import sys
import time

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from apps.ai.embeddings.base import EmbeddingConfig
from apps.ai.embeddings.service import EmbeddingService
from apps.ai.retrieval.index import DenseIndex
from apps.ai.retrieval.storage import load_index, save_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=REPO_ROOT / "data/fixtures/w3-sample-chunks.json")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "backend/apps/ai/embeddings/config.json")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data/processed/w3-sample-index")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to((REPO_ROOT / "data/processed").resolve()):
        parser.error("Sample artifacts must stay inside data/processed; originals are read-only.")
    fixture_bytes = args.fixture.read_bytes()
    fixture = json.loads(fixture_bytes)
    if fixture.get("sample_type") != "synthetic_fixture":
        parser.error("This smoke runner expects a clearly labeled synthetic fixture.")
    chunks = []
    for document in fixture["documents"]:
        source = {key: value for key, value in document.items() if key != "chunks"}
        for chunk in document["chunks"]:
            chunks.append({**source, **chunk, "source_kind": "synthetic_fixture"})
    service = EmbeddingService(EmbeddingConfig.from_file(args.config))
    started = time.perf_counter()
    embeddings = service.embed_chunks(chunks)
    embedding_seconds = time.perf_counter() - started
    started = time.perf_counter()
    index = DenseIndex(chunks, embeddings, service.config)
    build_seconds = time.perf_counter() - started
    # Identity queries check vector row -> chunk mapping independently of QA quality.
    self_match = all(index.search(vector, 1)[0]["chunk_id"] == chunk_id for chunk_id, vector in zip(embeddings.chunk_ids, embeddings.vectors))
    if not self_match:
        raise AssertionError("Self-search did not preserve every chunk ID.")
    queries = []
    query_vectors = []
    for sample in fixture["queries"]:
        started = time.perf_counter()
        query_vector = service.embed_query(sample["query"])
        query_vectors.append(query_vector)
        results = index.search(query_vector, 5)
        queries.append({**sample, "results": results, "top1_matches_fixture_expectation": results[0]["chunk_id"] == sample["expected_top1_chunk_id"], "query_seconds_including_embedding": round(time.perf_counter() - started, 4)})
    save_index(index, output / "bundle", metadata={"sample_type": "synthetic_fixture", "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(), "runtime": service.runtime_info()})
    reloaded = load_index(output / "bundle", service.config)
    if reloaded.manifest() != index.manifest():
        raise AssertionError("Index metadata changed after reload.")
    for vector, query in zip(query_vectors, queries):
        if reloaded.search(vector, 5) != query["results"]:
            raise AssertionError("Query ranking, score, text or source changed after reload.")
    buffer = io.BytesIO()
    np.save(buffer, np.stack(query_vectors), allow_pickle=False)
    query_vector_bytes = buffer.getvalue()
    index_bytes = index.serialize()
    manifest = {
        **index.manifest(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sample_type": "synthetic_fixture",
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
        "index_file": "sample.index",
        "chunks_file": "chunks_sample.jsonl",
        "faiss_version": version("faiss-cpu"),
        "runtime": service.runtime_info(),
    }
    report = {
        "status": "PASSED",
        "sample_type": "synthetic_fixture",
        "vector_count": index.count,
        "self_search_id_matches": sum(index.search(vector, 1)[0]["chunk_id"] == chunk_id for chunk_id, vector in zip(embeddings.chunk_ids, embeddings.vectors)),
        "embedding_seconds_including_model_load": round(embedding_seconds, 3),
        "index_build_seconds": round(build_seconds, 6),
        "fixture_query_top1_matches": sum(item["top1_matches_fixture_expectation"] for item in queries),
        "fixture_query_count": len(queries),
        "is_100_qa_benchmark": False,
        "access_control_verified": False,
        "reload_verified": True,
        "reload_query_matches": len(queries),
        "query_vectors_sha256": hashlib.sha256(query_vector_bytes).hexdigest(),
        "queries": queries,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "sample.index").write_bytes(index_bytes)
    (output / "sample_query_vectors.npy").write_bytes(query_vector_bytes)
    (output / "chunks_sample.jsonl").write_text("".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks), encoding="utf-8")
    (output / "sample_index_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "sample_query_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "queries"}, indent=2))
    for query in queries:
        print(json.dumps({"query": query["query"], "top1": query["results"][0]["chunk_id"], "score": query["results"][0]["score"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
