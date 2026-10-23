from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework.exceptions import NotFound, ValidationError, PermissionDenied
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from apps.courses.permissions import can_manage_course
from apps.courses.assessment_models import Assessment, AssessmentAttempt, AssessmentEvent, AssessmentGradeAudit
from apps.courses.assessment_services import assessment_output, attempt_output, expire, start_attempt, save_draft, submit_attempt
from apps.courses.assessment_reports import dashboard, export_workbook
from .video_views import VideoAccessView
from .assessment_serializers import AssessmentInput, StartInput, DraftInput, SubmitInput, EventInput, GradeInput


def schema(summary, description='', request=None, binary=False):
    return extend_schema(tags=['Assessments'], summary=summary, description=description or summary, request=request,
        responses={(200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'): bytes} if binary else OpenApiTypes.OBJECT)


class AssessmentAccessView(VideoAccessView):
    serializer_class = AssessmentInput

    @transaction.atomic
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def assessment(self, request, course_id, classroom_id, session_id, assessment_id, manage=False, **kwargs):
        session = self.video_session(request, course_id, classroom_id, session_id, manage)
        manager = can_manage_course(request.user, session.classroom.course)
        rows = session.assessments.select_for_update().filter(removed_at__isnull=True)
        if not manager:
            rows = rows.filter(is_published=True)
        obj = rows.filter(pk=assessment_id).first()
        if not obj:
            raise NotFound('Bài tập không khả dụng.')
        return obj, manager

    def attempt(self, request, attempt_id, manage=False, **kwargs):
        assessment, manager = self.assessment(request, manage=manage, **kwargs)
        rows = assessment.attempts.select_for_update().select_related('student')
        if not manager:
            rows = rows.filter(student=request.user)
        attempt = rows.filter(pk=attempt_id).first()
        if not attempt:
            raise NotFound('Không tìm thấy lượt làm.')
        expire(attempt)
        return attempt, manager

    def validated(self, serializer, request, **kwargs):
        data = serializer(data=request.data, **kwargs)
        data.is_valid(raise_exception=True)
        return data.validated_data


class AssessmentsView(AssessmentAccessView):
    http_method_names = ['get', 'post', 'head', 'options']

    @extend_schema(tags=['Assessments'], operation_id='session_assessments_list', summary='Danh sách bài tập của buổi học', description='Thành viên đúng lớp xem bài đã công bố; giáo viên sở hữu xem cả bản nháp.', responses=OpenApiTypes.OBJECT)
    def get(self, request, course_id, classroom_id, session_id):
        session = self.video_session(request, course_id, classroom_id, session_id)
        manager = can_manage_course(request.user, session.classroom.course)
        rows = session.assessments.filter(removed_at__isnull=True)
        if not manager:
            rows = rows.filter(is_published=True)
        return self.get_paginated_response([assessment_output(a, manager) for a in self.paginate_queryset(rows)])

    @schema('Tạo quiz hoặc bài tự luận', request=AssessmentInput)
    def post(self, request, course_id, classroom_id, session_id):
        session = self.video_session(request, course_id, classroom_id, session_id, manage=True)
        values = self.validated(AssessmentInput, request)
        obj = Assessment.objects.create(session=session, **values)
        return Response(assessment_output(obj, True), status=201)


class AssessmentDetailView(AssessmentAccessView):
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    @schema('Xem bài tập và các lượt làm cá nhân')
    def get(self, request, **kwargs):
        obj, manager = self.assessment(request, **kwargs)
        result = assessment_output(obj, manager)
        if not manager:
            own = list(obj.attempts.filter(student=request.user))
            for a in own:
                expire(a)
            result['attempts'] = [attempt_output(a) for a in own]
        return Response(result)

    @schema('Sửa hoặc công bố bài tập và kết quả', request=AssessmentInput)
    def patch(self, request, **kwargs):
        obj, _ = self.assessment(request, manage=True, **kwargs)
        values = self.validated(AssessmentInput, request, instance=obj, partial=True)
        mutable = {'is_published', 'results_published', 'solutions_published'}
        if obj.attempts.exists() and any(k not in mutable and getattr(obj, k) != v for k, v in values.items()):
            raise ValidationError('Đã có lượt làm: giữ nguyên đề, chế độ và hạn. Hãy tạo bài mới nếu cần thay đổi.')
        for k, v in values.items():
            setattr(obj, k, v)
        obj.save()
        return Response(assessment_output(obj, True))

    @schema('Gỡ bài tập, giữ lịch sử bài làm')
    def delete(self, request, **kwargs):
        obj, _ = self.assessment(request, manage=True, **kwargs)
        obj.removed_at = timezone.now(); obj.is_published = False; obj.save()
        return Response(status=204)


class AssessmentStartView(AssessmentAccessView):
    http_method_names = ['post', 'options']

    @schema('Bắt đầu hoặc tiếp tục lượt làm', request=StartInput)
    def post(self, request, **kwargs):
        obj, manager = self.assessment(request, **kwargs)
        if manager:
            raise ValidationError('Giáo viên dùng phần xem đề, không tạo lượt học viên.')
        attempt = start_attempt(obj, request.user, self.validated(StartInput, request))
        return Response(attempt_output(attempt))


class AssessmentAttemptView(AssessmentAccessView):
    http_method_names = ['get', 'patch', 'head', 'options']
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @schema('Xem bài làm, điểm và phản hồi được công bố')
    def get(self, request, **kwargs):
        obj, manager = self.attempt(request, **kwargs)
        return Response(attempt_output(obj, manager))

    @schema('Lưu bản nháp bài làm có kiểm tra phiên bản', request=DraftInput)
    def patch(self, request, **kwargs):
        obj, manager = self.attempt(request, **kwargs)
        if manager:
            raise PermissionDenied('Giáo viên không sửa bài làm của học viên.')
        save_draft(obj, self.validated(DraftInput, request))
        return Response(attempt_output(obj))


class AssessmentSubmitView(AssessmentAccessView):
    http_method_names = ['post', 'options']

    @schema('Nộp bài; kiểm tra cần xác nhận một lần', request=SubmitInput)
    def post(self, request, **kwargs):
        obj, manager = self.attempt(request, **kwargs)
        if manager:
            raise PermissionDenied('Chỉ học viên được nộp bài của mình.')
        submit_attempt(obj, self.validated(SubmitInput, request))
        return Response(attempt_output(obj))


class AssessmentEventView(AssessmentAccessView):
    http_method_names = ['post', 'options']

    @schema('Ghi nhận chuyển tab hoặc thoát toàn màn hình', 'Chỉ ghi cảnh báo; giáo viên tự quyết định xử lý. Thời điểm do server ghi.', request=EventInput)
    def post(self, request, **kwargs):
        obj, manager = self.attempt(request, **kwargs)
        if manager or obj.assessment.mode != 'TEST':
            raise PermissionDenied('Chỉ ghi sự kiện cho lượt kiểm tra của chính học viên.')
        values = self.validated(EventInput, request)
        existing = obj.events.filter(event_id=values['event_id']).first()
        if existing and existing.kind != values['kind']:
            raise ValidationError('Mã sự kiện đã dùng cho nội dung khác.')
        if obj.status == 'DRAFT' and not existing:
            AssessmentEvent.objects.create(attempt=obj, **values)
        return Response({'recorded': obj.status == 'DRAFT' or bool(existing), 'warning': 'Vi phạm được ghi nhận để giáo viên xem xét.'}, status=201)


class AssessmentGradeView(AssessmentAccessView):
    http_method_names = ['patch', 'options']

    @schema('Chấm, công bố điểm và ghi quyết định xử lý vi phạm', request=GradeInput)
    def patch(self, request, **kwargs):
        obj, _ = self.attempt(request, manage=True, **kwargs)
        if obj.status != 'SUBMITTED':
            raise ValidationError('Chỉ chấm bài đã nộp.')
        values = self.validated(GradeInput, request)
        def snapshot():
            return {'score': str(obj.score) if obj.score is not None else None, 'feedback': obj.feedback, 'published': obj.grade_published, 'moderation_note': obj.moderation_note}
        before = snapshot()
        for k, v in values.items():
            setattr(obj, 'grade_published' if k == 'published' else k, v)
        if obj.grade_published and obj.score is None:
            raise ValidationError('Nhập điểm trước khi công bố kết quả.')
        obj.save()
        after = snapshot()
        if before != after:
            AssessmentGradeAudit.objects.create(attempt=obj, teacher=request.user, before=before, after=after)
        return Response(attempt_output(obj, True))


class AssessmentFileView(AssessmentAccessView):
    http_method_names = ['get', 'head', 'options']

    @extend_schema(tags=['Assessments'], summary='Tải tệp bài nộp riêng tư', description='Chỉ người nộp hoặc giáo viên phụ trách có quyền tải.', responses={(200, 'application/octet-stream'): bytes})
    def get(self, request, **kwargs):
        obj, _ = self.attempt(request, **kwargs)
        if not obj.file:
            raise NotFound('Bài làm không có tệp.')
        try:
            stream = obj.file.open('rb')
        except FileNotFoundError:
            raise NotFound('Tệp bài nộp không khả dụng.')
        response = FileResponse(stream, content_type=obj.file_type, as_attachment=True, filename=obj.file_name)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class AssessmentAssistanceView(AssessmentAccessView):
    http_method_names = ['post', 'options']

    @schema('Xem gợi ý ôn tập và trạng thái trợ giúp AI')
    def post(self, request, **kwargs):
        obj, _ = self.assessment(request, **kwargs)
        if obj.mode != 'PRACTICE':
            raise PermissionDenied('Không hỗ trợ AI trong chế độ Kiểm tra.')
        return Response({'ai_available': False, 'hint': obj.hint, 'message': 'Chưa kết nối mô hình AI. Bạn có thể xem gợi ý do giáo viên cung cấp.'})


class AssessmentDashboardView(AssessmentAccessView):
    http_method_names = ['get', 'head', 'options']

    @schema('Dashboard bài tập, các lượt làm và log vi phạm')
    def get(self, request, **kwargs):
        obj, _ = self.assessment(request, manage=True, **kwargs)
        return Response(dashboard(obj, request.query_params))


class AssessmentExportView(AssessmentAccessView):
    http_method_names = ['get', 'head', 'options']

    @schema('Xuất Excel tổng hợp, chi tiết, thống kê và vi phạm', 'Áp dụng cùng bộ lọc dashboard; chỉ chủ khóa học được xuất dữ liệu.', binary=True)
    def get(self, request, **kwargs):
        obj, _ = self.assessment(request, manage=True, **kwargs)
        content = export_workbook(obj, dashboard(obj, request.query_params))
        response = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="assessment-{obj.pk}.xlsx"'
        response['Cache-Control'] = 'private, no-store'
        return response
