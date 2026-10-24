from rest_framework import serializers

CHAT_MODE_CHOICES=(('qa','Hỏi đáp'),('hint','Gợi ý'))


class ChatRequest(serializers.Serializer):
    question = serializers.CharField(max_length=8000, trim_whitespace=True)
    mode = serializers.ChoiceField(choices=CHAT_MODE_CHOICES, default='qa')
    course_id = serializers.UUIDField()
    classroom_id = serializers.UUIDField(required=False, allow_null=True)
    session_id = serializers.UUIDField(required=False, allow_null=True)
    document_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_null=True, max_length=100)
    assessment_id = serializers.UUIDField(required=False, allow_null=True)
    question_id = serializers.UUIDField(required=False, allow_null=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({'non_field_errors': ['Yêu cầu chứa trường không được hỗ trợ.']})
        return super().to_internal_value(data)

    def validate(self, data):
        if data['mode'] == 'hint' and not data.get('assessment_id'):
            raise serializers.ValidationError('Vui lòng chọn bài ôn tập cần gợi ý.')
        if data['mode'] == 'qa' and any(data.get(key) for key in ('assessment_id', 'question_id')):
            raise serializers.ValidationError('Hỏi đáp tài liệu không nhận thông tin bài tập.')
        if data.get('question_id') and not data.get('assessment_id'):
            raise serializers.ValidationError('Câu hỏi phải thuộc một bài tập.')
        if data.get('document_ids') is not None:
            data['document_ids'] = sorted({str(value) for value in data['document_ids']})
        return data


class CitationResponse(serializers.Serializer):
    label = serializers.IntegerField(min_value=1)
    document_id = serializers.UUIDField()
    version_id = serializers.UUIDField()
    chunk_id = serializers.CharField()
    document_title = serializers.CharField()
    page_number = serializers.IntegerField(min_value=1)
    section_title = serializers.CharField(allow_null=True)
    excerpt = serializers.CharField()


class ChatFeedbackRequest(serializers.Serializer):
    rating = serializers.ChoiceField(choices=('LIKE', 'DISLIKE'), allow_null=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != {'rating'}:
            raise serializers.ValidationError({'non_field_errors': ['Chỉ nhận trường rating.']})
        return super().to_internal_value(data)


class ChatResponse(serializers.Serializer):
    request_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=('ANSWERED', 'INSUFFICIENT_EVIDENCE'))
    mode = serializers.ChoiceField(choices=CHAT_MODE_CHOICES)
    answer = serializers.CharField()
    citations = CitationResponse(many=True)
    timing = serializers.DictField(child=serializers.FloatField(min_value=0))


class ChatErrorResponse(serializers.Serializer):
    request_id = serializers.UUIDField()
    code = serializers.CharField()
    message = serializers.CharField()
