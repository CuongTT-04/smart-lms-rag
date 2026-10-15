"""Run the real pinned embedding model and record smoke-test evidence."""

import argparse
import json
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import numpy as np
import psutil

from apps.ai.embeddings.base import EmbeddingConfig, EmbeddingError
from apps.ai.embeddings.service import EmbeddingService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "backend/apps/ai/embeddings/config.json")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "data/processed/w3-embedding-smoke.json")
    args = parser.parse_args()
    if args.output.resolve().is_relative_to((REPO_ROOT / "data/corpus").resolve()):
        parser.error("Corpus originals and sidecars are read-only.")
    service = EmbeddingService(EmbeddingConfig.from_file(args.config))
    chunks = [
        {"chunk_id": "sample-1", "text": "Vật chất tồn tại khách quan, độc lập với ý thức."},
        {"chunk_id": "sample-2", "text": "Ý thức phản ánh thế giới khách quan vào bộ óc con người."},
        {"chunk_id": "sample-3", "text": "Giáo viên quản lý học viên và tài liệu trong lớp học."},
    ]
    started = time.perf_counter()
    try:
        result = service.embed_chunks(chunks)
        initial_seconds = time.perf_counter() - started
        started = time.perf_counter()
        repeated = service.embed_chunks(list(reversed(chunks)))
        repeat_seconds = time.perf_counter() - started
        assert repeated.chunk_ids == tuple(reversed(result.chunk_ids))
        assert np.allclose(repeated.vectors, result.vectors[::-1], atol=1e-5)
        query = service.embed_query("Vật chất và ý thức có quan hệ như thế nào?")
        assert query.shape == (1024,) and np.isfinite(query).all()
        long_text = "kiến thức " * 600
        try:
            service.embed_chunks([{"chunk_id": "too-long", "text": long_text}])
        except EmbeddingError as exc:
            assert exc.code == "TOKEN_LIMIT_EXCEEDED"
        else:
            raise AssertionError("Overlong text was silently accepted.")
    except (EmbeddingError, AssertionError) as exc:
        print(json.dumps({"status": "FAILED", "code": getattr(exc, "code", "ASSERTION_FAILED"), "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    report = {
        "status": "PASSED",
        "sample_type": "synthetic Vietnamese smoke samples, not the W3 corpus benchmark",
        **service.runtime_info(),
        "chunk_ids": result.chunk_ids,
        "token_counts": result.token_counts,
        "vector_shape": list(result.vectors.shape),
        "dtype": str(result.vectors.dtype),
        "norms": np.linalg.norm(result.vectors, axis=1).tolist(),
        "initial_call_seconds_including_model_load": round(initial_seconds, 3),
        "repeat_call_seconds": round(repeat_seconds, 3),
        "process_rss_gib_not_peak": round(psutil.Process().memory_info().rss / 1024**3, 3),
        "id_mapping_preserved": True,
        "overlong_input_rejected": True,
        "query_shape": list(query.shape),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
