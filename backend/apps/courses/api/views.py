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
        operation_id="courses_list", tags=["Courses"], summary="Danh sách khóa học được phép truy cập",
        description=(
            "Yêu cầu Bearer JWT. Phân trang 20 bản ghi/trang, chuyển trang bằng query page. "
            "Giáo viên xem khóa học mình là OWNER đang ACTIVE ở mọi trạng thái; học viên chỉ xem "
            "khóa học PUBLISHED có thành viên STUDENT đang ACTIVE. ADMIN không tự có quyền truy cập. "
            "Danh sách rỗng trả 200 với results=[]. Không trả mã lớp; đây không phải danh mục mọi khóa học công khai."
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
        operation_id="courses_create", tags=["Courses"], summary="Giáo viên tạo khóa học nháp",
        description="Chỉ giáo viên (TEACHER) đang hoạt động. title bắt buộc, tối đa 255 ký tự; description tùy chọn, cho phép rỗng. Tạo khóa học DRAFT, thành viên OWNER duy nhất, chính sách miễn phí mặc định và một lớp mặc định trong cùng giao dịch. Không gửi owner_id hay status. Sau khi tạo, dùng API lớp học để lấy mã lớp và PATCH khóa học sang PUBLISHED trước khi học viên tham gia.",
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
        operation_id="courses_retrieve", tags=["Courses"], summary="Xem chi tiết khóa học",
        description="Giáo viên là chủ khóa học hoặc học viên có thành viên STUDENT đang ACTIVE trong khóa học PUBLISHED. Dùng id từ danh sách khóa học làm course_id. Quyền tài khoản và thành viên được kiểm tra mỗi lần gọi; thu hồi quyền có hiệu lực ngay cả khi JWT còn hạn. Không đủ quyền trả 403, khóa học không tồn tại trả 404.",
        responses={200: CourseSerializer, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request, course_id):
        course = self.get_course(course_id)
        return Response(self.get_serializer(course).data)

    @extend_schema(
        operation_id="courses_update", tags=["Courses"], summary="Cập nhật hoặc xuất bản khóa học",
        description="Chỉ giáo viên đang hoạt động và là OWNER đang ACTIVE. Gửi ít nhất một trường title, description hoặc status; trường không gửi được giữ nguyên. status nhận DRAFT (nháp), PUBLISHED (xuất bản), ARCHIVED (lưu trữ). Học viên chỉ truy cập/tham gia khi khóa học PUBLISHED. Không hỗ trợ chuyển chủ khóa học hay cập nhật chính sách tham gia qua endpoint này.",
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
        operation_id="course_members_list", tags=["Course Members"], summary="Danh sách thành viên khóa học",
        description="Chỉ chủ khóa học. Phân trang 20 bản ghi/trang bằng query page; gồm cả thành viên ACTIVE, SUSPENDED và REMOVED. id là mã bản ghi thành viên (member_id), khác user.id. Dùng member_id để thu hồi quyền học viên. Không còn POST cấp quyền trực tiếp; học viên phải tham gia bằng mã lớp và được duyệt nếu chính sách yêu cầu.",
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
        operation_id="course_members_revoke", tags=["Course Members"], summary="Thu hồi quyền truy cập của học viên",
        description=(
            "Chỉ chủ khóa học. member_id là UUID bản ghi thành viên trong khóa học, không phải UUID người dùng. "
            "Không gửi body. Chuyển thành viên STUDENT sang REMOVED và các lượt ghi danh của học viên "
            "trong khóa học sang WITHDRAWN; không xóa tài khoản hoặc lịch sử. Thành công trả 204 không có body; "
            "gọi lại vẫn trả 204. Không thể thu hồi OWNER. Học viên muốn tham gia lại phải gửi mã lớp và chờ chủ khóa học duyệt."
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
