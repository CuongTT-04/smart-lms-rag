from rest_framework import serializers
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from .session_views import ClassroomSessionsView


class ClassPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class ClassPeopleSerializer(serializers.Serializer):
    owners = ClassPersonSerializer(many=True)
    students = ClassPersonSerializer(many=True)


class ClassroomPeopleView(ClassroomSessionsView):
    http_method_names = ['get', 'head', 'options']
    serializer_class = ClassPeopleSerializer

    @extend_schema(tags=['Classrooms'], operation_id='classroom_people_list', summary='Xem thành viên trong lớp', description='Chủ khóa học và học viên có quyền truy cập đúng lớp được xem tên giáo viên sở hữu và các học viên còn ghi danh. Không trả email, thông tin liên hệ, điểm số hoặc tiến độ của người khác.', responses={200: ClassPeopleSerializer})
    def get(self, request, course_id, classroom_id):
        room = self.room(request, course_id, classroom_id)
        owners = room.course.memberships.filter(role='OWNER', status='ACTIVE', user__is_active=True).select_related('user').order_by('user__full_name', 'user_id')
        enrollments = room.enrollments.filter(status__in=['ACTIVE', 'COMPLETED'], student__user__is_active=True, student__user__course_memberships__course=room.course, student__user__course_memberships__status='ACTIVE').select_related('student__user').order_by('student__user__full_name', 'student_id')
        def person(user):
            return {'id': user.pk, 'name': user.full_name or user.username}
        return Response({'owners': [person(item.user) for item in owners], 'students': [person(item.student.user) for item in enrollments]})
