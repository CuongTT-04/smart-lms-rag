"""Verify saved FAISS query results in a fresh process without loading BGE-M3."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from apps.ai.embeddings.base import EmbeddingConfig
from apps.ai.retrieval.storage import load_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=REPO_ROOT / "data/processed/w3-sample-index")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "backend/apps/ai/embeddings/config.json")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to((REPO_ROOT / "data/processed").resolve()):
        parser.error("Verification output must stay inside data/processed.")
    config = EmbeddingConfig.from_file(args.config)
    started = time.perf_counter()
    index = load_index(directory / "bundle", config)
    load_seconds = time.perf_counter() - started
    previous = json.loads((directory / "sample_query_results.json").read_text(encoding="utf-8"))
    vector_bytes = (directory / "sample_query_vectors.npy").read_bytes()
    assert hashlib.sha256(vector_bytes).hexdigest() == previous["query_vectors_sha256"]
    vectors = np.load(io.BytesIO(vector_bytes), allow_pickle=False)
    assert vectors.shape == (len(previous["queries"]), config.dimension)
    checked = []
    for vector, query in zip(vectors, previous["queries"]):
        actual = index.search(vector, 5)
        assert actual == query["results"], "Ranking/score/text/source differs from the saved run."
        checked.append({"query": query["query"], "top1": actual[0]["chunk_id"], "all_top5_fields_identical": True})
    report = {
        "status": "PASSED", "sample_type": "synthetic_fixture",
        "vector_count": index.count, "query_count": len(checked),
        "all_queries_identical": True, "model_loaded": "sentence_transformers" in sys.modules,
        "load_seconds_without_model": round(load_seconds, 6),
        "embedding_config_hash": config.fingerprint(), "queries": checked,
    }
    assert report["model_loaded"] is False
    (directory / "reload_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
