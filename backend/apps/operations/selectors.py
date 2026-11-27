"""Platform overview: current snapshots and explicitly dated submission activity."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count
from django.utils import timezone

from apps.courses.assessment_models import AssessmentAttempt
from apps.courses.models import Classroom, Course
from apps.users.models import TeacherApproval, User

PLATFORM_TIMEZONE = ZoneInfo('Asia/Ho_Chi_Minh')


def platform_overview(start_date, end_date):
    start = datetime.combine(start_date, time.min, tzinfo=PLATFORM_TIMEZONE)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=PLATFORM_TIMEZONE)
    return dict(as_of=timezone.now(), timezone=str(PLATFORM_TIMEZONE),
        scope='PLATFORM_AGGREGATE', period=dict(start=start, end_exclusive=end),
        accounts=dict(total=User.objects.count(), by_role=list(User.objects.values('role').annotate(count=Count('pk')).order_by('role')),
                      by_status=list(User.objects.values('status').annotate(count=Count('pk')).order_by('status'))),
        courses=Course.objects.count(), classrooms=Classroom.objects.count(),
        teacher_approvals=list(TeacherApproval.objects.filter(teacher_profile__user__role='TEACHER').values('status').annotate(count=Count('pk')).order_by('status')),
        submitted_attempts=AssessmentAttempt.objects.filter(submitted_at__gte=start, submitted_at__lt=end).count(),
        definitions=dict(accounts='Số tài khoản hiện tại, không lọc theo ngày.',
            courses='Số khóa hiện tại, gồm bản nháp và khóa lưu trữ.', classrooms='Số lớp hiện tại chưa bị gỡ.',
            teacher_approvals='Trạng thái duyệt của hồ sơ hiện mang vai trò giáo viên.',
            submitted_attempts='Lượt có submitted_at trong [đầu ngày bắt đầu, đầu ngày sau ngày kết thúc), không tính bản nháp chưa nộp.'))
