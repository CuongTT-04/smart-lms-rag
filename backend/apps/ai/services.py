"""W4 chat orchestration. LLM implementation is injected by the operator."""
import math
import re
from time import monotonic
from apps.documents.exceptions import DocumentError
from apps.documents.retrieval_scope import resolve_scope
from apps.documents.retrieval_adapter import live_scope
from .policy import enforce_chat_policy
from .runtime import get_runtime
from .rag.errors import public_validation_error, VALIDATION_ERROR_CODES


def retrieve_dense_authorized(*args, **kwargs):
    # Optional embedding dependencies must not prevent the entire Django API booting.
    try:
        from apps.documents.dense_retrieval import retrieve_dense_authorized as retrieve
        return retrieve(*args, **kwargs)
    except ImportError as exc:
        raise DocumentError('RETRIEVAL_UNAVAILABLE','Thư viện truy xuất chưa sẵn sàng.',503) from exc


def invalid_generation():
    return DocumentError(*public_validation_error())


def map_output(output, contexts):
    if not isinstance(output, dict) or set(output) != {'status', 'answer', 'references', 'usage'}:
        raise invalid_generation()
    status, answer, references, usage = (output[key] for key in ('status','answer','references','usage'))
    if status not in ('ANSWERED','INSUFFICIENT_EVIDENCE') or not isinstance(answer,str) or not answer.strip() or len(answer)>64000 or not isinstance(references,list):
        raise invalid_generation()
    if usage is not None and (not isinstance(usage,dict) or set(usage)!={'input_tokens','output_tokens'} or
        any(type(v) is not int or v<0 for v in usage.values())):
        raise invalid_generation()
    raw_labels = re.findall(r'\[([0-9]+)\]',answer)
    if any(len(label)>2 or label.startswith('0') for label in raw_labels):
        raise invalid_generation()
    labels = [int(label) for label in raw_labels]
    if status == 'INSUFFICIENT_EVIDENCE':
        if references or labels:
            raise invalid_generation()
        return status, answer.strip(), []
    sources = {context['source_id']: context for context in contexts}
    unique = list(dict.fromkeys(labels))
    if not unique or unique != list(range(1,len(unique)+1)) or len(references)!=len(unique):
        raise invalid_generation()
    citations=[]; seen=set()
    for label, reference in enumerate(references,1):
        if not isinstance(reference,dict) or set(reference)!={'label','source_id'} or type(reference['label']) is not int or reference['label']!=label:
            raise invalid_generation()
        source_id=reference['source_id']
        if not isinstance(source_id,str) or source_id not in sources or source_id in seen:
            raise invalid_generation()
        seen.add(source_id)
        citations.append({'label':label, 'excerpt':sources[source_id]['text'], **{key:value for key,value in sources[source_id].items()
            if key not in ('source_id','text')}})
    return status, answer.strip(), citations


def answer_chat(*, user, data, request_id, runtime=None, history=None):
    started=monotonic()
    user.refresh_from_db()
    exercise=enforce_chat_policy(user,data)
    # Hint retrieval is restricted to the exercise's actual session even if UI omitted it.
    scope=resolve_scope(user,data['course_id'],data.get('classroom_id'),
        data.get('session_id'),data.get('document_ids'),data['mode'])
    if exercise and not scope.session_id:
        from apps.courses.assessment_models import Assessment
        assessment=Assessment.objects.get(pk=exercise['assessment_id'])
        scope=resolve_scope(user,data['course_id'],data.get('classroom_id'),assessment.session_id,
            data.get('document_ids'),data['mode'])
    contexts=[]
    memory=None
    retrieval_question=data['question']
    if history:
        prefix='\nChủ đề câu hỏi trước: '
        remaining=8000-len(retrieval_question)-len(prefix)
        if remaining>0:
            retrieval_question+=prefix+history[-1]['question'][:min(600,remaining)]
    if scope.allowed_version_ids:
        runtime=runtime or get_runtime()
        try:
            hits=retrieve_dense_authorized(user,retrieval_question,scope,runtime.index,runtime.embedding,
                catalog=runtime.catalog,top_k=5)
        except DocumentError as exc:
            if exc.status==503:
                raise DocumentError('RETRIEVAL_UNAVAILABLE','Không thể truy xuất học liệu lúc này.',503) from exc
            raise
        contexts=[{'source_id':f'S{i}', 'chunk_id':hit['chunk_id'],'text':hit['text'],
            **{key:value for key,value in hit['source'].items() if key!='course_id'}} for i,hit in enumerate(hits,1)]
    if contexts:
        try:
            arguments=dict(question=data['question'], mode=data['mode'], contexts=contexts, exercise=exercise, config=runtime.config)
            if history is not None:
                arguments['history']=history
            output=runtime.generate(**arguments)
            if history is not None:
                output=dict(output)
                memory=output.pop('_memory',None)
                if not isinstance(memory,dict) or memory.get('protocol')!='chat_history_v1':
                    raise DocumentError('GENERATION_CONFIG_MISMATCH','Gateway chưa hỗ trợ context nhiều lượt. Cần đồng bộ cell mới.',503)
        except DocumentError as exc:
            if exc.code=='INVALID_GENERATION': raise invalid_generation() from exc
            if exc.code in VALIDATION_ERROR_CODES: raise
            if exc.status==400 and exc.code=='INVALID_REQUEST': raise
            if exc.code in {'OUTPUT_LIMIT_REACHED', 'INCOMPLETE_GENERATION', 'GENERATION_TIMEOUT',
                    'OUT_OF_MEMORY', 'GENERATION_BUSY', 'GENERATION_CONFIG_MISMATCH'}: raise
            raise DocumentError('GENERATION_UNAVAILABLE','Mô hình AI chưa sẵn sàng. Vui lòng thử lại.',503) from exc
        except Exception as exc:
            raise DocumentError('GENERATION_UNAVAILABLE','Mô hình AI chưa sẵn sàng. Vui lòng thử lại.',503) from exc
        status,answer,citations=map_output(output,contexts)
    else:
        status,answer,citations='INSUFFICIENT_EVIDENCE','Chưa đủ căn cứ trong học liệu được phép để trả lời câu hỏi này.',[]
        if history is not None:
            memory=dict(protocol='chat_history_v1',turns_used=0,turns_dropped=len(history),history_tokens=0)
    user.refresh_from_db()
    final_exercise=enforce_chat_policy(user,data)
    if final_exercise!=exercise:
        raise DocumentError('SCOPE_CHANGED','Nội dung bài tập đã thay đổi. Vui lòng tải lại.',409)
    live_scope(user,scope)
    elapsed=(monotonic()-started)*1000
    if not math.isfinite(elapsed): raise invalid_generation()
    result={'request_id':request_id,'status':status,'mode':data['mode'],'answer':answer,
            'citations':citations,'timing':{'total_ms':round(elapsed,3)}}
    if memory is not None:
        result['memory']=memory
    return result
