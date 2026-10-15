"""Input/output contracts for dense BGE-M3 embeddings."""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re

import numpy as np


class EmbeddingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EmbeddingConfig:
    model_id: str = "BAAI/bge-m3"
    revision: str = "5617a9f61b028005a4858fdac845db406aefb181"
    device: str = "cpu"
    batch_size: int = 2
    max_tokens: int = 512
    dimension: int = 1024
    dtype: str = "float32"
    normalize_embeddings: bool = True
    local_files_only: bool = True

    def __post_init__(self):
        if self.model_id != "BAAI/bge-m3":
            raise ValueError("This service supports BAAI/bge-m3 only.")
        if not isinstance(self.revision, str) or not re.fullmatch(r"[0-9a-f]{40}", self.revision):
            raise ValueError("Model revision must be a pinned 40-character commit hash.")
        if not isinstance(self.device, str) or (self.device != "cpu" and not re.fullmatch(r"cuda(?::\d+)?", self.device)):
            raise ValueError("Device must be cpu, cuda or cuda:<index>.")
        if type(self.batch_size) is not int or self.batch_size < 1:
            raise ValueError("Batch size must be a positive integer.")
        if type(self.max_tokens) is not int or not 1 <= self.max_tokens <= 8192:
            raise ValueError("Token limit must be between 1 and 8192, including special tokens.")
        if self.dimension != 1024 or self.dtype != "float32":
            raise ValueError("The baseline requires 1024-dimensional float32 vectors.")
        if self.normalize_embeddings is not True or type(self.local_files_only) is not bool:
            raise ValueError("Normalization must be enabled and local_files_only must be boolean.")

    @classmethod
    def from_file(cls, path: str | Path):
        with Path(path).open(encoding="utf-8") as stream:
            return cls(**json.load(stream))

    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EmbeddedChunks:
    """Row i always belongs to chunk_ids[i]; source metadata remains with the caller."""

    chunk_ids: tuple[str, ...]
    vectors: np.ndarray
    token_counts: tuple[int, ...]
    config_hash: str
