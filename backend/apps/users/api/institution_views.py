from django.core.exceptions import ValidationError as ModelValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, Throttled, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.institution_fields import LEVELS, normalize_search
from apps.users.institutions import import_institutions, require_catalog_admin, save_institution
from apps.users.models import Institution
from apps.users.rate_limit import check_and_increment


class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = ('id', 'name', 'aliases', 'province', 'campus', 'levels')
        read_only_fields = fields


class InstitutionAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = ('id', 'code', 'name', 'aliases', 'province', 'campus', 'levels', 'external_code',
                  'source_url', 'source_checked_at', 'active', 'updated_at')
        read_only_fields = fields


class LookupSerializer(serializers.Serializer):
    q = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    province = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    level = serializers.ChoiceField(choices=LEVELS, required=False)
    limit = serializers.IntegerField(min_value=1, max_value=20, default=20)
    offset = serializers.IntegerField(min_value=0, max_value=100000, default=0)


class InstitutionPageSerializer(serializers.Serializer):
    results = InstitutionSerializer(many=True)
    has_more = serializers.BooleanField()
    next_offset = serializers.IntegerField(allow_null=True)


class InstitutionAdminPageSerializer(InstitutionPageSerializer):
    results = InstitutionAdminSerializer(many=True)


class InstitutionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = ('code', 'name', 'aliases', 'province', 'campus', 'levels', 'external_code',
                  'source_url', 'source_checked_at', 'active')


def list_institutions(request, *, admin=False):
    query = LookupSerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    params = query.validated_data
    objects = Institution.objects.all()
    if not admin:
        objects = objects.filter(active=True)
    for word in normalize_search(params['q']).split():
        objects = objects.filter(search_text__contains=word)
    if params['province']:
        objects = objects.filter(province_key=normalize_search(params['province']))
    if params.get('level'):
        objects = objects.filter(levels__contains=[params['level']])
    start, limit = params['offset'], params['limit']
    rows = list(objects.order_by('name', 'code')[start:start + limit + 1])
    serializer = InstitutionAdminSerializer if admin else InstitutionSerializer
    return Response(dict(results=serializer(rows[:limit], many=True).data, has_more=len(rows) > limit,
                         next_offset=start + limit if len(rows) > limit else None))


def catalog_action(action):
    try:
        return action()
    except PermissionError as exc:
        raise PermissionDenied('Catalog administration permission required.') from exc
    except Institution.DoesNotExist as exc:
        raise NotFound('Institution not found.') from exc
    except ModelValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages) from exc


@method_decorator(never_cache, name='dispatch')
class InstitutionLookupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(operation_id='users_institutions_lookup', tags=['Institutions'], summary='Tìm trường đang hoạt động', description='Tìm tên có dấu, không dấu hoặc viết tắt; lọc tỉnh/cấp học, tối đa 20 kết quả/lần và 60 lượt/phút/IP.', auth=[], parameters=[LookupSerializer], responses=InstitutionPageSerializer)
    def get(self, request):
        # REMOTE_ADDR is authoritative here; never trust client-supplied forwarding headers.
        allowed, retry_after = check_and_increment('institution_lookup', request.META.get('REMOTE_ADDR', 'unknown'),
                                                   limit=60, window_seconds=60)
        if not allowed:
            raise Throttled(wait=retry_after)
        return list_institutions(request)


@method_decorator(never_cache, name='dispatch')
class InstitutionAdminListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id='operations_institutions_list', tags=['Institutions'], summary='Danh mục trường dành cho quản trị', description='Admin có quyền xem danh mục lấy danh sách trường, gồm cả trường ngừng hoạt động; kết quả phân trang tối đa 20 mục.', parameters=[LookupSerializer], responses=InstitutionAdminPageSerializer)
    def get(self, request):
        catalog_action(lambda: require_catalog_admin(request.user, 'view'))
        return list_institutions(request, admin=True)

    @extend_schema(tags=['Institutions'], summary='Thêm trường vào danh mục', description='Admin có quyền thêm trường cung cấp mã nội bộ, tên, địa phương, cấp học và nguồn đối chiếu; không chấp nhận trùng danh tính chuẩn hóa.', request=InstitutionWriteSerializer, responses={201: InstitutionAdminSerializer})
    def post(self, request):
        obj = catalog_action(lambda: save_institution(actor=request.user, values=request.data))
        return Response(InstitutionAdminSerializer(obj).data, status=201)


@method_decorator(never_cache, name='dispatch')
class InstitutionAdminDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Institutions'], summary='Xem thông tin quản trị của trường', description='Admin có quyền xem được nguồn và ngày đối chiếu cùng trạng thái hoạt động; không trả hồ sơ giáo viên liên kết.', responses=InstitutionAdminSerializer)
    def get(self, request, institution_id):
        catalog_action(lambda: require_catalog_admin(request.user, 'view'))
        obj = catalog_action(lambda: Institution.objects.get(pk=institution_id))
        return Response(InstitutionAdminSerializer(obj).data)

    @extend_schema(tags=['Institutions'], summary='Cập nhật danh mục trường', description='Admin có quyền sửa cập nhật tên, nguồn hoặc trạng thái; không đổi mã ổn định, không xóa quan hệ hồ sơ khi ngừng hoạt động.', request=InstitutionWriteSerializer, responses=InstitutionAdminSerializer)
    def patch(self, request, institution_id):
        obj = catalog_action(lambda: save_institution(actor=request.user, institution_id=institution_id, values=request.data))
        return Response(InstitutionAdminSerializer(obj).data)


class ImportSerializer(serializers.Serializer):
    file = serializers.FileField()
    dry_run = serializers.BooleanField(default=True)


@method_decorator(never_cache, name='dispatch')
class InstitutionImportView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(tags=['Institutions'], summary='Xem trước hoặc nhập danh mục trường', description='Nhận CSV/XLSX tối đa 2 MiB và 500 dòng, mặc định dry_run=true; chỉ ghi toàn bộ khi dữ liệu hợp lệ và dry_run=false.', request=ImportSerializer, responses={200: OpenApiTypes.OBJECT, 400: OpenApiResponse(response=OpenApiTypes.OBJECT, description='Lỗi file hoặc báo cáo các dòng không hợp lệ; không ghi một phần dữ liệu.', examples=[OpenApiExample('Invalid file', value={'file': ['Invalid CSV/XLSX file.']})])})
    def post(self, request):
        catalog_action(lambda: require_catalog_admin(request.user, 'add', 'change'))
        serializer = ImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = catalog_action(lambda: import_institutions(actor=request.user,
            upload=serializer.validated_data['file'], dry_run=serializer.validated_data['dry_run']))
        return Response(report, status=200 if report['dry_run'] or report['valid'] else 400)
