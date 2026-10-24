"""W4 v1.0 JSON boundaries shared by integration and generation implementations."""
from typing import TypedDict


class EvidenceContext(TypedDict):
    source_id: str
    chunk_id: str
    text: str
    document_id: str
    version_id: str
    document_title: str
    page_number: int
    section_title: str | None


class ExerciseContext(TypedDict):
    assessment_id: str
    title: str
    description: str
    kind: str
    question: dict | None


class GenerationConfig(TypedDict):
    model: str
    revision: str | None
    prompt_version: str
    max_input_tokens: int
    max_output_tokens: int
    timeout_seconds: float
    temperature: float


class GenerationResult(TypedDict):
    status: str
    answer: str
    references: list[dict]
    usage: dict | None
