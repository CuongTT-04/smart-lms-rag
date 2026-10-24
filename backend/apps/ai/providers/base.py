"""Provider contracts; no Django, torch or model downloads at import time."""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re


class GenerationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelConfig:
    model_id: str = "Qwen/Qwen2.5-7B-Instruct"
    revision: str = "a09a35458c702b33eeacc393d103063234e8bc28"
    device: str = "cuda:0"
    checkpoint_path: str | None = None
    cache_dir: str | None = None
    local_files_only: bool = True
    context_tokens: int = 4096
    max_input_tokens: int = 3584
    max_new_tokens: int = 256
    timeout_seconds: float = 30.0

    def __post_init__(self):
        if self.model_id != "Qwen/Qwen2.5-7B-Instruct":
            raise ValueError("Only the verified Qwen2.5-7B-Instruct model is supported.")
        if not isinstance(self.revision, str) or not re.fullmatch(r"[0-9a-f]{40}", self.revision):
            raise ValueError("A pinned model revision is required.")
        if not isinstance(self.device, str) or not re.fullmatch(r"cuda:\d+", self.device):
            raise ValueError("This NF4 provider requires an explicit CUDA device.")
        for name in ("checkpoint_path", "cache_dir"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a nonblank path string or None.")
        if type(self.local_files_only) is not bool:
            raise ValueError("local_files_only must be boolean.")
        for name in ("context_tokens", "max_input_tokens", "max_new_tokens"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if self.context_tokens > 32768:
            raise ValueError("Context exceeds the supported model configuration.")
        if self.max_input_tokens + self.max_new_tokens > self.context_tokens:
            raise ValueError("Input and output budgets must fit the total context.")
        if (type(self.timeout_seconds) not in (int, float)
                or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0):
            raise ValueError("Timeout must be finite and positive.")

    @classmethod
    def from_file(cls, path: str | Path):
        with Path(path).open(encoding="utf-8") as stream:
            return cls(**json.load(stream))

    def fingerprint(self):
        data = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ModelOutput:
    text: str
    usage: TokenUsage
    finish_reason: str
    model_id: str
    revision: str
    config_hash: str
    load_seconds: float
    generation_seconds: float
    elapsed_seconds: float
