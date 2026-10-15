"""Keep v1 unchanged, repair its THMLN rows in v2 and append 25 sourced QA."""

from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
QA_DIR = ROOT / "data/qa"
BASE = QA_DIR / "qa_pilot_v1.0.csv"
OUTPUT = QA_DIR / "qa_pilot_v2.0.csv"
ADDITIONS = QA_DIR / "qa_pilot_v2.0_additions.json"
CORRECTIONS = QA_DIR / "qa_pilot_v2.0_corrections.json"
REVIEW = QA_DIR / "qa_pilot_v2.0_review.csv"
REPORT = ROOT / "docs/reports/w3-a-qa-verification.json"

def compact(text):
    return re.sub(r"\s+", "", text).casefold()


def evidence_span(text, anchor, window=1800):
    chars = [(i, char.casefold()) for i, char in enumerate(text) if not char.isspace()]
    joined = "".join(char for _, char in chars)
    start = joined.find(compact(anchor))
    if start < 0:
        raise ValueError(f"Evidence anchor not found: {anchor}")
    offset = chars[start][0]
    return text[offset:offset + window]


def csv_bytes(rows, fields, line_ending="\r\n", header=True):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator=line_ending, extrasaction="raise")
    if header:
        writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def build():
    original = BASE.read_bytes()
    reader = csv.DictReader(io.StringIO(original.decode("utf-8-sig"), newline=""))
    fields = reader.fieldnames
    old = list(reader)
    if len(old) != 50 or not original.endswith(b"\n"):
        raise ValueError("Expected the existing 50-row v1 CSV with a terminating newline.")
    supplement = json.loads(ADDITIONS.read_text(encoding="utf-8"))
    corrections = json.loads(CORRECTIONS.read_text(encoding="utf-8"))
    expected_ids = [f"THMLN_QA_{i:03d}" for i in range(1, 25)]
    if corrections["course_id"] != "THMLN" or corrections["page_unit"] != "physical_pdf_1based" or [r["qa_id"] for r in corrections["rows"]] != expected_ids:
        raise ValueError("Expected exactly the 24 legacy THMLN corrections.")
    previous = list(csv.DictReader(io.StringIO(OUTPUT.read_text(encoding="utf-8-sig"), newline=""))) if OUTPUT.exists() else None
    if supplement["course_id"] != "THMLN" or supplement["page_unit"] != "physical_pdf_1based" or len(supplement["rows"]) != 25:
        raise ValueError("Expected exactly 25 THMLN additions with physical page labels.")
    documents = {}
    for path in sorted((ROOT / "data/corpus/THMLN").glob("*.pdf")):
        documents[path.name] = {
            "pages": [re.sub(r"\s+", " ", page.extract_text() or "").strip() for page in PdfReader(path).pages],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    rows, reviews, corrected = [], [], {}
    old_by_id = {r["qa_id"]: r for r in old}
    if [r["qa_id"] for r in old if r["course_id"] == "THMLN"] != expected_ids:
        raise ValueError("Legacy THMLN IDs do not match the correction set.")
    for addition in corrections["rows"] + supplement["rows"]:
        source = documents[addition["source_doc"]]
        page = addition["source_page"]
        if type(page) is not int or not 1 <= page <= len(source["pages"]):
            raise ValueError(f"Invalid physical page for {addition['qa_id']}")
        text = source["pages"][page-1]
        excerpt = evidence_span(text, addition["evidence_anchor"], addition.get("evidence_window", 1800))
        for term in addition["evidence_terms"]:
            if compact(term) not in compact(excerpt):
                raise ValueError(f"Missing supporting text for {addition['qa_id']}: {term}")
        row = {key: addition[key] for key in fields if key not in ("course_id", "notes")}
        row["course_id"] = "THMLN"
        row["notes"] = "W3 development; physical_pdf_1based; source_checked; peer_review_pending; evidence=qa_pilot_v2.0_review.csv"
        legacy = old_by_id.get(row["qa_id"])
        if legacy is None:
            rows.append(row)
        else:
            corrected[row["qa_id"]] = row
        reviews.append({"qa_id": row["qa_id"], "origin": "v1_corrected" if legacy else "v2_addition", "course_id": "THMLN",
                        "source_doc": row["source_doc"], "source_page": page, "pdf_page_count": len(source["pages"]),
                        "review_status": "SOURCE_CHECKED_PENDING_PEER", "review_note": "Đã đối chiếu câu hỏi/đáp án với trang PDF; đoạn trích từ pypdf có thể chứa khoảng trắng tách âm tiết.",
                        "evidence_excerpt": excerpt, "source_sha256": source["sha256"], "peer_review_status": "pending",
                        "old_source_doc": legacy["source_doc"] if legacy else "",
                        "old_source_page": legacy["source_page"] if legacy else "",
                        "changed_fields": ",".join(key for key in fields if legacy and str(row[key]) != legacy[key]),
                        "correction_reason": addition.get("correction_reason", "")})
    if [r["qa_id"] for r in rows] != [f"THMLN_QA_{i:03d}" for i in range(25, 50)]:
        raise ValueError("New THMLN IDs must be 025 through 049.")
    repaired = [corrected.get(r["qa_id"], r) for r in old]
    combined = repaired + rows
    if len({r["qa_id"] for r in combined}) != 75:
        raise ValueError("QA IDs are duplicated.")
    if len({compact(r["question"]) for r in combined if r["course_id"] == "THMLN"}) != 49:
        raise ValueError("THMLN questions are duplicated.")
    old_questions = {compact(r["question"]) for r in repaired}
    if any(compact(r["question"]) in old_questions for r in rows) or len({compact(r["question"]) for r in rows}) != 25:
        raise ValueError("An exact question is duplicated.")
    result_bytes = csv_bytes(combined, fields, "\r\n" if b"\r\n" in original else "\n")
    parsed = list(csv.DictReader(io.StringIO(result_bytes.decode("utf-8-sig"), newline="")))
    if [r["qa_id"] for r in parsed[:50]] != [r["qa_id"] for r in old] or len(parsed) != 75 or any(None in row or None in row.values() for row in parsed):
        raise ValueError("CSV preservation or shape validation failed.")
    if [r for r in parsed[:50] if r["course_id"] != "THMLN"] != [r for r in old if r["course_id"] != "THMLN"]:
        raise ValueError("Unrelated legacy QA changed.")
    if previous is not None and previous[50:] != parsed[50:]:
        raise ValueError("The existing 25 additions changed.")
    if BASE.read_bytes() != original:
        raise ValueError("v1 changed during processing.")
    OUTPUT.write_bytes(result_bytes)
    review_fields = ["qa_id", "origin", "course_id", "source_doc", "source_page", "pdf_page_count", "review_status", "review_note", "evidence_excerpt", "source_sha256", "peer_review_status", "old_source_doc", "old_source_page", "changed_fields", "correction_reason"]
    REVIEW.write_bytes(csv_bytes(reviews, review_fields))
    report = {
        "verified_date": "2026-10-14", "version": "2.0", "output": "data/qa/qa_pilot_v2.0.csv",
        "base_file_unchanged": BASE.read_bytes() == original, "base_ids_and_order_preserved": True,
        "corrected_legacy_thmln_rows": len(corrected), "other_legacy_rows_preserved": 26,
        "new_25_rows_preserved": previous is None or previous[50:] == parsed[50:],
        "all_thmln_sources_checked": len(reviews),
        "base_sha256": hashlib.sha256(original).hexdigest(), "v2_sha256": hashlib.sha256(result_bytes).hexdigest(),
        "added_rows": 25, "total_rows": 75, "course_counts": dict(Counter(r["course_id"] for r in parsed)),
        "new_id_range": [rows[0]["qa_id"], rows[-1]["qa_id"]], "page_unit": "physical_pdf_1based",
        "new_sources_checked": 25, "new_source_documents": sorted({r["source_doc"] for r in rows}),
        "new_question_types": dict(Counter(r["question_type"] for r in rows)),
        "new_difficulty": dict(Counter(r["difficulty"] for r in rows)),
        "legacy_thmln_reviewed": 24, "legacy_review_status_counts": dict(Counter(r["review_status"] for r in reviews if r["origin"] == "v1_corrected")),
        "peer_review_complete": False, "all_75_rows_certified_as_benchmark": False,
        "review_file": "data/qa/qa_pilot_v2.0_review.csv",
        "note": "v1 remains unchanged. Its 24 THMLN rows are repaired only in v2; the other 26 legacy rows and 25 additions are unchanged. All 49 THMLN rows are source-checked, not independently peer-reviewed. The other courses are not certified by this check.",
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
