"""Single-instance NF4 inference, without retrieval, citations or database access."""

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import platform
from threading import Lock
from time import perf_counter

from .base import GenerationError, ModelConfig, ModelOutput, TokenUsage
from .checkpoint import validate_checkpoint


class LocalModelProvider:
    """Keep one provider per worker; calls on that instance are serialized.

    timeout_seconds covers generate, not model loading or waiting for the lock.
    It is a soft deadline: an in-flight CUDA operation cannot be interrupted here.
    """

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig()
        self._runtime = None
        self._lock = Lock()
        self._load_count = 0
        self._borrowed_runtime = False

    @classmethod
    def from_loaded(cls, model, tokenizer, config: ModelConfig | None = None):
        """Attach a notebook model without allocating a second copy."""
        provider = cls(config)
        try:
            import torch

            provider._check_runtime(model, tokenizer, torch, check_identity=True)
            model.eval()
            provider._runtime = (model, tokenizer, torch)
            provider._borrowed_runtime = True
        except GenerationError:
            raise
        except Exception as exc:
            raise GenerationError("INVALID_RUNTIME", "Cannot attach the supplied model.") from exc
        return provider

    def _check_runtime(self, model, tokenizer, torch, *, check_identity):
        device_index = int(self.config.device.split(":")[1])
        if not torch.cuda.is_available() or device_index >= torch.cuda.device_count():
            raise GenerationError("CUDA_UNAVAILABLE", "The configured CUDA device is unavailable.")
        if not callable(getattr(tokenizer, "apply_chat_template", None)):
            raise GenerationError("INVALID_RUNTIME", "Tokenizer has no chat template API.")
        if not getattr(model, "is_loaded_in_4bit", False):
            raise GenerationError("INVALID_RUNTIME", "The model must be loaded in NF4.")
        quant = getattr(model.config, "quantization_config", None)
        quant = quant if isinstance(quant, dict) else getattr(quant, "to_dict", lambda: {})()
        if (quant.get("bnb_4bit_quant_type") != "nf4"
                or quant.get("bnb_4bit_use_double_quant") is not True
                or str(quant.get("bnb_4bit_compute_dtype")) not in ("float16", "torch.float16")):
            raise GenerationError("INVALID_RUNTIME", "Quantization differs from the verified configuration.")
        parameters = list(model.parameters())
        if not parameters or any(str(parameter.device) != self.config.device for parameter in parameters):
            raise GenerationError("INVALID_RUNTIME", "All model weights must be on the configured GPU.")
        if check_identity:
            revision = getattr(model.config, "_commit_hash", None)
            if self.config.checkpoint_path:
                validate_checkpoint(self.config)
                model_path = getattr(model.config, "_name_or_path", "")
                if Path(model_path).resolve() != Path(self.config.checkpoint_path).resolve():
                    raise GenerationError("INVALID_RUNTIME", "Attached model path differs from the checkpoint.")
            elif (revision != self.config.revision
                  or getattr(model.config, "_name_or_path", None) != self.config.model_id):
                raise GenerationError("INVALID_RUNTIME", "Attached model identity or revision differs.")

    def _build_runtime(self):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            index = int(self.config.device.split(":")[1])
            if not torch.cuda.is_available() or index >= torch.cuda.device_count():
                raise GenerationError("CUDA_UNAVAILABLE", "The configured CUDA device is unavailable.")
            if self.config.checkpoint_path:
                validate_checkpoint(self.config)
                source = self.config.checkpoint_path
                kwargs = {"local_files_only": True, "trust_remote_code": False}
                tokenizer = AutoTokenizer.from_pretrained(source, **kwargs)
                model = AutoModelForCausalLM.from_pretrained(
                    source, **kwargs, dtype=torch.float16, device_map={"": index},
                )
            else:
                source = self.config.model_id
                kwargs = {
                    "revision": self.config.revision,
                    "local_files_only": self.config.local_files_only,
                    "trust_remote_code": False,
                    "cache_dir": self.config.cache_dir,
                }
                tokenizer = AutoTokenizer.from_pretrained(source, **kwargs)
                model = AutoModelForCausalLM.from_pretrained(
                    source, **kwargs, dtype=torch.float16, device_map={"": index},
                    quantization_config=BitsAndBytesConfig(
                        load_in_4bit=True, bnb_4bit_quant_type="nf4",
                        bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16,
                    ),
                )
            self._check_runtime(model, tokenizer, torch, check_identity=False)
            model.eval()
            return model, tokenizer, torch
        except GenerationError:
            raise
        except Exception as exc:
            if type(exc).__name__ in ("OutOfMemoryError", "CudaOutOfMemoryError"):
                raise GenerationError("OUT_OF_MEMORY", "Insufficient GPU memory to load the model.") from exc
            raise GenerationError("MODEL_LOAD_FAILED", "Cannot load the configured generation model.") from exc

    def _ensure_runtime(self):
        if self._runtime is None:
            self._runtime = self._build_runtime()
            self._load_count += 1
        return self._runtime

    @staticmethod
    def _messages(messages):
        if isinstance(messages, (str, bytes)) or not isinstance(messages, Sequence) or not messages:
            raise GenerationError("INVALID_INPUT", "Messages must be a nonempty sequence.")
        result = []
        for index, message in enumerate(messages):
            if not isinstance(message, Mapping) or set(message) != {"role", "content"}:
                raise GenerationError("INVALID_INPUT", "Each message needs only role and content.")
            role, content = message["role"], message["content"]
            if (role not in ("system", "user", "assistant")
                    or (role == "system" and index != 0)
                    or not isinstance(content, str) or not content.strip()):
                raise GenerationError("INVALID_INPUT", "Invalid message role or blank content.")
            result.append({"role": role, "content": content})
        if result[-1]["role"] != "user":
            raise GenerationError("INVALID_INPUT", "The final message must be from the user.")
        return result

    def _encode(self, tokenizer, messages, output_limit):
        try:
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            encoded = tokenizer(prompt, add_special_tokens=False, truncation=False, return_tensors="pt")
            count = int(encoded["input_ids"].shape[-1])
        except Exception as exc:
            raise GenerationError("TOKENIZATION_FAILED", "Cannot tokenize the generation prompt.") from exc
        if count < 1:
            raise GenerationError("INVALID_INPUT", "Tokenized prompt is empty.")
        if count > self.config.max_input_tokens or count + output_limit > self.config.context_tokens:
            raise GenerationError("TOKEN_LIMIT_EXCEEDED", "Prompt exceeds the input/context budget; it was not truncated.")
        return encoded, count

    def count_tokens(self, messages):
        messages = self._messages(messages)
        with self._lock:
            _, tokenizer, _ = self._ensure_runtime()
            return self._encode(tokenizer, messages, self.config.max_new_tokens)[1]

    def generate(self, messages, *, max_new_tokens: int | None = None) -> ModelOutput:
        messages = self._messages(messages)
        limit = self.config.max_new_tokens if max_new_tokens is None else max_new_tokens
        if type(limit) is not int or not 1 <= limit <= self.config.max_new_tokens:
            raise GenerationError("INVALID_INPUT", "Output limit must be positive and cannot exceed provider config.")
        started = perf_counter()
        with self._lock:
            loading_started = perf_counter()
            cold = self._runtime is None
            model, tokenizer, torch = self._ensure_runtime()
            load_seconds = perf_counter() - loading_started if cold else 0.0
            encoded, count = self._encode(tokenizer, messages, limit)
            inputs = outputs = tokens = None
            try:
                inputs = encoded.to(self.config.device)
                torch.cuda.synchronize(self.config.device)
                generation_started = perf_counter()
                with torch.inference_mode():
                    outputs = model.generate(
                        **inputs, max_new_tokens=limit, do_sample=False,
                        temperature=None, top_p=None, top_k=None,
                        max_time=self.config.timeout_seconds, use_cache=True,
                        prefix_allowed_tokens_fn=None, pad_token_id=tokenizer.eos_token_id,
                    )
                torch.cuda.synchronize(self.config.device)
                seconds = perf_counter() - generation_started
                if seconds >= self.config.timeout_seconds:
                    raise GenerationError("GENERATION_TIMEOUT", "Generation exceeded its soft deadline.")
                tokens = outputs[0, count:]
                output_count = int(tokens.shape[0])
                eos = model.generation_config.eos_token_id
                eos = eos if isinstance(eos, (list, tuple)) else [eos]
                if output_count < 1:
                    raise GenerationError("EMPTY_OUTPUT", "The model returned no tokens.")
                if int(tokens[-1]) not in eos:
                    code = "OUTPUT_LIMIT_REACHED" if output_count >= limit else "INCOMPLETE_GENERATION"
                    raise GenerationError(code, "Generation did not finish; partial text was not released.")
                text = tokenizer.decode(tokens, skip_special_tokens=True).strip()
                if not text:
                    raise GenerationError("EMPTY_OUTPUT", "The model returned no text.")
                return ModelOutput(
                    text=text, usage=TokenUsage(count, output_count), finish_reason="eos",
                    model_id=self.config.model_id, revision=self.config.revision,
                    config_hash=self.config.fingerprint(), load_seconds=load_seconds,
                    generation_seconds=seconds, elapsed_seconds=perf_counter() - started,
                )
            except GenerationError:
                raise
            except Exception as exc:
                if type(exc).__name__ in ("OutOfMemoryError", "CudaOutOfMemoryError"):
                    raise GenerationError("OUT_OF_MEMORY", "Insufficient GPU memory for generation.") from exc
                raise GenerationError("GENERATION_FAILED", "Model inference failed.") from exc
            finally:
                # Exceptions retain frame locals; do not retain request tensors with them.
                inputs = outputs = tokens = encoded = None

    def runtime_info(self):
        packages = {}
        for name in ("torch", "transformers", "accelerate", "bitsandbytes", "huggingface-hub"):
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                packages[name] = None
        return {
            "config": asdict(self.config), "config_hash": self.config.fingerprint(),
            "model_loaded": self._runtime is not None, "load_count": self._load_count,
            "borrowed_runtime": self._borrowed_runtime,
            "python": platform.python_version(), "packages": packages,
            "decoding_backend": "transformers_greedy_no_token_filter",
            "timeout_kind": "soft_generation_deadline_not_hard_process_timeout",
            "concurrency": "one_call_per_provider_instance",
        }
