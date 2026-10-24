from rest_framework.exceptions import NotFound
from apps.courses.models import Course, Classroom, ClassroomSession
from apps.courses.permissions import can_view_course, can_view_classroom, can_manage_course


def resolve_target(item, user):
    context = item.context
    if user.role == 'STUDENT' and item.kind in ['JOIN_REJECTED', 'ENROLLMENT_WITHDRAWN', 'ACCESS_CHANGED']:
        return {'enrollment': True}
    if context.get('admin'):
        if user.role != 'ADMIN':
            raise NotFound('Nội dung không còn khả dụng.')
        detail = {}
        if context.get('user_id'):
            from apps.users.models import User
            detail = User.objects.filter(pk=context['user_id']).values('username', 'email', 'full_name', 'role', 'status').first() or {}
        return {'admin': True, 'account': detail, 'report': context.get('report', {})}
    course_id = context.get('course_id')
    if not course_id:
        return {}
    course = Course.objects.filter(pk=course_id).first()
    if not course or not can_view_course(user, course):
        raise NotFound('Bạn không còn quyền truy cập nội dung này.')
    manager = can_manage_course(user, course)
    room = None
    if context.get('classroom_id'):
        room = Classroom.objects.select_related('course').filter(pk=context['classroom_id'], course=course).first()
        if not room or not can_view_classroom(user, room):
            raise NotFound('Lớp học không còn khả dụng.')
    if context.get('session_id'):
        session = ClassroomSession.objects.filter(pk=context['session_id'], classroom_id=context.get('classroom_id'), removed_at__isnull=True).first()
        if not session or (session.is_draft and not manager):
            raise NotFound('Buổi học không còn khả dụng.')
    resources = [('video_id', 'courses.SessionVideo'), ('assessment_id', 'courses.Assessment'), ('document_id', 'documents.KnowledgeDocument')]
    from django.apps import apps
    for key, label in resources:
        if not context.get(key):
            continue
        resource = apps.get_model(label).objects.filter(pk=context[key], removed_at__isnull=True).first()
        if not resource or (not manager and not resource.is_published):
            raise NotFound('Nội dung đã bị gỡ hoặc thu hồi công bố.')
        if key == 'document_id':
            if resource.course_id != course.pk or str(resource.session_id or '') != context.get('session_id', ''):
                raise NotFound('Học liệu không còn thuộc phạm vi này.')
        elif str(resource.session_id) != context.get('session_id'):
            raise NotFound('Nội dung không còn thuộc buổi học này.')
    if context.get('announcement_id'):
        from apps.courses.models import ClassroomAnnouncement
        if not ClassroomAnnouncement.objects.filter(pk=context['announcement_id'], classroom_id=context.get('classroom_id')).exists():
            raise NotFound('Bảng tin không còn khả dụng.')
    return {**context, **({'classroom_name': room.name} if room else {})}


def visible_content(item, user):
    if item.kind in ['JOIN_REJECTED', 'ENROLLMENT_WITHDRAWN', 'ACCESS_CHANGED', 'COMMENT_MUTED', 'COMMENT_UNMUTED']:
        return item.title, item.body or item.context.get('scope_name', '')
    try:
        resolve_target(item, user)
        return item.title, item.body or item.context.get('scope_name', '')
    except NotFound:
        return 'Hoạt động liên quan đến tài khoản của bạn', 'Nội dung đã thay đổi hoặc bạn không còn quyền truy cập.'

