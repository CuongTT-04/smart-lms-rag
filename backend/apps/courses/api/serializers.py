from rest_framework import serializers

from apps.courses.models import Course, CourseMember
from apps.users.api.serializers import PublicUserSerializer


class CourseCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(
        allow_blank=True, default="", trim_whitespace=False
    )

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not accepted." for field in unexpected}
            )
        return values

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class CourseUpdateSerializer(CourseCreateSerializer):
    status = serializers.ChoiceField(choices=Course.Status.choices)


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = (
            "id", "title", "description", "status",
            "created_at", "updated_at", "published_at",
        )
        read_only_fields = fields


class GrantStudentAccessSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        unexpected = set(data) - {"user_id"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not accepted." for field in unexpected}
            )
        return values


class CourseMemberSerializer(serializers.ModelSerializer):
    course_id = serializers.UUIDField(read_only=True)
    user = PublicUserSerializer(read_only=True)

    class Meta:
        model = CourseMember
        fields = ("id", "course_id", "user", "role", "status", "joined_at", "removed_at")
        read_only_fields = fields
