"""Persist business transitions inside the caller's transaction, including offline recipients."""
import uuid
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from .context import actor as current_actor
from .services import notify

WATCHED = {
    'users.User', 'courses.Course', 'courses.CourseMember', 'courses.Classroom',
    'courses.Enrollment', 'courses.JoinRequest', 'courses.ClassroomSession',
    'courses.ClassroomAnnouncement', 'courses.AnnouncementComment', 'courses.ClassroomCommentMute',
    'courses.SessionVideo', 'courses.Assessment', 'courses.AssessmentAttempt',
    'documents.KnowledgeDocument',
}


def owners(course):
    return list(course.memberships.filter(role='OWNER', status='ACTIVE', user__is_active=True).values_list('user_id', flat=True))


def students(course, room=None):
    from apps.users.models import User
    query = User.objects.filter(role='STUDENT', is_active=True, status='ACTIVE',
        course_memberships__course=course, course_memberships__status='ACTIVE')
    if not type(course).objects.filter(pk=course.pk, status='PUBLISHED').exists():
        return []
    if room:
        query = query.filter(student_profile__enrollments__classroom=room,
                             student_profile__enrollments__status__in=['ACTIVE', 'COMPLETED'])
    return list(query.distinct().values_list('pk', flat=True))


def scope(course, room=None, session=None):
    result = {'course_id': str(course.pk), 'scope_name': ' · '.join(value for value in [course.title, room.name if room else None] if value)}
    if room:
        result['classroom_id'] = str(room.pk)
    if session:
        result['session_id'] = str(session.pk)
    return result


@receiver(pre_save)
def snapshot(sender, instance, raw=False, **kwargs):
    if raw or sender._meta.label not in WATCHED:
        return
    from django.apps import apps
    if sender is not apps.get_model(sender._meta.label):
        return  # Ignore historical migration models.
    instance._notification_before = sender._base_manager.filter(pk=instance.pk).values().first() if instance.pk else None


@receiver(post_save)
def transition(sender, instance, created, raw=False, **kwargs):
    label = sender._meta.label
    if raw or label not in WATCHED:
        return
    from django.apps import apps
    if sender is not apps.get_model(label):
        return
    old = getattr(instance, '_notification_before', None) or {}
    actor = current_actor.get()
    key = str(uuid.uuid4())
    def changed(*fields):
        saved = kwargs.get('update_fields')
        return not created and any(old.get(field) != getattr(instance, field) for field in fields
            if saved is None or field in saved or (field.endswith('_id') and field[:-3] in saved))
    def emit(kind, title, recipients, context, by=actor, body=''):
        notify(event_id=f'{key}:{kind}', recipients=recipients, actor=by, kind=kind, title=title, body=body, context=context)

    if label == 'users.User':
        if created or changed('status'):
            admins = sender.objects.filter(role='ADMIN', is_active=True).values_list('pk', flat=True)
            emit('USER_REGISTERED' if created else 'USER_STATUS', 'Có tài khoản mới' if created else 'Trạng thái tài khoản đã thay đổi', admins, {'admin': True, 'user_id': str(instance.pk)}, by=instance if created else actor, body=instance.username)
            if not created:
                emit('ACCOUNT_STATUS', 'Tài khoản của bạn đã được khôi phục' if instance.status == 'ACTIVE' else 'Tài khoản của bạn đã bị tạm khóa', [instance.pk], {})
        return
    if label == 'courses.CourseMember':
        if changed('status') and instance.role == 'STUDENT':
            emit('ACCESS_CHANGED', 'Quyền truy cập khóa học của bạn đã thay đổi', [instance.user_id], scope(instance.course))
        return
    if label == 'courses.Course':
        if changed('title', 'description', 'status') and old.get('status') == 'PUBLISHED':
            from apps.users.models import User
            recipients = User.objects.filter(course_memberships__course=instance, course_memberships__status='ACTIVE', role='STUDENT').values_list('pk', flat=True)
            emit('COURSE_UPDATED', 'Khóa học của bạn đã được cập nhật', recipients, scope(instance))
        return
    if label == 'courses.Classroom':
        if changed('name', 'is_join_enabled', 'visibility', 'require_approval', 'removed_at'):
            emit('CLASSROOM_UPDATED', 'Thông tin lớp học đã thay đổi', students(instance.course, instance), scope(instance.course, instance))
        return
    if label in ('courses.Enrollment', 'courses.JoinRequest', 'courses.ClassroomCommentMute'):
        room = instance.classroom; context = scope(room.course, room)
        if label == 'courses.Enrollment':
            if created or changed('status'):
                if instance.status in ['ACTIVE', 'COMPLETED']:
                    emit('CLASS_JOINED', 'Có học viên tham gia lớp', owners(room.course), context, by=instance.student.user)
                else:
                    emit('ENROLLMENT_WITHDRAWN', 'Ghi danh lớp học của bạn đã bị thu hồi', [instance.student.user_id], context)
        elif label == 'courses.JoinRequest':
            if created:
                emit('JOIN_REQUESTED', 'Có yêu cầu tham gia lớp', owners(room.course), context, by=instance.student)
            elif changed('status'):
                if instance.status in ['APPROVED', 'REJECTED']:
                    emit('JOIN_'+instance.status, 'Yêu cầu tham gia lớp đã được '+('duyệt' if instance.status == 'APPROVED' else 'từ chối'), [instance.student_id], context)
                elif instance.status == 'CANCELED':
                    emit('JOIN_CANCELED', 'Yêu cầu tham gia lớp đã được hủy', owners(room.course), context)
        elif created:
            emit('COMMENT_MUTED', 'Bạn đã bị tắt quyền bình luận trong lớp', [instance.user_id], context)
        return
    if label in ('courses.ClassroomAnnouncement', 'courses.AnnouncementComment'):
        post = instance if label.endswith('ClassroomAnnouncement') else instance.announcement
        room = post.classroom; context = {**scope(room.course, room), 'announcement_id': str(post.pk)}
        if label.endswith('ClassroomAnnouncement'):
            if created or changed('content', 'link'):
                emit('ANNOUNCEMENT_CREATED' if created else 'ANNOUNCEMENT_UPDATED', 'Bảng tin lớp có thông báo mới' if created else 'Thông báo của lớp đã cập nhật', students(room.course, room), context, by=post.author)
        elif created:
            recipients = set(owners(room.course))
            if instance.parent_id:
                recipients.add(instance.parent.author_id)
            eligible = set(students(room.course, room)) | set(owners(room.course))
            emit('COMMENT_REPLY' if instance.parent_id else 'COMMENT_CREATED', 'Có trả lời bình luận của bạn' if instance.parent_id else 'Có bình luận mới trong lớp', recipients & eligible,
                 {**context, 'comment_id': str(instance.pk)}, by=instance.author)
        elif changed('deleted_at'):
            emit('COMMENT_REMOVED', 'Bình luận của bạn đã bị xóa', [instance.author_id], context)
        return
    if label == 'courses.AssessmentAttempt':
        assessment = instance.assessment; session = assessment.session; room = session.classroom
        context = {**scope(room.course, room, session), 'assessment_id': str(assessment.pk), 'attempt_id': str(instance.pk)}
        if changed('status') and instance.status == 'SUBMITTED':
            emit('ATTEMPT_SUBMITTED', 'Có bài làm mới được nộp', owners(room.course), context, by=instance.student)
            count = instance.events.count()
            if count:
                emit('TEST_VIOLATIONS', 'Bài kiểm tra có ghi nhận vi phạm', owners(room.course), context, by=instance.student, body=f'{count} sự kiện; xem dashboard để xử lý.')
        if instance.status == 'SUBMITTED' and (instance.grade_published or assessment.results_published) and (created or changed('grade_published', 'score', 'feedback')):
            emit('GRADE_PUBLISHED', 'Bài làm của bạn có điểm hoặc nhận xét mới', [instance.student_id], context)
        return
    if label == 'documents.KnowledgeDocument':
        course = instance.course; session = instance.session; room = session.classroom if session else None
        context = {**scope(course, room, session), 'document_id': str(instance.pk)}
        noun, field = 'Học liệu', 'DOCUMENT'
    else:
        session = instance if label == 'courses.ClassroomSession' else instance.session
        room = session.classroom; course = room.course
        context = scope(course, room, session)
        if label == 'courses.ClassroomSession':
            was_live = bool(old) and not old.get('is_draft', True) and not old.get('removed_at')
            live = not instance.is_draft and not instance.removed_at
            if live and not was_live:
                emit('SESSION_PUBLISHED', 'Lớp có buổi học mới', students(course, room), context)
            elif was_live and (changed('title', 'removed_at')):
                emit('SESSION_UPDATED', 'Buổi học đã được cập nhật', students(course, room), context)
            return
        if label == 'courses.SessionVideo':
            noun, field = 'Video', 'VIDEO'; context['video_id'] = str(instance.pk)
        else:
            noun, field = 'Bài tập', 'ASSESSMENT'; context['assessment_id'] = str(instance.pk)
            if changed('results_published') and instance.results_published:
                for attempt in instance.attempts.filter(status='SUBMITTED'):
                    emit('RESULTS_PUBLISHED', 'Giáo viên đã công bố kết quả bài tập', [attempt.student_id], context)
    was_live = bool(old.get('is_published')) and not old.get('removed_at')
    live = instance.is_published and not instance.removed_at
    if label == 'documents.KnowledgeDocument':
        live = live and bool(instance.published_version_id)
        was_live = was_live and bool(old.get('published_version_id'))
    if session and session.is_draft:
        return
    if live and not was_live:
        emit(field+'_PUBLISHED', noun+' mới đã được công bố', students(course, room), context)
    elif was_live and not live:
        emit(field+'_WITHDRAWN', noun+' đã được gỡ hoặc thu hồi công bố', students(course, room), context)
    elif live and changed(*[f for f in ['title', 'description', 'due_at', 'published_version_id', 'material_policy'] if hasattr(instance, f)]):
        emit(field+'_UPDATED', noun+' đã được cập nhật', students(course, room), context)


@receiver(post_delete)
def unmute(sender, instance, **kwargs):
    if sender._meta.label == 'courses.ClassroomCommentMute':
        origin = kwargs.get('origin')
        if origin is not None and getattr(origin, 'model', type(origin)) is not sender:
            return  # Cascade deletion is not a teacher's explicit unmute action.
        room = instance.classroom
        notify(event_id=uuid.uuid4(), recipients=[instance.user_id], actor=current_actor.get(),
               kind='COMMENT_UNMUTED', title='Bạn đã được khôi phục quyền bình luận trong lớp', context=scope(room.course, room))
