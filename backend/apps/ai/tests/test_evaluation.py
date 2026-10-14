from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from apps.ai.evaluation.metrics import evaluate, export_report, load_pilot_csv

COURSE = "00000000-0000-4000-8000-000000000001"
DOC = "00000000-0000-4000-8000-000000000101"
VERSION = "00000000-0000-4000-8000-000000001001"
OTHER = "00000000-0000-4000-8000-000000001002"


def source(page=1, version=VERSION, document=DOC):
    return {"document_id": document, "version_id": version, "page_number": page}


def case(qid="q1", pages=(1,)):
    return {"qa_id": qid, "course_id": COURSE, "question": "Fixture question",
            "gold_sources": [source(p) for p in pages]}


def prediction(pages=(1,)):
    return {"latency_seconds": 0.25, "response": {"status": "OK", "results": [
        {"rank": i, "chunk_id": f"chunk-{i}", "score": 1 / i,
         "source": {"course_id": COURSE, **source(page)}} for i, page in enumerate(pages, 1)]}}


class EvaluationTests(unittest.TestCase):
    def score(self, qa=None, pred=None):
        return evaluate([qa or case()], {"q1": pred or prediction()})

    def test_single_page_hit(self):
        rows, metrics = self.score()
        self.assertEqual(metrics["page_recall"], {"1": 1, "3": 1, "5": 1, "10": 1})
        self.assertEqual(rows[0]["hit_at_1"], 1)

    def test_multiple_pages_partial_recall_not_hit_rate(self):
        rows, metrics = self.score(case(pages=(1, 2)), prediction((1,)))
        self.assertEqual(rows[0]["page_recall_at_5"], 0.5)
        self.assertEqual(metrics["hit_rate"]["5"], 1)

    def test_deduplicate_pages_after_chunk_cutoff(self):
        rows, _ = self.score(case(pages=(1, 2)), prediction((1, 1, 1, 2)))
        self.assertEqual(rows[0]["page_recall_at_3"], 0.5)
        self.assertEqual(rows[0]["page_recall_at_5"], 1)

    def test_duplicate_gold_does_not_inflate_denominator(self):
        rows, _ = self.score(case(pages=(1, 1)), prediction())
        self.assertEqual(rows[0]["page_recall_at_1"], 1)

    def test_wrong_version_is_miss(self):
        pred = prediction()
        pred["response"]["results"][0]["source"]["version_id"] = OTHER
        rows, _ = self.score(pred=pred)
        self.assertEqual(rows[0]["page_recall_at_10"], 0)

    def test_wrong_document_is_miss(self):
        pred = prediction()
        pred["response"]["results"][0]["source"]["document_id"] = OTHER
        rows, _ = self.score(pred=pred)
        self.assertEqual(rows[0]["hit_at_10"], 0)

    def test_wrong_course_is_error_and_sources_not_exported(self):
        pred = prediction()
        pred["response"]["results"][0]["source"]["course_id"] = OTHER
        rows, metrics = self.score(pred=pred)
        self.assertEqual(metrics["retrieval_error_qa"], 1)
        self.assertEqual(rows[0]["retrieved"], [])

    def test_empty_retrieval_stays_in_denominator(self):
        _, metrics = evaluate([case(), case("q2")], {"q1": prediction(), "q2": prediction(())})
        self.assertEqual(metrics["scored_qa"], 2)
        self.assertEqual(metrics["page_recall"]["1"], 0.5)

    def test_error_stays_in_denominator(self):
        pred = {"response": {"status": "TIMEOUT", "results": []}, "error": "TIMEOUT"}
        _, metrics = evaluate([case(), case("q2")], {"q1": prediction(), "q2": pred})
        self.assertEqual(metrics["scored_qa"], 2)
        self.assertEqual(metrics["retrieval_error_qa"], 1)
        self.assertEqual(metrics["page_recall"]["10"], 0.5)

    def test_missing_prediction_is_error_not_exclusion(self):
        rows, metrics = evaluate([case()], {})
        self.assertEqual(rows[0]["error"], "MISSING_PREDICTION")
        self.assertEqual(metrics["scored_qa"], 1)

    def test_no_evidence_excluded_without_division_by_zero(self):
        rows, metrics = evaluate([case(pages=())], {})
        self.assertEqual(rows[0]["status"], "NO_EVIDENCE")
        self.assertEqual(metrics["page_recall"]["1"], None)

    def test_missing_gold_not_treated_as_no_evidence(self):
        qa = case()
        del qa["gold_sources"]
        rows, metrics = self.score(qa)
        self.assertEqual(rows[0]["status"], "INVALID_LABEL")
        self.assertEqual(metrics["invalid_label_qa"], 1)

    def test_invalid_gold_page_or_uuid_is_label_error(self):
        for value in (0, -1, True, "1"):
            with self.subTest(page=value):
                qa = case(pages=(value,))
                self.assertEqual(self.score(qa)[0][0]["status"], "INVALID_LABEL")
        qa = case()
        qa["gold_sources"][0]["version_id"] = "unknown"
        self.assertEqual(self.score(qa)[0][0]["status"], "INVALID_LABEL")

    def test_invalid_rank_or_duplicate_chunk_invalidates_whole_query(self):
        for field, value in (("rank", 3), ("chunk_id", "chunk-1")):
            pred = prediction((1, 2))
            pred["response"]["results"][1][field] = value
            rows, _ = self.score(pred=pred)
            self.assertEqual(rows[0]["status"], "RETRIEVAL_ERROR")
            self.assertEqual(rows[0]["page_recall_at_1"], 0)

    def test_nonfinite_score_or_latency_rejected(self):
        for value in (float("nan"), float("inf"), True):
            pred = prediction()
            pred["response"]["results"][0]["score"] = value
            self.assertEqual(self.score(pred=pred)[0][0]["status"], "RETRIEVAL_ERROR")
            pred = prediction()
            pred["latency_seconds"] = value
            self.assertEqual(self.score(pred=pred)[0][0]["status"], "RETRIEVAL_ERROR")

    def test_empty_scope_and_missing_index_are_zero(self):
        for status in ("EMPTY_SCOPE", "NO_INDEXED_SOURCES"):
            pred = {"response": {"status": status, "results": []}}
            rows, _ = self.score(pred=pred)
            self.assertEqual(rows[0]["status"], "EMPTY_RESULTS")
            self.assertEqual(rows[0]["page_recall_at_10"], 0)

    def test_failure_response_with_results_rejected(self):
        pred = prediction()
        pred["response"]["status"] = "EMPTY_SCOPE"
        self.assertEqual(self.score(pred=pred)[0][0]["status"], "RETRIEVAL_ERROR")

    def test_invalid_ks_and_insufficient_requested_k(self):
        for ks in ((), (1, 1), (True,), (0,), (1.5,)):
            with self.assertRaises(ValueError): evaluate([case()], {}, ks=ks)
        with self.assertRaises(ValueError): evaluate([case()], {}, requested_top_k=5)

    def test_duplicate_ids_empty_dataset_and_unknown_predictions(self):
        for cases, predictions in (([], {}), ([case(), case()], {}), ([case()], {"unknown": prediction()})):
            with self.assertRaises(ValueError): evaluate(cases, predictions)

    def test_macro_average_not_micro_average(self):
        _, metrics = evaluate([case(), case("q2", (1, 2, 3))], {"q1": prediction(), "q2": prediction()})
        self.assertAlmostEqual(metrics["page_recall"]["1"], (1 + 1/3) / 2)

    def test_hint_and_input_immutability(self):
        qa, pred = case(), prediction()
        qa["mode"] = "hint"
        before = deepcopy((qa, pred))
        rows, _ = self.score(qa, pred)
        self.assertEqual(rows[0]["mode"], "hint")
        self.assertEqual((qa, pred), before)

    def test_export_roundtrip_hash_and_private_field_whitelist(self):
        pred = prediction()
        pred["response"]["results"][0]["source"]["private_key"] = "secret"
        rows, metrics = self.score(pred=pred)
        with tempfile.TemporaryDirectory() as directory:
            report = export_report(directory, rows, metrics)
            path = Path(directory) / "retrieval_results.csv"
            self.assertEqual(report["results_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertNotIn("secret", path.read_text(encoding="utf-8"))
            with path.open(encoding="utf-8", newline="") as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual(json.loads(saved[0]["gold_sources"]), rows[0]["gold_sources"])
            self.assertEqual(json.loads((Path(directory) / "metrics.json").read_text())["total_qa"], 1)

    def test_pilot_source_mapping_valid_missing_out_of_range(self):
        mapping = {"sources": [{"course_code": "THMLN", "source_doc": "ch01.pdf", "course_id": COURSE,
                                "document_id": DOC, "version_id": VERSION, "page_count": 12}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qa.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["qa_id", "course_id", "question", "source_doc", "source_page"])
                writer.writeheader()
                for qid, doc, page in (("q1", "ch01.pdf", "1"), ("q2", "missing.pdf", "1"), ("q3", "ch01.pdf", "13")):
                    writer.writerow({"qa_id": qid, "course_id": "THMLN", "question": "Question", "source_doc": doc, "source_page": page})
            cases = load_pilot_csv(path, mapping)
            rows, metrics = evaluate(cases, {"q1": prediction()})
            self.assertEqual(metrics["scored_qa"], 1)
            self.assertEqual(metrics["invalid_label_qa"], 2)
            self.assertEqual(rows[0]["gold_sources"][0], source())

    def test_duplicate_snapshot_mapping_rejected(self):
        entry = {"course_code": "THMLN", "source_doc": "ch01.pdf", "course_id": COURSE,
                 "document_id": DOC, "version_id": VERSION, "page_count": 12}
        with self.assertRaises(ValueError): load_pilot_csv("unused.csv", {"sources": [entry, entry]})

    def test_alternative_evidence_groups_not_silently_merged(self):
        qa = case()
        qa["gold_source_groups"] = [[source(1)], [source(2)]]
        self.assertEqual(self.score(qa)[0][0]["status"], "INVALID_LABEL")

    def test_malformed_response_and_invalid_retrieved_page(self):
        for pred in ({}, {"response": []}, {"response": {"status": "OK", "results": None}}):
            rows, _ = evaluate([case()], {"q1": pred})
            self.assertEqual(rows[0]["status"], "RETRIEVAL_ERROR")
        pred = prediction()
        pred["response"]["results"][0]["source"]["page_number"] = True
        self.assertEqual(self.score(pred=pred)[0][0]["status"], "RETRIEVAL_ERROR")

    def test_too_many_results_rejected(self):
        rows, _ = self.score(pred=prediction(tuple(range(1, 12))))
        self.assertEqual(rows[0]["status"], "RETRIEVAL_ERROR")

    def test_missing_prediction_counts_reported(self):
        _, metrics = evaluate([case(), case("q2")], {"q1": prediction()})
        self.assertEqual(metrics["recorded_prediction_qa"], 1)
        self.assertEqual(metrics["missing_prediction_qa"], 1)


if __name__ == "__main__":
    unittest.main()
