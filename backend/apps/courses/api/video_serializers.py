import math
import re
from pathlib import Path
from rest_framework import serializers
from apps.courses.video_models import SessionVideo, VideoQuestion, VideoAnswer
from .serializers import StrictRequestSerializer


class VideoUploadInput(StrictRequestSerializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(max_length=5000, allow_blank=True, required=False, default='')
    duration = serializers.FloatField(min_value=0.1, max_value=14400)
    file = serializers.FileField()

    def validate_duration(self, value):
        if not math.isfinite(value):
            raise serializers.ValidationError('Thời lượng không hợp lệ.')
        return round(value, 3)

    def validate_file(self, file):
        if file.size > 200 * 1024 * 1024:
            raise serializers.ValidationError('Video tối đa 200 MiB.')
        header = file.read(12)
        file.seek(0)
        ext = Path(file.name).suffix.lower()
        if not ((ext == '.mp4' and header[4:8] == b'ftyp') or (ext == '.webm' and header[:4] == b'\x1aE\xdf\xa3')):
            raise serializers.ValidationError('Chọn tệp video MP4 hoặc WebM hợp lệ.')
        return file


class VideoUpdateInput(StrictRequestSerializer):
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    is_published = serializers.BooleanField(required=False)


class VideoSummary(serializers.ModelSerializer):
    class Meta:
        model = SessionVideo
        fields = ['id', 'title', 'description', 'duration', 'is_published', 'created_at']
        read_only_fields = fields


class QuestionInput(StrictRequestSerializer):
    kind = serializers.ChoiceField(choices=['MCQ', 'TEXT'])
    prompt = serializers.CharField(max_length=2000)
    choices = serializers.ListField(child=serializers.DictField(), required=False, default=list, max_length=10)
    correct_ids = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list, max_length=10)
    multiple = serializers.BooleanField(required=False)
    hint = serializers.CharField(max_length=2000, required=False, default='', allow_blank=True)
    start_time = serializers.FloatField(min_value=0)
    rewind_time = serializers.FloatField(min_value=0, required=False, allow_null=True, default=None)

    def validate(self, values):
        video = self.context['video']
        merged = {field: getattr(self.instance, field) for field in self.fields} if self.instance else {}
        merged.update(values)
        if 'multiple' not in merged:
            merged['multiple'] = len(merged.get('correct_ids', [])) > 1
        values['multiple'] = merged['multiple'] if merged['kind'] == 'MCQ' else False
        start, rewind = merged['start_time'], merged.get('rewind_time')
        if not math.isfinite(start) or start > video.duration:
            raise serializers.ValidationError({'start_time': 'Mốc bắt đầu phải nằm trong thời lượng video.'})
        if rewind is not None and (not math.isfinite(rewind) or rewind >= start):
            raise serializers.ValidationError({'rewind_time': 'Mốc quay lại phải trước mốc bắt đầu.'})
        same_time = video.questions.filter(removed_at__isnull=True, start_time=start)
        if self.instance:
            same_time = same_time.exclude(pk=self.instance.pk)
        if same_time.exists():
            raise serializers.ValidationError({'start_time': 'Đã có câu hỏi tại mốc này.'})
        if merged['kind'] == 'TEXT':
            if rewind is not None or merged.get('choices') or merged.get('correct_ids'):
                raise serializers.ValidationError('Tự luận không có mốc quay lại hoặc đáp án trắc nghiệm.')
        else:
            choices = merged.get('choices', [])
            ids = []
            for choice in choices:
                if set(choice) != {'id', 'text'} or not isinstance(choice['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', choice['id']) or not isinstance(choice['text'], str) or not choice['text'].strip() or len(choice['text']) > 500:
                    raise serializers.ValidationError({'choices': 'Mỗi lựa chọn cần mã riêng và nội dung 1–500 ký tự.'})
                ids.append(choice['id'])
            correct = merged.get('correct_ids', [])
            if len(choices) < 2 or len(set(ids)) != len(ids) or not correct or len(set(correct)) != len(correct) or not set(correct).issubset(ids):
                raise serializers.ValidationError('Cần ít nhất hai lựa chọn khác mã và ít nhất một đáp án đúng hợp lệ.')
            if not merged['multiple'] and len(correct) != 1:
                raise serializers.ValidationError('Câu một đáp án phải có đúng một đáp án đúng.')
        return values


class QuestionOutput(serializers.ModelSerializer):
    def get_fields(self):
        fields = super().get_fields()
        if not self.context.get('manage', False):
            fields.pop('correct_ids', None)
        return fields

    class Meta:
        model = VideoQuestion
        fields = ['id', 'kind', 'prompt', 'choices', 'correct_ids', 'hint', 'start_time', 'rewind_time', 'revision', 'multiple']
        read_only_fields = fields


class ProgressInput(StrictRequestSerializer):
    position = serializers.FloatField(min_value=0)


class ProgressOutput(serializers.Serializer):
    position = serializers.FloatField()
    watched_until = serializers.FloatField()
    seekable_until = serializers.FloatField()
    completed = serializers.BooleanField()
    passed_ids = serializers.ListField(child=serializers.UUIDField())


class VideoDetail(VideoSummary):
    questions = QuestionOutput(many=True, read_only=True)
    progress = ProgressOutput(allow_null=True, read_only=True)

    class Meta(VideoSummary.Meta):
        fields = VideoSummary.Meta.fields + ['questions', 'progress']


class AnswerInput(StrictRequestSerializer):
    request_id = serializers.UUIDField()
    revision = serializers.IntegerField(min_value=1)
    selected_ids = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list, max_length=10)
    text = serializers.CharField(max_length=5000, required=False, default='', allow_blank=True)


class AnswerOutput(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    question_id = serializers.UUIDField(read_only=True)

    def get_student_name(self, obj) -> str:
        return obj.student.full_name or obj.student.username

    class Meta:
        model = VideoAnswer
        fields = ['id', 'question_id', 'question_revision', 'student_name', 'snapshot', 'selected_ids', 'text', 'is_correct', 'rewind_to', 'created_at']
        read_only_fields = fields


class AnswerResult(AnswerOutput):
    progress = ProgressOutput(read_only=True)

    class Meta(AnswerOutput.Meta):
        fields = AnswerOutput.Meta.fields + ['progress']
