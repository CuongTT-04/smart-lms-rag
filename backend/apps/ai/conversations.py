"""Owner-scoped durable conversations; never hold SQL locks during inference."""
from datetime import timedelta
from uuid import uuid4

from django.core import signing
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.documents.exceptions import DocumentError
from apps.documents.models import KnowledgeDocument
from apps.documents.retrieval_scope import resolve_scope
from .models import ChatConversation, ChatTurn, ChatResponseRecord
from .policy import enforce_chat_policy
from .services import answer_chat

PAGE_SIZE = 20
LEASE_SECONDS = 180


def unavailable():
    return DocumentError('NOT_FOUND', 'Tài nguyên không khả dụng.', 404)


def document_scope(user, selector):
    user.refresh_from_db()
    data = {**selector, 'mode': 'qa'}
    enforce_chat_policy(user, data)
    scope = resolve_scope(user, selector['course_id'], selector.get('classroom_id'),
        selector.get('session_id'), [str(selector['document_id'])], 'qa')
    document = KnowledgeDocument.objects.filter(pk=selector['document_id'], is_published=True,
        removed_at__isnull=True, published_version_id__in=scope.allowed_version_ids).first()
    if document is None:
        raise unavailable()
    return document, scope


def owned_conversation(user, conversation_id):
    conversation = ChatConversation.objects.filter(pk=conversation_id, user=user).first()
    if conversation is None:
        raise unavailable()
    document, _ = document_scope(user, dict(course_id=conversation.course_id,
        classroom_id=conversation.classroom_id, session_id=conversation.classroom_session_id,
        document_id=conversation.document_id))
    if document.published_version_id != conversation.version_id:
        raise unavailable()
    return conversation


def metadata(conversation):
    return dict(id=str(conversation.pk), document_id=str(conversation.document_id),
        version_id=str(conversation.version_id), title=conversation.title,
        created_at=conversation.created_at.isoformat(), updated_at=conversation.updated_at.isoformat())


def create_conversation(user, selector):
    document, scope = document_scope(user, selector)
    return ChatConversation.objects.create(user=user, course_id=scope.course_id,
        classroom_id=scope.classroom_id, classroom_session_id=scope.session_id,
        document=document, version_id=document.published_version_id)


def list_conversations(user, selector, cursor=None):
    document, scope = document_scope(user, selector)
    query = ChatConversation.objects.filter(user=user, document=document, version_id=document.published_version_id,
        course_id=scope.course_id, classroom_id=scope.classroom_id, classroom_session_id=scope.session_id
    ).annotate(turn_count=Count('turns')).filter(turn_count__gt=0)
    if cursor:
        try:
            value = signing.loads(cursor, salt='ai-conversations', max_age=86400*7)
            stamp, key = parse_datetime(value['updated_at']), value['id']
            if stamp is None:
                raise ValueError('timestamp')
            query = query.filter(Q(updated_at__lt=stamp) | Q(updated_at=stamp, id__lt=key))
        except Exception as exc:
            raise DocumentError('INVALID_REQUEST', 'Trang lịch sử không hợp lệ. Vui lòng tải lại.', 400) from exc
    rows = list(query.order_by('-updated_at', '-id')[:PAGE_SIZE+1])
    page = rows[:PAGE_SIZE]
    next_cursor = signing.dumps(dict(updated_at=page[-1].updated_at.isoformat(), id=str(page[-1].pk)),
        salt='ai-conversations') if len(rows)>PAGE_SIZE else None
    # Do not return stored questions/titles if permission changed during the query.
    current_document, _ = document_scope(user, selector)
    if current_document.published_version_id != document.published_version_id:
        raise unavailable()
    return dict(results=[metadata(row) for row in page], next_cursor=next_cursor)


def serialize_turn(turn):
    result = dict(turn.result) if turn.result else None
    if result is not None:
        try:
            result['rating'] = turn.feedback.rating
        except ChatResponseRecord.DoesNotExist:
            result['rating'] = None
    return dict(id=str(turn.pk), position=turn.position, question=turn.question, status=turn.status,
        result=result, error=dict(code=turn.error_code, message=turn.error_message) if turn.status=='FAILED' else None,
        created_at=turn.created_at.isoformat())


def conversation_detail(user, conversation_id, before=None):
    conversation = owned_conversation(user, conversation_id)
    # A restarted HTTP process must not leave a spinner forever.
    expire_turns(conversation)
    query = conversation.turns.select_related('feedback')
    if before is not None:
        query = query.filter(position__lt=before)
    rows = list(query.order_by('-position')[:PAGE_SIZE+1])
    page = rows[:PAGE_SIZE]
    owned_conversation(user, conversation_id)
    return dict(**metadata(conversation), turns=[serialize_turn(row) for row in reversed(page)],
                next_before=page[-1].position if len(rows)>PAGE_SIZE else None)


def expire_turns(conversation):
    conversation.turns.filter(status='PENDING', lease_expires_at__lte=timezone.now()).update(
        status='FAILED', error_code='GENERATION_TIMEOUT', error_message='Lượt hỏi đã hết thời gian xử lý. Hãy gửi lại.',
        lease_token=None, updated_at=timezone.now())


def claim_turn(conversation, question, client_message_id):
    with transaction.atomic():
        locked = ChatConversation.objects.select_for_update().get(pk=conversation.pk)
        expire_turns(locked)
        previous = locked.turns.filter(client_message_id=client_message_id).first()
        if previous:
            if previous.question != question:
                raise DocumentError('MESSAGE_CONFLICT', 'Mã lượt hỏi đã được dùng cho nội dung khác.', 409)
            return previous, True
        if locked.turns.filter(status='PENDING').exists():
            raise DocumentError('CONVERSATION_BUSY', 'Phiên chat đang xử lý một câu hỏi. Vui lòng đợi.', 409)
        position = max(locked.next_position, (locked.turns.aggregate(last=Max('position'))['last'] or 0)+1)
        turn = ChatTurn.objects.create(conversation=locked, client_message_id=client_message_id,
            position=position, question=question, status='PENDING', lease_token=uuid4(),
            lease_expires_at=timezone.now()+timedelta(seconds=LEASE_SECONDS))
        if position == 1:
            locked.title = ' '.join(question.split())[:80]
        locked.next_position = position+1
        locked.save(update_fields=['next_position', 'title', 'updated_at'])
        return turn, False


def fail_turn(turn, error):
    ChatTurn.objects.filter(pk=turn.pk, status='PENDING', lease_token=turn.lease_token).update(
        status='FAILED', error_code=error.code[:48], error_message=error.message[:255],
        error_status=error.status, lease_token=None, updated_at=timezone.now())


def send_conversation(*, user, data):
    conversation = owned_conversation(user, data['conversation_id'])
    for field, actual in [('course_id', conversation.course_id), ('classroom_id', conversation.classroom_id),
                          ('session_id', conversation.classroom_session_id)]:
        if data.get(field) is not None and str(data[field]) != str(actual):
            raise unavailable()
    if data.get('document_ids') is not None and [str(x) for x in data['document_ids']] != [str(conversation.document_id)]:
        raise unavailable()
    turn, replay = claim_turn(conversation, data['question'], data['client_message_id'])
    if replay:
        if turn.status == 'PENDING':
            return dict(status='PENDING', conversation_id=str(conversation.pk), turn_id=str(turn.pk)), 202
        if turn.status == 'FAILED':
            raise DocumentError(turn.error_code, turn.error_message, turn.error_status)
        owned_conversation(user, conversation.pk)
        return serialize_turn(turn)['result'], 200
    previous = list(conversation.turns.filter(status='COMPLETED', position__lt=turn.position).order_by('-position')[:4])
    history = [dict(question=row.question, answer=row.result['answer']) for row in reversed(previous)]
    selector = dict(course_id=str(conversation.course_id), classroom_id=str(conversation.classroom_id) if conversation.classroom_id else None,
        session_id=str(conversation.classroom_session_id) if conversation.classroom_session_id else None,
        document_ids=[str(conversation.document_id)], question=turn.question, mode='qa')
    try:
        result = answer_chat(user=user, data=selector, request_id=str(turn.pk), history=history)
        owned_conversation(user, conversation.pk)
        result = {**result, 'request_id': str(turn.pk), 'conversation_id': str(conversation.pk), 'turn_id': str(turn.pk)}
        with transaction.atomic():
            ChatConversation.objects.select_for_update().get(pk=conversation.pk)
            current = ChatTurn.objects.select_for_update().get(pk=turn.pk)
            if current.status != 'PENDING' or current.lease_token != turn.lease_token or current.lease_expires_at <= timezone.now():
                raise DocumentError('CHAT_SUPERSEDED', 'Lượt hỏi đã hết hiệu lực. Vui lòng tải lại phiên chat.', 409)
            current.status = 'COMPLETED'; current.result = result; current.lease_token = None
            current.save(update_fields=['status', 'result', 'lease_token', 'updated_at'])
            ChatResponseRecord.objects.create(id=turn.pk, user=user, turn=current)
            ChatConversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())
        return result, 200
    except DocumentError as exc:
        fail_turn(turn, exc)
        raise
    except Exception as exc:
        error = DocumentError('GENERATION_UNAVAILABLE', 'Trợ lý AI chưa sẵn sàng. Vui lòng thử lại.', 503)
        fail_turn(turn, error)
        raise error from exc
