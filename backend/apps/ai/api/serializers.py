from rest_framework import serializers

CHAT_MODE_CHOICES=(('qa','Hỏi đáp'),('hint','Gợi ý'),('summary','Tóm tắt nội dung'))


class ChatRequest(serializers.Serializer):
    question = serializers.CharField(max_length=8000, trim_whitespace=True)
    mode = serializers.ChoiceField(choices=CHAT_MODE_CHOICES, default='qa')
    course_id = serializers.UUIDField()
    classroom_id = serializers.UUIDField(required=False, allow_null=True)
    session_id = serializers.UUIDField(required=False, allow_null=True)
    document_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_null=True, max_length=100)
    assessment_id = serializers.UUIDField(required=False, allow_null=True,
        help_text='Bắt buộc với hint: bài PRACTICE đã công bố, thuộc phạm vi được phép. Không gửi đáp án, rubric hoặc trạng thái TEST từ client.')
    question_id = serializers.UUIDField(required=False, allow_null=True,
        help_text='Với hint cho QUIZ: ID câu hỏi trong bài; với TEXT: bỏ trường này. Chỉ nội dung đề và lựa chọn công khai được gửi tới model.')
    conversation_id = serializers.UUIDField(required=False)
    client_message_id = serializers.UUIDField(required=False)
    page_start = serializers.IntegerField(min_value=1, required=False)
    page_end = serializers.IntegerField(min_value=1, required=False)
    summary_request_id = serializers.UUIDField(required=False)
    hint_action = serializers.ChoiceField(choices=['initial', 'explain_task', 'next_step', 'practice'], required=False)
    previous_hint_id = serializers.UUIDField(required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({'non_field_errors': ['Yêu cầu chứa trường không được hỗ trợ.']})
        return super().to_internal_value(data)

    def validate(self, data):
        if data['mode'] != 'hint' and any(key in data for key in ('hint_action', 'previous_hint_id')):
            raise serializers.ValidationError('Thao tác gợi ý chỉ dùng cho bài ôn tập.')
        if data.get('hint_action') in ('next_step', 'practice') and not data.get('previous_hint_id'):
            raise serializers.ValidationError('Cần lượt gợi ý trước để tiếp tục.')
        if bool(data.get('conversation_id')) != bool(data.get('client_message_id')):
            raise serializers.ValidationError('Phiên chat cần mã lượt hỏi để tránh gửi trùng.')
        if data.get('conversation_id') and data['mode'] != 'qa':
            raise serializers.ValidationError('Phiên tài liệu chỉ hỗ trợ hỏi đáp học liệu.')
        if data['mode'] == 'hint' and not data.get('assessment_id'):
            raise serializers.ValidationError('Vui lòng chọn bài ôn tập cần gợi ý.')
        if data['mode'] != 'hint' and any(data.get(key) for key in ('assessment_id', 'question_id')):
            raise serializers.ValidationError('Hỏi đáp tài liệu không nhận thông tin bài tập.')
        if data.get('question_id') and not data.get('assessment_id'):
            raise serializers.ValidationError('Câu hỏi phải thuộc một bài tập.')
        if data.get('document_ids') is not None:
            data['document_ids'] = sorted({str(value) for value in data['document_ids']})
        if data['mode'] == 'summary':
            if len(data.get('document_ids') or []) != 1:
                raise serializers.ValidationError('Tóm tắt cần chọn đúng một học liệu.')
            if data.get('page_start', 1) > data.get('page_end', 2147483647):
                raise serializers.ValidationError('Trang bắt đầu không được lớn hơn trang kết thúc.')
        elif 'page_start' in data or 'page_end' in data or 'summary_request_id' in data:
            raise serializers.ValidationError('Phạm vi trang chỉ dùng cho tóm tắt.')
        return data


class ConversationSelector(serializers.Serializer):
    course_id = serializers.UUIDField()
    classroom_id = serializers.UUIDField(required=False, allow_null=True)
    session_id = serializers.UUIDField(required=False, allow_null=True)
    document_id = serializers.UUIDField()

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data)-set(self.fields):
            raise serializers.ValidationError({'non_field_errors': ['Phạm vi lịch sử không hợp lệ.']})
        return super().to_internal_value(data)


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
    conversation_id = serializers.UUIDField(required=False)
    turn_id = serializers.UUIDField(required=False)
    memory = serializers.DictField(required=False)
    coverage = serializers.DictField(required=False)
    hint = serializers.DictField(required=False)
    suggested_questions = serializers.ListField(child=serializers.CharField(max_length=240), max_length=3, required=False,
        help_text='Tối đa 3 câu hỏi tiếp theo từ nguồn hiện tại; không tự gửi hoặc gọi model thêm. Có thể rỗng nếu không có gợi ý phù hợp.')
    rating = serializers.ChoiceField(choices=['LIKE', 'DISLIKE'], required=False, allow_null=True)


class ConversationPendingResponse(serializers.Serializer):
    status = serializers.ChoiceField(choices=['PENDING'])
    conversation_id = serializers.UUIDField()
    turn_id = serializers.UUIDField()


class SummaryProgress(serializers.Serializer):
    phase = serializers.ChoiceField(choices=['map', 'reduce'])
    blocks_read = serializers.IntegerField(min_value=0)
    blocks_total = serializers.IntegerField(min_value=1)
    steps = serializers.IntegerField(min_value=0)


class SummaryFailure(serializers.Serializer):
    code = serializers.CharField()
    remote_code = serializers.CharField(required=False,
        help_text='Mã lỗi gateway đã qua danh sách cho phép, không chứa nội dung model hoặc token.')
    reason = serializers.CharField(required=False)


class SummaryTaskResponse(serializers.Serializer):
    id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=['summary'])
    status = serializers.ChoiceField(choices=['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'])
    progress = SummaryProgress()
    result = ChatResponse(allow_null=True)
    error = SummaryFailure(allow_null=True)


class ConversationMetadata(serializers.Serializer):
    id = serializers.UUIDField()
    document_id = serializers.UUIDField()
    version_id = serializers.UUIDField()
    title = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class ConversationTurnResponse(serializers.Serializer):
    id = serializers.UUIDField()
    position = serializers.IntegerField(min_value=1)
    question = serializers.CharField()
    status = serializers.ChoiceField(choices=['PENDING', 'COMPLETED', 'FAILED'])
    result = ChatResponse(allow_null=True)
    error = serializers.DictField(allow_null=True)
    created_at = serializers.DateTimeField()


class ConversationPage(serializers.Serializer):
    results = ConversationMetadata(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class ConversationDetail(ConversationMetadata):
    turns = ConversationTurnResponse(many=True)
    next_before = serializers.IntegerField(min_value=1, allow_null=True)


class ChatErrorResponse(serializers.Serializer):
    request_id = serializers.UUIDField()
    code = serializers.CharField()
    message = serializers.CharField()
