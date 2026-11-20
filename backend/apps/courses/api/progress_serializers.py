from rest_framework import serializers


class ProgressActivitySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=['PDF', 'VIDEO', 'ASSESSMENT'])
    id = serializers.UUIDField()
    version_id = serializers.UUIDField(required=False)
    title = serializers.CharField()
    completed = serializers.BooleanField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get('kind') != 'PDF':
            data.pop('version_id', None)
        return data


class ProgressSessionSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    position = serializers.IntegerField()
    total_activities = serializers.IntegerField()
    completed_activities = serializers.IntegerField()
    activities = ProgressActivitySerializer(many=True)


class ClassroomProgressSerializer(serializers.Serializer):
    classroom_id = serializers.UUIDField()
    total_activities = serializers.IntegerField()
    completed_activities = serializers.IntegerField()
    percent = serializers.FloatField()
    has_activities = serializers.BooleanField()
    completed_at = serializers.DateTimeField(allow_null=True)
    sessions = ProgressSessionSerializer(many=True)
