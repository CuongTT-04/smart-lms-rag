"""Offline lexical screening of saved answers, not semantic factuality certification."""

from collections import Counter
from dataclasses import asdict, dataclass
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from time import perf_counter
import unicodedata
import zipfile

from ..providers.base import GenerationError
from ..rag.citations import choice_options, validate_choice_answer


@dataclass(frozen=True)
class RuleConfig:
    version: str = "lexical_screening_v1"
    keyword_threshold: float = 0.65
    claim_overlap_threshold: float = 0.35
    hint_copy_words: int = 6

    def __post_init__(self):
        if self.version != "lexical_screening_v1":
            raise ValueError("Unsupported rules version.")
        for value in (self.keyword_threshold, self.claim_overlap_threshold):
            if type(value) not in (int, float) or not 0 <= value <= 1:
                raise ValueError("Thresholds must be finite numbers in [0, 1].")
        if type(self.hint_copy_words) is not int or self.hint_copy_words < 4:
            raise ValueError("hint_copy_words must be an integer >= 4.")


# Negations are deliberately not stopwords; overlap still cannot prove entailment.
STOPWORDS = frozenset("là của và các những một được với cho về để đó này thì từ trên khi cũng do đã ở theo".split())
NEGATIONS = frozenset(("không", "chưa", "chẳng", "never", "not"))
INLINE_LABEL = re.compile(r"\[([1-9][0-9]*)\]")
CLAIM = re.compile(r"(.*?)(\[[1-9][0-9]*\](?:\s*\[[1-9][0-9]*\])*)", re.DOTALL)


def words(text):
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFC", text).casefold())


def keywords(text):
    return {word for word in words(INLINE_LABEL.sub("", text))
            if word not in STOPWORDS and len(word) > 1}


def _coverage(reference, answer):
    expected = keywords(reference)
    found = expected & keywords(answer)
    return {"coverage": len(found) / len(expected) if expected else None,
            "matched": sorted(found), "missing": sorted(expected - found)}


def _reference_kind(case):
    if case["mode"] == "hint":
        return "hint"
    gold = case.get("ground_truth")
    if not isinstance(gold, str) or not gold.strip():
        return "unsupported"
    if gold.strip().casefold() in ("true", "false"):
        return "boolean"
    if re.fullmatch(r"[A-D]", gold.strip()):
        return "choice" if gold.strip() in choice_options(case["question"]) else "unsupported"
    return "keywords"


def _page(source):
    value = (source.get("document_id"), source.get("version_id"), source.get("page_number"))
    if not all(isinstance(x, str) and x for x in value[:2]) or type(value[2]) is not int or value[2] < 1:
        raise ValueError("Invalid source page identity.")
    return value


def _citations(case, prediction, answer, config):
    contexts = prediction.get("used_contexts") or []
    sources = {item["source_id"]: item for item in contexts}
    refs = prediction.get("references") or []
    labels = [item.get("label") for item in refs]
    actual = {int(x) for x in INLINE_LABEL.findall(answer)}
    valid = (bool(actual) and len(sources) == len(contexts)
             and all(type(label) is int and label > 0 for label in labels)
             and len(labels) == len(set(labels)) and set(labels) == actual
             and len({item.get("source_id") for item in refs}) == len(refs)
             and all(item.get("source_id") in sources for item in refs))
    first_use = list(dict.fromkeys(int(x) for x in INLINE_LABEL.findall(answer)))
    valid = valid and labels == first_use == list(range(1, len(first_use) + 1))
    prompt_membership = None
    messages = prediction.get("prompt_messages_internal")
    if messages is not None:
        try:
            evidence = json.loads(messages[-1]["content"])["evidence"]
            prompt_ids = [item["source_id"] for item in evidence]
            prompt_membership = (len(prompt_ids) == len(set(prompt_ids))
                                 and all(item.get("source_id") in prompt_ids for item in refs))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            prompt_membership = False
    by_label = {item["label"]: sources[item["source_id"]] for item in refs} if valid else {}
    cited_pages = {_page(item) for item in by_label.values()}
    gold_pages = {_page(item) for item in case.get("gold_sources", [])}
    checks, end = [], 0
    for number, match in enumerate(CLAIM.finditer(answer), 1):
        end = match.end()
        text, markers = match.groups()
        claim_labels = [int(x) for x in INLINE_LABEL.findall(markers)]
        support = " ".join(by_label[label]["text"] for label in claim_labels if label in by_label)
        coverage = _coverage(text, support)["coverage"]
        checks.append({"segment": number, "text": text.strip(), "labels": claim_labels,
                       "lexical_overlap": coverage,
                       "low_overlap": len(keywords(text)) >= 3 and coverage is not None
                       and coverage < config.claim_overlap_threshold})
    return {"structure_valid": valid, "prompt_membership_verified": prompt_membership,
            "cited_gold_page_hit": bool(cited_pages & gold_pages) if gold_pages else None,
            "claim_checks": checks,
            "uncited_tail": bool(keywords(answer[end:]))}


def _hint_matches(case, answer, minimum):
    answer_words = words(answer)
    question_words = words(case["question"])
    reference_words = words(case.get("ground_truth") or "")
    question_phrases = {tuple(question_words[i:i + minimum]) for i in range(len(question_words) - minimum + 1)}
    answer_phrases = {tuple(answer_words[i:i + minimum]) for i in range(len(answer_words) - minimum + 1)}
    copied = sorted(({tuple(reference_words[i:i + minimum]) for i in range(len(reference_words) - minimum + 1)}
                     & answer_phrases) - question_phrases)
    forbidden = []
    for phrase in (case.get("hint_policy") or {}).get("must_not_reveal", []):
        pattern = words(phrase)
        if len(pattern) >= 3 and any(answer_words[i:i + len(pattern)] == pattern
                                     for i in range(len(answer_words) - len(pattern) + 1)):
            forbidden.append(phrase)
    return {"copied_gold_phrases": [" ".join(item) for item in copied], "forbidden_phrase_matches": forbidden}


def screen_answer(case, prediction, config=None):
    config = config or RuleConfig()
    kind = _reference_kind(case)
    row = {"qa_id": case["qa_id"], "mode": case["mode"], "status": prediction["status"],
           "rule_kind": kind, "rule_result": "REVIEW", "flags": [], "label_match": None,
           "expected_label": None, "observed_label": None, "keyword_checks": [],
           "keyword_coverage": None, "citations": None, "hint_checks": None,
           "human_review_required": True, "factuality_verified": False}
    if prediction["status"] == "ERROR":
        row.update(rule_result="NO_VALID_ANSWER", flags=["GENERATION_OR_SERVICE_ERROR"])
        row["original_error"] = prediction.get("error")
        return row
    if prediction["status"] != "ANSWERED":
        row.update(rule_result="ABSTENTION_REVIEW", flags=["ABSTENTION_NEEDS_REVIEW"])
        return row
    answer = prediction["answer"]
    row["citations"] = _citations(case, prediction, answer, config)
    if not row["citations"]["structure_valid"]:
        row["flags"].append("INVALID_CITATION_STRUCTURE")
    if row["citations"]["prompt_membership_verified"] is not True:
        row["flags"].append("UNVERIFIED_PROMPT_MEMBERSHIP")
    if row["citations"]["cited_gold_page_hit"] is False:
        row["flags"].append("NO_CITED_GOLD_PAGE")
    if any(item["low_overlap"] for item in row["citations"]["claim_checks"]):
        row["flags"].append("LOW_CLAIM_SOURCE_OVERLAP")
    if row["citations"]["uncited_tail"]:
        row["flags"].append("UNCITED_TAIL_REVIEW")
    # Matching only the leading label never certifies the explanation or its sources.
    plain = re.sub(r"^[\s*#>\"']+", "", answer).strip()
    if kind in ("boolean", "choice"):
        expected = case["ground_truth"].strip()
        if kind == "boolean":
            expected = "true" if expected.casefold() == "true" else "false"
            match = re.match(r"^(đúng|sai|true|false)\b", plain, re.IGNORECASE)
            observed = {"đúng": "true", "sai": "false", "true": "true", "false": "false"}.get(
                match.group(1).casefold()) if match else None
        else:
            match = re.match(r"^([A-D])\s*[).:]", plain, re.IGNORECASE)
            observed = match.group(1).upper() if match else None
            try:
                validate_choice_answer(case["question"], answer)
            except GenerationError:
                row["flags"].append("CHOICE_TEXT_CONTRACT_REVIEW")
        row.update(expected_label=expected, observed_label=observed,
                   label_match=observed == expected if observed is not None else None)
        row["rule_result"] = "LABEL_MATCH" if row["label_match"] else "LABEL_MISMATCH" if observed else "LABEL_UNCLEAR"
        if row["label_match"] is not True:
            row["flags"].append(row["rule_result"])
    elif kind == "keywords":
        references = case.get("expected_points") or [case["ground_truth"]]
        checks = [{"reference": value, **_coverage(value, answer)} for value in references]
        row["keyword_checks"] = checks
        coverages = [item["coverage"] for item in checks if item["coverage"] is not None]
        row["keyword_coverage"] = sum(coverages) / len(coverages) if coverages else None
        covered = bool(coverages) and all(value >= config.keyword_threshold for value in coverages)
        row["rule_result"] = "KEYWORD_COVERED" if covered else "LOW_KEYWORD_COVERAGE"
        if not covered:
            row["flags"].append("LOW_KEYWORD_COVERAGE")
        if bool(NEGATIONS & set(words(" ".join(references)))) != bool(NEGATIONS & set(words(answer))):
            row["flags"].append("NEGATION_REVIEW")
    elif kind == "hint":
        row["rule_result"] = "HINT_REVIEW"
        row["hint_checks"] = _hint_matches(case, answer, config.hint_copy_words)
        if any(row["hint_checks"].values()):
            row["flags"].append("POSSIBLE_HINT_LEAK")
    else:
        row["flags"].append("UNSUPPORTED_REFERENCE")
    return row


def _read_run(source):
    source = Path(source).resolve()
    required = ("run_manifest.json", "dataset.json", "predictions.jsonl")
    limit = 64 * 1024 * 1024
    if source.is_dir():
        payloads = {}
        for name in required:
            path = source / name
            if path.is_symlink() or path.stat().st_size > limit:
                raise ValueError("Unsafe or oversized run input.")
            payloads[name] = path.read_bytes()
    else:
        with zipfile.ZipFile(source) as archive:
            payloads, parents = {}, set()
            for name in required:
                matches = [item for item in archive.infolist() if PurePosixPath(item.filename).name == name]
                if len(matches) != 1 or matches[0].file_size > limit:
                    raise ValueError("ZIP must contain exactly one bounded copy of each run input.")
                path = PurePosixPath(matches[0].filename)
                if path.is_absolute() or ".." in path.parts or "\\" in matches[0].filename:
                    raise ValueError("Unsafe archive member path.")
                parents.add(path.parent)
                payloads[name] = archive.read(matches[0])
            if len(parents) != 1:
                raise ValueError("Run inputs must belong to the same archive directory.")
    manifest = json.loads(payloads["run_manifest.json"])
    if manifest.get("run_kind") not in ("unit", "live_model"):
        raise ValueError("Unknown source run kind.")
    for name in ("dataset.json", "predictions.jsonl"):
        if hashlib.sha256(payloads[name]).hexdigest() != manifest["output_sha256"].get(name):
            raise ValueError("Saved run checksum mismatch: " + name)
    cases = json.loads(payloads["dataset.json"])["cases"]
    predictions = [json.loads(line) for line in payloads["predictions.jsonl"].decode("utf-8").splitlines() if line.strip()]
    ids = [case["qa_id"] for case in cases]
    if (not ids or len(set(ids)) != len(ids) or ids != [row["qa_id"] for row in predictions]
            or ids != manifest["selected_qa_ids"] or len(ids) != manifest["selected_count"]):
        raise ValueError("Dataset/prediction/manifest IDs or counts differ.")
    for case, row in zip(cases, predictions):
        if (case.get("mode") not in ("qa", "hint") or row.get("mode") != case["mode"]
                or not isinstance(case.get("question"), str) or not case["question"].strip()
                or row.get("status") not in ("ANSWERED", "ERROR", "INSUFFICIENT_EVIDENCE")
                or (row["status"] == "ANSWERED" and (not isinstance(row.get("answer"), str) or not row["answer"].strip()))):
            raise ValueError("Invalid saved case or prediction.")
        points = case.get("expected_points")
        if (points is not None and (not isinstance(points, list)
                                   or any(not isinstance(item, str) or not item.strip() for item in points))):
            raise ValueError("Expected points must be a list of nonblank reference strings.")
        if case.get("ground_truth") is not None and not isinstance(case["ground_truth"], str):
            raise ValueError("Reference answer must be a string or missing.")
    return manifest, cases, predictions, {name: hashlib.sha256(value).hexdigest() for name, value in payloads.items()}


def _csv_text(value):
    text = str(value) if value is not None else ""
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def score_saved_run(source, output_dir, config=None):
    """Read ZIP/folder without extracting it, and keep machine grades separate from humans."""
    started = perf_counter()
    config = config or RuleConfig()
    source, output = Path(source).resolve(), Path(output_dir).resolve()
    if output == source or (source.is_dir() and (output.is_relative_to(source) or source.is_relative_to(output))):
        raise ValueError("Keep rule outputs outside the original run.")
    manifest, cases, predictions, hashes = _read_run(source)
    rows = [screen_answer(case, row, config) for case, row in zip(cases, predictions)]
    output.mkdir(parents=True, exist_ok=False)
    with (output / "rule_scores.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    fields = ["qa_id", "assigned_member", "mode", "status", "rule_kind", "rule_result", "label_match",
              "keyword_coverage", "citation_structure_valid", "cited_gold_page_hit", "flags", "question",
              "answer", "expected_reference", "human_review_required"]
    with (output / "rule_scores.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for number, (case, prediction, row) in enumerate(zip(cases, predictions, rows)):
            values = {key: row[key] for key in ("qa_id", "mode", "status", "rule_kind", "rule_result", "label_match",
                                               "keyword_coverage", "human_review_required")}
            values.update(assigned_member="A" if number % 2 == 0 else "B",
                          citation_structure_valid=(row["citations"] or {}).get("structure_valid"),
                          cited_gold_page_hit=(row["citations"] or {}).get("cited_gold_page_hit"),
                          flags="; ".join(row["flags"]), question=case["question"], answer=prediction.get("answer"),
                          expected_reference=json.dumps(case.get("expected_points") or case.get("ground_truth"), ensure_ascii=False))
            writer.writerow({key: _csv_text(value) for key, value in values.items()})
    label_rows = [row for row in rows if row["rule_kind"] in ("boolean", "choice")]
    recognized = [row for row in label_rows if row["label_match"] is not None]
    citation_rows = [row["citations"] for row in rows if row["citations"] is not None]
    summary = {
        "method": "rules_and_keywords_not_semantic_factuality", "rules": asdict(config),
        "total_qa": len(rows), "source_run_kind": manifest["run_kind"],
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "rule_result_counts": dict(Counter(row["rule_result"] for row in rows)),
        "flag_counts": dict(Counter(flag for row in rows for flag in row["flags"])),
        "label_checks": {"total_label_qa": len(label_rows), "recognized_answer_labels": len(recognized),
                         "matching_labels": sum(row["label_match"] is True for row in recognized),
                         "mismatching_labels": sum(row["label_match"] is False for row in recognized),
                         "unscored_including_errors": len(label_rows) - len(recognized)},
        "citation_checks": {"answered_denominator": len(citation_rows),
                            "structure_valid": sum(row["structure_valid"] for row in citation_rows),
                            "prompt_membership_verified": sum(row["prompt_membership_verified"] is True for row in citation_rows),
                            "cited_gold_page_hit_count": sum(row["cited_gold_page_hit"] is True for row in citation_rows),
                            "gold_page_denominator": sum(row["cited_gold_page_hit"] is not None for row in citation_rows)},
        "input_sha256": hashes,
        "source_archive_sha256": hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None,
        "grader_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "output_sha256": {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                          for name in ("rule_scores.jsonl", "rule_scores.csv")},
        "human_review_required_count": len(rows), "human_review_complete": False,
        "factuality_accuracy": None, "quality_verified": False, "model_calls": 0,
        "elapsed_seconds": perf_counter() - started,
        "limitation": "Label matching checks only the leading decision, not its rationale. Keyword overlap can miss "
                      "paraphrases and accept contradictions, copied gold or swapped entities. Low source overlap and "
                      "hint copying are review flags, not entailment/leakage proofs. A matching gold page does not prove "
                      "citation support. No human scores were filled; all cases still require review. Checksums detect "
                      "inconsistency, not authenticity of a run or correctness of its labels.",
    }
    (output / "rule_metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return summary
