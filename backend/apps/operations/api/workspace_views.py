from django.db import DatabaseError
from django.db.models import Count, Max
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.users.account_administration import require_account_admin
from .account_views import AccountAdminView, action

CAPABILITIES = {
    'overview': ('users.view_platform_overview',),
    'accounts': ('users.view_user',),
    'create_account': ('users.add_user',),
    'edit_account': ('users.change_user',),
    'assign_role': ('users.change_user', 'users.assign_user_role'),
    'account_history': ('users.view_user', 'admin.view_logentry'),
    'teachers': ('users.view_user', 'users.view_teacherapproval'),
    'decide_teacher': ('users.change_teacherapproval',),
    'teacher_history': ('users.view_user', 'users.view_teacherapprovalevent'),
    'institutions': ('users.view_institution',),
    'create_institution': ('users.add_institution',),
    'edit_institution': ('users.change_institution',),
    'import_institutions': ('users.add_institution', 'users.change_institution'),
    'operations': ('ai.view_generationevent',),
}


class CapabilitiesView(AccountAdminView):
    @extend_schema(tags=['Administration'], summary='Quyền sử dụng không gian Admin', description='Trả các khả năng của Admin hiện hành để giao diện ẩn thao tác không được phép; backend vẫn kiểm quyền từng API.', responses=OpenApiTypes.OBJECT)
    def get(self, request):
        admin = action(lambda: require_account_admin(request.user))
        return Response({'user_id': str(admin.pk), 'capabilities': {
            key: all(admin.has_perm(permission) for permission in permissions)
            for key, permissions in CAPABILITIES.items()}})


class OperationsHealthView(AccountAdminView):
    @extend_schema(tags=['Administration'], summary='Vận hành AI và xử lý học liệu', description='Dùng tín hiệu ayo_operations_v1 hiện có; chỉ trả tổng hợp ingestion khi được cấp quyền, không trả prompt hoặc nội dung tài liệu.', responses=OpenApiTypes.OBJECT)
    def get(self, request):
        admin = action(lambda: require_account_admin(request.user, 'ai.view_generationevent'))
        from apps.ai.operations import operations_snapshot
        from apps.documents.exceptions import DocumentError
        from apps.documents.models import IngestionJob
        ingestion = None
        if admin.has_perm('documents.view_ingestionjob'):
            rows = IngestionJob.objects.all()
            ingestion = {'states': list(rows.values('status').annotate(count=Count('pk')).order_by('status')),
                         'latest': rows.aggregate(latest=Max('created_at'))['latest']}
        try:
            ai = operations_snapshot()
        except (DocumentError, DatabaseError):
            ai = None
        return Response({'as_of': timezone.now(), 'ai': ai, 'ingestion': ingestion})
