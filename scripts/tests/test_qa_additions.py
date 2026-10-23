from copy import deepcopy
from collections import Counter
import csv
import json
from pathlib import Path
import unittest
import re

from scripts.check_qa_additions import check_additions, question_key


ROOT = Path(__file__).resolve().parents[2]


class QAAdditionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads((ROOT / "data/qa/qa_additions.json").read_text(encoding="utf-8"))
        cls.baseline = json.loads((ROOT / "data/qa/qa_baseline.json").read_text(encoding="utf-8"))
        cls.source_map = json.loads((ROOT / "data/qa/source_map.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.data = deepcopy(self.original)

    def check(self, **kwargs):
        return check_additions(self.data, self.baseline, self.source_map, ROOT / "data/corpus", **kwargs)

    def test_real_snapshot_50_cases_and_all_source_anchors(self):
        checked, report = self.check()
        self.assertEqual(checked, self.data)
        self.assertEqual(report["mode_counts"], {"qa": 40, "hint": 10})
        self.assertEqual(report["course_counts"], {"THMLN": 25, "KTCTMLN": 13, "CNXHKH": 12})
        self.assertEqual(report["verified_page_references"], 53)
        self.assertEqual(report["source_document_count"], 18)
        self.assertEqual(report["prospective_merged_count"], 150)
        self.assertFalse(report["human_peer_review_complete"])
        self.assertFalse(report["semantic_answer_correctness_proven"])
        self.assertFalse(report["database_source_mapping_verified"])

    def test_annotation_is_idempotent_and_does_not_mutate_input(self):
        before = deepcopy(self.data)
        annotated, _ = self.check(annotate=True)
        self.assertEqual(before, annotated)
        self.assertEqual(before, self.data)

    def test_duplicate_baseline_question_rejected_after_normalization(self):
        self.data["cases"][0]["question"] = self.baseline["cases"][0]["question"].upper() + " !!!"
        with self.assertRaisesRegex(ValueError, "Duplicate normalized"):
            self.check()

    def test_wrong_or_reused_id_rejected(self):
        self.data["cases"][0]["qa_id"] = "THMLN_QA_001"
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_record_or_wrong_mode_count_rejected(self):
        self.data["cases"].pop()
        with self.assertRaises(ValueError):
            self.check()
        self.data = deepcopy(self.original)
        self.data["cases"][-1]["mode"] = "qa"
        with self.assertRaises(ValueError):
            self.check()

    def test_out_of_range_or_boolean_page_rejected(self):
        for page in [0, 9999, True]:
            self.data = deepcopy(self.original)
            self.data["cases"][0]["source_pages"] = [page]
            with self.subTest(page=page), self.assertRaises(ValueError):
                self.check()

    def test_missing_anchor_or_fingerprint_rejected(self):
        self.data["cases"][0]["evidence"][0]["anchor"] = "NONEXISTENT_SOURCE_EVIDENCE_123"
        with self.assertRaisesRegex(ValueError, "anchor/term"):
            self.check()
        self.data = deepcopy(self.original)
        self.data["cases"][0]["evidence"][0]["page_text_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.check()

    def test_tampered_uuid_not_silently_replaced_by_annotation(self):
        self.data["cases"][0]["gold_sources"][0]["version_id"] = "00000000-0000-0000-0000-000000000000"
        with self.assertRaisesRegex(ValueError, "identity/scope"):
            self.check(annotate=True)

    def test_missing_hint_rubric_rejected(self):
        self.data["cases"][-1]["hint_policy"]["must_not_reveal"] = []
        with self.assertRaisesRegex(ValueError, "hint support"):
            self.check()

    def test_invented_reviewer_rejected(self):
        self.data["cases"][0]["review"]["reviewer"] = "Invented approval"
        with self.assertRaisesRegex(ValueError, "human review"):
            self.check()

    def test_offline_scope_cannot_claim_an_assessment_in_live_database(self):
        self.data["cases"][0]["scope"]["assessment_id"] = "fake-db-assessment"
        with self.assertRaisesRegex(ValueError, "identity/scope"):
            self.check()

    def test_wrong_pdf_checksum_rejected(self):
        sources = deepcopy(self.source_map)
        next(item for item in sources["sources"] if item["course_code"] == "THMLN"
             and item["source_doc"] == "ch01.pdf")["source_checksum"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum"):
            check_additions(self.data, self.baseline, sources, ROOT / "data/corpus")

    def test_question_key_handles_whitespace_case_and_punctuation(self):
        self.assertEqual(question_key("  VẬT CHẤT là gì?!"), question_key("Vật chất là gì"))

    def test_standard_ids_and_legacy_mapping_cover_same_baseline_questions(self):
        lookup = {source["course_id"]: source["course_code"] for source in self.source_map["sources"]}
        cases = self.baseline["cases"] + self.original["cases"]
        self.assertEqual(Counter(lookup[c["course_id"]] for c in cases),
                         {"THMLN": 74, "KTCTMLN": 44, "CNXHKH": 32})
        for case in cases:
            self.assertRegex(case["qa_id"], "^" + lookup[case["course_id"]] + r"_QA_[0-9]{3}$")
        with (ROOT / "data/qa/qa_id_mapping.csv").open(encoding="utf-8", newline="") as stream:
            mapping = list(csv.DictReader(stream))
        self.assertEqual(len(mapping), 25)
        self.assertEqual(len({r["old_qa_id"] for r in mapping}), 25)
        new_ids = {r["new_qa_id"] for r in mapping}
        self.assertEqual(len(new_ids), 25)
        self.assertTrue(new_ids <= {c["qa_id"] for c in self.baseline["cases"]})
        self.assertTrue(all(re.fullmatch(r"CUONG_W3_QA_[0-9]{3}", r["old_qa_id"]) for r in mapping))

    def test_final_25_are_distinct_course_drafts_not_fake_b_peer_review(self):
        cases = self.original["cases"][25:]
        self.assertEqual(Counter(c["course_code"] for c in cases), {"KTCTMLN": 13, "CNXHKH": 12})
        self.assertEqual(Counter(c["mode"] for c in cases), {"qa": 20, "hint": 5})
        for case in cases:
            self.assertEqual(case["review"]["author_member"], "A")
            self.assertEqual(case["review"]["status"], "pending_human_peer")
            self.assertIsNone(case["review"]["reviewer"])
            self.assertIsNone(case["review"]["reviewed_at"])


if __name__ == "__main__":
    unittest.main()
