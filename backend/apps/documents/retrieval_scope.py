"""Resolve live LMS permissions, never trust client-provided allowed versions."""
from uuid import UUID
from apps.courses.models import Course,Classroom,ClassroomSession
from apps.courses.permissions import can_manage_course,can_view_classroom
from .access import require_access,require_session_access
from .exceptions import DocumentError
from .models import KnowledgeDocument
from .retrieval_contracts import RetrievalScope


def unavailable():
    return DocumentError('NOT_FOUND','Resource unavailable.',404)


def identifier(value):
    try:return str(UUID(str(value)))
    except (ValueError,TypeError,AttributeError) as exc:raise unavailable() from exc


def resolve_scope(user,course_id,classroom_id=None,session_id=None,document_ids=None,mode='qa',preview=False):
    if mode not in ('qa','hint') or type(preview) is not bool:
        raise DocumentError('INVALID_SCOPE','Unsupported retrieval mode.',400)
    try:course=Course.objects.get(pk=identifier(course_id))
    except Course.DoesNotExist as exc:raise unavailable() from exc
    require_access(user,course)
    if preview and not can_manage_course(user,course):raise unavailable()
    classroom=None;session=None
    if classroom_id is not None:
        try:classroom=Classroom.objects.get(pk=identifier(classroom_id),course=course)
        except Classroom.DoesNotExist as exc:raise unavailable() from exc
        if not can_view_classroom(user,classroom):raise unavailable()
    if session_id is not None:
        try:session=ClassroomSession.objects.select_related('classroom').get(pk=identifier(session_id),classroom__course=course)
        except ClassroomSession.DoesNotExist as exc:raise unavailable() from exc
        require_session_access(user,session,course)
        if classroom and session.classroom_id!=classroom.pk:raise unavailable()
        if session.is_draft and not preview:raise unavailable()
        classroom=session.classroom
    if document_ids is not None:
        if not isinstance(document_ids,(list,tuple)):raise DocumentError('INVALID_SCOPE','Document IDs must be a list.',400)
        document_ids=tuple(sorted({identifier(x) for x in document_ids}))
    query=KnowledgeDocument.objects.filter(course=course,removed_at__isnull=True).select_related(
        'published_version','active_version','session__classroom')
    if session:query=query.filter(session=session)
    elif classroom:query=query.filter(session__classroom=classroom)
    if document_ids is not None:
        query=query.filter(pk__in=document_ids)
        if query.count()!=len(document_ids):raise unavailable()
    allowed=[]
    for document in query:
        if document.session:
            try:require_session_access(user,document.session,course)
            except DocumentError:continue
            if document.session.is_draft and not preview:continue
        version=document.published_version if document.is_published else None
        if preview:
            # No implicit arbitrary "latest" version: explicit active source or published source only.
            version=document.active_version or version
        if (document_ids and version and version.document_id == document.pk and not version.removed_at
                and version.status not in ('EXTRACTED', 'READY', 'REMOVED')):
            raise DocumentError('RETRIEVAL_NOT_READY',
                'Học liệu đã chọn đang xử lý hoặc xử lý lỗi. Chờ học liệu sẵn sàng rồi thử lại.', 503)
        if (version and version.document_id==document.pk and not version.removed_at
                and version.status in ('EXTRACTED','READY')):
            allowed.append(str(version.pk))
    return RetrievalScope(str(user.pk),str(course.pk),str(classroom.pk) if classroom else None,
        str(session.pk) if session else None,document_ids,tuple(sorted(allowed)),mode,preview)


def verify_citation_access(user, *, document_id, version_id, page_number=None, scope=None):
    """Authoritative live permission check when validating or opening a citation."""
    doc_pk = identifier(document_id)
    ver_pk = identifier(version_id)
    try:
        document = KnowledgeDocument.objects.select_related(
            'course', 'session__classroom', 'published_version', 'active_version',
        ).get(pk=doc_pk, removed_at__isnull=True)
    except KnowledgeDocument.DoesNotExist as exc:
        raise unavailable() from exc
    require_access(user, document.course)
    preview = bool(scope.preview) if scope is not None else False
    if preview and not can_manage_course(user, document.course):
        raise unavailable()
    if document.session_id:
        require_session_access(user, document.session, document.course, manage=preview)
        if document.session.is_draft and not preview:
            raise unavailable()
    manager = can_manage_course(user, document.course)
    if not document.is_published and not (preview and manager):
        raise unavailable()
    allowed_version = (document.active_version or document.published_version) if (preview and manager) else document.published_version
    if not allowed_version or allowed_version.removed_at or allowed_version.document_id != document.pk:
        raise unavailable()
    if allowed_version.status not in ('EXTRACTED', 'READY'):
        raise DocumentError('SCOPE_CHANGED', 'Phiên bản nguồn trích dẫn chưa sẵn sàng.', 409)
    if str(allowed_version.pk) != ver_pk:
        raise DocumentError('SCOPE_CHANGED', 'Phiên bản nguồn trích dẫn đã thay đổi.', 409)
    if page_number is not None:
        if type(page_number) is not int or not 1 <= page_number <= allowed_version.page_count:
            raise DocumentError('SCOPE_CHANGED', 'Trang nguồn trích dẫn không hợp lệ.', 409)
    if scope is not None:
        from .retrieval_adapter import live_scope
        current = live_scope(user, scope)
        if ver_pk not in current.allowed_version_ids:
            raise DocumentError('SCOPE_CHANGED', 'Nguồn trích dẫn không còn trong phạm vi được phép.', 409)
    return document, allowed_version
