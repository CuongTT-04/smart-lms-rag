from django.core.exceptions import ValidationError as ModelValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.models import CourseMember
from apps.courses.permissions import CanManageCourse, CanViewCourse, IsTeacher
from apps.courses.selectors import get_course, list_accessible_courses, list_course_members
from apps.courses.services import (
    create_course, revoke_student_access, update_course,
)
from common.schema import (
    COURSE_OR_PAGE_NOT_FOUND, CREATE_BAD_REQUEST, FORBIDDEN,
    NOT_FOUND, PAGE_NOT_FOUND, REVOKE_BAD_REQUEST,
    UPDATE_BAD_REQUEST,
)

from .serializers import (
    CourseCreateSerializer, CourseMemberSerializer, CourseSerializer,
    CourseUpdateSerializer,
)


@method_decorator(never_cache, name="dispatch")
class CourseListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsTeacher()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CourseCreateSerializer
        return CourseSerializer

    @extend_schema(
        operation_id="courses_list", tags=["Courses"], summary='Danh sách khóa học được phép truy cập',
        description=(
            'Trả danh sách khóa học theo quyền tài khoản, phân trang 20 mục. Giáo viên xem khóa mình sở hữu; học viên xem khóa đã xuất bản còn quyền truy cập.'
        ),
        responses={200: CourseSerializer(many=True), 403: FORBIDDEN, 404: PAGE_NOT_FOUND},
    )
    def get(self, request):
        courses = list_accessible_courses(user=request.user)
        page = self.paginate_queryset(courses)
        serializer = self.get_serializer(page if page is not None else courses, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @extend_schema(
        operation_id="courses_create", tags=["Courses"], summary='Giáo viên tạo khóa học nháp',
        description='Giáo viên tạo khóa học nháp với tên và mô tả tùy chọn; được gán làm chủ khóa học. Không tự tạo lớp; tạo lớp riêng qua API lớp học.',
        request=CourseCreateSerializer,
        examples=[OpenApiExample("Khóa học mới", value={"title": "Nhập môn Python", "description": "Khóa học Python cơ bản."}, request_only=True)],
        responses={201: CourseSerializer, 400: CREATE_BAD_REQUEST, 403: FORBIDDEN},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            course = create_course(actor=request.user, **serializer.validated_data)
        except ModelValidationError as error:
            raise ValidationError(error.message_dict) from error
        return Response(CourseSerializer(course).data, status=status.HTTP_201_CREATED)


@method_decorator(never_cache, name="dispatch")
class CourseManagementView(GenericAPIView):
    permission_classes = [IsAuthenticated, CanManageCourse]

    def get_course(self, course_id):
        course = get_course(course_id=course_id, user=self.request.user)
        if course is None:
            raise NotFound("Course not found.")
        self.check_object_permissions(self.request, course)
        return course


class CourseDetailView(CourseManagementView):
    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated(), CanViewCourse()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return CourseUpdateSerializer
        return CourseSerializer

    @extend_schema(
        operation_id="courses_retrieve", tags=["Courses"], summary='Xem chi tiết khóa học',
        description='Trả thông tin khóa học cho chủ khóa học hoặc học viên còn quyền truy cập khóa đã xuất bản.',
        responses={200: CourseSerializer, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request, course_id):
        course = self.get_course(course_id)
        return Response(self.get_serializer(course).data)

    @extend_schema(
        operation_id="courses_update", tags=["Courses"], summary='Cập nhật hoặc xuất bản khóa học',
        description='Chủ khóa học cập nhật tên, mô tả hoặc trạng thái DRAFT/PUBLISHED/ARCHIVED. Các trường không gửi được giữ nguyên.',
        request=CourseUpdateSerializer,
        examples=[OpenApiExample("Xuất bản khóa học", value={"status": "PUBLISHED"}, request_only=True)],
        responses={200: CourseSerializer, 400: UPDATE_BAD_REQUEST, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def patch(self, request, course_id):
        course = self.get_course(course_id)
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            course = update_course(
                actor=request.user, course=course, changes=serializer.validated_data
            )
        except ModelValidationError as error:
            detail = error.message_dict if hasattr(error, "message_dict") else error.messages
            raise ValidationError(detail) from error
        return Response(CourseSerializer(course).data)


class CourseMembersView(CourseManagementView):
    def get_serializer_class(self):
        return CourseMemberSerializer

    @extend_schema(
        operation_id="course_members_list", tags=["Course Members"], summary='Danh sách thành viên khóa học',
        description='Chủ khóa học xem thành viên và trạng thái quyền truy cập, phân trang 20 mục. Dùng member_id để thu hồi quyền học viên.',
        responses={200: CourseMemberSerializer(many=True), 403: FORBIDDEN, 404: COURSE_OR_PAGE_NOT_FOUND},
    )
    def get(self, request, course_id):
        course = self.get_course(course_id)
        members = list_course_members(course=course)
        page = self.paginate_queryset(members)
        serializer = self.get_serializer(page if page is not None else members, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

class CourseMemberRevokeView(CourseManagementView):
    @extend_schema(
        operation_id="course_members_revoke", tags=["Course Members"], summary='Thu hồi quyền truy cập của học viên',
        description=(
            'Chủ khóa học thu hồi quyền học viên và ghi danh trong toàn khóa; giữ lịch sử, không xóa tài khoản và không thu hồi chủ khóa học.'
        ),
        request=None,
        responses={204: None, 400: REVOKE_BAD_REQUEST, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def delete(self, request, course_id, member_id):
        course = self.get_course(course_id)
        try:
            revoke_student_access(actor=request.user, course=course, member_id=member_id)
        except CourseMember.DoesNotExist as error:
            raise NotFound("Membership not found in this course.") from error
        except ModelValidationError as error:
            raise ValidationError(error.message_dict) from error
        return Response(status=status.HTTP_204_NO_CONTENT)
