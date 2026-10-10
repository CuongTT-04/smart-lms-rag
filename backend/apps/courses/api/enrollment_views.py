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
        summary="Xem chính sách tham gia khóa học",
        description="Chỉ giáo viên đang hoạt động và là chủ khóa học (OWNER). Trả về mức hiển thị, loại truy cập, giá và điều kiện tham gia. Hiện chỉ hỗ trợ khóa học miễn phí, vào lớp bằng mã; Điều kiện xét duyệt hiện áp dụng theo require_approval của từng Classroom. PUBLIC không đồng nghĩa với quyền xem nội dung khi chưa là thành viên.",
        responses={200: PolicySerializer, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request, course_id):
        return Response(PolicySerializer(AccessPolicy.objects.get(course=self.get_course(course_id))).data)

    @extend_schema(
        operation_id="course_policy_update", tags=["Enrollment"],
        summary="Cập nhật chính sách tham gia khóa học",
        description="Chỉ chủ khóa học. Gửi ít nhất một trong hai trường require_approval hoặc visibility (PUBLIC/PRIVATE). Không nhận price, access_type hay require_class_code. Thiết lập require_approval ở endpoint này được giữ để tương thích dữ liệu cũ; không thay đổi chính sách của các lớp. Dùng PATCH classroom để thay đổi xét duyệt riêng lớp. Tắt duyệt không tự chấp nhận yêu cầu PENDING cũ; thành viên bị đình chỉ/thu hồi vẫn phải được duyệt lại.",
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
        summary="Danh sách lớp học và mã tham gia",
        description="Chỉ chủ khóa học. Danh sách phân trang 20 bản ghi/trang, dùng query page để chuyển trang. Mỗi lớp có id (classroom_id), class_code để chia sẻ cho học viên và is_join_enabled để biết lớp còn nhận đăng ký không. Mã lớp không được công khai trong API danh sách khóa học.",
        responses={200: ClassroomSerializer(many=True), 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request, course_id):
        return page_response(self, Classroom.objects.filter(course=self.get_course(course_id)), ClassroomSerializer)

    @extend_schema(
        operation_id="classrooms_create", tags=["Enrollment"],
        summary="Tạo lớp học trong khóa học",
        description="Chỉ chủ khóa học. name bắt buộc, tối đa 255 ký tự; is_join_enabled tùy chọn, mặc định true. visibility mặc định PRIVATE, require_approval mặc định false, áp dụng riêng lớp. Server tự sinh mã lớp duy nhất gồm 12 ký tự hệ thập lục phân; không gửi class_code hay course_id trong body. Trả về 201 cùng thông tin lớp và mã tham gia. Tạo lớp không tự xuất bản khóa học.",
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

    @extend_schema(operation_id='classrooms_delete', tags=['Enrollment'], summary='Xóa lớp học', description='Chỉ chủ khóa học được xóa lớp thuộc đúng khóa. Xóa mềm lớp cùng các buổi học, gỡ học liệu và hủy yêu cầu tham gia đang chờ. Các ghi danh được thu hồi; bản ghi và tệp gốc được giữ nội bộ.', responses={204: None, 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND})
    def delete(self, request, course_id, classroom_id):
        service(remove_classroom, actor=request.user, course=self.get_course(course_id), classroom_id=classroom_id)
        return Response(status=204)

    @extend_schema(
        operation_id="classrooms_update", tags=["Enrollment"],
        summary="Chỉnh sửa tên và chính sách riêng của lớp",
        description="Chỉ chủ khóa học. classroom_id phải thuộc course_id trên đường dẫn. Gửi ít nhất một trường name, is_join_enabled, visibility (PUBLIC/PRIVATE) hoặc require_approval; các thay đổi được lưu nguyên tử và chỉ áp dụng cho lớp này; không thể đổi mã lớp. is_join_enabled=false chặn lượt tham gia mới và thao tác chấp nhận yêu cầu đang chờ, nhưng không thu hồi quyền của học viên đã tham gia.",
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
        summary="Học viên tham gia lớp bằng mã",
        description=(
            "**Quyền:** học viên (STUDENT) đang hoạt động, xác thực bằng Bearer JWT. Không gửi student_id; hệ thống lấy tài khoản từ token.\n\n"
            "**Đầu vào:** class_code bắt buộc, 12 ký tự 0-9/A-F, không phân biệt hoa thường; message tùy chọn, tối đa 2000 ký tự. Thay mã trong ví dụ bằng mã thật do giáo viên cung cấp.\n\n"
            "**Điều kiện:** khóa học FREE, giá 0, đã PUBLISHED, lớp mở đăng ký và chủ khóa học còn hoạt động. Mã sai hoặc không đáp ứng điều kiện trả 400.\n\n"
            "**Kết quả:** ENROLLED kèm enrollment nếu vào ngay; PENDING kèm join_request nếu cần duyệt. Trường còn lại là null. Thành viên SUSPENDED/REMOVED hoặc lượt học WITHDRAWN luôn cần duyệt lại. Yêu cầu PENDING cũ không bị bỏ qua khi tắt chế độ duyệt.\n\n"
            "Tạo mới trả 201; gửi lại khi đã tham gia hoặc đã có yêu cầu chờ trả 200, không tạo trùng. Điều kiện nhận đăng ký vẫn được kiểm tra khi gửi lại. Giới hạn 30 yêu cầu/phút/tài khoản; vượt giới hạn trả 429."
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
        summary="Học viên xem yêu cầu tham gia của mình",
        description="Chỉ học viên đang hoạt động. Trả về yêu cầu của chính tài khoản đăng nhập, gồm PENDING (chờ duyệt), APPROVED (đã chấp nhận), REJECTED (bị từ chối), CANCELED (đã hủy), thông tin lớp và ghi chú xét duyệt. Mới nhất trước, phân trang 20 bản ghi/trang bằng query page. Không hỗ trợ lọc status ở endpoint này. Lấy id trong results để hủy yêu cầu còn PENDING.",
        responses={200: JoinRequestSerializer(many=True), 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request):
        return page_response(self, JoinRequest.objects.filter(student=request.user).select_related("classroom__course", "student"), JoinRequestSerializer)


class MyEnrollmentsView(StudentEnrollmentView):
    serializer_class = EnrollmentSerializer

    @extend_schema(
        operation_id="enrollments_mine", tags=["Enrollment"],
        summary="Học viên xem các lượt ghi danh của mình",
        description="Chỉ học viên đang hoạt động. Trả về các lượt ghi danh theo lớp của chính tài khoản đăng nhập, bao gồm ACTIVE, COMPLETED và WITHDRAWN; có tiến độ và thời điểm tham gia/hoàn thành. Mới nhất trước, phân trang 20 bản ghi/trang bằng query page. Đây là lịch sử ghi danh, không đảm bảo quyền truy cập hiện tại; dùng GET /api/courses/ để lấy khóa học được phép xem. Yêu cầu PENDING chưa tạo lượt ghi danh.",
        responses={200: EnrollmentSerializer(many=True), 401: UNAUTHORIZED, 403: FORBIDDEN, 404: NOT_FOUND},
    )
    def get(self, request):
        return page_response(self, Enrollment.objects.filter(student__user=request.user).select_related("classroom__course").order_by("-enrolled_at", "id"), EnrollmentSerializer)


class CancelJoinRequestView(StudentEnrollmentView):
    serializer_class = EmptyRequestSerializer

    @extend_schema(
        operation_id="join_requests_cancel", tags=["Enrollment"],
        summary="Học viên hủy yêu cầu đang chờ duyệt",
        description="Chỉ học viên đang hoạt động, chỉ hủy yêu cầu của mình. Lấy request_id từ danh sách yêu cầu cá nhân; gửi body {} (không có trường dữ liệu). PENDING chuyển thành CANCELED và trả 200; hủy lại CANCELED vẫn trả 200. Yêu cầu đã APPROVED/REJECTED trả 400; yêu cầu không tồn tại hoặc của người khác trả 404. Thao tác này không phải rời lớp đã tham gia.",
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
        summary="Giáo viên xem yêu cầu tham gia khóa học",
        description="Chỉ chủ khóa học. Danh sách yêu cầu của tất cả lớp thuộc course_id, gồm thông tin học viên và ghi chú. Mới nhất trước, phân trang 20 bản ghi/trang bằng query page. Dùng ?status=PENDING để lấy yêu cầu cần xử lý; bỏ status để lấy tất cả trạng thái. Giá trị status không hợp lệ trả 400. Lấy id trong results làm request_id khi xét duyệt.",
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
        summary="Giáo viên chấp nhận hoặc từ chối yêu cầu",
        description=(
            "**Quyền:** chỉ chủ khóa học; request_id phải thuộc course_id.\n\n"
            "**Đầu vào:** decision bắt buộc, approve hoặc reject; review_note tùy chọn, tối đa 2000 ký tự.\n\n"
            "**approve:** chuyển PENDING thành APPROVED, đồng thời kích hoạt thành viên STUDENT và lượt ghi danh trong một giao dịch. Kiểm tra lại khóa học miễn phí, đã xuất bản, lớp mở đăng ký và học viên còn hoạt động; không đủ điều kiện trả 400.\n\n"
            "**reject:** chuyển PENDING thành REJECTED, không cấp quyền truy cập. Trả 200 cùng yêu cầu sau xử lý, người duyệt và thời điểm duyệt.\n\n"
            "Lặp lại cùng quyết định trả 200, không cập nhật ghi chú hay cấp lại quyền đã bị thu hồi sau đó. Đảo quyết định đã xử lý hoặc duyệt yêu cầu CANCELED trả 400; yêu cầu không thuộc khóa học trả 404."
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
        summary="Giáo viên xem học viên theo lớp",
        description="Chỉ giáo viên đang hoạt động và là chủ khóa học. classroom_id phải thuộc course_id. Trả về danh sách ghi danh của riêng lớp đó, gồm thông tin học viên, trạng thái và tiến độ; phân trang 20 bản ghi/trang bằng query page. Có thể lọc status=ACTIVE, COMPLETED hoặc WITHDRAWN; bỏ status để xem tất cả. id là enrollment_id để thu hồi riêng lớp, không phải member_id hay user.id. Không hỗ trợ cấp quyền hoặc sửa tiến độ qua endpoint này.",
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
        summary="Thu hồi ghi danh của học viên ở một lớp",
        description="Chỉ chủ khóa học. Dùng enrollment_id lấy từ danh sách học viên của lớp; bản ghi phải thuộc đúng classroom_id và course_id. Không gửi body. Chuyển ghi danh sang WITHDRAWN, giữ lại lịch sử, tiến độ và thời điểm hoàn thành nếu có. Nếu học viên còn lớp ACTIVE hoặc COMPLETED khác trong cùng khóa học thì giữ nguyên quyền khóa học; nếu không còn, thành viên khóa học chuyển REMOVED. Không ảnh hưởng khóa học khác. Thành công trả 204 không có body, gọi lại vẫn trả 204. Muốn vào lại lớp đã bị thu hồi phải gửi yêu cầu và được duyệt lại. DELETE thành viên ở cấp khóa học vẫn thu hồi tất cả lớp trong khóa học.",
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
        summary="Học viên xem các lớp của mình trong khóa học",
        description="Chỉ học viên đang hoạt động, có thành viên STUDENT ACTIVE trong khóa học PUBLISHED. Trả về các lượt ghi danh ACTIVE hoặc COMPLETED của chính tài khoản trong course_id, gồm classroom_id, classroom_name và tiến độ; không lộ mã lớp hay học viên khác. Phân trang 20 bản ghi/trang bằng query page. Lớp đã bị thu hồi không xuất hiện ở đây; xem lịch sử đầy đủ qua GET /api/courses/enrollments/mine/. Danh sách và chi tiết khóa học cũng trả my_classrooms với cùng phạm vi ghi danh còn hiệu lực. Một học viên hiện có thể tham gia nhiều lớp trong cùng khóa học.",
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
