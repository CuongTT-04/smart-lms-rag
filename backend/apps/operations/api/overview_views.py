from datetime import timedelta

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from apps.users.account_administration import require_account_admin
from ..selectors import PLATFORM_TIMEZONE, platform_overview
from .account_views import AccountAdminView, action, validated


class OverviewQuery(serializers.Serializer):
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def validate(self, attrs):
        today = timezone.localdate(timezone=PLATFORM_TIMEZONE)
        attrs.setdefault('end_date', today)
        if any(value.year < 2 or value.year >= 9999 for value in attrs.values()):
            raise serializers.ValidationError('Ngày ngoài phạm vi được hỗ trợ.')
        attrs.setdefault('start_date', attrs['end_date'] - timedelta(days=29))
        if attrs['end_date'] < attrs['start_date'] or (attrs['end_date'] - attrs['start_date']).days > 365:
            raise serializers.ValidationError('Khoảng ngày phải đúng thứ tự và không quá 366 ngày.')
        return attrs


class OverviewView(AccountAdminView):
    @extend_schema(tags=['Administration'], summary='Tổng quan nền tảng', description='Số tài khoản/khóa/lớp hiện tại và lượt nộp trong kỳ theo Asia/Ho_Chi_Minh; có thời điểm chụp, định nghĩa và khoảng nửa mở.', parameters=[OverviewQuery], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        action(lambda: require_account_admin(request.user, 'view_platform_overview'))
        params = validated(OverviewQuery, request.query_params)
        return Response(platform_overview(**params))
