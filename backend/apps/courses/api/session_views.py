from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from apps.courses.models import Classroom, ClassroomSession
from apps.courses.permissions import can_view_classroom, can_manage_course
from apps.courses.enrollment_services import locked_course
from .serializers import StrictRequestSerializer


class SessionInput(StrictRequestSerializer):
    title = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class SessionUpdateInput(SessionInput):
    is_draft = serializers.BooleanField(required=False)

    def validate_is_draft(self, value):
        if value:
            raise serializers.ValidationError('Only finalizing a draft is supported.')
        return value


class SessionSerializer(serializers.ModelSerializer):
    material_count = serializers.SerializerMethodField()
    def get_material_count(self, obj) -> int:
        materials = obj.materials.filter(removed_at__isnull=True)
        if not can_manage_course(self.context['request'].user, obj.classroom.course):
            materials = materials.filter(is_published=True, published_version__isnull=False)
        return materials.count()
    class Meta:
        model = ClassroomSession
        fields = ['id', 'classroom_id', 'title', 'position', 'created_at', 'material_count', 'is_draft']
        read_only_fields = fields


class ClassroomSessionsView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SessionSerializer
    def room(self, request, course_id, classroom_id, manage=False):
        room = Classroom.objects.select_related('course').filter(pk=classroom_id, course_id=course_id).first()
        if not room or not (can_manage_course(request.user, room.course) if manage else can_view_classroom(request.user, room)):
            raise NotFound('Classroom unavailable.')
        return room
    @extend_schema(tags=['Classrooms'], operation_id='classroom_sessions_list', summary='Danh sách buổi học của lớp', description='Giáo viên sở hữu hoặc học viên còn quyền trong đúng lớp xem danh sách buổi học. Ghi danh lớp khác không cấp quyền xem.', responses=SessionSerializer(many=True))
    def get(self, request, course_id, classroom_id):
        room = self.room(request, course_id, classroom_id)
        page = self.paginate_queryset(room.sessions.filter(removed_at__isnull=True))
        return self.get_paginated_response(SessionSerializer(page, many=True, context={'request': request}).data)
    @extend_schema(tags=['Classrooms'], operation_id='classroom_sessions_create', summary='Tạo buổi học trong lớp', description='Chủ khóa học tạo buổi học; tên có thể để trống, tối đa 255 ký tự. Hệ thống tự gán thứ tự tiếp theo trong lớp.', request=SessionInput, responses={201: SessionSerializer})
    def post(self, request, course_id, classroom_id):
        room = self.room(request, course_id, classroom_id, manage=True)
        serializer = SessionInput(data=request.data); serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            locked_course(request.user, room.course)
            room = self.room(request, course_id, classroom_id, manage=True)
            position = (room.sessions.aggregate(last=Max('position'))['last'] or 0) + 1
            session = ClassroomSession.objects.create(classroom=room, position=position, **serializer.validated_data)
        return Response(SessionSerializer(session, context={'request': request}).data, status=201)


class ClassroomSessionDetailView(ClassroomSessionsView):
    http_method_names = ['patch', 'delete', 'options']

    @extend_schema(tags=['Classrooms'], operation_id='classroom_session_delete', summary='Xóa buổi học và gỡ học liệu', description='Chủ khóa học xóa mềm buổi học, gỡ học liệu, thu hồi công bố và hủy trích xuất. Giữ bản ghi và tệp gốc nội bộ.', responses={204: None})
    def delete(self, request, course_id, classroom_id, session_id):
        from apps.documents.services import remove_document
        room = self.room(request, course_id, classroom_id, manage=True)
        with transaction.atomic():
            locked_course(request.user, room.course)
            session = room.sessions.select_for_update().filter(pk=session_id, removed_at__isnull=True).first()
            if not session:
                raise NotFound('Session unavailable.')
            for material in session.materials.filter(removed_at__isnull=True).order_by('pk'):
                remove_document(request.user, material)
            session.removed_at = timezone.now()
            session.save(update_fields=['removed_at'])
        return Response(status=204)

    @extend_schema(tags=['Classrooms'], operation_id='classroom_session_update', summary='Cập nhật hoặc hoàn tất tạo buổi học', description='Chủ khóa học đổi tên hoặc gửi is_draft=false để hoàn tất buổi học. Không tự công bố PDF và không chuyển ngược về bản nháp.', request=SessionUpdateInput, responses=SessionSerializer)
    def patch(self, request, course_id, classroom_id, session_id):
        room = self.room(request, course_id, classroom_id, manage=True)
        serializer = SessionUpdateInput(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            locked_course(request.user, room.course)
            session = room.sessions.filter(pk=session_id, removed_at__isnull=True).first()
            if not session:
                raise NotFound('Session unavailable.')
            if 'title' in serializer.validated_data:
                session.title = serializer.validated_data['title']
            if 'is_draft' in serializer.validated_data:
                session.is_draft = False
            if serializer.validated_data:
                session.save(update_fields=list(serializer.validated_data))
        return Response(SessionSerializer(session, context={'request': request}).data)
