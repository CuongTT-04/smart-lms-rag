from django.utils import timezone
from rest_framework import serializers
from .serializers import StrictRequestSerializer


class ChoiceInput(StrictRequestSerializer):
    id = serializers.RegexField(r'^[a-zA-Z0-9_-]{1,64}$')
    text = serializers.CharField(max_length=1000)


class AssessmentQuestionInput(StrictRequestSerializer):
    id = serializers.RegexField(r'^[a-zA-Z0-9_-]{1,64}$')
    prompt = serializers.CharField(max_length=3000)
    choices = ChoiceInput(many=True, min_length=2, max_length=8)
    multiple = serializers.BooleanField(required=False, default=False)
    correct_ids = serializers.ListField(child=serializers.CharField(max_length=64), required=False, max_length=8)
    correct_id = serializers.CharField(max_length=64, required=False, write_only=True)
    hint = serializers.CharField(max_length=2000, allow_blank=True, required=False, default='')

    def validate(self, data):
        ids = [c['id'] for c in data['choices']]
        correct = data.get('correct_ids', [data['correct_id']] if 'correct_id' in data else [])
        if 'correct_id' in data and ('correct_ids' in data and correct != [data['correct_id']]):
            raise serializers.ValidationError('Hai trường đáp án không nhất quán.')
        if len(set(ids)) != len(ids) or not correct or len(set(correct)) != len(correct) or not set(correct).issubset(ids):
            raise serializers.ValidationError('Đáp án hoặc mã lựa chọn không hợp lệ.')
        if not data.get('multiple', False) and len(correct) != 1:
            raise serializers.ValidationError('Câu một đáp án phải có đúng một đáp án đúng.')
        data.pop('correct_id', None)
        data['correct_ids'] = correct
        return data


class AssessmentInput(StrictRequestSerializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(max_length=10000, allow_blank=True, required=False, default='')
    kind = serializers.ChoiceField(choices=['QUIZ', 'TEXT'])
    mode = serializers.ChoiceField(choices=['PRACTICE', 'TEST'])
    questions = AssessmentQuestionInput(many=True, required=False, default=list, max_length=100)
    hint = serializers.CharField(max_length=5000, allow_blank=True, required=False, default='')
    duration_seconds = serializers.IntegerField(min_value=60, max_value=14400, required=False, default=1800)
    due_at = serializers.DateTimeField()
    is_published = serializers.BooleanField(required=False)
    results_published = serializers.BooleanField(required=False)
    solutions_published = serializers.BooleanField(required=False)

    def validate_due_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError('Hạn nộp phải ở tương lai.')
        return value

    def validate(self, data):
        kind = data.get('kind', getattr(self.instance, 'kind', None))
        questions = data.get('questions', getattr(self.instance, 'questions', []))
        if kind == 'QUIZ' and not questions:
            raise serializers.ValidationError('Quiz cần ít nhất một câu hỏi.')
        if kind == 'TEXT' and questions:
            raise serializers.ValidationError('Bài tự luận không chứa câu hỏi quiz.')
        if len({q['id'] for q in questions}) != len(questions):
            raise serializers.ValidationError('Mã câu hỏi không được trùng.')
        return data


class StartInput(StrictRequestSerializer):
    request_id = serializers.UUIDField()
    fullscreen = serializers.BooleanField(required=False, default=False)


class DraftInput(StrictRequestSerializer):
    revision = serializers.IntegerField(min_value=0)
    answers = serializers.DictField(child=serializers.JSONField(), required=False)
    text = serializers.CharField(max_length=50000, allow_blank=True, required=False)
    file = serializers.FileField(required=False)
    remove_file = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        # DRF's HTML DictField parser synthesizes {} when multipart has no answers.
        if 'answers' not in self.initial_data:
            data.pop('answers', None)
        return data


class SubmitInput(StrictRequestSerializer):
    revision = serializers.IntegerField(min_value=0)
    confirmed = serializers.BooleanField(required=False, default=False)


class EventInput(StrictRequestSerializer):
    event_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=['TAB_HIDDEN', 'FULLSCREEN_EXIT'])


class GradeInput(StrictRequestSerializer):
    score = serializers.DecimalField(max_digits=4, decimal_places=2, min_value=0, max_value=10, required=False)
    feedback = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    published = serializers.BooleanField(required=False)
    moderation_note = serializers.CharField(max_length=5000, allow_blank=True, required=False)
