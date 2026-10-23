from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.pagination import PageNumberPagination
from ..models import Notification
from ..services import mark_read
from ..targets import resolve_target, visible_content


class NoticeSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()
    actor_name = serializers.SerializerMethodField()

    def content(self, obj):
        if not hasattr(obj, '_visible_content'):
            obj._visible_content = visible_content(obj, self.context['request'].user)
        return obj._visible_content

    def get_actor_name(self, obj) -> str:
        if self.content(obj)[0] == 'Hoạt động liên quan đến tài khoản của bạn':
            return ''
        return (obj.actor.full_name or obj.actor.username) if obj.actor else 'Hệ thống'

    def get_title(self, obj) -> str:
        return self.content(obj)[0]

    def get_body(self, obj) -> str:
        return self.content(obj)[1]

    class Meta:
        model = Notification
        fields = ['id', 'kind', 'title', 'body', 'actor_name', 'created_at', 'read_at']


class ReadOutput(serializers.Serializer):
    unread_count = serializers.IntegerField()


class TicketOutput(serializers.Serializer):
    ticket = serializers.CharField()
    expires_at = serializers.IntegerField()


class TargetOutput(serializers.Serializer):
    target = serializers.DictField()


class InboxPagination(PageNumberPagination):
    def get_paginated_response_schema(self, schema):
        result = super().get_paginated_response_schema(schema)
        result['properties']['unread_count'] = {'type': 'integer', 'minimum': 0, 'description': 'Tổng số thông báo chưa đọc.'}
        return result


class InboxView(GenericAPIView):
    serializer_class = NoticeSerializer
    pagination_class = InboxPagination

    @extend_schema(tags=['Notifications'], summary='Xem thông báo của bạn', description='Xem lịch sử thông báo đã lưu, kể cả khi ngoại tuyến; lọc unread=true để xem chưa đọc.', parameters=[OpenApiParameter('unread', bool, description='Chỉ xem thông báo chưa đọc.')])
    def get(self, request):
        query = Notification.objects.filter(recipient=request.user).select_related('actor')
        unread = query.filter(read_at__isnull=True).count()
        if request.query_params.get('unread') == 'true':
            query = query.filter(read_at__isnull=True)
        page = self.paginate_queryset(query)
        response = self.get_paginated_response(self.get_serializer(page, many=True).data)
        response.data['unread_count'] = unread
        return response


class ReadView(GenericAPIView):
    serializer_class = NoticeSerializer

    @extend_schema(tags=['Notifications'], summary='Đánh dấu đã đọc', description='Đánh dấu thông báo của chính bạn là đã đọc; gọi lại không tạo tác dụng phụ.', request=None, responses=ReadOutput)
    @transaction.atomic
    def post(self, request, notice_id=None):
        item = None
        if notice_id:
            item = Notification.objects.filter(pk=notice_id, recipient=request.user).first()
            if not item:
                raise NotFound('Không tìm thấy thông báo.')
        mark_read(request.user, item)
        return Response({'unread_count': Notification.objects.filter(recipient=request.user, read_at__isnull=True).count()})


class TargetView(GenericAPIView):
    serializer_class = NoticeSerializer

    @extend_schema(tags=['Notifications'], summary='Mở nội dung thông báo', description='Kiểm tra lại quyền hiện tại trước khi mở lớp, buổi học hoặc nội dung liên quan.', responses=TargetOutput)
    def get(self, request, notice_id):
        item = Notification.objects.filter(pk=notice_id, recipient=request.user).first()
        if not item:
            raise NotFound('Không tìm thấy thông báo.')
        return Response({'target': resolve_target(item, request.user)})


class TicketThrottle(UserRateThrottle):
    rate = '30/minute'


class TicketView(GenericAPIView):
    serializer_class = NoticeSerializer
    throttle_classes = [TicketThrottle]

    @extend_schema(tags=['Notifications'], summary='Kết nối thông báo realtime', description='Cấp vé WebSocket dùng một lần, hết hạn sau 30 giây; không đưa mã đăng nhập vào URL.', request=None, responses=TicketOutput)
    def post(self, request):
        from ..tickets import issue_ticket
        return Response(issue_ticket(request.user, request.auth))


class ReadAllView(ReadView):
    @extend_schema(tags=['Notifications'], summary='Đọc tất cả thông báo', description='Đánh dấu toàn bộ thông báo hiện có của bạn là đã đọc; giữ thông báo đến sau ở trạng thái chưa đọc.', request=None, responses=ReadOutput)
    def post(self, request):
        return super().post(request)

