from drf_spectacular.utils import OpenApiExample, OpenApiResponse
from rest_framework import serializers

from apps.courses.models import Course, CourseMember
from apps.users.models import User
from apps.users.services import REGISTRATION_ROLE_CHOICES


USER_ROLE_CHOICES = User.Role.choices
USER_STATUS_CHOICES = User.Status.choices
COURSE_STATUS_CHOICES = Course.Status.choices
COURSE_ROLE_CHOICES = CourseMember.Role.choices
MEMBER_STATUS_CHOICES = CourseMember.Status.choices


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField(read_only=True)


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField(read_only=True)
    service = serializers.CharField(read_only=True)


VALIDATION_ERROR_SCHEMA = {
    "type": "object",
    "additionalProperties": {
        "oneOf": [
            {"type": "array", "items": {"type": "string"}},
            {"type": "string"},
        ],
    },
}


def validation_error_response(*examples):
    return OpenApiResponse(
        response=VALIDATION_ERROR_SCHEMA,
        description="Validation errors keyed by field/non_field_errors; parse errors use detail.",
        examples=list(examples),
    )


PARSE_ERROR = OpenApiExample("Malformed JSON", value={"detail": "JSON parse error - ..."})
CREATE_BAD_REQUEST = validation_error_response(
    OpenApiExample("Blank title", value={"title": ["This field may not be blank."]}),
    OpenApiExample("Unexpected field", value={"owner_id": "This field is not accepted."}),
    PARSE_ERROR,
)
UPDATE_BAD_REQUEST = validation_error_response(
    OpenApiExample("Blank title", value={"title": ["This field may not be blank."]}),
    OpenApiExample("Empty update", value={"non_field_errors": ["Provide at least one field to update."]}),
    OpenApiExample("Immutable field", value={"id": "This field is not accepted."}),
    PARSE_ERROR,
)
LOGIN_BAD_REQUEST = validation_error_response(
    OpenApiExample("Required credentials", value={"username": ["This field is required."], "password": ["This field is required."]}),
    PARSE_ERROR,
)
REGISTER_BAD_REQUEST = validation_error_response(
    OpenApiExample("Duplicate identifier", value={"username": ["This username is already registered."]}),
    OpenApiExample("Password mismatch", value={"password_confirm": ["Passwords do not match."]}),
    OpenApiExample("Unsupported role", value={"role": ['"ADMIN" is not a valid choice.']}),
    OpenApiExample("Required role", value={"role": ["This field is required."]}),
    PARSE_ERROR,
)
RESET_BAD_REQUEST = validation_error_response(
    OpenApiExample("Invalid email", value={"email": ["Enter a valid email address."]}),
    OpenApiExample("Invalid reset link", value={"token": ["Reset link is invalid or expired."]}),
    OpenApiExample("Password mismatch", value={"password_confirm": ["Passwords do not match."]}),
    PARSE_ERROR,
)
USER_UPDATE_BAD_REQUEST = validation_error_response(
    OpenApiExample("Protected role", value={"role": ["This field is not accepted."]}),
    OpenApiExample("Incorrect current password", value={"current_password": ["Current password is incorrect."]}),
    OpenApiExample("Wrong profile", value={"teacher_profile": ["This profile does not match your role."]}),
    OpenApiExample("Duplicate email", value={"email": ["This email is already registered."]}),
    PARSE_ERROR,
)
AVATAR_BAD_REQUEST = validation_error_response(
    OpenApiExample("Missing file", value={"avatar": ["No file was submitted."]}),
    OpenApiExample("Oversized file", value={"avatar": ["Avatar must not exceed 5 MB."]}),
    OpenApiExample("Invalid image", value={"avatar": ["Upload a valid JPG, PNG or WebP image, at most 4096 pixels per side."]}),
)
GRANT_BAD_REQUEST = validation_error_response(
    OpenApiExample("Ineligible account", value={"user_id": ["Select an existing active student account."]}),
    OpenApiExample("Unexpected role", value={"role": "This field is not accepted."}),
    PARSE_ERROR,
)
REVOKE_BAD_REQUEST = validation_error_response(
    OpenApiExample("Protected membership", value={"member_id": ["Only student memberships can be revoked."]}),
)
FORBIDDEN = OpenApiResponse(
    response=DetailSerializer,
    description="Authenticated account lacks the required business permission.",
)
UNAUTHORIZED = OpenApiResponse(
    response=DetailSerializer,
    description="Bearer access token is missing, invalid, expired, or belongs to an unavailable account.",
)
NOT_FOUND = OpenApiResponse(
    response=DetailSerializer,
    description="Course or course-scoped membership not found.",
)
PAGE_NOT_FOUND = OpenApiResponse(
    response=DetailSerializer,
    description="Page number is invalid or outside the available pages.",
)
COURSE_OR_PAGE_NOT_FOUND = OpenApiResponse(
    response=DetailSerializer,
    description="Course not found, or page number is invalid/outside the available pages.",
)
def align_request_constraints(result, generator, request, public):
    # These serializers reject unknown fields; PATCH also rejects an empty object.
    schemas = result["components"]["schemas"]
    for name in ("CourseCreateRequest", "PatchedCourseUpdateRequest", "GrantStudentAccessRequest", "RegistrationRequest", "PasswordResetRequestRequest", "PasswordResetConfirmRequest", "AvatarUploadRequest"):
        if name in schemas:
            schemas[name]["additionalProperties"] = False
    if "PatchedCourseUpdateRequest" in schemas:
        schemas["PatchedCourseUpdateRequest"]["minProperties"] = 1
    for name in ("PatchedUserUpdateRequest", "StudentProfileUpdateRequest", "TeacherProfileUpdateRequest"):
        if name in schemas:
            schemas[name]["additionalProperties"] = False
            schemas[name]["minProperties"] = 1
    # Read-only fields are normally required by spectacular; profiles depend on role.
    if "User" in schemas:
        schemas["User"]["required"] = [
            field for field in schemas["User"].get("required", [])
            if field not in {"student_profile", "teacher_profile"}
        ]
    return result
