"""Offline RAG evaluation using the application pipeline, not an answer simulator."""

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import re
from time import perf_counter
from unittest.mock import patch
import unicodedata
from uuid import UUID

from ..providers.base import GenerationError, ModelOutput
from ..rag.base import EvidenceContext
from ..rag.guardrails import check_request_policy
from ..rag.citations import VALIDATION_REASONS
from .metrics import evaluate


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_qa_files(paths):
    cases, inputs, ids, questions = [], [], set(), set()
    for path in paths:
        path = Path(path).resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("cases"), list) or not data["cases"]:
            raise ValueError("Each dataset must contain a nonempty cases list.")
        inputs.append({"path": str(path), "sha256": file_hash(path), "case_count": len(data["cases"]),
                       "review_status": data.get("review_status", "unknown")})
        for case in data["cases"]:
            qid = case.get("qa_id")
            if not isinstance(qid, str) or not qid.strip() or qid in ids:
                raise ValueError("Missing/duplicate QA ID; do not silently overwrite a shared record.")
            question = case.get("question")
            if isinstance(question, str) and question.strip():
                key = " ".join(re.findall(r"\w+", unicodedata.normalize("NFC", question).casefold()))
                if key in questions:
                    raise ValueError("Duplicate normalized question across datasets: " + qid)
                questions.add(key)
            ids.add(qid)
            cases.append(dict(case))
    if not cases:
        raise ValueError("At least one QA dataset is required.")
    return cases, inputs


def public_request(case):
    """Never forward grading answers, hint rubrics, gold sources or author metadata."""
    if case.get("label_error"):
        raise ValueError("Gold label is outside the pinned source snapshot.")
    if not isinstance(case.get("question"), str) or not case["question"].strip() or case.get("mode") not in ("qa", "hint"):
        raise ValueError("Invalid question/mode.")
    UUID(case["course_id"])
    scope = case.get("scope", {})
    if scope is None:
        scope = {}
    if not isinstance(scope, dict) or any(value is not None for value in scope.values()):
        raise ValueError("This offline runner cannot resolve live classroom/session/assessment selectors.")
    # Dataset labels are checked but are never used to restrict retrieval to the answer page.
    gold = case.get("gold_sources")
    if not isinstance(gold, list):
        raise ValueError("Explicit gold_sources list required; [] means no evidence.")
    for source in gold:
        UUID(source["document_id"])
        UUID(source["version_id"])
        if type(source["page_number"]) is not int or source["page_number"] < 1:
            raise ValueError("Invalid gold physical page.")
    return {"question": case["question"].strip(), "mode": case["mode"], "course_id": case["course_id"]}


def response_contexts(response, course_id, top_k):
    if response.get("status") not in ("OK", "EMPTY_SCOPE", "NO_INDEXED_SOURCES"):
        raise GenerationError("RETRIEVAL_FAILED", "Retrieval did not complete.")
    results = response.get("results")
    if (not isinstance(results, list) or len(results) > top_k
            or (response["status"] != "OK" and results)):
        raise GenerationError("INVALID_RETRIEVAL", "Invalid ranked result container.")
    contexts, ids = [], set()
    for number, result in enumerate(results, 1):
        source = result["source"]
        if (result.get("rank") != number or type(result.get("rank")) is not int
                or UUID(source["course_id"]) != UUID(course_id)
                or type(result.get("score")) not in (int, float) or not math.isfinite(result["score"])
                or result["chunk_id"] in ids):
            raise GenerationError("INVALID_RETRIEVAL", "Rank, identity or score is invalid.")
        ids.add(result["chunk_id"])
        contexts.append(EvidenceContext(
            source_id=f"S{number}", chunk_id=result["chunk_id"], text=result["text"],
            document_id=source["document_id"], version_id=source["version_id"],
            document_title=source["document_title"], page_number=source["page_number"],
            section_title=source.get("section_title"),
        ))
    return contexts


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def attach_guardrails(source, output, config_hash):
    source = Path(source)
    summary = json.loads(source.with_name("summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    if (summary.get("config_sha256") != config_hash or summary.get("results_sha256") != file_hash(source)
            or summary.get("case_count") != len(rows) or summary.get("run_kind") != "live_model"
            or len({row["case_id"] for row in rows}) != len(rows)):
        raise ValueError("Guardrail evidence checksum/config/run identity mismatch.")
    (output / "guardrail_results.jsonl").write_bytes(source.read_bytes())
    write_json(output / "guardrail_summary.json", summary)
    return {"source": str(source.resolve()), "sha256": file_hash(source),
            "status": summary["status"], "origin": "imported_previous_live_run_not_rerun",
            "automatic_pass_count": summary.get("automatic_pass_count"), "case_count": len(rows)}


def run_evaluation(cases, pipeline, retrieve, output_dir, *, run_kind, provenance,
                   total_available=None, top_k=5, guardrail_results=None):
    if run_kind not in ("unit", "live_model") or type(top_k) is not int or top_k < 1:
        raise ValueError("Explicit unit/live_model run kind and positive top_k required.")
    if not cases or len({case["qa_id"] for case in cases}) != len(cases):
        raise ValueError("Require nonempty, unique selected QA IDs.")
    available = len(cases) if total_available is None else total_available
    if type(available) is not int or available < len(cases):
        raise ValueError("Selected sample cannot exceed the available dataset.")
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": "1.0", "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_kind": run_kind, "scope": "offline_snapshot_scope_not_database_authorization",
        "dataset_available_count": available, "selected_count": len(cases),
        "selected_qa_ids": [case["qa_id"] for case in cases], "top_k_chunks": top_k,
        "is_full_150_run": len(cases) == available == 150,
        "config": asdict(pipeline.config), "config_sha256": pipeline.config.fingerprint(),
        "provenance": dict(provenance), "python": platform.python_version(),
        "latency_protocol": "sequential_retrieval_plus_pipeline_including_possible_lazy_load; no warmup",
        "human_review_complete": False, "quality_verified": False, "authorization_verified": False,
        "guardrail_evidence": None, "status": "RUNNING",
    }
    if guardrail_results:
        manifest["guardrail_evidence"] = attach_guardrails(guardrail_results, output, pipeline.config.fingerprint())
    write_json(output / "run_manifest.json", manifest)
    write_json(output / "dataset.json", {"cases": cases, "review_status": "see_input_manifests"})
    rows, retrieval_predictions = [], {}
    with (output / "predictions.jsonl").open("w", encoding="utf-8") as stream:
        for case in cases:
            tick = perf_counter()
            row = {"qa_id": case["qa_id"], "mode": case.get("mode"), "status": "ERROR",
                   "answer": None, "references": [], "usage": None, "error": None,
                   "retrieval": None, "supplied_contexts": [], "used_contexts": [], "trace": None,
                   "prompt_messages_internal": None, "model_output_internal": None,
                   "retrieval_seconds": None, "pipeline_seconds": None}
            phase = "input"
            try:
                request = public_request(case)
                check_request_policy(request["question"])
                phase = "retrieval"
                started = perf_counter()
                response = retrieve(request, top_k=top_k)
                row["retrieval_seconds"] = perf_counter() - started
                contexts = response_contexts(response, request["course_id"], top_k)
                row["retrieval"] = response
                row["supplied_contexts"] = [asdict(item) for item in contexts]
                retrieval_predictions[case["qa_id"]] = {"response": response, "latency_seconds": row["retrieval_seconds"]}
                phase = "generation"
                started = perf_counter()
                original_generate = pipeline.provider.generate

                def observe_generate(messages, **kwargs):
                    row["prompt_messages_internal"] = messages
                    payload = json.loads(messages[-1]["content"])
                    used = {item["source_id"] for item in payload["evidence"]}
                    row["used_contexts"] = [asdict(item) for item in contexts if item.source_id in used]
                    output_value = original_generate(messages, **kwargs)
                    if isinstance(output_value, ModelOutput):
                        row["model_output_internal"] = asdict(output_value)
                    return output_value

                with patch.object(pipeline.provider, "generate", side_effect=observe_generate):
                    result = pipeline.generate_answer(question=request["question"], mode=request["mode"],
                                                      contexts=contexts, exercise=None)
                row["pipeline_seconds"] = perf_counter() - started
                row.update(result.to_dict())
                row["trace"] = asdict(result.trace)
                used = set(result.trace.used_source_ids)
                row["used_contexts"] = [asdict(item) for item in contexts if item.source_id in used]
            except Exception as exc:
                # Error text may contain private prompt/storage values; keep safe codes only.
                row["error"] = {"stage": phase, "code": getattr(exc, "code", type(exc).__name__)}
                reason = getattr(exc, "validation_reason", None)
                if isinstance(reason, str) and reason in VALIDATION_REASONS:
                    row["error"]["reason"] = reason
                if phase in ("generation", "retrieval"):
                    row["pipeline_seconds" if phase == "generation" else "retrieval_seconds"] = perf_counter() - started
            row["elapsed_seconds"] = perf_counter() - tick
            if case["qa_id"] not in retrieval_predictions:
                retrieval_predictions[case["qa_id"]] = {"response": {"status": "ERROR", "results": []},
                                                         "error": "RETRIEVAL_NOT_COMPLETED", "latency_seconds": None}
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            print(f"[{len(rows)}/{len(cases)}] {row['qa_id']}: {row['status']} | {row['elapsed_seconds']:.3f}s")
    fields = ["qa_id", "assigned_member", "calibration_first_ten", "mode", "status", "question", "ground_truth",
              "expected_points", "hint_policy", "gold_sources", "answer", "references", "error",
              "content_correct", "grounded", "citation_supports_claim", "citation_page_correct",
              "hint_no_answer_leak", "reviewer", "reviewed_at", "notes"]
    with (output / "scores.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for number, (case, row) in enumerate(zip(cases, rows)):
            values = {key: case.get(key, "") for key in ("qa_id", "mode", "question", "ground_truth")}
            values.update(status=row["status"], answer=row["answer"] or "",
                          assigned_member="A" if number % 2 == 0 else "B", calibration_first_ten=number < 10)
            for key in ("expected_points", "hint_policy", "gold_sources"):
                values[key] = json.dumps(case.get(key), ensure_ascii=False)
            for key in ("references", "error"):
                values[key] = json.dumps(row[key], ensure_ascii=False)
            writer.writerow(values)
    ks = tuple(k for k in (1, 3, 5) if k <= top_k)
    metric_cases = []
    for case in cases:
        metric_case = dict(case)
        if not isinstance(case.get("question"), str) or not case["question"].strip() or case.get("mode") not in ("qa", "hint"):
            metric_case["label_error"] = "INVALID_QUESTION_OR_MODE"
        metric_cases.append(metric_case)
    _, retrieval_metrics = evaluate(metric_cases, retrieval_predictions, ks=ks, requested_top_k=top_k,
                                    provenance={"run_kind": run_kind, "offline_scope": True})
    latencies = [row["elapsed_seconds"] for row in rows]
    usages = []
    for row in rows:
        usage = (row["model_output_internal"] or {}).get("usage")
        if isinstance(usage, dict) and all(type(usage.get(key)) is int and usage[key] >= 0
                                           for key in ("input_tokens", "output_tokens")):
            usages.append(usage)
    metrics = {
        "run_kind": run_kind, "total_qa": len(rows), "dataset_available_count": available,
        "is_full_150_run": manifest["is_full_150_run"], "status_counts": dict(Counter(r["status"] for r in rows)),
        "error_count": sum(r["error"] is not None for r in rows),
        "error_groups": dict(Counter(r["error"]["stage"] + ":" + r["error"]["code"] for r in rows if r["error"])),
        "validation_reason_counts": dict(Counter(r["error"]["reason"] for r in rows
                                                  if r["error"] and "reason" in r["error"])),
        "latency_seconds": {"count": len(rows), "mean": sum(latencies) / len(rows),
                            "p50": percentile(latencies, .5), "p95": percentile(latencies, .95),
                            "method": "nearest_rank", "first_case": latencies[0]},
        "token_usage": {"measured_generation_calls": len(usages),
                        "no_generation_calls": sum(r["prompt_messages_internal"] is None for r in rows),
                        "unmeasured_generation_attempts": sum(r["prompt_messages_internal"] is not None for r in rows) - len(usages),
                        "input_tokens": sum(u["input_tokens"] for u in usages) if usages else None,
                        "output_tokens": sum(u["output_tokens"] for u in usages) if usages else None,
                        "note": "Includes observed model usage even when output validation fails; exceptions without usage remain unmeasured. Hint tokens describe action selection."},
        "cost": None, "human_review_complete": False,
        "quality": {"content_correct": None, "grounded": None, "citation_supports_claim": None,
                    "citation_page_correct": None, "hint_no_answer_leak": None, "reviewed_qa": 0},
        "retrieval_page_metrics": retrieval_metrics,
        "authorization_verified": False, "rag_verified": False,
        "limitation": "Output status and page hits are not semantic quality. Human scores remain blank; no DB/API/UI authorization tested.",
    }
    write_json(output / "metrics.json", metrics)
    runtime_info = getattr(pipeline.provider, "runtime_info", None)
    manifest.update(status="COMPLETED_AWAITING_REVIEW", finished_at_utc=datetime.now(timezone.utc).isoformat(),
                    provider_runtime_after=runtime_info() if callable(runtime_info) else None,
                    output_sha256={name: file_hash(output / name) for name in
                                   ("dataset.json", "predictions.jsonl", "scores.csv", "metrics.json")})
    write_json(output / "run_manifest.json", manifest)
    return metrics


def run_prompt_comparison(cases, baseline, candidate, retrieve, output_dir, *, run_kind,
                          provenance, total_available=None, top_k=5):
    """Offline prompt experiment, not an end-to-end latency or semantic quality claim."""
    if (baseline.provider is not candidate.provider
            or baseline.config.model != candidate.config.model
            or baseline.config.prompt_version != "frozen_baseline"
            or candidate.config.prompt_version != "efficient_grounded"
            or baseline.config.max_sources != candidate.config.max_sources
            or baseline.config.reject_cjk_output != candidate.config.reject_cjk_output):
        raise ValueError("Compare the two prompts on one provider with identical budgets and guards.")
    if (run_kind not in ("unit", "live_model") or type(top_k) is not int or top_k < 1
            or not cases or len({case["qa_id"] for case in cases}) != len(cases)):
        raise ValueError("Require unique cases, explicit run kind and positive top_k.")
    available = len(cases) if total_available is None else total_available
    if type(available) is not int or available < len(cases):
        raise ValueError("Selected sample cannot exceed the available dataset.")
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    snapshots, retrieval_rows = {}, []

    def key(request):
        return json.dumps(request, sort_keys=True, ensure_ascii=False)

    for case in cases:
        tick = perf_counter()
        try:
            request = public_request(case)
            check_request_policy(request["question"])
            request_key = key(request)
        except Exception:
            # The normal runner records input/policy errors separately for both arms.
            continue
        if request_key in snapshots:
            continue
        try:
            response = retrieve(request, top_k=top_k)
            response_contexts(response, request["course_id"], top_k)
            snapshots[request_key] = deepcopy(response)
        except Exception:
            snapshots[request_key] = None
        retrieval_rows.append({"request": request, "response": snapshots[request_key],
                               "elapsed_seconds": perf_counter() - tick})
    write_json(root / "retrieval_snapshot.json", retrieval_rows)

    def replay(request, *, top_k):
        response = snapshots[key(request)]
        if response is None:
            raise GenerationError("RETRIEVAL_FAILED", "Pinned retrieval failed before comparison.")
        return deepcopy(response)

    warmup = {"attempted": False, "excluded_from_arm_metrics": True}
    for case in cases:
        try:
            request = public_request(case)
            check_request_policy(request["question"])
            response = snapshots.get(key(request))
            if response is None or not response["results"]:
                continue
            contexts = response_contexts(response, request["course_id"], top_k)
        except Exception:
            continue
        tick = perf_counter()
        warmup.update(attempted=True, qa_id=case["qa_id"], prompt_version="frozen_baseline")
        try:
            result = baseline.generate_answer(question=request["question"], mode=request["mode"], contexts=contexts)
            warmup["output"] = result.to_dict()
        except Exception as exc:
            warmup["error"] = {"code": getattr(exc, "code", type(exc).__name__)}
        warmup["elapsed_seconds"] = perf_counter() - tick
        break
    write_json(root / "warmup.json", warmup)

    arms, rows = {}, {}
    for name, pipeline in (("baseline", baseline), ("candidate", candidate)):
        arms[name] = run_evaluation(
            cases, pipeline, replay, root / name, run_kind=run_kind, total_available=available, top_k=top_k,
            provenance={**provenance, "experiment": "prompt_comparison",
                        "latency_scope_override": "pipeline_only; retrieval is pinned replay, not live search",
                        "retrieval_snapshot_sha256": file_hash(root / "retrieval_snapshot.json"),
                        "warmup_sha256": file_hash(root / "warmup.json"),
                        "arm_order": ["baseline", "candidate"], "arm": name},
        )
        rows[name] = [json.loads(line) for line in
                      (root / name / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    pairs = []
    for before, after in zip(rows["baseline"], rows["candidate"]):
        pairs.append({"qa_id": before["qa_id"],
                      "baseline_status": before["status"], "candidate_status": after["status"],
                      "baseline_pipeline_seconds": before["pipeline_seconds"],
                      "candidate_pipeline_seconds": after["pipeline_seconds"],
                      "same_used_chunks": before["used_contexts"] == after["used_contexts"]})
    timing = {}
    for name in arms:
        values = [row["pipeline_seconds"] for row in rows[name] if row["pipeline_seconds"] is not None]
        timing[name] = {"count": len(values), "mean": sum(values) / len(values) if values else None,
                        "p95": percentile(values, .95)}
    report = {
        "run_kind": run_kind, "scope": "offline_prompt_comparison_not_end_to_end_latency",
        "case_count": len(cases), "generation_call_budget": 2 * len(cases) + int(warmup["attempted"]),
        "pipeline_seconds": timing, "pairs": pairs,
        "arms": {name: {key: metrics[key] for key in
                        ("status_counts", "error_count", "validation_reason_counts", "token_usage")}
                 for name, metrics in arms.items()},
        "human_review_complete": False, "quality_verified": False, "candidate_accepted": None,
        "artifact_sha256": {name + "/" + filename: file_hash(root / name / filename)
                            for name in arms for filename in ("predictions.jsonl", "metrics.json", "run_manifest.json")},
        "limitation": "Sequential baseline then candidate; order/hardware noise remains. Compare pipeline_seconds, "
                      "not replay retrieval/end-to-end latency. Check same_used_chunks; shorter prompts can fit more evidence. "
                      "No retries, answer cache or automatic quality certification. Review both scores.csv before adoption.",
    }
    write_json(root / "comparison.json", report)
    return report


def summarize_reviews(directory):
    """Read actual human grades; never infer them from the answer or gold strings."""
    directory = Path(directory)
    manifest = json.loads((directory / "run_manifest.json").read_text(encoding="utf-8"))
    if file_hash(directory / "predictions.jsonl") != manifest["output_sha256"]["predictions.jsonl"]:
        raise ValueError("Prediction artifact changed after the run.")
    predictions = [json.loads(line) for line in (directory / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    with (directory / "scores.csv").open(encoding="utf-8-sig", newline="") as stream:
        scores = list(csv.DictReader(stream))
    if [row["qa_id"] for row in scores] != [row["qa_id"] for row in predictions]:
        raise ValueError("Scores must cover every prediction once, in the recorded order.")
    criteria = ("content_correct", "grounded", "citation_supports_claim", "citation_page_correct", "hint_no_answer_leak")
    grades = {key: [] for key in criteria}
    reviewed = 0
    for score, prediction in zip(scores, predictions):
        if score["mode"] != prediction["mode"] or score["status"] != prediction["status"]:
            raise ValueError("Score mode/status differs from the prediction.")
        values = [score.get(key, "").strip() for key in criteria]
        if not any(values) and not score.get("reviewer", "").strip():
            continue
        if not all(score.get(key, "").strip() for key in ("reviewer", "reviewed_at", "notes")):
            raise ValueError("Reviewed rows require reviewer, date and evidence/error notes.")
        for key in criteria:
            applicable = ((key == "content_correct" and prediction["mode"] == "qa")
                          or (key in ("grounded", "citation_supports_claim", "citation_page_correct")
                              and prediction["status"] == "ANSWERED")
                          or (key == "hint_no_answer_leak" and prediction["mode"] == "hint"
                              and prediction["status"] == "ANSWERED"))
            value = score.get(key, "").strip()
            if not applicable:
                if value != "N/A":
                    raise ValueError("Non-applicable grades must be explicitly N/A.")
            elif value not in ("0", "1"):
                raise ValueError("Applicable grades must be 0 or 1, never silently excluded.")
            else:
                if key == "content_correct" and prediction["status"] == "ERROR" and value != "0":
                    raise ValueError("A failed QA cannot receive content_correct=1.")
                grades[key].append(int(value))
        reviewed += 1
    report = {
        "total_qa": len(predictions), "reviewed_qa": reviewed, "unreviewed_qa": len(predictions) - reviewed,
        "human_review_complete": reviewed == len(predictions),
        "quality": {key: {"rate": sum(values) / len(values) if values else None,
                          "denominator": len(values), "passed": sum(values)} for key, values in grades.items()},
        "scores_sha256": file_hash(directory / "scores.csv"),
        "predictions_sha256": file_hash(directory / "predictions.jsonl"),
        "calibration_verified": False, "authorization_verified": False,
        "note": "Content grades apply to reviewed QA including errors; grounding/citation grades condition on ANSWERED. "
                "Hint leakage grades condition on answered hints. Partial review is not a full-dataset accuracy estimate. "
                "Reviewer identity, calibration and human authorship are not authenticated by this tool.",
    }
    write_json(directory / "review_metrics.json", report)
    return report
