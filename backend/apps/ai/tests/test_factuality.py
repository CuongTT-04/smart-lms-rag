import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from apps.ai.evaluation.factuality import RuleConfig, _csv_text, score_saved_run, screen_answer


class FactualityRuleTests(unittest.TestCase):
    def setUp(self):
        self.context = {"source_id": "S1", "document_id": "doc", "version_id": "version", "page_number": 2,
                        "text": "Mọi vật chất tồn tại khách quan độc lập với cảm giác con người."}
        self.case = {"qa_id": "Q1", "mode": "qa", "question": "Vật chất tồn tại thế nào?",
                     "ground_truth": "Vật chất tồn tại khách quan độc lập với cảm giác con người.",
                     "gold_sources": [{"document_id": "doc", "version_id": "version", "page_number": 2}]}
        self.row = {"qa_id": "Q1", "mode": "qa", "status": "ANSWERED", "error": None,
                    "answer": "Vật chất tồn tại khách quan độc lập với cảm giác con người [1].",
                    "references": [{"label": 1, "source_id": "S1"}], "used_contexts": [self.context],
                    "prompt_messages_internal": [{"role": "user", "content": json.dumps({"evidence": [self.context]})}]}

    def test_keyword_match_is_not_factuality_or_human_approval(self):
        result = screen_answer(self.case, self.row)
        self.assertEqual(result["rule_result"], "KEYWORD_COVERED")
        self.assertEqual(result["keyword_coverage"], 1)
        self.assertTrue(result["human_review_required"])
        self.assertFalse(result["factuality_verified"])

    def test_negated_answer_can_share_keywords_but_is_flagged(self):
        row = {**self.row, "answer": "Vật chất không tồn tại khách quan độc lập với cảm giác con người [1]."}
        result = screen_answer(self.case, row)
        self.assertEqual(result["keyword_coverage"], 1)
        self.assertIn("NEGATION_REVIEW", result["flags"])
        self.assertFalse(result["factuality_verified"])

    def test_expected_points_are_checked_individually(self):
        case = {**self.case, "expected_points": ["vật chất tồn tại khách quan", "nhận thức dựa vào thực tiễn"]}
        result = screen_answer(case, self.row)
        self.assertEqual(result["rule_result"], "LOW_KEYWORD_COVERAGE")
        self.assertEqual(len(result["keyword_checks"]), 2)
        self.assertIn("thực", result["keyword_checks"][1]["missing"])

    def test_boolean_label_is_leading_not_substring(self):
        case = {**self.case, "ground_truth": "False"}
        for answer, observed in (("Sai. Có căn cứ [1]", False), ("Đúng [1]", True),
                                 ("Nhận định này có từ sai [1]", None)):
            result = screen_answer(case, {**self.row, "answer": answer})
            self.assertEqual(result["observed_label"], {True: "true", False: "false", None: None}[observed])
            self.assertEqual(result["label_match"], observed is False if observed is not None else None)

    def test_choice_label_does_not_match_letter_inside_word_or_citation(self):
        case = {**self.case, "ground_truth": "B", "question": "Chọn? A) Một B) Hai"}
        result = screen_answer(case, {**self.row, "answer": "B) Hai [1]"})
        self.assertTrue(result["label_match"])
        for text in ("Bảo vệ [1]", "Một câu có chữ B [1]"):
            self.assertIsNone(screen_answer(case, {**self.row, "answer": text})["label_match"])
        result = screen_answer(case, {**self.row, "answer": "B) Một [1]"})
        self.assertTrue(result["label_match"])
        self.assertIn("CHOICE_TEXT_CONTRACT_REVIEW", result["flags"])
        self.assertFalse(result["factuality_verified"])

    def test_service_errors_are_retained_not_scored_from_internal_raw_output(self):
        row = {**self.row, "status": "ERROR", "answer": None,
               "model_output_internal": {"text": self.row["answer"]}, "error": {"code": "INVALID_GENERATION"}}
        result = screen_answer(self.case, row)
        self.assertEqual(result["rule_result"], "NO_VALID_ANSWER")
        self.assertIsNone(result["keyword_coverage"])
        self.assertEqual(result["original_error"], row["error"])

    def test_abstention_and_missing_reference_need_review(self):
        row = {**self.row, "status": "INSUFFICIENT_EVIDENCE", "references": []}
        self.assertEqual(screen_answer(self.case, row)["rule_result"], "ABSTENTION_REVIEW")
        self.assertIn("UNSUPPORTED_REFERENCE", screen_answer({**self.case, "ground_truth": None}, self.row)["flags"])

    def test_citation_page_hit_is_not_claim_support(self):
        row = {**self.row, "answer": "Công nghệ phát triển năng suất kinh tế quốc tế [1]."}
        result = screen_answer(self.case, row)
        self.assertTrue(result["citations"]["cited_gold_page_hit"])
        self.assertIn("LOW_CLAIM_SOURCE_OVERLAP", result["flags"])
        self.assertFalse(result["factuality_verified"])

    def test_citation_renumbering_uses_reference_source_identity(self):
        context = {**self.context, "source_id": "S2"}
        row = {**self.row, "references": [{"label": 1, "source_id": "S2"}], "used_contexts": [context],
               "prompt_messages_internal": [{"role": "user", "content": json.dumps({"evidence": [context]})}]}
        result = screen_answer(self.case, row)
        self.assertTrue(result["citations"]["structure_valid"])
        self.assertTrue(result["citations"]["cited_gold_page_hit"])
        result = screen_answer(self.case, {**row, "references": [{"label": 8, "source_id": "S2"}]})
        self.assertIn("INVALID_CITATION_STRUCTURE", result["flags"])

    def test_context_not_in_actual_prompt_is_flagged(self):
        row = {**self.row, "prompt_messages_internal": [{"content": '{"evidence":[]}'}]}
        result = screen_answer(self.case, row)
        self.assertFalse(result["citations"]["prompt_membership_verified"])
        self.assertIn("UNVERIFIED_PROMPT_MEMBERSHIP", result["flags"])
        row = {**self.row, "prompt_messages_internal": None}
        self.assertIsNone(screen_answer(self.case, row)["citations"]["prompt_membership_verified"])

    def test_uncited_tail_is_flag_not_silently_dropped(self):
        row = {**self.row, "answer": self.row["answer"] + " Thêm một khẳng định chưa dẫn nguồn."}
        self.assertIn("UNCITED_TAIL_REVIEW", screen_answer(self.case, row)["flags"])

    def test_hint_copy_flag_never_becomes_safe_hint_certification(self):
        case = {**self.case, "mode": "hint", "hint_policy": {"must_not_reveal": ["tồn tại khách quan"]}}
        row = {**self.row, "mode": "hint"}
        result = screen_answer(case, row)
        self.assertIn("POSSIBLE_HINT_LEAK", result["flags"])
        self.assertTrue(result["hint_checks"]["forbidden_phrase_matches"])
        result = screen_answer(case, {**row, "answer": "Hãy đọc đoạn nguồn rồi tự diễn đạt [1]."})
        self.assertNotIn("POSSIBLE_HINT_LEAK", result["flags"])
        self.assertTrue(result["human_review_required"])
        self.assertEqual(screen_answer({**case, "ground_truth": None}, row)["rule_result"], "HINT_REVIEW")

    def test_unicode_normalization_and_config_validation(self):
        import unicodedata
        self.assertEqual(screen_answer(self.case, self.row)["keyword_coverage"],
                         screen_answer(self.case, {**self.row, "answer": unicodedata.normalize("NFD", self.row["answer"])})["keyword_coverage"])
        for kwargs in ({"keyword_threshold": True}, {"keyword_threshold": float("nan")},
                       {"hint_copy_words": 2}, {"claim_overlap_threshold": 2}):
            with self.assertRaises(ValueError):
                RuleConfig(**kwargs)

    def make_run(self, directory, *, mismatch=False):
        directory.mkdir()
        dataset = json.dumps({"cases": [self.case]}, ensure_ascii=False).encode()
        row = {**self.row, "qa_id": "OTHER"} if mismatch else self.row
        predictions = (json.dumps(row, ensure_ascii=False) + "\n").encode()
        manifest = {"run_kind": "unit", "selected_count": 1, "selected_qa_ids": ["Q1"],
                    "output_sha256": {"dataset.json": hashlib.sha256(dataset).hexdigest(),
                                      "predictions.jsonl": hashlib.sha256(predictions).hexdigest()}}
        for name, data in (("dataset.json", dataset), ("predictions.jsonl", predictions),
                           ("run_manifest.json", json.dumps(manifest).encode()), ("scores.csv", b"UNTOUCHED HUMAN SCORES")):
            (directory / name).write_bytes(data)

    def test_saved_run_outputs_are_separate_and_denominators_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, output = root / "input", root / "output"
            self.make_run(run)
            before = {p.name: p.read_bytes() for p in run.iterdir()}
            result = score_saved_run(run, output)
            self.assertEqual(result["total_qa"], 1)
            self.assertEqual(result["model_calls"], 0)
            self.assertIsNone(result["factuality_accuracy"])
            self.assertEqual(result["human_review_required_count"], 1)
            self.assertEqual(result["citation_checks"]["answered_denominator"], 1)
            self.assertEqual(before, {p.name: p.read_bytes() for p in run.iterdir()})
            self.assertEqual({p.name for p in output.iterdir()}, {"rule_scores.jsonl", "rule_scores.csv", "rule_metrics.json"})
            with self.assertRaises(FileExistsError):
                score_saved_run(run, output)
            with self.assertRaises(ValueError):
                score_saved_run(run, run / "child")

    def test_checksum_or_id_mismatch_rejected_before_output(self):
        for mismatch in (False, True):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_run(root / "input", mismatch=mismatch)
                if not mismatch:
                    with (root / "input/predictions.jsonl").open("ab") as stream:
                        stream.write(b" ")
                with self.assertRaises(ValueError):
                    score_saved_run(root / "input", root / "output")
                self.assertFalse((root / "output").exists())

    def test_zip_reads_without_extraction_and_rejects_duplicate_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_run(root / "input")
            with zipfile.ZipFile(root / "run.zip", "w") as archive:
                for path in (root / "input").iterdir():
                    archive.write(path, "run/" + path.name)
            result = score_saved_run(root / "run.zip", root / "output")
            self.assertEqual(result["total_qa"], 1)
            self.assertIsNotNone(result["source_archive_sha256"])
            self.assertFalse((root / "run").exists())
            with zipfile.ZipFile(root / "run.zip", "a") as archive:
                archive.writestr("other/dataset.json", b"{}")
            with self.assertRaises(ValueError):
                score_saved_run(root / "run.zip", root / "bad")
            self.assertFalse((root / "bad").exists())

    def test_csv_formula_prefix_is_escaped(self):
        for text in ("=SUM(A1:A2)", " +1", "-2", "@cmd"):
            self.assertTrue(_csv_text(text).startswith("'"))
        self.assertEqual(_csv_text("Regular text"), "Regular text")


if __name__ == "__main__":
    unittest.main()
