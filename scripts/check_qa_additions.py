"""Check authored development QA against the unchanged PDF snapshot and baseline."""

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from uuid import UUID

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", text)).casefold()


def question_key(text):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold()))


def check_additions(data, baseline, source_map, corpus, *, annotate=False):
    data = deepcopy(data)
    cases = data.get("cases", [])
    if len(cases) != 50 or data.get("review_status") != "pending_human_peer":
        raise ValueError("Require 50 additions and honest pending human peer review.")
    ids = [case["qa_id"] for case in cases]
    expected_ids = ([f"THMLN_QA_{n:03d}" for n in range(50, 75)]
                    + [f"KTCTMLN_QA_{n:03d}" for n in range(32, 45)]
                    + [f"CNXHKH_QA_{n:03d}" for n in range(21, 33)])
    if ids != expected_ids:
        raise ValueError("Addition IDs must match the published per-course ranges and order.")
    if set(ids) & {case["qa_id"] for case in baseline["cases"]}:
        raise ValueError("Addition ID already exists in baseline.")
    seen = {question_key(case["question"]) for case in baseline["cases"]}
    for case in cases:
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise ValueError("Question must be nonblank.")
        key = question_key(case["question"])
        if not key or key in seen:
            raise ValueError("Duplicate normalized question: " + case["qa_id"])
        seen.add(key)
    if Counter(case.get("mode") for case in cases) != {"qa": 40, "hint": 10}:
        raise ValueError("Require 40 QA and ten practice hints.")
    catalog = {}
    for source in source_map["sources"]:
        key = (source["course_code"], source["source_doc"])
        if key in catalog:
            raise ValueError("Duplicate source mapping.")
        catalog[key] = source
    course_codes = {source["course_id"]: source["course_code"] for source in source_map["sources"]}
    for case in baseline["cases"]:
        course = course_codes.get(case.get("course_id"))
        if not course or not re.fullmatch(re.escape(course) + r"_QA_[0-9]{3}", case["qa_id"]):
            raise ValueError("Baseline QA ID does not match its course: " + case["qa_id"])
    readers, checksums = {}, {}
    verified_pages = 0
    for case in cases:
        qa_id = case["qa_id"]
        course = case.get("course_code")
        if course not in ("THMLN", "KTCTMLN", "CNXHKH") or not qa_id.startswith(course + "_QA_") or not re.fullmatch(r"ch\d{2}\.pdf", case["source_doc"]):
            raise ValueError("Invalid course/source: " + qa_id)
        if not isinstance(case.get("ground_truth"), str) or not case["ground_truth"].strip():
            raise ValueError("Missing private grading reference: " + qa_id)
        points = case.get("expected_points")
        if not isinstance(points, list) or not points or any(not isinstance(p, str) or not p.strip() for p in points):
            raise ValueError("Missing grading points: " + qa_id)
        if case["mode"] == "hint":
            policy = case.get("hint_policy", {})
            forbidden = policy.get("must_not_reveal")
            if (not isinstance(policy.get("allowed_support"), str) or not policy["allowed_support"].strip()
                    or not isinstance(forbidden, list) or not forbidden
                    or any(not isinstance(term, str) or not term.strip() for term in forbidden)
                    or policy.get("expected_response_kind") != "authored_reading_guide"
                    or policy.get("usage_context") != "offline_practice_not_test"):
                raise ValueError("Missing hint support/leakage rubric: " + qa_id)
        elif "hint_policy" in case:
            raise ValueError("QA unexpectedly contains hint-only rubric: " + qa_id)
        source = catalog[(course, case["source_doc"])]
        for name in ("course_id", "document_id", "version_id"):
            UUID(source[name])
        path = Path(corpus) / course / case["source_doc"]
        if path not in readers:
            checksums[path] = digest(path)
            if checksums[path] != source["source_checksum"]:
                raise ValueError("Source checksum mismatch: " + str(path))
            readers[path] = PdfReader(path)
        reader = readers[path]
        if len(reader.pages) != source["page_count"]:
            raise ValueError("Catalog page count mismatch.")
        pages = case["source_pages"]
        if (not isinstance(pages, list) or not pages or len(set(pages)) != len(pages)
                or any(type(p) is not int or not 1 <= p <= len(reader.pages) for p in pages)):
            raise ValueError("Invalid physical page: " + qa_id)
        evidence = case["evidence"]
        if len(evidence) != len(pages) or [item["page_number"] for item in evidence] != pages:
            raise ValueError("Evidence must cover every selected page exactly once: " + qa_id)
        for item in evidence:
            text = reader.pages[item["page_number"] - 1].extract_text() or ""
            terms = [item["anchor"], *item["terms"]]
            if any(not isinstance(term, str) or not term.strip() or compact(term) not in compact(text) for term in terms):
                raise ValueError("Evidence anchor/term missing on page: " + qa_id + " " + str(item["page_number"]))
            page_hash = hashlib.sha256(compact(text).encode("utf-8")).hexdigest()
            if annotate and "page_text_sha256" not in item:
                item["page_text_sha256"] = page_hash
            if item.get("page_text_sha256") != page_hash:
                raise ValueError("Page text fingerprint mismatch: " + qa_id)
            verified_pages += 1
        expected = {
            "course_id": source["course_id"],
            "gold_sources": [{"document_id": source["document_id"], "version_id": source["version_id"],
                              "page_number": page} for page in pages],
            "source_checksum": checksums[path],
            "expected_status": "ANSWERED",
            "evidence_reference": "data/qa/qa_additions.json#" + qa_id,
            "scope": {"classroom_id": None, "session_id": None, "assessment_id": None, "question_id": None},
        }
        for name, value in expected.items():
            if annotate and name not in case:
                case[name] = value
            if case.get(name) != value:
                raise ValueError("Snapshot identity/scope mismatch: " + qa_id + " " + name)
        if annotate and "review" not in case:
            case["review"] = {"author_member": "A", "drafting_assistance": "Codex",
                              "status": "pending_human_peer", "reviewer": None, "reviewed_at": None,
                              "source_check": "anchors_verified_not_semantic_or_human_approval"}
        review = case.get("review", {})
        if review.get("status") != "pending_human_peer" or review.get("reviewer") is not None or review.get("reviewed_at") is not None:
            raise ValueError("Do not invent completed human review: " + qa_id)
    return data, {
        "status": "SOURCE_CHECKS_PASSED_PENDING_HUMAN_REVIEW",
        "addition_count": len(cases), "mode_counts": dict(Counter(c["mode"] for c in cases)),
        "course_counts": dict(Counter(c["course_code"] for c in cases)),
        "baseline_count": len(baseline["cases"]), "prospective_merged_count": len(baseline["cases"]) + len(cases),
        "source_document_count": len(readers), "verified_page_references": verified_pages,
        "exact_duplicate_questions": 0, "overlapping_ids": 0,
        "human_peer_review_complete": False, "semantic_answer_correctness_proven": False,
        "database_source_mapping_verified": False,
        "limitation": "Checks prove snapshot identity, page bounds and anchor presence, not full semantic correctness, "
                      "paraphrase uniqueness, legal access, human approval or live database mapping.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotate", action="store_true", help="Fill missing source IDs/hashes from the verified snapshot; never rewrite authored questions/answers.")
    args = parser.parse_args()
    path = ROOT / "data/qa/qa_additions.json"
    baseline_path = ROOT / "data/qa/qa_baseline.json"
    map_path = ROOT / "data/qa/source_map.json"
    data, report = check_additions(json.loads(path.read_text(encoding="utf-8")),
                                   json.loads(baseline_path.read_text(encoding="utf-8")),
                                   json.loads(map_path.read_text(encoding="utf-8")), ROOT / "data/corpus",
                                   annotate=args.annotate)
    if args.annotate:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.update(dataset_sha256=digest(path), baseline_sha256=digest(baseline_path), source_map_sha256=digest(map_path))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
