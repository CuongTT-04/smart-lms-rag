from rest_framework import serializers


class ResultProgressSummarySerializer(serializers.Serializer):
    total_activities = serializers.IntegerField()
    completed_activities = serializers.IntegerField()
    percent = serializers.FloatField()
    has_activities = serializers.BooleanField()
    completed_at = serializers.DateTimeField(allow_null=True)


class ResultAssessmentCellSerializer(serializers.Serializer):
    assessment_id = serializers.UUIDField()
    title = serializers.CharField()
    mode = serializers.ChoiceField(choices=['PRACTICE', 'TEST'])
    kind = serializers.ChoiceField(choices=['QUIZ', 'TEXT'])
    is_removed = serializers.BooleanField()
    is_overdue = serializers.BooleanField()
    submission_status = serializers.ChoiceField(choices=['NOT_SUBMITTED', 'DRAFT', 'SUBMITTED'])
    grading_status = serializers.ChoiceField(choices=['NOT_APPLICABLE', 'PENDING', 'GRADED'])
    has_pending_grading = serializers.BooleanField()
    score = serializers.FloatField(allow_null=True)
    score_policy = serializers.ChoiceField(choices=['HIGHEST_SUBMITTED', 'SINGLE_ATTEMPT'])
    attempt_count = serializers.IntegerField()
    submitted_attempts_count = serializers.IntegerField()
    pending_attempts_count = serializers.IntegerField()
    submitted_at = serializers.DateTimeField(allow_null=True)


class ClassroomResultRowSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    name = serializers.CharField()
    username = serializers.CharField()
    enrollment_status = serializers.CharField()
    progress = ResultProgressSummarySerializer()
    submitted_count = serializers.IntegerField()
    draft_count = serializers.IntegerField()
    not_submitted_count = serializers.IntegerField()
    pending_grading_count = serializers.IntegerField()
    pending_attempts_count = serializers.IntegerField()
    graded_count = serializers.IntegerField()
    overdue_count = serializers.IntegerField()
    average_score = serializers.FloatField(allow_null=True)
    assessments = ResultAssessmentCellSerializer(many=True)


class ClassroomResultAssessmentHeaderSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    mode = serializers.ChoiceField(choices=['PRACTICE', 'TEST'])
    kind = serializers.ChoiceField(choices=['QUIZ', 'TEXT'])
    due_at = serializers.DateTimeField()
    is_overdue = serializers.BooleanField()
    is_removed = serializers.BooleanField()


class ClassroomResultSummarySerializer(serializers.Serializer):
    student_count = serializers.IntegerField()
    active_assessment_count = serializers.IntegerField()
    removed_assessment_count = serializers.IntegerField()
    submitted_cells = serializers.IntegerField()
    draft_cells = serializers.IntegerField()
    not_submitted_cells = serializers.IntegerField()
    pending_grading_cells = serializers.IntegerField()
    pending_attempts = serializers.IntegerField()
    average_score = serializers.FloatField(allow_null=True)


class ClassroomResultsPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    classroom_id = serializers.UUIDField()
    classroom_name = serializers.CharField()
    viewer_role = serializers.ChoiceField(choices=['TEACHER', 'STUDENT'])
    score_policy = serializers.DictField()
    filters = serializers.DictField()
    assessments = ClassroomResultAssessmentHeaderSerializer(many=True)
    summary = ClassroomResultSummarySerializer()
    results = ClassroomResultRowSerializer(many=True)
