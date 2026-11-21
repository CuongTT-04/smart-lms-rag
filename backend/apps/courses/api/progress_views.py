from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import Classroom
from apps.courses.progress_services import classroom_progress, mark_document_complete
from common.schema import ENROLLMENT_BAD_REQUEST, FORBIDDEN, NOT_FOUND, UNAUTHORIZED
from .progress_serializers import ClassroomProgressSerializer
from .serializers import EmptyRequestSerializer


class ClassroomProgressBaseView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ClassroomProgressSerializer

    def ensure_classroom_in_course(self, course_id, classroom_id):
        if not Classroom.objects.filter(pk=classroom_id, course_id=course_id, removed_at__isnull=True).exists():
            raise NotFound('Lớp học không khả dụng.')


class ClassroomProgressView(ClassroomProgressBaseView):
    http_method_names = ['get', 'head', 'options']

    @extend_schema(
        tags=['Classrooms'],
        operation_id='classroom_progress_retrieve',
        summary='Xem tiến độ học tập trong lớp',
        description='Học viên đang ghi danh xem tiến độ tổng và trạng thái từng hoạt động theo buổi học. Giáo viên sử dụng API kết quả lớp.',
        responses={200: ClassroomProgressSerializer, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request, course_id, classroom_id):
        self.ensure_classroom_in_course(course_id, classroom_id)
        data = classroom_progress(actor=request.user, classroom_id=classroom_id)
        return Response(data)


class DocumentCompleteView(ClassroomProgressBaseView):
    http_method_names = ['post', 'options']
    serializer_class = EmptyRequestSerializer

    @extend_schema(
        tags=['Classrooms'],
        operation_id='classroom_progress_document_complete',
        summary='Đánh dấu đã học tài liệu PDF',
        description='Học viên xác nhận đã học phiên bản PDF đang công bố trong lớp. Chỉ nhận body rỗng; trả về tiến độ cập nhật và chống trùng lặp.',
        request=EmptyRequestSerializer,
        responses={
            200: ClassroomProgressSerializer,
            400: ENROLLMENT_BAD_REQUEST,
            401: UNAUTHORIZED,
            403: FORBIDDEN,
            404: NOT_FOUND,
        },
    )
    def post(self, request, course_id, classroom_id, version_id):
        self.ensure_classroom_in_course(course_id, classroom_id)
        serializer = EmptyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = mark_document_complete(actor=request.user, classroom_id=classroom_id, version_id=version_id)
        return Response(data)
