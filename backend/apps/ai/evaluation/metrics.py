"""Page-level retrieval metrics using the W3 document/version/page protocol."""

from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
from uuid import UUID

DEFAULT_KS = (1, 3, 5, 10)


def identifier(value):
    if not isinstance(value, str):
        raise ValueError("Identifiers must be UUID strings.")
    return str(UUID(value))


def page_unit(source):
    page = source["page_number"]
    if type(page) is not int or page < 1:
        raise ValueError("Pages must be positive physical PDF integers.")
    return (identifier(source["document_id"]), identifier(source["version_id"]), page)


def validate_ks(ks):
    ks = tuple(ks)
    if not ks or any(type(k) is not int or k < 1 for k in ks) or len(set(ks)) != len(ks):
        raise ValueError("ks must contain distinct positive integers.")
    return tuple(sorted(ks))


def load_pilot_csv(path, source_map):
    """Resolve legacy course/filename labels against an explicitly pinned snapshot."""
    mapping = {}
    for source in source_map["sources"]:
        key = (source["course_code"], source["source_doc"])
        if key in mapping:
            raise ValueError("Duplicate course/filename mapping.")
        if type(source["page_count"]) is not int or source["page_count"] < 1:
            raise ValueError("Invalid mapped PDF page count.")
        for field in ("course_id", "document_id", "version_id"):
            identifier(source[field])
        mapping[key] = source
    cases = []
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"qa_id", "course_id", "question", "source_doc", "source_page"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Missing pilot CSV columns.")
        for row in reader:
            case = {"qa_id": row["qa_id"], "question": row["question"], "mode": "qa",
                    "ground_truth": row.get("ground_truth", ""), "gold_sources": None,
                    "evidence_reference": row.get("notes", "")}
            try:
                source = mapping[(row["course_id"], row["source_doc"])]
                page = int(row["source_page"])
                if not 1 <= page <= source["page_count"]:
                    raise ValueError("Source page outside mapped PDF.")
                case["course_id"] = identifier(source["course_id"])
                case["gold_sources"] = [{"document_id": source["document_id"],
                                         "version_id": source["version_id"], "page_number": page}]
            except (KeyError, TypeError, ValueError) as exc:
                case["label_error"] = f"UNRESOLVED_SOURCE: {exc}"
            cases.append(case)
    return cases


def evaluate(cases, predictions, *, ks=DEFAULT_KS, requested_top_k=10, provenance=None):
    """Score ranked, already scope-filtered results. Never authorize or expand scope."""
    ks = validate_ks(ks)
    if type(requested_top_k) is not int or requested_top_k < max(ks):
        raise ValueError("Retrieval must request at least the maximum evaluated k.")
    ids = [case.get("qa_id") for case in cases]
    if not cases or any(not isinstance(qid, str) or not qid.strip() for qid in ids) or len(set(ids)) != len(ids):
        raise ValueError("A nonempty dataset with distinct QA IDs is required.")
    if not isinstance(predictions, dict) or set(predictions) - set(ids):
        raise ValueError("Predictions must be keyed by known QA IDs.")
    rows = []
    for case in cases:
        row = {"qa_id": case["qa_id"], "question": case.get("question", ""),
               "ground_truth": case.get("ground_truth", ""), "mode": case.get("mode", "qa"),
               "evidence_reference": case.get("evidence_reference", ""),
               "gold_sources": [], "retrieved": [], "latency_seconds": None,
               "status": "", "error": "", "retrieval_status": "NOT_RUN"}
        for k in ks:
            row[f"page_recall_at_{k}"] = None
            row[f"hit_at_{k}"] = None
        try:
            if case.get("label_error"):
                raise ValueError(case["label_error"])
            if "gold_source_groups" in case:
                raise ValueError("Alternative evidence groups require a separate scoring protocol.")
            if row["mode"] not in ("qa", "hint") or not row["question"].strip():
                raise ValueError("Invalid mode or blank question.")
            course = identifier(case["course_id"])
            if not isinstance(case.get("gold_sources"), list):
                raise ValueError("Missing gold source labels; use [] only for explicit no-evidence QA.")
            gold = {page_unit(source) for source in case["gold_sources"]}
            row["gold_sources"] = [dict(zip(("document_id", "version_id", "page_number"), unit)) for unit in sorted(gold)]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            row.update(status="INVALID_LABEL", error=str(exc))
            rows.append(row)
            continue
        if not gold:
            row["status"] = "NO_EVIDENCE"
            rows.append(row)
            continue
        retrieved_units = []
        try:
            prediction = predictions.get(case["qa_id"])
            if prediction is None:
                raise ValueError("MISSING_PREDICTION")
            latency = prediction.get("latency_seconds")
            if latency is not None and (type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0):
                raise ValueError("INVALID_LATENCY")
            row["latency_seconds"] = latency
            response = prediction["response"]
            row["retrieval_status"] = response["status"]
            if prediction.get("error") or response["status"] not in ("OK", "EMPTY_SCOPE", "NO_INDEXED_SOURCES"):
                raise ValueError(prediction.get("error") or response["status"])
            results = response["results"]
            if not isinstance(results, list) or len(results) > requested_top_k:
                raise ValueError("INVALID_RESULT_COUNT")
            if response["status"] != "OK" and results:
                raise ValueError("NONEMPTY_FAILURE_RESPONSE")
            chunks = set()
            for rank, result in enumerate(results, 1):
                if type(result["rank"]) is not int or result["rank"] != rank:
                    raise ValueError("INVALID_RANK_ORDER")
                chunk = result["chunk_id"]
                if not isinstance(chunk, str) or not chunk.strip() or chunk in chunks:
                    raise ValueError("INVALID_OR_DUPLICATE_CHUNK")
                score = result["score"]
                if type(score) not in (int, float) or not math.isfinite(score):
                    raise ValueError("INVALID_SCORE")
                source = result["source"]
                if identifier(source["course_id"]) != course:
                    raise ValueError("COURSE_MISMATCH")
                unit = page_unit(source)
                chunks.add(chunk)
                retrieved_units.append(unit)
                # Persist only public source identifiers, never text/private storage metadata.
                row["retrieved"].append({"rank": rank, "chunk_id": chunk, "score": score,
                                         "source": {"course_id": course, **dict(zip(("document_id", "version_id", "page_number"), unit))}})
            row["status"] = "OK" if results else "EMPTY_RESULTS"
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            row.update(status="RETRIEVAL_ERROR", error=str(exc), retrieved=[])
            retrieved_units = []
        for k in ks:
            hits = len(gold.intersection(retrieved_units[:k]))
            row[f"page_recall_at_{k}"] = hits / len(gold)
            row[f"hit_at_{k}"] = int(hits > 0)
        rows.append(row)
    scored = [row for row in rows if row["status"] not in ("NO_EVIDENCE", "INVALID_LABEL")]
    counts = dict(Counter(row["status"] for row in rows))
    known_latencies = [row["latency_seconds"] for row in scored if row["latency_seconds"] is not None]
    metrics = {"protocol_version": "w3-page-v1", "unit": "document_version_page", "k_unit": "chunk",
               "ks": list(ks), "requested_top_k": requested_top_k,
               "aggregation": "macro over valid gold QA; empty/error retrieval=0; deduplicate pages after slicing top-k chunks",
               "total_qa": len(rows), "scored_qa": len(scored),
               "recorded_prediction_qa": sum(row["qa_id"] in predictions for row in scored),
               "missing_prediction_qa": sum(row["qa_id"] not in predictions for row in scored),
               "invalid_label_qa": counts.get("INVALID_LABEL", 0), "no_evidence_qa": counts.get("NO_EVIDENCE", 0),
               "retrieval_error_qa": counts.get("RETRIEVAL_ERROR", 0), "status_counts": counts,
               "latency_count": len(known_latencies),
               "mean_latency_seconds": sum(known_latencies) / len(known_latencies) if known_latencies else None,
               "page_recall": {str(k): sum(row[f"page_recall_at_{k}"] for row in scored) / len(scored) if scored else None for k in ks},
               "hit_rate": {str(k): sum(row[f"hit_at_{k}"] for row in scored) / len(scored) if scored else None for k in ks},
               "provenance": dict(provenance or {}), "authorization_verified": False,
               "limitation": "Page matches do not establish passage relevance or answer quality; no-evidence behavior requires separate tests."}
    return rows, metrics


def export_report(directory, rows, metrics):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fields = ["qa_id", "question", "ground_truth", "mode", "evidence_reference", "gold_sources",
              "retrieved", "latency_seconds", "status", "retrieval_status", "error"]
    fields += [field for k in metrics["ks"] for field in (f"page_recall_at_{k}", f"hit_at_{k}")]
    output = directory / "retrieval_results.csv"
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            values = dict(row)
            for field in ("gold_sources", "retrieved"):
                values[field] = json.dumps(values[field], ensure_ascii=False, allow_nan=False)
            writer.writerow(values)
    report = {**metrics, "results_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    (directory / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report
