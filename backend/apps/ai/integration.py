"""Application JSON boundary for Dương's generation pipeline.

This adapter does not authorize sources or turn Kaggle notebooks into an API.
"""
from functools import lru_cache
import json
from .providers import GenerationError, LocalModelProvider, ModelConfig
from .rag import ExerciseContext, GenerationConfig, RAGPipeline
from apps.documents.exceptions import DocumentError


def visible_exercise(value):
    if value is None:
        return None
    if not isinstance(value,dict) or set(value)-{'assessment_id','title','description','kind','question'}:
        raise ValueError('Unexpected exercise fields')
    question=value.get('question')
    if value.get('kind')=='QUIZ':
        if not isinstance(question,dict) or set(question)-{'id','prompt','choices'}:
            raise ValueError('Only visible quiz fields are allowed')
        choices=question.get('choices',[])
        if not isinstance(choices,list) or any(not isinstance(c,dict) or set(c)!={'id','text'} for c in choices):
            raise ValueError('Only visible choices are allowed')
        return ExerciseContext(exercise_id=f"{value['assessment_id']}:{question['id']}",
            question=question['prompt'],choices=tuple(c['text'] for c in choices))
    if value.get('kind')!='TEXT' or question is not None:
        raise ValueError('Invalid exercise type')
    text='\n'.join(part for part in (value.get('title'),value.get('description')) if part)
    return ExerciseContext(exercise_id=value['assessment_id'],question=text)


class GenerationBridge:
    def __init__(self,pipeline):
        self.pipeline=pipeline

    def __call__(self,*,question,mode,contexts,exercise,config):
        try:
            public_exercise=visible_exercise(exercise)
        except (ValueError,KeyError,TypeError) as exc:
            raise DocumentError('INVALID_REQUEST','Thông tin bài ôn tập không hợp lệ.',400) from exc
        try:
            result=self.pipeline.generate_answer(question=question,mode=mode,contexts=contexts,exercise=public_exercise)
            # Validate against the actual prompt, not every pre-budget retrieval hit.
            used=set(result.trace.used_source_ids)
            if any(reference.source_id not in used for reference in result.references):
                raise GenerationError('INVALID_GENERATION','Reference outside prompt')
            return result.to_dict()
        except GenerationError as exc:
            if exc.code=='INVALID_REQUEST':
                raise DocumentError('INVALID_REQUEST','Yêu cầu không phù hợp với chính sách trợ lý.',400) from exc
            if exc.code=='INVALID_GENERATION':
                raise DocumentError('INVALID_GENERATION','Phản hồi AI chưa hợp lệ. Vui lòng thử lại.',503) from exc
            raise DocumentError('GENERATION_UNAVAILABLE','Mô hình AI không thể hoàn tất yêu cầu lúc này.',503) from exc


@lru_cache(maxsize=1)
def _local_bridge(config_json):
    config=json.loads(config_json)
    model=ModelConfig(model_id=config['model'],revision=config.get('revision') or ModelConfig().revision,
        device=config.get('device','cuda:0'),checkpoint_path=config.get('checkpoint_path'),
        local_files_only=True,context_tokens=config.get('context_tokens',4096),
        max_input_tokens=config['max_input_tokens'],max_new_tokens=config['max_output_tokens'],
        timeout_seconds=config['timeout_seconds'])
    provider=LocalModelProvider(model)
    return GenerationBridge(RAGPipeline(provider,GenerationConfig(model=model,
        prompt_version=config['prompt_version'],temperature=config['temperature'])))


def generate_answer(*,question,mode,contexts,exercise,config):
    """Local CUDA entrypoint; Kaggle hosting requires an authenticated remote provider."""
    bridge=_local_bridge(json.dumps(config,sort_keys=True))
    return bridge(question=question,mode=mode,contexts=contexts,exercise=exercise,config=config)
