"""Prototype-only, per-user PDF annotations. Intentionally no database or disk storage."""
from django.core.cache.backends.locmem import LocMemCache
import uuid
from rest_framework import serializers
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .views import DocumentAPIView

study_cache = LocMemCache('prototype-study-notes', {'TIMEOUT': None, 'OPTIONS': {'MAX_ENTRIES': 10000}})
study_session = str(uuid.uuid4())


class StudyItemSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=80)
    page = serializers.IntegerField(min_value=1, max_value=100)
    kind = serializers.ChoiceField(choices=['pen', 'highlight', 'text'])
    points = serializers.ListField(child=serializers.ListField(child=serializers.FloatField(min_value=0, max_value=1), min_length=2, max_length=2), min_length=1, max_length=2000, required=False)
    x = serializers.FloatField(min_value=0, max_value=1, required=False)
    y = serializers.FloatField(min_value=0, max_value=1, required=False)
    text = serializers.CharField(max_length=2000, required=False)

    def validate(self, value):
        if value['kind'] == 'text':
            if not {'x', 'y', 'text'} <= value.keys():
                raise serializers.ValidationError('Text position and content required.')
        elif 'points' not in value:
            raise serializers.ValidationError('Stroke points required.')
        if value['page'] > self.context['page_count']:
            raise serializers.ValidationError('Page unavailable.')
        return value


class StudyReportSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)
    opinion = serializers.CharField(max_length=3000, allow_blank=True)


class StudyFeedbackSerializer(serializers.Serializer):
    vote = serializers.ChoiceField(choices=['like', 'dislike', 'none'])
    report = StudyReportSerializer(required=False)


class StudyNotesSerializer(serializers.Serializer):
    scope = serializers.CharField(max_length=140)
    items = StudyItemSerializer(many=True, max_length=2000)
    notes = serializers.CharField(max_length=20000, allow_blank=True, trim_whitespace=False)
    feedback = StudyFeedbackSerializer(required=False)


class StudyNotesView(DocumentAPIView):
    @extend_schema(tags=['Documents'], summary='Xem ghi chú và nét vẽ cá nhân', description='Trả ghi chú, nét vẽ và đánh giá của tài khoản trên phiên bản PDF được phép xem. Dữ liệu tạm trong bộ nhớ, mất khi máy chủ khởi động lại.', parameters=[OpenApiParameter('version_id', str, required=True)], responses=StudyNotesSerializer)
    def get(self, request, document_id):
        document = self.document(request, document_id)
        version = self.version(request, document)
        scope = f'{study_session}:{request.user.pk}:{version.pk}'
        return Response({**study_cache.get(f'{request.user.pk}:{version.pk}', {'items': [], 'notes': ''}), 'scope': scope}, headers={'Cache-Control': 'private, no-store'})

    @extend_schema(tags=['Documents'], summary='Lưu ghi chú và nét vẽ cá nhân', description='Thay ghi chú, nét vẽ và đánh giá cá nhân theo phiên bản PDF và scope hiện tại. Không sửa tệp gốc; dữ liệu mất khi máy chủ khởi động lại.', parameters=[OpenApiParameter('version_id', str, required=True)], request=StudyNotesSerializer, responses=StudyNotesSerializer)
    def put(self, request, document_id):
        document = self.document(request, document_id)
        version = self.version(request, document)
        if request.data.get('scope') != f'{study_session}:{request.user.pk}:{version.pk}':
            return Response({'detail': 'Study session changed. Reopen the PDF.'}, status=409)
        serializer = StudyNotesSerializer(data=request.data, context={'page_count': version.page_count})
        serializer.is_valid(raise_exception=True)
        previous = study_cache.get(f'{request.user.pk}:{version.pk}', {})
        report = serializer.validated_data.get('feedback', {}).get('report')
        if report and report != previous.get('feedback', {}).get('report'):
            from apps.notifications.events import owners, scope
            from apps.notifications.services import notify
            from apps.users.models import User
            session = document.session
            context = {**scope(document.course, session.classroom if session else None, session), 'document_id': str(document.pk)}
            event = str(uuid.uuid4())
            notify(event_id=event, recipients=owners(document.course), actor=request.user, kind='MATERIAL_REPORTED',
                   title='Có báo cáo về học liệu', body=report['reason'], context=context)
            notify(event_id=event, recipients=User.objects.filter(role='ADMIN', is_active=True).values_list('pk', flat=True),
                   actor=request.user, kind='MATERIAL_REPORTED', title='Có báo cáo về học liệu', body=report['reason'], context={'admin': True, 'report': {
                       'document_id': str(document.pk), 'document_title': document.title, 'course_title': document.course.title,
                       'reporter': request.user.full_name or request.user.username, 'reason': report['reason'], 'opinion': report['opinion']}})
        study_cache.set(f'{request.user.pk}:{version.pk}', serializer.validated_data, timeout=None)
        return Response(serializer.validated_data, headers={'Cache-Control': 'private, no-store'})
