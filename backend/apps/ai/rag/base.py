"""Internal RAG contracts; callers must resolve authorization before supplying evidence."""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from uuid import UUID

from ..providers.base import ModelConfig, TokenUsage


def _nonblank(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string.")


@dataclass(frozen=True)
class EvidenceContext:
    source_id: str
    chunk_id: str
    text: str
    document_id: str
    version_id: str
    document_title: str
    page_number: int
    section_title: str | None = None

    def __post_init__(self):
        if not isinstance(self.source_id, str) or not re.fullmatch(r"S[1-9][0-9]*", self.source_id):
            raise ValueError("source_id must be assigned by the caller, e.g. S1.")
        for name in ("chunk_id", "text", "document_title"):
            _nonblank(getattr(self, name), name)
        for name in ("document_id", "version_id"):
            _nonblank(getattr(self, name), name)
            UUID(getattr(self, name))
        if type(self.page_number) is not int or self.page_number < 1:
            raise ValueError("page_number must be a physical PDF page starting at 1.")
        if self.section_title is not None:
            _nonblank(self.section_title, "section_title")

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("Evidence must be a context record.")
        return cls(**dict(value))


@dataclass(frozen=True)
class ExerciseContext:
    exercise_id: str
    question: str
    choices: tuple[str, ...] = ()

    def __post_init__(self):
        _nonblank(self.exercise_id, "exercise_id")
        _nonblank(self.question, "question")
        if isinstance(self.choices, (str, bytes)) or not isinstance(self.choices, Sequence):
            raise ValueError("choices must contain only visible option text.")
        for choice in self.choices:
            _nonblank(choice, "choice")
        object.__setattr__(self, "choices", tuple(self.choices))

    @classmethod
    def from_value(cls, value):
        if value is None or isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("Exercise must contain only visible exercise fields.")
        return cls(**dict(value))


@dataclass(frozen=True)
class GenerationConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    prompt_version: str = "bounded_guidance"
    temperature: float = 0.0
    max_sources: int = 10
    reject_cjk_output: bool = True

    def __post_init__(self):
        if not isinstance(self.model, ModelConfig):
            raise ValueError("model must be a server-side ModelConfig.")
        if self.prompt_version not in ("grounded_text", "grounded_text_guarded", "bounded_guidance",
                                       "concise_grounded_qa", "direct_grounded_qa", "routed_grounded_qa", "frozen_baseline",
                                       "efficient_grounded"):
            raise ValueError("Unsupported prompt version.")
        if type(self.temperature) not in (int, float) or self.temperature != 0:
            raise ValueError("This baseline uses greedy generation only.")
        if type(self.max_sources) is not int or self.max_sources < 1:
            raise ValueError("max_sources must be positive.")
        if type(self.reject_cjk_output) is not bool:
            raise ValueError("reject_cjk_output must be boolean.")

    def fingerprint(self):
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class Reference:
    label: int
    source_id: str


@dataclass(frozen=True)
class GenerationTrace:
    used_source_ids: tuple[str, ...]
    dropped_source_ids: tuple[str, ...]
    prompt_sha256: str | None
    config_hash: str
    input_tokens: int | None
    label_mapping: tuple[tuple[int, int], ...]
    elapsed_seconds: float
    hint_review_required: bool
    answer_origin: str = "model_text"
    memory: dict | None = None


@dataclass(frozen=True)
class GenerationResult:
    status: str
    answer: str
    references: tuple[Reference, ...]
    usage: TokenUsage | None
    trace: GenerationTrace

    def to_dict(self):
        """API/pipeline contract only; keep trace server-side, not in public JSON."""
        return {
            "status": self.status, "answer": self.answer,
            "references": [asdict(reference) for reference in self.references],
            "usage": asdict(self.usage) if self.usage is not None else None,
        }
