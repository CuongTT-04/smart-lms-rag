from django.core.exceptions import ValidationError as ModelValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.courses.enrollment_services import active_student, cancel_request, join_by_code, review_request, save_classroom, save_policy, withdraw_classroom_enrollment, remove_classroom
from apps.courses.models import AccessPolicy, Classroom, Enrollment, JoinRequest
from apps.courses.permissions import CanViewCourse
from apps.courses.selectors import get_course
from common.schema import ENROLLMENT_BAD_REQUEST as UPDATE_BAD_REQUEST, FORBIDDEN, NOT_FOUND, DetailSerializer, UNAUTHORIZED
from .serializers import ClassroomEnrollmentSerializer, ClassroomInputSerializer, ClassroomSerializer, EmptyRequestSerializer, EnrollmentSerializer, JoinByCodeSerializer, JoinRequestSerializer, JoinResultSerializer, PolicySerializer, PolicyUpdateSerializer, ReviewRequestSerializer
from .views import CourseManagementView


def service(call, **kwargs):
    try:
        return call(**kwargs)
    except ModelValidationError as error:
        raise ValidationError(error.message_dict if hasattr(error, "message_dict") else error.messages) from error
    except (Classroom.DoesNotExist, Enrollment.DoesNotExist, JoinRequest.DoesNotExist) as error:
        raise NotFound("Classroom, enrollment or join request not found.") from error


def page_response(view, queryset, serializer):
    page = view.paginate_queryset(queryset)
    data = serializer(page if page is not None else queryset, many=True).data
    return view.get_paginated_response(data) if page is not None else Response(data)


@method_decorator(never_cache, name="dispatch")
class PolicyView(CourseManagementView):
    serializer_class = PolicySerializer

    @extend_schema(
        operation_id="course_policy_retrieve", tags=["Enrollment"],
        summary='Xem chính sách tham gia khóa học',
        description='Chủ khóa học xem mức hiển thị và điều kiện tham gia. Chỉ hỗ trợ khóa miễn phí; yêu cầu xét duyệt áp dụng riêng từng lớp.',
        responses={200: PolicySerializer, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request, course_id):
        return Response(PolicySerializer(AccessPolicy.objects.get(course=self.get_course(course_id))).data)

    @extend_schema(
        operation_id="course_policy_update", tags=["Enrollment"],
        summary='Cập nhật chính sách tham gia khóa học',
        description='Chủ khóa học sửa visibility hoặc require_approval của khóa. Thiết lập cũ không thay đổi chính sách từng lớp; sửa lớp để đổi xét duyệt.',
        request=PolicyUpdateSerializer,
        examples=[OpenApiExample("Bật xét duyệt", value={"require_approval": True}, request_only=True)],
        responses={200: PolicySerializer, 400: UPDATE_BAD_REQUEST, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def patch(self, request, course_id):
        course = self.get_course(course_id)
        serializer = PolicyUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(PolicySerializer(service(save_policy, actor=request.user, course=course, changes=serializer.validated_data)).data)


class ClassroomsView(CourseManagementView):
    serializer_class = ClassroomSerializer

    @extend_schema(
        operation_id="classrooms_list", tags=["Enrollment"],
        summary='Danh sách lớp học và mã tham gia',
        description='Chủ khóa học xem danh sách lớp và mã tham gia, phân trang 20 mục. Mã lớp chỉ được cung cấp cho người quản lý khóa.',
        responses={200: ClassroomSerializer(many=True), 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request, course_id):
        return page_response(self, Classroom.objects.filter(course=self.get_course(course_id)), ClassroomSerializer)

    @extend_schema(
        operation_id="classrooms_create", tags=["Enrollment"],
        summary='Tạo lớp học trong khóa học',
        description='Chủ khóa học tạo lớp bằng tên và chính sách đăng ký. Hệ thống tự sinh mã lớp; thao tác không tự xuất bản khóa học.',
        request=ClassroomInputSerializer,
        examples=[OpenApiExample("Lớp mới", value={"name": "Lớp Python buổi tối", "is_join_enabled": True}, request_only=True)],
        responses={201: ClassroomSerializer, 400: UPDATE_BAD_REQUEST, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def post(self, request, course_id):
        course = self.get_course(course_id)
        serializer = ClassroomInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(ClassroomSerializer(service(save_classroom, actor=request.user, course=course, changes=serializer.validated_data)).data, status=201)


class ClassroomDetailView(CourseManagementView):
    serializer_class = ClassroomSerializer

    @extend_schema(operation_id='classrooms_delete', tags=['Enrollment'], summary='Xóa lớp học', description='Chủ khóa học xóa mềm lớp, buổi học và gỡ học liệu; thu hồi ghi danh, hủy yêu cầu đang chờ và giữ bản ghi nội bộ.', responses={204: None, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND})
    def delete(self, request, course_id, classroom_id):
        service(remove_classroom, actor=request.user, course=self.get_course(course_id), classroom_id=classroom_id)
        return Response(status=204)

    @extend_schema(
        operation_id="classrooms_update", tags=["Enrollment"],
        summary='Chỉnh sửa tên và chính sách riêng của lớp',
        description='Chủ khóa học sửa tên, hiển thị, mở đăng ký hoặc xét duyệt của lớp. Đóng đăng ký không thu hồi học viên đã tham gia.',
        request=ClassroomInputSerializer,
        examples=[OpenApiExample("Đóng đăng ký lớp", value={"is_join_enabled": False}, request_only=True)],
        responses={200: ClassroomSerializer, 400: UPDATE_BAD_REQUEST, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def patch(self, request, course_id, classroom_id):
        course = self.get_course(course_id)
        serializer = ClassroomInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(ClassroomSerializer(service(save_classroom, actor=request.user, course=course, classroom_id=classroom_id, changes=serializer.validated_data)).data)


class JoinCodeThrottle(UserRateThrottle):
    scope = "join_code"
    rate = "30/min"


@method_decorator(never_cache, name="dispatch")
class StudentEnrollmentView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not active_student(request.user):
            raise PermissionDenied("Only active students can use this endpoint.")


class JoinByCodeView(StudentEnrollmentView):
    serializer_class = JoinByCodeSerializer
    throttle_classes = [JoinCodeThrottle]

    @extend_schema(
        operation_id="classrooms_join", tags=["Enrollment"],
        summary='Học viên tham gia lớp bằng mã',
        description=(
            'Học viên gửi mã lớp 12 ký tự và lời nhắn tùy chọn. Vào lớp ngay hoặc chờ duyệt theo chính sách; khóa phải miễn phí, đã xuất bản và mở đăng ký.'
        ),
        examples=[OpenApiExample("Tham gia bằng mã lớp", value={"class_code": "A1B2C3D4E5F6", "message": "Em muốn tham gia lớp học."}, request_only=True)],
        responses={200: JoinResultSerializer, 201: JoinResultSerializer, 400: UPDATE_BAD_REQUEST, 401: UNAUTHORIZED, 403: FORBIDDEN, 429: DetailSerializer},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result, record, created = service(join_by_code, actor=request.user, **serializer.validated_data)
        return Response({"status": result, "enrollment": EnrollmentSerializer(record).data if result == "ENROLLED" else None, "join_request": JoinRequestSerializer(record).data if result == "PENDING" else None}, status=201 if created else 200)


class MyJoinRequestsView(StudentEnrollmentView):
    serializer_class = JoinRequestSerializer

    @extend_schema(
        operation_id="join_requests_mine", tags=["Enrollment"],
        summary='Học viên xem yêu cầu tham gia của mình',
        description='Trả yêu cầu tham gia của học viên đăng nhập cùng trạng thái và ghi chú xét duyệt. Mới nhất trước, phân trang 20 mục.',
        responses={200: JoinRequestSerializer(many=True), 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request):
        return page_response(self, JoinRequest.objects.filter(student=request.user).select_related("classroom__course", "student"), JoinRequestSerializer)


class MyEnrollmentsView(StudentEnrollmentView):
    serializer_class = EnrollmentSerializer

    @extend_schema(
        operation_id="enrollments_mine", tags=["Enrollment"],
        summary='Học viên xem các lượt ghi danh của mình',
        description='Trả lịch sử ghi danh của học viên đăng nhập, gồm lượt đang học, hoàn thành hoặc đã thu hồi. Phân trang 20 mục; lịch sử không đảm bảo quyền hiện tại.',
        responses={200: EnrollmentSerializer(many=True), 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request):
        return page_response(self, Enrollment.objects.filter(student__user=request.user).select_related("classroom__course").order_by("-enrolled_at", "id"), EnrollmentSerializer)


class CancelJoinRequestView(StudentEnrollmentView):
    serializer_class = EmptyRequestSerializer

    @extend_schema(
        operation_id="join_requests_cancel", tags=["Enrollment"],
        summary='Học viên hủy yêu cầu đang chờ duyệt',
        description='Học viên hủy yêu cầu của mình khi còn chờ duyệt. Không phải thao tác rời lớp đã tham gia; hủy lại yêu cầu đã hủy vẫn thành công.',
        request=EmptyRequestSerializer,
        responses={200: JoinRequestSerializer, 400: UPDATE_BAD_REQUEST, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def post(self, request, request_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(JoinRequestSerializer(service(cancel_request, actor=request.user, request_id=request_id)).data)


class CourseJoinRequestsView(CourseManagementView):
    serializer_class = JoinRequestSerializer

    @extend_schema(
        operation_id="join_requests_list", tags=["Enrollment"],
        summary='Giáo viên xem yêu cầu tham gia khóa học',
        description='Chủ khóa học xem yêu cầu từ các lớp trong khóa, phân trang 20 mục. Lọc bằng status để xem yêu cầu chờ hoặc đã xử lý.',
        parameters=[OpenApiParameter("status", str, enum=JoinRequest.Status.values, description="Lọc trạng thái yêu cầu (tùy chọn): PENDING, APPROVED, REJECTED hoặc CANCELED.")],
        responses={200: JoinRequestSerializer(many=True), 400: UPDATE_BAD_REQUEST, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request, course_id):
        queryset = JoinRequest.objects.filter(classroom__course=self.get_course(course_id), classroom__removed_at__isnull=True).select_related("classroom__course", "student")
        state = request.query_params.get("status")
        if state:
            if state not in JoinRequest.Status.values:
                raise ValidationError({"status": ["Invalid request status."]})
            queryset = queryset.filter(status=state)
        return page_response(self, queryset, JoinRequestSerializer)


class ReviewJoinRequestView(CourseManagementView):
    serializer_class = ReviewRequestSerializer

    @extend_schema(
        operation_id="join_requests_review", tags=["Enrollment"],
        summary='Giáo viên chấp nhận hoặc từ chối yêu cầu',
        description=(
            'Chủ khóa học gửi decision=approve/reject và ghi chú tùy chọn. Chấp nhận cấp quyền khóa học và ghi danh; không đảo quyết định đã xử lý.'
        ),
        request=ReviewRequestSerializer,
        examples=[
            OpenApiExample("Chấp nhận", value={"decision": "approve", "review_note": "Chào mừng em đến với lớp!"}, request_only=True),
            OpenApiExample("Từ chối", value={"decision": "reject", "review_note": "Em vui lòng kiểm tra lại lớp đăng ký."}, request_only=True),
        ],
        responses={200: JoinRequestSerializer, 400: UPDATE_BAD_REQUEST, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def post(self, request, course_id, request_id):
        course = self.get_course(course_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(JoinRequestSerializer(service(review_request, actor=request.user, course=course, request_id=request_id, **serializer.validated_data)).data)


class ClassroomEnrollmentsView(CourseManagementView):
    serializer_class = ClassroomEnrollmentSerializer

    @extend_schema(
        operation_id="classroom_enrollments_list", tags=["Enrollment"],
        summary='Giáo viên xem học viên theo lớp',
        description='Chủ khóa học xem ghi danh trong đúng lớp, phân trang 20 mục. Lọc status=ACTIVE/COMPLETED/WITHDRAWN; dùng enrollment_id để thu hồi riêng lớp.',
        parameters=[OpenApiParameter("status", str, enum=Enrollment.Status.values, description="Trạng thái ghi danh cần lọc; bỏ trống để xem tất cả.")],
        responses={200: ClassroomEnrollmentSerializer(many=True), 400: UPDATE_BAD_REQUEST, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request, course_id, classroom_id):
        course = self.get_course(course_id)
        if not Classroom.objects.filter(pk=classroom_id, course=course).exists():
            raise NotFound("Classroom not found in this course.")
        queryset = Enrollment.objects.filter(classroom_id=classroom_id).select_related(
            "classroom__course", "student__user"
        ).order_by("enrolled_at", "id")
        state = request.query_params.get("status")
        if state:
            if state not in Enrollment.Status.values:
                raise ValidationError({"status": ["Invalid enrollment status."]})
            queryset = queryset.filter(status=state)
        return page_response(self, queryset, ClassroomEnrollmentSerializer)


class ClassroomEnrollmentRevokeView(CourseManagementView):
    @extend_schema(
        operation_id="classroom_enrollments_revoke", tags=["Enrollment"],
        summary='Thu hồi ghi danh của học viên ở một lớp',
        description='Chủ khóa học thu hồi ghi danh trong đúng lớp và giữ lịch sử. Quyền khóa học chỉ bị thu hồi khi học viên không còn lớp hợp lệ khác.',
        request=None,
        responses={204: None, 400: UPDATE_BAD_REQUEST, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def delete(self, request, course_id, classroom_id, enrollment_id):
        course = self.get_course(course_id)
        service(withdraw_classroom_enrollment, actor=request.user, course=course,
                classroom_id=classroom_id, enrollment_id=enrollment_id)
        return Response(status=204)


class MyCourseClassroomsView(StudentEnrollmentView):
    permission_classes = [IsAuthenticated, CanViewCourse]
    serializer_class = EnrollmentSerializer

    @extend_schema(
        operation_id="course_my_classrooms", tags=["Enrollment"],
        summary='Học viên xem các lớp của mình trong khóa học',
        description='Trả các lớp đang học hoặc đã hoàn thành của học viên trong khóa còn quyền truy cập, phân trang 20 mục; không trả mã lớp.',
        responses={200: EnrollmentSerializer(many=True), 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request, course_id):
        course = get_course(course_id=course_id)
        if course is None:
            raise NotFound("Course not found.")
        self.check_object_permissions(request, course)
        queryset = Enrollment.objects.filter(classroom__course=course, student__user=request.user).exclude(
            status=Enrollment.Status.WITHDRAWN
        ).select_related("classroom__course").order_by("enrolled_at", "id")
        return page_response(self, queryset, EnrollmentSerializer)
