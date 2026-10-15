"""Exercise real query embeddings and scoped FAISS retrieval with a fixture resolver."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from apps.ai.embeddings.base import EmbeddingConfig
from apps.ai.embeddings.service import EmbeddingService
from apps.ai.retrieval.retriever import RetrievalError, RetrievalScope, RetrievalService
from apps.ai.retrieval.storage import load_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=REPO_ROOT / "data/processed/w3-sample-index")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to((REPO_ROOT / "data/processed").resolve()):
        parser.error("Verification output must stay inside data/processed.")
    fixture = json.loads((REPO_ROOT / "data/fixtures/w3-sample-chunks.json").read_text(encoding="utf-8"))
    config = EmbeddingConfig.from_file(REPO_ROOT / "backend/apps/ai/embeddings/config.json")
    index = load_index(directory / "bundle", config)
    user_id = "00000000-0000-4000-8000-000000000999"
    grants = {doc["course_id"]: frozenset({doc["version_id"]}) for doc in fixture["documents"]}

    def fixture_resolver(request):
        if request.user_id != user_id:
            raise RetrievalError("SCOPE_FORBIDDEN", "Fixture user is not authorized.")
        return replace(request, allowed_version_ids=grants.get(request.course_id, frozenset()))

    service = RetrievalService(index, EmbeddingService(config), fixture_resolver)
    queries = []
    for document, sample in zip(fixture["documents"], fixture["queries"]):
        scope = RetrievalScope(user_id, document["course_id"], frozenset(), mode="qa")
        started = time.perf_counter()
        result = service.retrieve(sample["query"], scope, 5)
        assert result["status"] == "OK" and result["returned_count"] == 4
        assert all(r["source"]["course_id"] == scope.course_id and r["source"]["version_id"] == document["version_id"] for r in result["results"])
        assert result["results"][0]["chunk_id"] == sample["expected_top1_chunk_id"]
        queries.append({"query": sample["query"], "course_id": scope.course_id, "seconds_including_query_embedding": round(time.perf_counter() - started, 4), "response": result})
    first = fixture["documents"][0]
    stale = RetrievalScope(user_id, first["course_id"], frozenset({first["version_id"]}))
    grants[first["course_id"]] = frozenset()
    revoked = service.retrieve("Kiểm tra nguồn đã thu hồi", stale)
    assert revoked["status"] == "EMPTY_SCOPE" and revoked["results"] == []
    grants[first["course_id"]] = frozenset({"00000000-0000-4000-8000-000000008888"})
    missing = service.retrieve("Kiểm tra phiên bản chưa có trong index", stale)
    assert missing["status"] == "NO_INDEXED_SOURCES"
    try:
        service.retrieve("Kiểm tra sai quyền", replace(stale, user_id="00000000-0000-4000-8000-000000000998"))
    except RetrievalError as exc:
        assert exc.code == "SCOPE_FORBIDDEN"
    else:
        raise AssertionError("Forbidden fixture user was accepted.")
    report = {
        "status": "PASSED", "sample_type": "synthetic_fixture",
        "permission_resolver": "in-memory fixture, not the live Django database",
        "database_authorization_verified": False,
        "query_count": len(queries), "all_expected_top1_matches": True,
        "all_sources_inside_resolved_scope": True,
        "revoked_scope_status": revoked["status"], "missing_index_status": missing["status"],
        "forbidden_user_rejected": True, "index_revision": service.index_revision,
        "runtime": service.embedding.runtime_info(), "queries": queries,
    }
    (directory / "scoped_retrieval_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in ("runtime", "queries")}, indent=2))
    for query in queries:
        print(json.dumps({"query": query["query"], "returned_count": query["response"]["returned_count"], "top1": query["response"]["results"][0]["chunk_id"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
