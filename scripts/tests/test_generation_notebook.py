import contextlib
import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "notebooks/generation_setup.ipynb"


class GenerationNotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cls.cells = {cell["id"]: cell for cell in cls.notebook["cells"]}
        cls.namespace = {"json": json}
        with contextlib.redirect_stdout(io.StringIO()):
            exec("".join(cls.cells["smoke-cases"]["source"]), cls.namespace)
            exec("".join(cls.cells["checkpoint-tools"]["source"]), cls.namespace)
        cls.cases = cls.namespace["SMOKE_CASES"]

    def validate(self, payload, contexts=None):
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        return self.namespace["smoke_validate"](
            payload, self.cases[0]["contexts"] if contexts is None else contexts
        )

    def answered(self):
        return {"status": "ANSWERED", "answer": "Evidence [1]",
                "references": [{"label": 1, "source_id": "S1"}]}

    def test_baseline_and_startup_code_cells_compile_without_fake_outputs(self):
        codes = [cell for cell in self.notebook["cells"] if cell["cell_type"] == "code"]
        startup_ids = {"ohayo-independent-startup", "ohayo-dual-gpu-startup"}
        baseline_codes = [cell for cell in codes if cell["id"] not in startup_ids]
        self.assertEqual(len(baseline_codes), 18)
        self.assertEqual({cell["id"] for cell in codes} & startup_ids, startup_ids)
        self.assertEqual(len(codes), 20)
        for cell in codes:
            compile("".join(cell["source"]), cell["id"], "exec")
            self.assertIsNone(cell["execution_count"])
            self.assertEqual(cell["outputs"], [])
        self.assertEqual(len(self.cells), len(self.notebook["cells"]))

    def test_five_cases_cover_qa_hint_and_missing_evidence(self):
        self.assertEqual(len(self.cases), 5)
        self.assertEqual(len({case["case_id"] for case in self.cases}), 5)
        self.assertEqual(sum(case["mode"] == "hint" for case in self.cases), 1)
        self.assertEqual(sum(case["expected_status"] == "INSUFFICIENT_EVIDENCE"
                             for case in self.cases), 1)

    def test_optional_prompt_comparison_does_not_replace_full_baseline_or_load_qwen(self):
        code = "".join(self.cells["prompt-comparison"]["source"])
        self.assertIn("run_prompt_comparison", code)
        self.assertIn("prompt_version='efficient_grounded'", code)
        self.assertIn("prompt_version='frozen_baseline'", code)
        self.assertNotIn("from_pretrained", code)
        self.assertNotIn("max_new_tokens=", code)
        prefix = code.split("subprocess.run", 1)[0]
        with self.assertRaises(AssertionError):
            exec(prefix, {})
        import ast
        assignments = [node for node in ast.parse(code).body if isinstance(node, ast.Assign)]
        ids = next(ast.literal_eval(node.value) for node in assignments
                   if any(isinstance(t, ast.Name) and t.id == "comparison_ids" for t in node.targets))
        self.assertEqual(len(set(ids)), 6)
        self.assertIn("THMLN_QA_070", ids)

    def test_old_source_package_is_rejected_before_source_refresh_or_tests(self):
        import ast
        code = "".join(self.cells["provider-load"]["source"])
        assignments = [n for n in ast.parse(code).body if isinstance(n, ast.Assign)]
        required = next(ast.literal_eval(n.value) for n in assignments
                        if any(isinstance(t, ast.Name) and t.id == "REQUIRED_EVALUATION_FILES" for t in n.targets))
        self.assertIn("backend/apps/ai/tests/test_generation_evaluation.py", required)
        self.assertIn("backend/apps/ai/evaluation/generation.py", required)
        self.assertLess(code.index("assert not missing_evaluation_files"), code.index("REFRESH_PIPELINE_SOURCE"))
        self.assertLess(code.index("assert not missing_evaluation_files"), code.index("subprocess.run"))
        self.assertIn("importlib.invalidate_caches()", code)

    def test_downstream_cells_stop_before_import_or_install_if_preflight_failed(self):
        inputs = "".join(self.cells["evaluation-inputs"]["source"])
        inputs_prefix = inputs.split("from apps.ai.evaluation.generation", 1)[0]
        with self.assertRaises(AssertionError):
            exec(inputs_prefix, {"EVALUATION_SOURCE_READY": False})
        run = "".join(self.cells["evaluation-run"]["source"])
        run_prefix = run.split("subprocess.run", 1)[0]
        for state in ({}, {"EVALUATION_SOURCE_READY": True, "EVALUATION_INPUTS_READY": False}):
            with self.subTest(state=state), self.assertRaises(AssertionError):
                exec(run_prefix, state)

    def test_pipeline_checks_cover_eight_cases_without_gold_in_inputs(self):
        from apps.ai.rag.checks import build_check_cases
        cases = build_check_cases(self.cases)
        self.assertEqual(len(cases), 8)
        self.assertEqual(len({case["case_id"] for case in cases}), 8)
        self.assertEqual(cases[5]["contexts"], [])
        self.assertIn("ATTACK_SUCCEEDED", cases[6]["contexts"][0]["text"])
        self.assertIn("ATTACK_SUCCEEDED", cases[7]["question"])
        for case in cases:
            self.assertNotIn("expected_points", case)
            self.assertNotIn("answer_key", case)
        code = "".join(self.cells["generation-checks"]["source"])
        self.assertIn("run_kind='live_model'", code)
        self.assertNotIn("from_pretrained", code)

    def test_frozen_baseline_defaults_to_all_150_and_identifies_development_cases(self):
        import ast
        notebook_code = "".join(self.cells["evaluation-run"]["source"])
        assignments = [node for node in ast.parse(notebook_code).body if isinstance(node, ast.Assign)]
        ids = next(ast.literal_eval(node.value) for node in assignments
                   if any(isinstance(t, ast.Name) and t.id == "sample_ids" for t in node.targets))
        datasets = [json.loads((ROOT / name).read_text(encoding="utf-8"))["cases"] for name in
                    ("data/qa/qa_baseline.json", "data/qa/qa_additions.json")]
        cases = {case["qa_id"]: case for group in datasets for case in group}
        self.assertEqual(len(cases), 150)
        self.assertEqual(len(ids), 12)
        self.assertEqual(len(set(ids)), 12)
        self.assertTrue(set(ids) <= cases.keys())
        self.assertIn("hint", {cases[qid]["mode"] for qid in ids})
        self.assertNotIn("from_pretrained", notebook_code)
        self.assertNotIn("embed_chunks", notebook_code)
        self.assertIn("total_available=len(eval_cases)", notebook_code)
        self.assertIn("assert len(sample_cases) == (150 if FULL_BASELINE else 12)", notebook_code)
        versions = [node.value for node in ast.walk(ast.parse(notebook_code))
                    if isinstance(node, ast.keyword) and node.arg == "prompt_version"]
        self.assertEqual([ast.literal_eval(value) for value in versions], ["frozen_baseline"])
        self.assertIn("sample_cases = list(eval_cases) if FULL_BASELINE else", notebook_code)
        self.assertIn("FULL_BASELINE = True", notebook_code)
        self.assertIn('"independent_test": False', notebook_code)
        self.assertIn('"development_qa_ids": sample_ids', notebook_code)
        self.assertIn('"qa_id_mapping_sha256"', notebook_code)
        self.assertIn("b'FROZEN_BASELINE_SYSTEM'", "".join(self.cells["provider-load"]["source"]))
        self.assertNotIn("timeout_seconds=", notebook_code)
        self.assertTrue({"THMLN_QA_001", "THMLN_QA_006", "THMLN_QA_020", "KTCTMLN_QA_008",
                         "THMLN_QA_051", "THMLN_QA_003", "THMLN_QA_012"} <= set(ids))

    def test_excerpts_match_audit_and_original_pdf_checksums(self):
        with (ROOT / "data/qa/qa_source_audit.csv").open(encoding="utf-8-sig") as stream:
            audits = {row["qa_id"]: row for row in csv.DictReader(stream)}
        for case in self.cases:
            for source in case["contexts"]:
                audit_id = source["evidence_origin"].split("#")[-1]
                self.assertIn(source["text"], audits[audit_id]["evidence_excerpt"])
                self.assertTrue(source["text"].strip())
                self.assertEqual(source["excerpt_sha256"], hashlib.sha256(
                    source["text"].encode("utf-8")).hexdigest())
                self.assertEqual(source["pdf_sha256"], hashlib.sha256(
                    (ROOT / source["pdf_path"]).read_bytes()).hexdigest())
                self.assertIn(source["page_number"], json.loads(audits[audit_id]["source_pages"]))

    def test_expected_answers_and_review_metadata_not_in_prompt(self):
        case = {**self.cases[0], "expected_points": "SECRET_GOLD_123",
                "review_instruction": "SECRET_REVIEW_456"}
        messages = self.namespace["smoke_messages"](case)
        text = json.dumps(messages)
        self.assertNotIn("SECRET_GOLD_123", text)
        self.assertNotIn("SECRET_REVIEW_456", text)
        user = json.loads(messages[1]["content"])
        self.assertEqual(set(user), {"mode", "question", "contexts"})
        self.assertNotIn("pdf_path", user["contexts"][0])

    def test_valid_answer_and_fenced_json(self):
        expected = self.answered()
        self.assertEqual(self.validate(expected), expected)
        self.assertEqual(self.validate("```json\n" + json.dumps(expected) + "\n```"), expected)

    def test_live_missing_inline_citations_remain_rejected(self):
        for answer in [
            "Đối tượng nghiên cứu là các quan hệ xã hội của sản xuất và trao đổi.",
            "Chủ nghĩa duy vật lịch sử, học thuyết giá trị thặng dư và sứ mệnh giai cấp công nhân.",
        ]:
            payload = {"status": "ANSWERED", "answer": answer,
                       "references": [{"label": 1, "source_id": "S1"}]}
            with self.assertRaisesRegex(ValueError, "INVALID_INLINE_LABELS"):
                self.validate(payload)

    def test_live_split_json_objects_remain_rejected(self):
        raw = ('{"status":"ANSWERED","answer":"Kết luận [1]."},'
               '{"references":[{"label":1,"source_id":"S1"}]}')
        with self.assertRaises(json.JSONDecodeError):
            self.validate(raw)

    def test_hint_has_dedicated_no_final_answer_instructions(self):
        qa = self.namespace["smoke_messages"](self.cases[0])[0]["content"]
        hint_case = next(case for case in self.cases if case["mode"] == "hint")
        hint = self.namespace["smoke_messages"](hint_case)[0]["content"]
        self.assertNotEqual(qa, hint)
        self.assertIn("KHÔNG trả lời câu hỏi kiến thức thay người học", hint)
        self.assertIn("Không chép, diễn giải hoặc khẳng định mệnh đề đáp án", hint)
        self.assertNotIn("expected_points", hint)

    def test_same_source_reuse_and_supported_hint_status_are_explicit(self):
        system = self.namespace["SYSTEM_PROMPT"]
        self.assertIn("Đánh số theo NGUỒN", system)
        self.assertIn("tất cả đều dùng lại [1]", system)
        hint = self.namespace["MODE_RULES"]["hint"]
        self.assertIn("không đồng nghĩa thiếu căn cứ", hint)
        valid_reuse = {"status": "ANSWERED", "answer": "First [1]. Second [1].",
                       "references": [{"label": 1, "source_id": "S1"}]}
        self.assertEqual(self.validate(valid_reuse), valid_reuse)

    def test_live_hint_insufficient_status_with_citation_remains_rejected(self):
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_WITH_CITATIONS"):
            self.validate({
                "status": "INSUFFICIENT_EVIDENCE", "answer": "Gợi ý đọc đoạn nguồn [1].",
                "references": [{"label": 1, "source_id": "S1"}],
            })

    def test_plain_text_envelope_uses_only_existing_inline_citations(self):
        pack = self.namespace["smoke_pack"]
        raw = "Ý thứ nhất [1]. Ý thứ hai [1]."
        result = pack(raw, self.cases[0]["contexts"])
        self.assertEqual(result["answer"], raw)
        self.assertEqual(result["references"], [{"label": 1, "source_id": "S1"}])

    def test_plain_text_does_not_invent_missing_or_unknown_citations(self):
        pack = self.namespace["smoke_pack"]
        for raw in ["Câu trả lời thiếu nguồn.", "Nguồn giả [2].", ""]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                pack(raw, self.cases[0]["contexts"])
        with self.assertRaises(ValueError):
            pack("Nội dung [1].", [])

    def test_plain_text_abstention_is_explicit_not_guessed_from_gold(self):
        pack = self.namespace["smoke_pack"]
        result = pack("INSUFFICIENT_EVIDENCE", self.cases[0]["contexts"])
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["references"], [])
        for raw in ["INSUFFICIENT_EVIDENCE nhưng vẫn trả lời [1].", '{"status":"ANSWERED"}']:
            with self.assertRaises(ValueError):
                pack(raw, self.cases[0]["contexts"])

    def test_gpu_generation_path_has_no_cpu_token_filter(self):
        import ast

        code = "".join(self.cells["smoke-run"]["source"])
        calls = [node for node in ast.walk(ast.parse(code))
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and node.func.attr == "generate"]
        self.assertEqual(len(calls), 1)
        keywords = {keyword.arg: keyword.value for keyword in calls[0].keywords}
        self.assertIsNone(ast.literal_eval(keywords["prefix_allowed_tokens_fn"]))
        self.assertNotIn("lmformatenforcer", code)
        settings = "".join(self.cells["smoke-decoder"]["source"])
        self.assertIn("SMOKE_CASE_LIMIT = 1", settings)
        self.assertNotIn("pip", settings)
        self.assertNotIn("build_token_enforcer", code)

    def test_insufficient_evidence_has_no_citations(self):
        payload = {"status": "INSUFFICIENT_EVIDENCE", "answer": "Not enough evidence.",
                   "references": []}
        self.assertEqual(self.validate(payload), payload)
        payload["answer"] += " [1]"
        with self.assertRaises(ValueError):
            self.validate(payload)

    def test_foreign_source_or_removed_source_rejected(self):
        payload = self.answered()
        payload["references"][0]["source_id"] = "S2"
        with self.assertRaises(ValueError):
            self.validate(payload)
        with self.assertRaises(ValueError):
            self.validate(self.answered(), contexts=[])

    def test_labels_and_references_must_match(self):
        for answer, refs in [
            ("No label", [{"label": 1, "source_id": "S1"}]),
            ("Wrong [2]", [{"label": 2, "source_id": "S1"}]),
            ("Text [1]", []),
            ("Text [1]", [{"label": True, "source_id": "S1"}]),
        ]:
            with self.subTest(answer=answer, refs=refs), self.assertRaises(ValueError):
                self.validate({"status": "ANSWERED", "answer": answer, "references": refs})

    def test_duplicate_source_reference_rejected(self):
        with self.assertRaises(ValueError):
            self.validate({"status": "ANSWERED", "answer": "A [1] B [2]",
                           "references": [{"label": 1, "source_id": "S1"},
                                          {"label": 2, "source_id": "S1"}]})

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            self.validate('{"status":"ANSWERED","status":"INSUFFICIENT_EVIDENCE",'
                          '"answer":"No evidence","references":[]}')

    def test_malformed_schema_and_empty_output_rejected(self):
        for payload in ["", "not JSON", [], {**self.answered(), "invented": 1},
                        {**self.answered(), "status": "UNKNOWN"},
                        {**self.answered(), "answer": " "},
                        {**self.answered(), "references": "S1"}]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.validate(payload)

    def test_token_budget_exact_boundary_and_no_silent_truncation(self):
        class FakeTokenizer:
            def apply_chat_template(self, messages, **kwargs):
                return "fixture prompt"

            def __call__(self, prompt, **kwargs):
                if "truncation" in kwargs:
                    raise AssertionError("Unexpected truncation")
                return {"input_ids": SimpleNamespace(shape=(1, 100))}

        encode = self.namespace["smoke_encode"]
        self.assertEqual(encode(self.cases[0], FakeTokenizer(), 100)[2], 100)
        with self.assertRaisesRegex(ValueError, "INPUT_BUDGET_EXCEEDED"):
            encode(self.cases[0], FakeTokenizer(), 99)

    def test_runner_records_all_five_model_failures_without_claiming_success(self):
        class FakeBatch(dict):
            def to(self, device):
                return self

        def fail_generation(**kwargs):
            raise RuntimeError("simulated model failure, not a GPU test")

        cuda = SimpleNamespace(
            reset_peak_memory_stats=lambda gpu: None,
            synchronize=lambda gpu: None,
            max_memory_allocated=lambda gpu: 0,
            empty_cache=lambda: None,
        )
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "setup"
            out.mkdir()
            config_path = out / "model-config.json"
            config = {"model_id": "test-only", "revision": "a" * 40,
                      "context_budget_tokens": 4096, "max_input_tokens": 3584,
                      "max_new_tokens": 512}
            config_path.write_text(json.dumps(config), encoding="utf-8")
            namespace = {
                **self.namespace, "OUT": out, "time": time, "GPU": 0,
                "subprocess": subprocess, "sys": sys,
                "config": config, "config_path": config_path, "environment": {},
                "torch": SimpleNamespace(cuda=cuda, inference_mode=contextlib.nullcontext),
                "tokenizer": SimpleNamespace(eos_token_id=0),
                "model": SimpleNamespace(is_loaded_in_4bit=True, generate=fail_generation,
                                         config=SimpleNamespace(_commit_hash="a" * 40)),
                "smoke_encode": lambda case, tokenizer, limit: ([], FakeBatch(), 100),
                "SMOKE_CASE_LIMIT": 5, "SMOKE_MAX_NEW_TOKENS": 256,
                "SMOKE_MAX_TIME_SECONDS": 30.0,
            }
            with contextlib.redirect_stdout(io.StringIO()):
                exec("".join(self.cells["smoke-run"]["source"]), namespace)
            run = namespace["RUN"]
            rows = [json.loads(line) for line in
                    (run / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
            summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 5)
            self.assertTrue(all(row["status"] == "ERROR" for row in rows))
            self.assertTrue(all("simulated model failure" in row["error"]["message"]
                                for row in rows))
            self.assertEqual(summary["status"], "NEEDS_ATTENTION")
            self.assertFalse(summary["quality_verified"])
            self.assertFalse(summary["human_review_complete"])
            self.assertEqual(summary["expected_status_match_count"], 0)
            self.assertTrue((run / "review.csv").is_file())

    def make_checkpoint_fixture(self, folder):
        folder.mkdir()
        quant = {"quant_method": "bitsandbytes", "load_in_4bit": True,
                 "bnb_4bit_quant_type": "nf4", "bnb_4bit_use_double_quant": True,
                 "bnb_4bit_compute_dtype": "float16"}
        (folder / "config.json").write_text(json.dumps({"quantization_config": quant}))
        (folder / "tokenizer_config.json").write_text("{}")
        (folder / "tokenizer.json").write_text("{}")
        (folder / "model.safetensors").write_bytes(b"test fixture, not real model weights")
        self.write_checkpoint_manifest(folder)

    def write_checkpoint_manifest(self, folder):
        manifest = {"schema_version": 1, "model_id": "test-model",
                    "source_revision": "a" * 40, "files": {}}
        for path in folder.iterdir():
            if path.name != "checkpoint-manifest.json":
                manifest["files"][path.name] = {
                    "size_bytes": path.stat().st_size,
                    "sha256": self.namespace["checkpoint_sha256"](path),
                }
        (folder / "checkpoint-manifest.json").write_text(json.dumps(manifest))

    def test_checkpoint_manifest_and_checksum_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "checkpoint"
            self.make_checkpoint_fixture(folder)
            manifest = self.namespace["checkpoint_validate"](folder, "test-model", "a" * 40)
            self.assertEqual(manifest["schema_version"], 1)
            (folder / "model.safetensors").write_bytes(b"tampered bytes")
            with self.assertRaisesRegex(ValueError, "CHECKSUM_MISMATCH"):
                self.namespace["checkpoint_validate"](folder, "test-model", "a" * 40)

    def test_checkpoint_requires_expected_model_revision_and_all_files(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "checkpoint"
            self.make_checkpoint_fixture(folder)
            for model_id, revision in [("wrong-model", "a" * 40), ("test-model", "b" * 40)]:
                with self.assertRaisesRegex(ValueError, "MODEL_OR_REVISION_MISMATCH"):
                    self.namespace["checkpoint_validate"](folder, model_id, revision)
            (folder / "tokenizer.json").unlink()
            with self.assertRaisesRegex(ValueError, "FILE_SET_MISMATCH"):
                self.namespace["checkpoint_validate"](folder, "test-model", "a" * 40)

    def test_checkpoint_rejects_wrong_quantization_even_with_updated_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "checkpoint"
            self.make_checkpoint_fixture(folder)
            config = json.loads((folder / "config.json").read_text())
            config["quantization_config"]["bnb_4bit_quant_type"] = "fp4"
            (folder / "config.json").write_text(json.dumps(config))
            self.write_checkpoint_manifest(folder)
            with self.assertRaisesRegex(ValueError, "QUANTIZATION_MISMATCH"):
                self.namespace["checkpoint_validate"](folder, "test-model", "a" * 40)

    def test_checkpoint_rejects_missing_manifest_and_extra_files(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "checkpoint"
            self.make_checkpoint_fixture(folder)
            (folder / "unexpected.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "FILE_SET_MISMATCH"):
                self.namespace["checkpoint_validate"](folder, "test-model", "a" * 40)
            (folder / "checkpoint-manifest.json").unlink()
            with self.assertRaisesRegex(ValueError, "MANIFEST_MISSING"):
                self.namespace["checkpoint_validate"](folder, "test-model", "a" * 40)

    def test_local_load_branch_does_not_requantize_or_download(self):
        import ast

        code = "".join(self.cells["generation-09"]["source"])
        tree = ast.parse(code)
        try_block = next(node for node in tree.body if isinstance(node, ast.Try))
        branch = try_block.body[0]
        self.assertIsInstance(branch, ast.If)
        self.assertEqual(branch.test.id, "LOCAL_CHECKPOINT")
        calls = [node for root in branch.body for node in ast.walk(root)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and node.func.attr == "from_pretrained"]
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(call.args[0].id, "LOCAL_CHECKPOINT")
            keywords = {keyword.arg: keyword.value for keyword in call.keywords}
            self.assertTrue(ast.literal_eval(keywords["local_files_only"]))
            self.assertNotIn("quantization_config", keywords)
            self.assertNotIn("revision", keywords)


if __name__ == "__main__":
    unittest.main()
