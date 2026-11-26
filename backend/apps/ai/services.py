"""W4 chat orchestration. LLM implementation is injected by the operator."""
import math
import re
from time import monotonic
from apps.documents.exceptions import DocumentError
from apps.documents.retrieval_scope import resolve_scope
from apps.documents.retrieval_adapter import assert_scope_and_citations_live
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


def answer_chat(*, user, data, request_id, runtime=None, history=None, tutoring=None):
    if data['mode'] == 'summary':
        from .summary import answer_summary
        return answer_summary(user=user, data=data, request_id=request_id, runtime=runtime)
    started=monotonic()
    user.refresh_from_db()
    exercise=enforce_chat_policy(user,data)
    from .providers.base import GenerationError
    from .rag.guardrails import check_request_policy, check_output_policy
    try:
        check_request_policy(data['question'])
    except GenerationError as exc:
        raise DocumentError('INVALID_REQUEST', 'Không hỗ trợ yêu cầu vượt chính sách hoặc tiết lộ thông tin riêng.', 400) from exc
    # Hint retrieval is restricted to the exercise's actual session even if UI omitted it.
    scope=resolve_scope(user,data['course_id'],data.get('classroom_id'),
        data.get('session_id'),data.get('document_ids'),data['mode'])
    if exercise and not scope.session_id:
        from apps.courses.assessment_models import Assessment
        assessment=Assessment.objects.get(pk=exercise['assessment_id'])
        scope=resolve_scope(user,data['course_id'],data.get('classroom_id'),assessment.session_id,
            data.get('document_ids'),data['mode'])
    if scope.document_ids and len(scope.allowed_version_ids) != len(scope.document_ids):
        raise DocumentError('NOT_FOUND', 'Học liệu không khả dụng hoặc bạn không có quyền truy cập.', 404)
    contexts=[]
    memory=None
    from .rag.conversation import extract_procedure_answer, is_full_procedure_question, retrieval_query
    retrieval_question=retrieval_query(data['question'],history)
    if exercise:
        prompt = (exercise.get('question') or {}).get('prompt', '')
        retrieval_question = '\n'.join(filter(None, (
            exercise['title'], prompt, exercise['description'], retrieval_question,
        )))[:8000]
    if scope.allowed_version_ids:
        runtime=runtime or get_runtime()
        try:
            hits=retrieve_dense_authorized(user,retrieval_question,scope,runtime.index,runtime.embedding,
                catalog=runtime.catalog,top_k=5,
                include_procedure_continuations=data['mode']=='qa' and is_full_procedure_question(data['question']))
        except DocumentError as exc:
            if exc.code == 'RETRIEVAL_NOT_READY':
                raise
            if exc.status==503:
                raise DocumentError('RETRIEVAL_UNAVAILABLE','Không thể truy xuất học liệu lúc này.',503) from exc
            raise
        contexts=[{'source_id':f'S{i}', 'chunk_id':hit['chunk_id'],'text':hit['text'],
            **{key:value for key,value in hit['source'].items() if key!='course_id'}} for i,hit in enumerate(hits,1)]
    if contexts:
        # Retrieval and runtime setup may have taken long enough for access to change.
        if enforce_chat_policy(user, data) != exercise:
            raise DocumentError('SCOPE_CHANGED', 'Nội dung bài tập đã thay đổi. Vui lòng tải lại.', 409)
        assert_scope_and_citations_live(user, scope, citations=contexts)
        try:
            arguments=dict(question=data['question'], mode=data['mode'], contexts=contexts, exercise=exercise, config=runtime.config)
            if history is not None:
                arguments['history']=history
            if tutoring is not None:
                arguments['tutoring']=tutoring
            from .operations import generation_slot
            with generation_slot(user, data['mode']) as generate:
                # Waiting may outlive a permission change; recheck before sending any source.
                if enforce_chat_policy(user, data) != exercise:
                    raise DocumentError('SCOPE_CHANGED', 'Nội dung bài tập đã thay đổi.', 409)
                assert_scope_and_citations_live(user, scope, citations=contexts)
                output=generate(runtime.generate, **arguments)
            if history is not None:
                output=dict(output)
                memory=output.pop('_memory',None)
                if not isinstance(memory,dict) or memory.get('protocol')!='chat_history_v1':
                    raise DocumentError('GENERATION_CONFIG_MISMATCH','Gateway chưa hỗ trợ context nhiều lượt. Cần đồng bộ cell mới.',503)
        except DocumentError as exc:
            output = None
            if exc.code == 'GENERATION_INCOMPLETE_ANSWER' and data['mode'] == 'qa':
                output = extract_procedure_answer(data['question'], contexts)
            if output is not None:
                if history is not None:
                    memory = dict(protocol='chat_history_v1', turns_used=0, turns_dropped=len(history), history_tokens=0)
            else:
                if exc.code=='INVALID_GENERATION': raise invalid_generation() from exc
                if exc.code in VALIDATION_ERROR_CODES: raise
                if exc.status==400 and exc.code=='INVALID_REQUEST': raise
                if exc.code in {'OUTPUT_LIMIT_REACHED', 'INCOMPLETE_GENERATION', 'GENERATION_TIMEOUT',
                        'OUT_OF_MEMORY', 'GENERATION_BUSY', 'GENERATION_CONFIG_MISMATCH',
                        'AI_QUOTA_EXCEEDED', 'AI_QUEUE_FULL', 'AI_QUEUE_TIMEOUT',
                        'NOT_FOUND', 'SCOPE_CHANGED', 'AI_NOT_ALLOWED'}: raise
                raise DocumentError('GENERATION_UNAVAILABLE','Mô hình AI chưa sẵn sàng. Vui lòng thử lại.',503) from exc
        except Exception as exc:
            raise DocumentError('GENERATION_UNAVAILABLE','Mô hình AI chưa sẵn sàng. Vui lòng thử lại.',503) from exc
        status,answer,citations=map_output(output,contexts)
        if status == 'ANSWERED' and data['mode'] == 'qa':
            from .source_quotes import complete_quote_context
            answer = complete_quote_context(answer, citations)
        try:
            check_output_policy(answer, [context['text'] for context in contexts])
        except GenerationError as exc:
            raise invalid_generation() from exc
    else:
        status,answer,citations='INSUFFICIENT_EVIDENCE','Chưa đủ căn cứ trong học liệu được phép để trả lời câu hỏi này.',[]
        if history is not None:
            memory=dict(protocol='chat_history_v1',turns_used=0,turns_dropped=len(history),history_tokens=0)
    user.refresh_from_db()
    final_exercise=enforce_chat_policy(user,data)
    if final_exercise!=exercise:
        raise DocumentError('SCOPE_CHANGED','Nội dung bài tập đã thay đổi. Vui lòng tải lại.',409)
    assert_scope_and_citations_live(user,scope,citations=citations)
    elapsed=(monotonic()-started)*1000
    if not math.isfinite(elapsed): raise invalid_generation()
    result={'request_id':request_id,'status':status,'mode':data['mode'],'answer':answer,
            'citations':citations,'timing':{'total_ms':round(elapsed,3)}}
    if memory is not None:
        result['memory']=memory
    if data['mode'] == 'qa':
        from .followups import suggested_questions
        result['suggested_questions'] = suggested_questions(data['question'], citations,
            mode=data['mode'], status=status, history=history)
    return result
