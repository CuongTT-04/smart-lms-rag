import contextlib
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from apps.ai.providers import GenerationError, LocalModelProvider, ModelConfig
from apps.ai.providers.checkpoint import validate_checkpoint


class Tokens(list):
    @property
    def shape(self):
        return (len(self),)


class Batch(dict):
    def __init__(self, count):
        super().__init__(input_ids=SimpleNamespace(shape=(1, count)))
        self.device = None

    def to(self, device):
        self.device = device
        return self


class Output:
    def __init__(self, tokens):
        self.tokens = Tokens(tokens)

    def __getitem__(self, key):
        return self.tokens


class GenerationProviderTests(unittest.TestCase):
    def setUp(self):
        self.config = ModelConfig(max_input_tokens=8, max_new_tokens=8, context_tokens=16)
        self.provider = LocalModelProvider(self.config)
        self.messages = [{"role": "system", "content": "Use sources."},
                         {"role": "user", "content": "Question?"}]
        self.model = MagicMock()
        self.model.config = SimpleNamespace(
            _commit_hash=self.config.revision, _name_or_path=self.config.model_id,
            quantization_config={"bnb_4bit_quant_type": "nf4",
                                 "bnb_4bit_use_double_quant": True,
                                 "bnb_4bit_compute_dtype": "float16"},
        )
        self.model.is_loaded_in_4bit = True
        self.model.parameters.return_value = [SimpleNamespace(device="cuda:0")]
        self.model.generation_config = SimpleNamespace(eos_token_id=[2, 3])
        self.model.generate.return_value = Output([7, 2])
        self.tokenizer = MagicMock()
        self.tokenizer.apply_chat_template.return_value = "formatted prompt"
        self.tokenizer.return_value = Batch(4)
        self.tokenizer.decode.return_value = "Answer [1]."
        self.tokenizer.eos_token_id = 2
        self.torch = SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 2,
                                 synchronize=MagicMock()),
            inference_mode=contextlib.nullcontext, float16="float16",
        )
        self.runtime = (self.model, self.tokenizer, self.torch)
        self.loader = patch.object(self.provider, "_build_runtime", return_value=self.runtime)
        self.build = self.loader.start()
        self.addCleanup(self.loader.stop)

    def assert_error(self, code, call):
        with self.assertRaises(GenerationError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_shorter_retry_deadline_is_passed_to_model_without_changing_config(self):
        result=self.provider.generate(self.messages,timeout_seconds=5)
        self.assertEqual(self.model.generate.call_args.kwargs['max_time'],5)
        self.assertEqual(result.config_hash,self.config.fingerprint())
        for invalid in [0,-1,31,True,float('nan')]:
            self.assert_error('INVALID_INPUT',lambda:self.provider.generate(self.messages,timeout_seconds=invalid))

    def test_structured_generation_passes_token_constraint_to_transformers(self):
        import sys
        schema={'type':'object','properties':{'items':{'type':'array'}},'required':['items']}
        parser=MagicMock();prefix=MagicMock()
        self.tokenizer.decode.return_value='{"items":[]}'
        modules={'lmformatenforcer':SimpleNamespace(JsonSchemaParser=parser,CharacterLevelParserConfig=MagicMock()),
                 'lmformatenforcer.tokenenforcer':SimpleNamespace(TokenEnforcerTokenizerData=MagicMock()),
                 'lmformatenforcer.integrations.transformers':SimpleNamespace(build_transformers_prefix_allowed_tokens_fn=MagicMock(return_value=prefix),build_token_enforcer_tokenizer_data=MagicMock())}
        with patch.dict(sys.modules,modules):
            self.provider.generate(self.messages,json_schema=schema)
        self.assertEqual(parser.call_args.args,(schema,))
        self.assertIn('config',parser.call_args.kwargs)
        self.assertTrue(callable(self.model.generate.call_args.kwargs['prefix_allowed_tokens_fn']))
        self.assertEqual(self.model.generate.call_args.kwargs['eos_token_id'],2)
        self.assertIsNone(self.model.generate.call_args.kwargs['forced_eos_token_id'])

    def test_schema_parser_initializes_with_the_real_tokenizer_alphabet(self):
        # A non-ASCII quote shorter than minLength used to empty the parser stack.
        schema={'type':'object'}
        data=SimpleNamespace(tokenizer_alphabet='abcKhối số học và logic')
        self.provider._format_tokenizer_data=(self.tokenizer,data,'json-control-safe-v1')
        self.tokenizer.decode.return_value='{"items":[]}'
        parser=MagicMock(); parser_config=MagicMock()
        config_factory=MagicMock(return_value=parser_config)
        modules={'lmformatenforcer':SimpleNamespace(JsonSchemaParser=parser,CharacterLevelParserConfig=config_factory),
                 'lmformatenforcer.integrations.transformers':SimpleNamespace(
                     build_transformers_prefix_allowed_tokens_fn=MagicMock(),build_token_enforcer_tokenizer_data=MagicMock())}
        with patch.dict(sys.modules,modules):
            self.provider.generate(self.messages,json_schema=schema)
        config_factory.assert_called_once_with(alphabet=data.tokenizer_alphabet)
        parser.assert_called_once_with(schema,config=parser_config)

    def test_eos_with_unclosed_structured_json_is_not_a_completed_answer(self):
        modules={'lmformatenforcer':SimpleNamespace(JsonSchemaParser=MagicMock(),CharacterLevelParserConfig=MagicMock()),
                 'lmformatenforcer.tokenenforcer':SimpleNamespace(TokenEnforcerTokenizerData=MagicMock()),
                 'lmformatenforcer.integrations.transformers':SimpleNamespace(build_transformers_prefix_allowed_tokens_fn=MagicMock(),build_token_enforcer_tokenizer_data=MagicMock())}
        self.tokenizer.decode.return_value='{"items":[{"text":"ALU","source":1,"quote":"Khoi'
        with patch.dict(sys.modules,modules):
            self.assert_error('INCOMPLETE_GENERATION',lambda:self.provider.generate(self.messages,json_schema={'type':'object'}))

    def test_json_tokenizer_adapter_removes_raw_controls_but_preserves_escaped_text(self):
        from apps.ai.providers.local import _control_safe_tokenizer_data
        raw=SimpleNamespace(regular_tokens=[(1,'ALU',False),(197,'\t',False),(198,'\n',False),(3,'x\ry',False),(4,'\\n',False)],
                            decoder=lambda ids:'',eos_token_id=2,use_bitmask=False,vocab_size=200)
        constructor=lambda tokens,decoder,eos,bitmask,vocab:SimpleNamespace(regular_tokens=tokens,decoder=decoder,eos_token_id=eos,use_bitmask=bitmask,vocab_size=vocab)
        with patch.dict(sys.modules,{'lmformatenforcer.tokenenforcer':SimpleNamespace(TokenEnforcerTokenizerData=constructor)}):
            safe=_control_safe_tokenizer_data(raw)
        self.assertEqual([row[0] for row in safe.regular_tokens],[1,4])
        self.assertEqual(safe.eos_token_id,2)

    def test_schema_backend_cannot_force_eos_before_json_is_complete(self):
        from apps.ai.providers.local import _complete_json_eos_guard
        tokenizer=SimpleNamespace(decode=lambda *args,**kwargs:'{"items":[')
        guard=_complete_json_eos_guard(lambda batch,seq:[2],tokenizer,1,[2,3])
        self.assert_error('INCOMPLETE_GENERATION',lambda:guard(0,[9,7]))
        guard=_complete_json_eos_guard(lambda batch,seq:[2,7],tokenizer,1,[2,3])
        self.assertEqual(guard(0,[9,7]),[7])

    def test_lazy_load_once_and_reuse(self):
        self.assertFalse(self.provider.runtime_info()["model_loaded"])
        self.build.assert_not_called()
        first = self.provider.generate(self.messages)
        second = self.provider.generate(self.messages)
        self.assertEqual(first.text, "Answer [1].")
        self.assertEqual(first.usage.input_tokens, 4)
        self.assertEqual(first.usage.output_tokens, 2)
        self.assertEqual(first.finish_reason, "eos")
        self.assertEqual(first.revision, self.config.revision)
        self.assertEqual(first.config_hash, self.config.fingerprint())
        self.assertEqual(second.load_seconds, 0)
        self.build.assert_called_once()
        self.assertEqual(self.provider.runtime_info()["load_count"], 1)

    def test_invalid_input_does_not_load_model(self):
        invalid = [None, "hello", [], [{"role": "user", "content": " "}],
                   [{"role": "tool", "content": "x"}], [{"role": "user"}],
                   [{"role": "assistant", "content": "x"}],
                   [{"role": "user", "content": "x", "hidden": True}],
                   [{"role": "user", "content": "x"}, {"role": "system", "content": "y"}]]
        for messages in invalid:
            with self.subTest(messages=messages):
                self.assert_error("INVALID_INPUT", lambda: self.provider.generate(messages))
        self.build.assert_not_called()

    def test_invalid_output_override_does_not_load(self):
        for limit in [0, -1, True, 1.5, 9]:
            self.assert_error("INVALID_INPUT", lambda: self.provider.generate(self.messages, max_new_tokens=limit))
        self.build.assert_not_called()

    def test_chat_template_token_budget_and_no_truncation(self):
        self.tokenizer.return_value = Batch(8)
        self.assertEqual(self.provider.count_tokens(self.messages), 8)
        self.provider.generate(self.messages)
        self.tokenizer.apply_chat_template.assert_called_with(
            self.messages, tokenize=False, add_generation_prompt=True,
        )
        self.assertIs(self.tokenizer.call_args.kwargs["truncation"], False)
        self.tokenizer.return_value = Batch(9)
        before = self.model.generate.call_count
        self.assert_error("TOKEN_LIMIT_EXCEEDED", lambda: self.provider.generate(self.messages))
        self.assertEqual(before, self.model.generate.call_count)

    def test_inference_settings_and_output_override(self):
        self.provider.generate(self.messages, max_new_tokens=4)
        settings = self.model.generate.call_args.kwargs
        self.assertEqual(settings["max_new_tokens"], 4)
        self.assertEqual(settings["max_time"], 30)
        self.assertFalse(settings["do_sample"])
        self.assertIsNone(settings["prefix_allowed_tokens_fn"])
        for name in ["temperature", "top_p", "top_k"]:
            self.assertIsNone(settings[name])
        self.assertEqual(self.tokenizer.return_value.device, "cuda:0")

    def test_tokenization_failure_is_not_generation_or_no_evidence(self):
        self.tokenizer.side_effect = RuntimeError("private prompt must not appear in public error")
        error = self.assert_error("TOKENIZATION_FAILED", lambda: self.provider.generate(self.messages))
        self.assertNotIn("private prompt", str(error))
        self.model.generate.assert_not_called()

    def test_loading_failure_is_retryable(self):
        self.build.side_effect = [GenerationError("MODEL_LOAD_FAILED", "Load failed"), self.runtime]
        self.assert_error("MODEL_LOAD_FAILED", lambda: self.provider.generate(self.messages))
        self.assertIsNone(self.provider._runtime)
        self.provider.generate(self.messages)
        self.assertEqual(self.build.call_count, 2)
        self.assertEqual(self.provider.runtime_info()["load_count"], 1)

    def test_inference_failure_has_safe_explicit_code(self):
        self.model.generate.side_effect = RuntimeError("private document text")
        error = self.assert_error("GENERATION_FAILED", lambda: self.provider.generate(self.messages))
        self.assertNotIn("private document", str(error))

    def test_oom_is_distinct(self):
        OutOfMemoryError = type("OutOfMemoryError", (RuntimeError,), {})
        self.model.generate.side_effect = OutOfMemoryError("CUDA")
        self.assert_error("OUT_OF_MEMORY", lambda: self.provider.generate(self.messages))

    def test_timeout_never_releases_partial_text(self):
        # start, load start, load end, generation start, generation end
        with patch("apps.ai.providers.local.perf_counter", side_effect=[0, 0, 0, 0, 31]):
            self.assert_error("GENERATION_TIMEOUT", lambda: self.provider.generate(self.messages))
        self.tokenizer.decode.assert_not_called()

    def test_output_limit_and_incomplete_generation_are_distinct(self):
        self.model.generate.return_value = Output([7] * 8)
        self.assert_error("OUTPUT_LIMIT_REACHED", lambda: self.provider.generate(self.messages))
        self.model.generate.return_value = Output([7])
        self.assert_error("INCOMPLETE_GENERATION", lambda: self.provider.generate(self.messages))
        self.tokenizer.decode.assert_not_called()

    def test_empty_tokens_or_decoded_text(self):
        self.model.generate.return_value = Output([])
        self.assert_error("EMPTY_OUTPUT", lambda: self.provider.generate(self.messages))
        self.model.generate.return_value = Output([2])
        self.tokenizer.decode.return_value = " "
        self.assert_error("EMPTY_OUTPUT", lambda: self.provider.generate(self.messages))

    def test_count_tokens_loads_once_but_does_not_generate(self):
        self.assertEqual(self.provider.count_tokens(self.messages), 4)
        self.assertEqual(self.provider.count_tokens(self.messages), 4)
        self.build.assert_called_once()
        self.model.generate.assert_not_called()

    def test_from_loaded_reuses_model_and_validates_revision(self):
        with patch.dict(sys.modules, {"torch": self.torch}):
            provider = LocalModelProvider.from_loaded(self.model, self.tokenizer, self.config)
            self.assertIs(provider._runtime[0], self.model)
            self.assertEqual(provider.runtime_info()["load_count"], 0)
            provider.generate(self.messages)
            self.model.config._commit_hash = "b" * 40
            self.assert_error("INVALID_RUNTIME", lambda: LocalModelProvider.from_loaded(
                self.model, self.tokenizer, self.config,
            ))

    def test_runtime_requires_expected_gpu_and_nf4(self):
        for change in ["gpu", "quant", "four_bit", "cuda"]:
            with self.subTest(change=change):
                if change == "gpu":
                    self.model.parameters.return_value = [SimpleNamespace(device="cpu")]
                elif change == "quant":
                    self.model.parameters.return_value = [SimpleNamespace(device="cuda:0")]
                    self.model.config.quantization_config["bnb_4bit_quant_type"] = "fp4"
                elif change == "four_bit":
                    self.model.config.quantization_config["bnb_4bit_quant_type"] = "nf4"
                    self.model.is_loaded_in_4bit = False
                else:
                    self.model.is_loaded_in_4bit = True
                    self.torch.cuda.is_available = lambda: False
                expected = "CUDA_UNAVAILABLE" if change == "cuda" else "INVALID_RUNTIME"
                self.assert_error(expected, lambda: self.provider._check_runtime(
                    self.model, self.tokenizer, self.torch, check_identity=True,
                ))

    def test_calls_on_one_provider_are_serialized(self):
        active = peak = 0
        errors = []
        gate = threading.Lock()

        def generate(**kwargs):
            nonlocal active, peak
            with gate:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            with gate:
                active -= 1
            return Output([7, 2])

        def call():
            try:
                self.provider.generate(self.messages)
            except Exception as exc:
                errors.append(exc)

        self.model.generate.side_effect = generate
        threads = [threading.Thread(target=call) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(peak, 1)
        self.build.assert_called_once()

    def transformers_module(self):
        return SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=MagicMock(return_value=self.tokenizer)),
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=MagicMock(return_value=self.model)),
            BitsAndBytesConfig=MagicMock(side_effect=lambda **kwargs: kwargs),
        )

    def test_loader_pins_revision_and_preserves_offline_default(self):
        transformers = self.transformers_module()
        with patch.dict(sys.modules, {"torch": self.torch, "transformers": transformers}):
            runtime = LocalModelProvider(self.config)._build_runtime()
        self.assertIs(runtime[0], self.model)
        kwargs = transformers.AutoModelForCausalLM.from_pretrained.call_args.kwargs
        self.assertEqual(kwargs["revision"], self.config.revision)
        self.assertIs(kwargs["local_files_only"], True)
        self.assertIs(kwargs["trust_remote_code"], False)
        self.assertEqual(kwargs["quantization_config"]["bnb_4bit_quant_type"], "nf4")

    def test_local_loader_validates_checkpoint_and_never_requantizes(self):
        transformers = self.transformers_module()
        config = replace(self.config, checkpoint_path="/trusted/checkpoint", local_files_only=False)
        with patch.dict(sys.modules, {"torch": self.torch, "transformers": transformers}), \
                patch("apps.ai.providers.local.validate_checkpoint") as validate:
            LocalModelProvider(config)._build_runtime()
        validate.assert_called_once_with(config)
        kwargs = transformers.AutoModelForCausalLM.from_pretrained.call_args.kwargs
        self.assertIs(kwargs["local_files_only"], True)
        self.assertNotIn("quantization_config", kwargs)
        transformers.BitsAndBytesConfig.assert_not_called()

    def test_invalid_local_checkpoint_does_not_fallback_to_network(self):
        transformers = self.transformers_module()
        config = replace(self.config, checkpoint_path="/invalid/checkpoint")
        with patch.dict(sys.modules, {"torch": self.torch, "transformers": transformers}), \
                patch("apps.ai.providers.local.validate_checkpoint",
                      side_effect=GenerationError("CHECKPOINT_INVALID", "Invalid")):
            self.assert_error("CHECKPOINT_INVALID", lambda: LocalModelProvider(config)._build_runtime())
        transformers.AutoTokenizer.from_pretrained.assert_not_called()
        transformers.AutoModelForCausalLM.from_pretrained.assert_not_called()


class ModelConfigTests(unittest.TestCase):
    def test_validation_and_fingerprint(self):
        config = ModelConfig()
        self.assertEqual(config.fingerprint(), ModelConfig(**asdict(config)).fingerprint())
        self.assertNotEqual(config.fingerprint(), replace(config, max_new_tokens=128).fingerprint())
        for kwargs in [{"model_id": "other"}, {"revision": "main"}, {"device": "cpu"},
                       {"max_new_tokens": True}, {"max_new_tokens": 0}, {"context_tokens": 10},
                       {"timeout_seconds": float("inf")}, {"timeout_seconds": float("nan")},
                       {"timeout_seconds": True}, {"local_files_only": 1}, {"checkpoint_path": ""}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ModelConfig(**kwargs)

    def test_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(json.dumps(asdict(ModelConfig())), encoding="utf-8")
            self.assertEqual(ModelConfig.from_file(path), ModelConfig())


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_missing_and_integrity_without_model_loading(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = ModelConfig(checkpoint_path=str(root))
            with self.assertRaises(GenerationError) as missing:
                validate_checkpoint(config)
            self.assertEqual(missing.exception.code, "CHECKPOINT_INVALID")
            quant = {"quant_method": "bitsandbytes", "load_in_4bit": True,
                     "bnb_4bit_quant_type": "nf4", "bnb_4bit_use_double_quant": True,
                     "bnb_4bit_compute_dtype": "float16"}
            (root / "config.json").write_text(json.dumps({"quantization_config": quant}))
            (root / "tokenizer_config.json").write_text("{}")
            (root / "tokenizer.json").write_text("{}")
            (root / "model.safetensors").write_bytes(b"fixture, not model weights")
            manifest = {"schema_version": 1, "model_id": config.model_id,
                        "source_revision": config.revision, "files": {}}
            for path in root.iterdir():
                manifest["files"][path.name] = {"size_bytes": path.stat().st_size,
                                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            (root / "checkpoint-manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(validate_checkpoint(config)["source_revision"], config.revision)
            (root / "model.safetensors").write_bytes(b"changed")
            with self.assertRaises(GenerationError):
                validate_checkpoint(config)


if __name__ == "__main__":
    unittest.main()
