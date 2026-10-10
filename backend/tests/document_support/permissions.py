from .models import Membership
def can_manage_course(user,course):
    return bool(user.is_authenticated and user.is_active and course.teacher_id==user.pk)
def can_read_course(user,course):
    return bool(user.is_authenticated and user.is_active and (can_manage_course(user,course) or Membership.objects.filter(course=course,user=user,active=True).exists()))
