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
        if (version and version.document_id==document.pk and not version.removed_at
                and version.status in ('EXTRACTED','READY')):
            allowed.append(str(version.pk))
    return RetrievalScope(str(user.pk),str(course.pk),str(classroom.pk) if classroom else None,
        str(session.pk) if session else None,document_ids,tuple(sorted(allowed)),mode,preview)
