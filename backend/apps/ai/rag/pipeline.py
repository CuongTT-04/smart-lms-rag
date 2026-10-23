"""Grounded generation without database access or implicit authorization."""

from collections.abc import Sequence
from time import perf_counter

from ..providers.base import GenerationError, ModelOutput, TokenUsage
from .base import (EvidenceContext, ExerciseContext, GenerationConfig,
                   GenerationResult, GenerationTrace)
from .citations import INSUFFICIENT_MESSAGE, parse_answer, validate_choice_answer
from .context_builder import prepare_prompt
from .guardrails import check_request_policy, parse_reading_hint


class RAGPipeline:
    def __init__(self, provider, config: GenerationConfig | None = None):
        self.provider = provider
        self.config = config or GenerationConfig(model=provider.config)
        self._check_config(self.config)

    def _check_config(self, config):
        if (not isinstance(config, GenerationConfig)
                or config.model.fingerprint() != self.provider.config.fingerprint()):
            raise GenerationError("INVALID_REQUEST", "Pipeline and provider configurations must agree.")

    def generate_answer(self, *, question, mode, contexts, exercise=None, config=None):
        started = perf_counter()
        config = self.config if config is None else config
        self._check_config(config)
        try:
            if not isinstance(question, str) or not question.strip() or mode not in ("qa", "hint"):
                raise ValueError("Invalid question or mode.")
            if isinstance(contexts, (str, bytes)) or not isinstance(contexts, Sequence):
                raise ValueError("contexts must be a sequence of authorized evidence.")
            evidence = tuple(EvidenceContext.from_value(context) for context in contexts)
            exercise = ExerciseContext.from_value(exercise)
            if mode == "qa" and exercise is not None:
                raise ValueError("Exercise context is only supported in hint mode.")
            if len({item.source_id for item in evidence}) != len(evidence):
                raise ValueError("Duplicate source IDs.")
            keys = {(item.document_id, item.version_id, item.chunk_id) for item in evidence}
            if len(keys) != len(evidence):
                raise ValueError("Duplicate evidence chunks.")
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise GenerationError("INVALID_REQUEST", "Question, evidence or visible exercise fields are invalid.") from exc
        check_request_policy(question)
        if not evidence:
            return GenerationResult(
                "INSUFFICIENT_EVIDENCE", INSUFFICIENT_MESSAGE, (), None,
                GenerationTrace((), (), None, config.fingerprint(), None, (),
                                perf_counter() - started, mode == "hint", "empty_context_notice"),
            )
        prepared = prepare_prompt(question=question.strip(), mode=mode, contexts=evidence,
                                  exercise=exercise, config=config, provider=self.provider)
        try:
            output = self.provider.generate(prepared.messages)
        except GenerationError:
            raise
        except Exception as exc:
            raise GenerationError("GENERATION_UNAVAILABLE", "Generation provider failed.") from exc
        if (not isinstance(output, ModelOutput)
                or output.model_id != config.model.model_id or output.revision != config.model.revision
                or output.config_hash != config.model.fingerprint() or output.finish_reason != "eos"):
            raise GenerationError("INVALID_GENERATION", "Model output provenance or completion is invalid.")
        usage = output.usage
        if usage is not None:
            if (not isinstance(usage, TokenUsage) or type(usage.input_tokens) is not int
                    or type(usage.output_tokens) is not int or usage.input_tokens != prepared.input_tokens
                    or not 0 <= usage.output_tokens <= config.model.max_new_tokens):
                raise GenerationError("INVALID_GENERATION", "Model token usage does not match the request.")
        if mode == "hint" and config.prompt_version in ("bounded_guidance", "concise_grounded_qa", "direct_grounded_qa", "routed_grounded_qa", "frozen_baseline", "efficient_grounded"):
            status, answer, references, mapping = parse_reading_hint(output.text, prepared.contexts)
        else:
            status, answer, references, mapping = parse_answer(
                output.text, prepared.contexts, reject_cjk_output=config.reject_cjk_output,
            )
            if mode == "qa" and config.prompt_version in ("frozen_baseline", "efficient_grounded"):
                validate_choice_answer(question, output.text)
        return GenerationResult(
            status, answer, references, usage,
            GenerationTrace(tuple(item.source_id for item in prepared.contexts),
                            prepared.dropped_source_ids, prepared.prompt_sha256,
                            config.fingerprint(), prepared.input_tokens, mapping,
                            perf_counter() - started, mode == "hint",
                            "authored_reading_guide" if mode == "hint" and status == "ANSWERED"
                            and config.prompt_version in ("bounded_guidance", "concise_grounded_qa", "direct_grounded_qa", "routed_grounded_qa", "frozen_baseline", "efficient_grounded") else
                            "insufficient_evidence_notice" if status == "INSUFFICIENT_EVIDENCE" else "model_text"),
        )


def generate_answer(*, question, mode, contexts, exercise, config, provider):
    """Explicit provider injection keeps its runtime reusable across API calls."""
    return RAGPipeline(provider, config).generate_answer(
        question=question, mode=mode, contexts=contexts, exercise=exercise, config=config,
    )
