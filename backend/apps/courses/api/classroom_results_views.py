from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated

from apps.courses.classroom_results import (
    GRADING_STATUSES,
    SUBMISSION_STATUSES,
    classroom_results,
    export_classroom_results_workbook,
    validate_result_filters,
)
from apps.courses.models import Classroom
from apps.courses.permissions import can_manage_course, can_view_classroom
from common.schema import ENROLLMENT_BAD_REQUEST, FORBIDDEN, NOT_FOUND, UNAUTHORIZED
from .classroom_results_serializers import ClassroomResultsPageSerializer


class ClassroomResultsBaseView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ClassroomResultsPageSerializer

    def get_classroom(self, course_id, classroom_id):
        classroom = Classroom.objects.select_related('course').filter(
            pk=classroom_id, course_id=course_id, removed_at__isnull=True
        ).first()
        if not classroom:
            raise NotFound('Lớp học không khả dụng.')
        return classroom


class ClassroomResultsView(ClassroomResultsBaseView):
    http_method_names = ['get', 'head', 'options']

    @extend_schema(
        tags=['Classrooms'],
        operation_id='classroom_results_list',
        summary='Xem bảng kết quả học tập của lớp',
        description='Giáo viên sở hữu xem tổng hợp tiến độ và điểm cao nhất/lượt duy nhất của học viên có phân trang; học viên chỉ xem dòng kết quả được phép của chính mình.',
        parameters=[
            OpenApiParameter('q', str, description='Tìm theo tên hoặc tài khoản học viên.'),
            OpenApiParameter('submission_status', str, enum=list(SUBMISSION_STATUSES), description='Lọc trạng thái nộp bài.'),
            OpenApiParameter('grading_status', str, enum=list(GRADING_STATUSES), description='Lọc trạng thái chấm điểm.'),
        ],
        responses={
            200: ClassroomResultsPageSerializer,
            400: ENROLLMENT_BAD_REQUEST,
            401: UNAUTHORIZED,
            403: FORBIDDEN,
            404: NOT_FOUND,
        },
    )
    def get(self, request, course_id, classroom_id):
        self.get_classroom(course_id, classroom_id)
        filters = validate_result_filters(request.query_params)
        report = classroom_results(actor=request.user, classroom_id=classroom_id, filters=filters)
        rows = report.pop('rows')
        page = self.paginate_queryset(rows)
        response = self.get_paginated_response(page if page is not None else rows)
        response.data.update(report)
        return response


class ClassroomResultsExportView(ClassroomResultsBaseView):
    http_method_names = ['get', 'head', 'options']

    @extend_schema(
        tags=['Classrooms'],
        operation_id='classroom_results_export',
        summary='Xuất Excel kết quả học tập toàn lớp',
        description='Chỉ chủ khóa học được xuất file Excel bảng kết quả lớp theo bộ lọc hiện tại.',
        parameters=[
            OpenApiParameter('q', str, description='Tìm theo tên hoặc tài khoản học viên.'),
            OpenApiParameter('submission_status', str, enum=list(SUBMISSION_STATUSES), description='Lọc trạng thái nộp bài.'),
            OpenApiParameter('grading_status', str, enum=list(GRADING_STATUSES), description='Lọc trạng thái chấm điểm.'),
        ],
        responses={
            (200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'): bytes,
            400: ENROLLMENT_BAD_REQUEST,
            401: UNAUTHORIZED,
            403: FORBIDDEN,
            404: NOT_FOUND,
        },
    )
    def get(self, request, course_id, classroom_id):
        classroom = self.get_classroom(course_id, classroom_id)
        if not can_view_classroom(request.user, classroom):
            raise NotFound('Lớp học không khả dụng.')
        if not can_manage_course(request.user, classroom.course):
            raise PermissionDenied('Chỉ giáo viên phụ trách được xuất bảng điểm lớp.')
        filters = validate_result_filters(request.query_params)
        report = classroom_results(actor=request.user, classroom_id=classroom_id, filters=filters)
        content = export_classroom_results_workbook(report)
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="classroom-results-{classroom.pk}.xlsx"'
        response['Cache-Control'] = 'private, no-store'
        return response
