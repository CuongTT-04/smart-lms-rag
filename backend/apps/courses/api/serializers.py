from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.courses.models import AccessPolicy, Classroom, Course, CourseMember, Enrollment, JoinRequest
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


class CourseMemberSerializer(serializers.ModelSerializer):
    course_id = serializers.UUIDField(read_only=True)
    user = PublicUserSerializer(read_only=True)

    class Meta:
        model = CourseMember
        fields = ("id", "course_id", "user", "role", "status", "joined_at", "removed_at")
        read_only_fields = fields


class StrictRequestSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({field: ["This field is not accepted."] for field in unexpected})
        return values


class PolicyUpdateSerializer(StrictRequestSerializer):
    require_approval = serializers.BooleanField()
    visibility = serializers.ChoiceField(choices=AccessPolicy.Visibility.choices)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class PolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessPolicy
        fields = ("id", "visibility", "access_type", "price", "require_class_code", "require_approval", "created_at", "updated_at")
        read_only_fields = fields


class ClassroomInputSerializer(PolicyUpdateSerializer):
    require_approval = serializers.BooleanField(required=False)
    visibility = serializers.ChoiceField(choices=AccessPolicy.Visibility.choices, required=False)
    name = serializers.CharField(max_length=255)
    is_join_enabled = serializers.BooleanField(required=False)


class ClassroomSerializer(serializers.ModelSerializer):
    enrolled_count = serializers.SerializerMethodField()

    def get_enrolled_count(self, obj) -> int:
        return obj.enrollments.exclude(status="WITHDRAWN").count()

    course_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Classroom
        fields = ("id", "course_id", "name", "class_code", "is_join_enabled", "visibility", "require_approval", "enrolled_count", "created_at", "updated_at")
        read_only_fields = fields


class JoinByCodeSerializer(StrictRequestSerializer):
    class_code = serializers.RegexField(r"^[0-9A-Fa-f]{12}$", max_length=12)
    message = serializers.CharField(max_length=2000, allow_blank=True, default="")


class ReviewRequestSerializer(StrictRequestSerializer):
    decision = serializers.ChoiceField(choices=["approve", "reject"])
    review_note = serializers.CharField(max_length=2000, allow_blank=True, default="")


class EmptyRequestSerializer(StrictRequestSerializer):
    pass


class JoinRequestSerializer(serializers.ModelSerializer):
    course_id = serializers.UUIDField(source="classroom.course_id", read_only=True)
    course_title = serializers.CharField(source="classroom.course.title", read_only=True)
    classroom_name = serializers.CharField(source="classroom.name", read_only=True)
    student = PublicUserSerializer(read_only=True)

    class Meta:
        model = JoinRequest
        fields = ("id", "course_id", "course_title", "classroom_id", "classroom_name", "student", "status", "message", "reviewed_by_id", "review_note", "created_at", "updated_at", "reviewed_at")
        read_only_fields = fields


class EnrollmentSerializer(serializers.ModelSerializer):
    course_id = serializers.UUIDField(source="classroom.course_id", read_only=True)
    course_title = serializers.CharField(source="classroom.course.title", read_only=True)
    classroom_name = serializers.CharField(source="classroom.name", read_only=True)

    class Meta:
        model = Enrollment
        fields = ("id", "course_id", "course_title", "classroom_id", "classroom_name", "status", "enrolled_at", "progress_percent", "completed_at")
        read_only_fields = fields


class ClassroomEnrollmentSerializer(EnrollmentSerializer):
    student = PublicUserSerializer(source="student.user", read_only=True)

    class Meta(EnrollmentSerializer.Meta):
        fields = (*EnrollmentSerializer.Meta.fields, "student")
        read_only_fields = fields


class CourseSerializer(serializers.ModelSerializer):
    my_classrooms = serializers.SerializerMethodField()

    @extend_schema_field(EnrollmentSerializer(many=True))
    def get_my_classrooms(self, course):
        request = self.context.get("request")
        if not request or request.user.role != "STUDENT":
            return []
        records = []
        for classroom in course.classrooms.all():
            enrollments = getattr(classroom, "student_enrollments", None)
            if enrollments is None:
                enrollments = classroom.enrollments.filter(student__user=request.user).exclude(
                    status=Enrollment.Status.WITHDRAWN
                ).select_related("classroom__course")
            records.extend(enrollments)
        return EnrollmentSerializer(records, many=True).data

    class Meta:
        model = Course
        fields = (
            "id", "title", "description", "status",
            "created_at", "updated_at", "published_at", "my_classrooms",
        )
        read_only_fields = fields


class JoinResultSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ENROLLED", "PENDING"])
    enrollment = EnrollmentSerializer(allow_null=True)
    join_request = JoinRequestSerializer(allow_null=True)
