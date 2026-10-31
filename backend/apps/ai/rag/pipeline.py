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

    def generate_answer(self, *, question, mode, contexts, exercise=None, config=None, history=None):
        started=perf_counter()
        arguments=dict(question=question,mode=mode,contexts=contexts,exercise=exercise,config=config,history=history)
        import inspect
        structured_chat=history is not None and mode=='qa' and 'json_schema' in inspect.signature(self.provider.generate).parameters
        try:
            return self._generate_once(**arguments,repair_format=structured_chat)
        except GenerationError as original:
            reason=getattr(original,'validation_reason',None)
            if history is None or mode!='qa' or reason not in {'MISSING_CITATION','MIXED_OUTPUT_FORMAT','INCOMPLETE_EVIDENCE_COVERAGE'}:
                raise
            import inspect
            parameters=inspect.signature(self.provider.generate).parameters
            if 'timeout_seconds' not in parameters:
                raise  # Do not retry a provider that cannot bound the remaining deadline.
            remaining=(config or self.config).model.timeout_seconds-(perf_counter()-started)-1
            if remaining<=0:
                raise
            try:
                result=self._generate_once(**arguments,repair_format=True,remaining_seconds=remaining,
                                           repair_feedback=getattr(original,'missing_evidence',None))
            except GenerationError as repair:
                if repair.code=='TOKEN_LIMIT_EXCEEDED':
                    raise original from repair
                raise
            from dataclasses import replace
            return replace(result,trace=replace(result.trace,elapsed_seconds=perf_counter()-started,
                                               answer_origin='model_text_retried' if result.status=='ANSWERED' else result.trace.answer_origin))

    def _generate_once(self, *, question, mode, contexts, exercise=None, config=None, history=None,
                       repair_format=False, remaining_seconds=None, repair_feedback=None):
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
        if history is not None:
            from .conversation import validate_history
            validate_history(history)
            if mode != 'qa' or exercise is not None:
                raise GenerationError('INVALID_REQUEST', 'Document memory only supports QA.')
        if not evidence:
            return GenerationResult(
                "INSUFFICIENT_EVIDENCE", INSUFFICIENT_MESSAGE, (), None,
                GenerationTrace((), (), None, config.fingerprint(), None, (),
                                perf_counter() - started, mode == "hint", "empty_context_notice",
                                dict(protocol='chat_history_v1',turns_used=0,turns_dropped=len(history),history_tokens=0) if history is not None else None),
            )
        memory = None
        if history is None:
            prepared = prepare_prompt(question=question.strip(), mode=mode, contexts=evidence,
                                      exercise=exercise, config=config, provider=self.provider)
        else:
            from .conversation import prepare_conversation_prompt
            prepared, memory = prepare_conversation_prompt(question=question.strip(), mode=mode, contexts=evidence,
                exercise=exercise, config=config, provider=self.provider, history=history, repair_format=repair_format,repair_feedback=repair_feedback)
        options={'timeout_seconds':remaining_seconds} if remaining_seconds is not None else {}
        if repair_format:
            import inspect
            if 'json_schema' in inspect.signature(self.provider.generate).parameters:
                from .conversation import build_evidence_units, citation_response_schema
                ids=[unit['evidence_id'] for unit in build_evidence_units(prepared.contexts)]
                options['json_schema']=citation_response_schema(len(prepared.contexts),evidence_ids=ids)
        try:
            output = self.provider.generate(prepared.messages, **options)
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
        text=output.text
        if repair_format:
            from .conversation import render_structured_answer
            text=render_structured_answer(text,prepared.contexts,require_proof='json_schema' in options)
            if 'json_schema' in options:
                from .conversation import validate_sequence_start
                validate_sequence_start(question,output.text,prepared.contexts)
        if mode == "hint" and config.prompt_version in ("bounded_guidance", "concise_grounded_qa", "direct_grounded_qa", "routed_grounded_qa", "frozen_baseline", "efficient_grounded"):
            status, answer, references, mapping = parse_reading_hint(text, prepared.contexts)
        else:
            status, answer, references, mapping = parse_answer(
                text, prepared.contexts, reject_cjk_output=config.reject_cjk_output,
            )
            if mode == "qa" and config.prompt_version in ("frozen_baseline", "efficient_grounded"):
                validate_choice_answer(question, text)
        if history is not None and status=='ANSWERED':
            from .conversation import validate_inline_citations
            validate_inline_citations(answer)
        result = GenerationResult(
            status, answer, references, usage,
            GenerationTrace(tuple(item.source_id for item in prepared.contexts),
                            prepared.dropped_source_ids, prepared.prompt_sha256,
                            config.fingerprint(), prepared.input_tokens, mapping,
                            perf_counter() - started, mode == "hint",
                            "authored_reading_guide" if mode == "hint" and status == "ANSWERED"
                            and config.prompt_version in ("bounded_guidance", "concise_grounded_qa", "direct_grounded_qa", "routed_grounded_qa", "frozen_baseline", "efficient_grounded") else
                            "insufficient_evidence_notice" if status == "INSUFFICIENT_EVIDENCE" else "model_text"),
        )
        if memory is not None:
            from dataclasses import replace
            result = replace(result, trace=replace(result.trace, memory=memory))
        return result


def generate_answer(*, question, mode, contexts, exercise, config, provider):
    """Explicit provider injection keeps its runtime reusable across API calls."""
    return RAGPipeline(provider, config).generate_answer(
        question=question, mode=mode, contexts=contexts, exercise=exercise, config=config,
    )
