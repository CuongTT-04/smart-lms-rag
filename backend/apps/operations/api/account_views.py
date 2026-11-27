from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, Throttled, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.account_administration import (
    AccountConflict, administer_teacher_decision, create_administered_user,
    require_account_admin, update_administered_user,
)
from apps.users.api.serializers import TeacherProfileSerializer
from apps.users.models import TeacherApproval, TeacherApprovalEvent, TeacherProfile, User
from apps.users.rate_limit import check_and_increment
from apps.users.teacher_approval import ApprovalConflict


class Conflict(APIException):
    status_code = 409
    default_code = 'ADMIN_REVISION_CONFLICT'


def action(callback):
    try:
        return callback()
    except (AccountConflict, ApprovalConflict) as exc:
        raise Conflict({'code': 'ADMIN_REVISION_CONFLICT', 'message': exc.messages[0]}) from exc
    except PermissionError as exc:
        raise PermissionDenied(str(exc)) from exc
    except (User.DoesNotExist, TeacherProfile.DoesNotExist) as exc:
        raise NotFound('Không tìm thấy tài khoản phù hợp.') from exc
    except ModelValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages) from exc
    except IntegrityError as exc:
        raise ValidationError({'detail': 'Tên đăng nhập hoặc email đã tồn tại; tải lại dữ liệu.'}) from exc


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise ValidationError({'detail': 'Cần một đối tượng JSON.'})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise ValidationError({key: ['Trường này không được chấp nhận.'] for key in sorted(unknown)})
        return super().to_internal_value(data)


class PageQuery(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20)
    offset = serializers.IntegerField(min_value=0, max_value=100000, default=0)


class AccountQuery(PageQuery):
    q = serializers.CharField(max_length=100, required=False, default='', allow_blank=True)
    role = serializers.ChoiceField(choices=User.Role.choices, required=False)
    status = serializers.ChoiceField(choices=User.Status.choices, required=False)
    approval_status = serializers.ChoiceField(choices=TeacherApproval.Status.choices, required=False)
    approval_source = serializers.ChoiceField(choices=TeacherApproval.Source.choices, required=False)
    institution_id = serializers.UUIDField(required=False)
    email_verified = serializers.BooleanField(required=False)


class AccountSerializer(serializers.ModelSerializer):
    teacher_profile = TeacherProfileSerializer(read_only=True)
    email_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'full_name', 'phone', 'role', 'status', 'email_verified',
                  'email_verified_at', 'date_joined', 'last_login', 'updated_at', 'teacher_profile')
        read_only_fields = fields


class AccountPage(serializers.Serializer):
    count = serializers.IntegerField()
    results = AccountSerializer(many=True)
    next_offset = serializers.IntegerField(allow_null=True)


class WriteConfirmation(StrictSerializer):
    reason = serializers.CharField(max_length=1000)
    current_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=1024)


class AccountCreate(WriteConfirmation):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=('STUDENT', 'TEACHER'), default='STUDENT')
    institution_id = serializers.UUIDField(required=False, allow_null=True)
    institution_other_name = serializers.CharField(max_length=255, required=False, allow_blank=True)


class AccountUpdate(WriteConfirmation):
    expected_updated_at = serializers.DateTimeField()
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    email = serializers.EmailField(max_length=254, required=False)
    phone = serializers.RegexField(r'^\+?[0-9]{8,15}$', required=False, allow_blank=True, max_length=20)
    status = serializers.ChoiceField(choices=User.Status.choices, required=False)


class RoleUpdate(WriteConfirmation):
    expected_updated_at = serializers.DateTimeField()
    role = serializers.ChoiceField(choices=User.Role.choices)


class ApprovalDecision(WriteConfirmation):
    expected_revision = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=('APPROVED', 'REJECTED', 'REVOKED'))


def validated(serializer, data):
    value = serializer(data=data)
    value.is_valid(raise_exception=True)
    return dict(value.validated_data)


def page(queryset, params, serializer):
    count = queryset.count()
    start, limit = params['offset'], params['limit']
    rows = queryset[start:start + limit]
    return Response(dict(count=count, results=serializer(rows, many=True).data,
                         next_offset=start + limit if start + limit < count else None))


def account_list(request, *, teachers=False):
    require = ('view_user', 'view_teacherapproval') if teachers else ('view_user',)
    action(lambda: require_account_admin(request.user, *require))
    # Query strings are filters, not HTML checkbox forms: an omitted BooleanField
    # must stay absent rather than becoming False through QueryDict handling.
    params = validated(AccountQuery, request.query_params.dict())
    rows = User.objects.select_related('teacher_profile__institution', 'teacher_profile__approval').all()
    if teachers:
        rows = rows.filter(role='TEACHER')
    if params['q']:
        q = params['q']
        rows = rows.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(full_name__icontains=q))
    for key in ('role', 'status'):
        if key in params:
            rows = rows.filter(**{key: params[key]})
    for key in ('approval_status', 'approval_source'):
        if key in params:
            rows = rows.filter(**{'teacher_profile__approval__' + key.split('_', 1)[1]: params[key]})
    if 'institution_id' in params:
        rows = rows.filter(teacher_profile__institution_id=params['institution_id'])
    if 'email_verified' in params:
        rows = rows.filter(email_verified_at__isnull=not params['email_verified'])
    return page(rows.order_by('-date_joined', 'pk'), params, AccountSerializer)


@method_decorator(never_cache, name='dispatch')
class AccountAdminView(APIView):
    permission_classes = [IsAuthenticated]

    def mutation(self, request, *permissions):
        action(lambda: require_account_admin(request.user, *permissions))
        allowed, retry = check_and_increment('admin_account_write', str(request.user.pk), limit=20, window_seconds=60)
        if not allowed:
            raise Throttled(wait=retry)


class AccountListView(AccountAdminView):
    @extend_schema(operation_id='operations_users_list', tags=['Administration'], summary='Tìm tài khoản quản trị', description='Admin có quyền xem tìm theo tên/email, lọc vai trò/trạng thái và phân trang tối đa 100 tài khoản.', parameters=[AccountQuery], responses=AccountPage)
    def get(self, request):
        return account_list(request)

    @extend_schema(tags=['Administration'], summary='Tạo tài khoản', description='Xác nhận mật khẩu Admin và lý do. Chỉ tạo học viên hoặc giáo viên chờ duyệt, không tự cấp quyền Admin.', request=AccountCreate, responses={201: AccountSerializer})
    def post(self, request):
        self.mutation(request, 'add_user')
        data = validated(AccountCreate, request.data)
        password, reason = data.pop('current_password'), data.pop('reason')
        user = action(lambda: create_administered_user(actor=request.user, values=data, current_password=password, reason=reason))
        return Response(AccountSerializer(user).data, status=201)


class AccountDetailView(AccountAdminView):
    @extend_schema(tags=['Administration'], summary='Xem tài khoản', description='Admin có quyền xem hồ sơ và trạng thái xét duyệt, không trả mật khẩu hoặc token.', responses=AccountSerializer)
    def get(self, request, user_id):
        action(lambda: require_account_admin(request.user, 'view_user'))
        user = action(lambda: User.objects.select_related('teacher_profile__institution', 'teacher_profile__approval').get(pk=user_id))
        return Response(AccountSerializer(user).data)

    @extend_schema(tags=['Administration'], summary='Cập nhật tài khoản', description='Kiểm mật khẩu, lý do và updated_at hiện hành; không được sửa tài khoản có quyền cao hơn. Khóa tài khoản thu hồi phiên, không cho vô hiệu hóa Admin cuối cùng.', request=AccountUpdate, responses={200: AccountSerializer, 409: OpenApiTypes.OBJECT})
    def patch(self, request, user_id):
        self.mutation(request, 'change_user')
        data = validated(AccountUpdate, request.data)
        arguments = {key: data.pop(key) for key in ('reason', 'current_password', 'expected_updated_at')}
        user = action(lambda: update_administered_user(actor=request.user, user_id=user_id, values=data, **arguments))
        return Response(AccountSerializer(user).data)


class AccountRoleView(AccountAdminView):
    @extend_schema(tags=['Administration'], summary='Đổi vai trò tài khoản', description='Cần quyền đổi vai trò riêng và đủ quyền quản trị đối tượng; giữ dữ liệu lịch sử, chặn chủ khóa chưa lưu trữ và thu hồi phiên cũ. Chuyển khỏi ADMIN thu hồi staff, superuser, nhóm và quyền Django đã gán.', request=RoleUpdate, responses={200: AccountSerializer, 409: OpenApiTypes.OBJECT})
    def post(self, request, user_id):
        self.mutation(request, 'change_user', 'assign_user_role')
        data = validated(RoleUpdate, request.data)
        role = data.pop('role')
        user = action(lambda: update_administered_user(actor=request.user, user_id=user_id, values={'role': role}, role_change=True, **data))
        return Response(AccountSerializer(user).data)


class TeacherListView(AccountAdminView):
    @extend_schema(tags=['Administration'], summary='Danh sách xét duyệt giáo viên', description='Lọc giáo viên theo trạng thái/nguồn duyệt, trường và email đã xác minh; không xét duyệt qua tham số truy vấn.', parameters=[AccountQuery], responses=AccountPage)
    def get(self, request):
        return account_list(request, teachers=True)


class TeacherDecisionView(AccountAdminView):
    @extend_schema(tags=['Administration'], summary='Quyết định duyệt giáo viên', description='Duyệt, từ chối hoặc thu hồi bằng service dùng chung; bắt buộc lý do, mật khẩu Admin và revision mới nhất.', request=ApprovalDecision, responses={200: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT})
    def post(self, request, user_id):
        self.mutation(request, 'change_teacherapproval')
        data = validated(ApprovalDecision, request.data)
        approval = action(lambda: administer_teacher_decision(actor=request.user, user_id=user_id, **data))
        from apps.users.api.serializers import TeacherApprovalSerializer
        return Response(TeacherApprovalSerializer(approval).data)


class ApprovalEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherApprovalEvent
        fields = ('id', 'actor_id', 'action', 'reason', 'revision', 'before', 'after', 'created_at')
        read_only_fields = fields


class AccountEventSerializer(serializers.ModelSerializer):
    details = serializers.SerializerMethodField()

    def get_details(self, obj):
        import json
        return json.loads(obj.change_message)

    class Meta:
        model = LogEntry
        fields = ('id', 'user_id', 'action_time', 'details')
        read_only_fields = fields


class AccountHistoryView(AccountAdminView):
    @extend_schema(tags=['Administration'], summary='Lịch sử quản trị tài khoản', description='Nhật ký chỉ đọc, có phân trang; không trả mật khẩu, token, số điện thoại hoặc giá trị email trước/sau.', parameters=[PageQuery], responses=OpenApiTypes.OBJECT)
    def get(self, request, user_id):
        action(lambda: require_account_admin(request.user, 'view_user', 'admin.view_logentry'))
        action(lambda: User.objects.get(pk=user_id))
        params = validated(PageQuery, request.query_params)
        rows = LogEntry.objects.filter(content_type=ContentType.objects.get_for_model(User),
            object_id=str(user_id), change_message__startswith='{"action":').order_by('-action_time', '-pk')
        return page(rows, params, AccountEventSerializer)


class TeacherHistoryView(AccountAdminView):
    @extend_schema(tags=['Administration'], summary='Lịch sử duyệt giáo viên', description='Admin có quyền đọc xem các quyết định và snapshot theo thứ tự thời gian; không cung cấp thao tác sửa/xóa lịch sử.', parameters=[PageQuery], responses=OpenApiTypes.OBJECT)
    def get(self, request, user_id):
        action(lambda: require_account_admin(request.user, 'view_user', 'view_teacherapprovalevent'))
        action(lambda: User.objects.get(pk=user_id))
        params = validated(PageQuery, request.query_params)
        rows = TeacherApprovalEvent.objects.filter(approval__teacher_profile__user_id=user_id).order_by('-created_at', '-pk')
        return page(rows, params, ApprovalEventSerializer)
