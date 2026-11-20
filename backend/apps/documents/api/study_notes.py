"""Private, durable study notes bound to the current user's permitted PDF version."""
import math
import uuid
from django.db import transaction
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework import serializers
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .views import DocumentAPIView
from ..exceptions import DocumentError
from ..models import DocumentStudyNotes, KnowledgeDocument


def study_scope(user, document, version):
    identity = f'{user.pk}:{document.pk}:{version.pk}'
    return 'study-v1:' + salted_hmac('documents.study-notes', identity, algorithm='sha256').hexdigest()


def study_payload(note, scope):
    payload = {'scope': scope, 'items': note.items if note else [], 'notes': note.notes if note else ''}
    if note and note.feedback:
        payload['feedback'] = note.feedback
    return payload


class StudyItemSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=80)
    page = serializers.IntegerField(min_value=1, max_value=100)
    kind = serializers.ChoiceField(choices=['pen', 'highlight', 'text'])
    points = serializers.ListField(child=serializers.ListField(child=serializers.FloatField(min_value=0, max_value=1), min_length=2, max_length=2), min_length=1, max_length=2000, required=False)
    x = serializers.FloatField(min_value=0, max_value=1, required=False)
    y = serializers.FloatField(min_value=0, max_value=1, required=False)
    text = serializers.CharField(max_length=2000, required=False)

    def validate(self, value):
        coordinates = [value[key] for key in ('x', 'y') if key in value]
        coordinates.extend(number for point in value.get('points', []) for number in point)
        if any(not math.isfinite(number) for number in coordinates):
            raise serializers.ValidationError('Coordinates must be finite numbers.')
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

    def validate_items(self, items):
        if len({item['id'] for item in items}) != len(items):
            raise serializers.ValidationError('Annotation IDs must be unique.')
        return items


class StudyNotesView(DocumentAPIView):
    def recheck_version(self, request, document_id, version):
        request.user.refresh_from_db()
        document = self.document(request, document_id)
        if self.version(request, document).pk != version.pk:
            raise DocumentError('SCOPE_CHANGED', 'Reopen the current PDF version.', 409)

    @extend_schema(tags=['Documents'], summary='Xem ghi chú và nét vẽ cá nhân', description='Đọc ghi chú, nét vẽ và đánh giá cá nhân từ database theo tài khoản và phiên bản PDF được phép xem. Dữ liệu được giữ qua restart; không chia sẻ giữa tài khoản hoặc chuyển sang phiên bản PDF mới.', parameters=[OpenApiParameter('version_id', str, required=True)], responses=StudyNotesSerializer)
    def get(self, request, document_id):
        document = self.document(request, document_id)
        version = self.version(request, document)
        note = DocumentStudyNotes.objects.filter(user=request.user, version=version).first()
        self.recheck_version(request, document_id, version)
        return Response(study_payload(note, study_scope(request.user, document, version)), headers={'Cache-Control': 'private, no-store'})

    @extend_schema(tags=['Documents'], summary='Lưu ghi chú và nét vẽ cá nhân', description='Thay toàn bộ ghi chú, nét vẽ và đánh giá cá nhân trong database theo phiên bản PDF và scope đã đọc. Không sửa PDF gốc. Scope sai tài khoản/phiên bản trả 409; mất quyền trả 404. Các lượt lưu được tuần tự hóa; lượt ghi sau thay nội dung trước.', parameters=[OpenApiParameter('version_id', str, required=True)], request=StudyNotesSerializer, responses=StudyNotesSerializer)
    def put(self, request, document_id):
        if not isinstance(request.data, dict):
            raise serializers.ValidationError('Expected a study notes object.')
        # Use the publication/removal lock too, including when the first notes row is created.
        with transaction.atomic():
            KnowledgeDocument.objects.select_for_update().get(pk=document_id, removed_at__isnull=True)
            request.user.refresh_from_db()
            document = self.document(request, document_id)
            version = self.version(request, document)
            expected_scope = study_scope(request.user, document, version)
            provided_scope = request.data.get('scope')
            if not isinstance(provided_scope, str) or not constant_time_compare(provided_scope, expected_scope):
                return Response({'detail': 'Study session changed. Reopen the PDF.'}, status=409)
            serializer = StudyNotesSerializer(data=request.data, context={'page_count': version.page_count})
            serializer.is_valid(raise_exception=True)
            note, _ = DocumentStudyNotes.objects.get_or_create(user=request.user, version=version)
            previous_report = note.feedback.get('report')
            note.items = serializer.validated_data['items']
            note.notes = serializer.validated_data['notes']
            note.feedback = serializer.validated_data.get('feedback', {})
            note.save(update_fields=['items', 'notes', 'feedback', 'updated_at'])
            self.recheck_version(request, document_id, version)
            report = note.feedback.get('report')
            if report and report != previous_report:
                self.notify_report(request, document, report)
            payload = study_payload(note, expected_scope)
        return Response(payload, headers={'Cache-Control': 'private, no-store'})

    def notify_report(self, request, document, report):
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
