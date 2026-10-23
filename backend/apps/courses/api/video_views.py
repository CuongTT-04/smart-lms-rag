import uuid
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from apps.courses.models import ClassroomSession
from apps.courses.permissions import can_manage_course
from apps.courses.video_models import SessionVideo, VideoQuestion
from apps.courses.video_services import progress_for, progress_output, update_progress, submit_answer
from .session_views import ClassroomSessionsView
from .video_serializers import VideoUploadInput, VideoUpdateInput, VideoSummary, QuestionInput, QuestionOutput, ProgressInput, AnswerInput, AnswerOutput, AnswerResult, ProgressOutput, VideoDetail


class VideoAccessView(ClassroomSessionsView):
    serializer_class = VideoSummary

    def video_session(self, request, course_id, classroom_id, session_id, manage=False):
        room = self.room(request, course_id, classroom_id, manage=manage)
        session = room.sessions.filter(pk=session_id, removed_at__isnull=True).first()
        if not session or (session.is_draft and not can_manage_course(request.user, room.course)):
            raise NotFound('Buổi học không khả dụng.')
        return session

    def get_video(self, request, course_id, classroom_id, session_id, video_id, manage=False, lock=False):
        session = self.video_session(request, course_id, classroom_id, session_id, manage)
        queryset = session.videos.filter(removed_at__isnull=True)
        if lock:
            queryset = queryset.select_for_update()
        if not can_manage_course(request.user, session.classroom.course):
            queryset = queryset.filter(is_published=True)
        video = queryset.filter(pk=video_id).first()
        if not video:
            raise NotFound('Video không khả dụng hoặc chưa được công bố.')
        return video


class SessionVideosView(VideoAccessView):
    http_method_names = ['get', 'post', 'head', 'options']
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(tags=['Videos'], summary='Danh sách video buổi học', description='Thành viên đúng lớp xem video đã công bố; chủ khóa học xem cả bản nháp.', responses=VideoSummary(many=True))
    def get(self, request, course_id, classroom_id, session_id):
        session = self.video_session(request, course_id, classroom_id, session_id)
        rows = session.videos.filter(removed_at__isnull=True)
        if not can_manage_course(request.user, session.classroom.course):
            rows = rows.filter(is_published=True)
        return self.get_paginated_response(VideoSummary(self.paginate_queryset(rows), many=True).data)

    @extend_schema(tags=['Videos'], summary='Tải video lên buổi học', description='Chủ khóa học tải MP4/WebM tối đa 200 MiB, kèm tên, mô tả và thời lượng từ metadata trình duyệt. Mặc định chưa công bố.', request=VideoUploadInput, responses={201: VideoSummary})
    @transaction.atomic
    def post(self, request, course_id, classroom_id, session_id):
        session = self.video_session(request, course_id, classroom_id, session_id, manage=True)
        ClassroomSession.objects.select_for_update().get(pk=session.pk)
        data = VideoUploadInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        file = values.pop('file')
        webm = file.name.lower().endswith('.webm')
        video = SessionVideo(session=session, content_type='video/webm' if webm else 'video/mp4', **values)
        try:
            video.file.save(f'{uuid.uuid4().hex}.{"webm" if webm else "mp4"}', file, save=False)
            video.save()
        except Exception:
            if video.file:
                video.file.delete(save=False)
            raise
        return Response(VideoSummary(video).data, status=201)


class SessionVideoDetailView(VideoAccessView):
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    @extend_schema(tags=['Videos'], summary='Xem video và câu hỏi theo mốc', description='Trả video, câu hỏi và tiến trình riêng của học viên. Chỉ chủ khóa học nhận correct_ids; không trả đáp án riêng cho học viên.', responses=VideoDetail)
    def get(self, request, **kwargs):
        video = self.get_video(request, **kwargs)
        manage = can_manage_course(request.user, video.session.classroom.course)
        result = dict(VideoSummary(video).data)
        result['questions'] = QuestionOutput(video.questions.filter(removed_at__isnull=True), many=True, context={'manage': manage}).data
        result['progress'] = None if manage else progress_output(video, progress_for(video, request.user))
        return Response(result)

    @extend_schema(tags=['Videos'], summary='Sửa hoặc công bố video', description='Chủ khóa học sửa tên, mô tả, công bố hoặc thu hồi công bố video. Không thay tệp gốc của video đã có câu trả lời.', request=VideoUpdateInput, responses=VideoSummary)
    @transaction.atomic
    def patch(self, request, **kwargs):
        video = self.get_video(request, **kwargs, manage=True, lock=True)
        data = VideoUpdateInput(data=request.data)
        data.is_valid(raise_exception=True)
        for field, value in data.validated_data.items():
            setattr(video, field, value)
        video.save()
        return Response(VideoSummary(video).data)

    @extend_schema(tags=['Videos'], summary='Gỡ video khỏi buổi học', description='Chủ khóa học gỡ video, giữ nội bộ tệp và lịch sử trả lời. Video đã gỡ không được xem hoặc trả lời.', responses={204: None})
    @transaction.atomic
    def delete(self, request, **kwargs):
        video = self.get_video(request, **kwargs, manage=True, lock=True)
        video.removed_at = timezone.now()
        video.is_published = False
        video.save(update_fields=['removed_at', 'is_published'])
        return Response(status=204)


class SessionVideoFileView(VideoAccessView):
    http_method_names = ['get', 'head', 'options']

    @extend_schema(tags=['Videos'], summary='Đọc tệp video riêng tư', description='Kiểm tra quyền lớp và công bố trước khi trả bytes video. Không có đường dẫn tệp công khai.', responses={(200, 'video/mp4'): bytes, (200, 'video/webm'): bytes})
    def get(self, request, **kwargs):
        video = self.get_video(request, **kwargs)
        try:
            stream = video.file.open('rb')
        except FileNotFoundError:
            raise NotFound('Không tìm thấy tệp video.')
        response = FileResponse(stream, content_type=video.content_type)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class VideoQuestionsView(VideoAccessView):
    http_method_names = ['post', 'options']

    @extend_schema(tags=['Videos'], summary='Tạo câu hỏi tại mốc video', description='Chủ khóa học tạo câu trắc nghiệm một/nhiều đáp án đúng hoặc tự luận. Mốc quay lại chỉ áp dụng trắc nghiệm và phải trước mốc bắt đầu.', request=QuestionInput, responses={201: QuestionOutput})
    @transaction.atomic
    def post(self, request, **kwargs):
        video = self.get_video(request, **kwargs, manage=True, lock=True)
        if video.questions.filter(removed_at__isnull=True).count() >= 100:
            raise ValidationError('Mỗi video tối đa 100 câu hỏi.')
        data = QuestionInput(data=request.data, context={'video': video})
        data.is_valid(raise_exception=True)
        question = VideoQuestion.objects.create(video=video, **data.validated_data)
        return Response(QuestionOutput(question, context={'manage': True}).data, status=201)


class VideoQuestionDetailView(VideoAccessView):
    http_method_names = ['patch', 'delete', 'options']

    @extend_schema(tags=['Videos'], summary='Sửa câu hỏi video', description='Chủ khóa học sửa câu hỏi; thay đổi tạo revision mới. Lịch sử trả lời cũ được giữ và không hoàn thành phiên bản câu hỏi mới.', request=QuestionInput, responses=QuestionOutput)
    @transaction.atomic
    def patch(self, request, question_id, **kwargs):
        video = self.get_video(request, **kwargs, manage=True, lock=True)
        question = video.questions.filter(pk=question_id, removed_at__isnull=True).first()
        if not question:
            raise NotFound('Câu hỏi không khả dụng.')
        data = QuestionInput(question, data=request.data, partial=True, context={'video': video})
        data.is_valid(raise_exception=True)
        if any(getattr(question, key) != value for key, value in data.validated_data.items()):
            for key, value in data.validated_data.items():
                setattr(question, key, value)
            question.revision += 1
            question.save()
        return Response(QuestionOutput(question, context={'manage': True}).data)

    @extend_schema(tags=['Videos'], summary='Gỡ câu hỏi video', description='Chủ khóa học gỡ câu hỏi khỏi trình phát, giữ lại lịch sử câu trả lời.', responses={204: None})
    @transaction.atomic
    def delete(self, request, question_id, **kwargs):
        video = self.get_video(request, **kwargs, manage=True, lock=True)
        question = video.questions.filter(pk=question_id, removed_at__isnull=True).first()
        if not question:
            raise NotFound('Câu hỏi không khả dụng.')
        question.removed_at = timezone.now()
        question.save(update_fields=['removed_at'])
        return Response(status=204)


class VideoProgressView(VideoAccessView):
    http_method_names = ['put', 'options']

    @extend_schema(tags=['Videos'], summary='Lưu vị trí xem video', description='Học viên lưu vị trí; được tua lùi, không nhảy tiến hoặc qua câu hỏi chưa hoàn thành. Server giới hạn mức tăng theo thời gian thực; giáo viên preview không bị giới hạn.', request=ProgressInput, responses=ProgressOutput)
    @transaction.atomic
    def put(self, request, **kwargs):
        video = self.get_video(request, **kwargs, lock=True)
        if can_manage_course(request.user, video.session.classroom.course):
            raise ValidationError('Giáo viên xem thử không cần lưu tiến trình học viên.')
        data = ProgressInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(update_progress(video, request.user, data.validated_data['position']))


class VideoAnswersView(VideoAccessView):
    http_method_names = ['post', 'options']

    @extend_schema(tags=['Videos'], summary='Trả lời câu hỏi video', description='Học viên trả lời đúng mốc đang bị chặn; trắc nghiệm chấm theo tập đáp án, sai có thể quay lại mốc đã đặt. Tự luận được lưu để giáo viên xem và cho tiếp tục. request_id chống gửi trùng.', request=AnswerInput, responses=AnswerResult)
    @transaction.atomic
    def post(self, request, question_id, **kwargs):
        video = self.get_video(request, **kwargs, lock=True)
        if can_manage_course(request.user, video.session.classroom.course):
            raise ValidationError('Giáo viên xem thử không gửi bài làm học viên.')
        question = video.questions.filter(pk=question_id, removed_at__isnull=True).first()
        if not question:
            raise NotFound('Câu hỏi không khả dụng.')
        data = AnswerInput(data=request.data)
        data.is_valid(raise_exception=True)
        answer = submit_answer(video, question, request.user, data.validated_data)
        result = dict(AnswerOutput(answer).data)
        result['progress'] = progress_output(video, progress_for(video, request.user))
        return Response(result)


class VideoResponsesView(VideoAccessView):
    http_method_names = ['get', 'head', 'options']
    serializer_class = AnswerOutput

    @extend_schema(tags=['Videos'], summary='Quản lý câu trả lời video', description='Chủ khóa học xem bài tự luận, lựa chọn trắc nghiệm, số học viên trả lời và số lần thử. Đếm riêng từng học viên theo revision hiện tại; lịch sử revision cũ vẫn có trong kết quả.', responses=AnswerOutput(many=True))
    def get(self, request, **kwargs):
        video = self.get_video(request, **kwargs, manage=True)
        answers = video.answers.select_related('student')
        question_filter = request.query_params.get('question_id')
        if question_filter:
            try:
                question_filter = uuid.UUID(question_filter)
            except ValueError:
                raise ValidationError('Mã câu hỏi không hợp lệ.')
            answers = answers.filter(question_id=question_filter)
        result = self.get_paginated_response(AnswerOutput(self.paginate_queryset(answers), many=True).data)
        result.data['questions'] = []
        for question in video.questions.filter(removed_at__isnull=True):
            attempts = question.answers.filter(question_revision=question.revision)
            result.data['questions'].append({'id': str(question.pk), 'prompt': question.prompt, 'kind': question.kind,
                'start_time': question.start_time, 'revision': question.revision,
                'answered_students': attempts.values('student_id').distinct().count(),
                'correct_students': attempts.filter(is_correct=True).values('student_id').distinct().count(),
                'attempt_count': attempts.count()})
        result.data['student_count'] = video.session.classroom.enrollments.filter(status__in=['ACTIVE', 'COMPLETED'],
            student__user__is_active=True, student__user__course_memberships__course=video.session.classroom.course,
            student__user__course_memberships__status='ACTIVE').values('student_id').distinct().count()
        return result


class VideoOwnAnswersView(VideoAccessView):
    http_method_names = ['get', 'head', 'options']
    serializer_class = AnswerOutput

    @extend_schema(tags=['Videos'], summary='Xem lại câu trả lời video của tôi', description='Học viên xem các lần trả lời của chính mình trong đúng video và lớp còn quyền truy cập. Giữ đề và lựa chọn theo phiên bản đã trả lời; không trả đáp án đúng hoặc bài của người khác.', responses=AnswerOutput(many=True))
    def get(self, request, **kwargs):
        video = self.get_video(request, **kwargs)
        answers = video.answers.filter(student=request.user).select_related('student')
        return self.get_paginated_response(AnswerOutput(self.paginate_queryset(answers), many=True).data)
