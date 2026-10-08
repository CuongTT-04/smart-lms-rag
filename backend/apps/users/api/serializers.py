from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.users.models import StudentProfile, TeacherProfile, User
from apps.users.services import REGISTRATION_ROLE_CHOICES
from apps.users.validators import PASSWORD_REQUIREMENTS


class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = ("id", "learning_goal", "created_at", "updated_at")
        read_only_fields = fields


class TeacherProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherProfile
        fields = ("id", "bio", "specialization", "created_at", "updated_at")
        read_only_fields = fields


class RegistrationSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=8, max_length=128, help_text=PASSWORD_REQUIREMENTS)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    full_name = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=REGISTRATION_ROLE_CHOICES)
    avatar_url = serializers.URLField(max_length=2048, required=False, allow_blank=True, default="")
    phone = serializers.RegexField(r"^\+?[0-9]{8,15}$", max_length=20, required=False, allow_blank=True, default="")
    learning_goal = serializers.CharField(max_length=5000, required=False, allow_blank=True, default="")
    bio = serializers.CharField(max_length=5000, required=False, allow_blank=True, default="")
    specialization = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({field: ["This field is not accepted."] for field in sorted(unknown)})
        return super().to_internal_value(data)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is already registered.")
        return value

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def validate(self, attrs):
        errors = {}
        if attrs["role"] == User.Role.STUDENT:
            for field in ("bio", "specialization"):
                if attrs[field]:
                    errors[field] = ["This field requires the TEACHER role."]
        elif attrs["learning_goal"]:
            errors["learning_goal"] = ["This field requires the STUDENT role."]
        if errors:
            raise serializers.ValidationError(errors)
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": ["Passwords do not match."]})
        candidate = User(username=attrs["username"], email=attrs["email"], full_name=attrs["full_name"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages}) from error
        attrs.pop("password_confirm")
        return attrs


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({field: ["This field is not accepted."] for field in sorted(unknown)})
        return super().to_internal_value(data)


class PasswordResetResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    reset_url = serializers.URLField(required=False)


class AvatarUploadSerializer(PasswordResetRequestSerializer):
    email = None
    avatar = serializers.FileField()


class StudentProfileUpdateSerializer(PasswordResetRequestSerializer):
    email = None
    learning_goal = serializers.CharField(max_length=5000, allow_blank=True, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class TeacherProfileUpdateSerializer(StudentProfileUpdateSerializer):
    learning_goal = None
    bio = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    specialization = serializers.CharField(max_length=255, allow_blank=True, required=False)


class UserUpdateSerializer(PasswordResetRequestSerializer):
    username = serializers.CharField(max_length=150, validators=[UnicodeUsernameValidator()], required=False)
    email = serializers.EmailField(max_length=254, required=False)
    full_name = serializers.CharField(max_length=255, required=False)
    avatar_url = serializers.URLField(max_length=2048, allow_blank=True, required=False)
    phone = serializers.RegexField(r"^\+?[0-9]{8,15}$", max_length=20, allow_blank=True, required=False)
    password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False, write_only=True, required=False, help_text=PASSWORD_REQUIREMENTS)
    password_confirm = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True, required=False)
    current_password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True, required=False)
    student_profile = StudentProfileUpdateSerializer(required=False)
    teacher_profile = TeacherProfileUpdateSerializer(required=False)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exclude(pk=self.context["user"].pk).exists():
            raise serializers.ValidationError("This username is already registered.")
        return value

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exclude(pk=self.context["user"].pk).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def validate(self, attrs):
        if not set(attrs) - {"current_password", "password_confirm"}:
            raise serializers.ValidationError("Provide at least one field to update.")
        role = self.context["user"].role
        for field, expected in (("student_profile", User.Role.STUDENT), ("teacher_profile", User.Role.TEACHER)):
            if field in attrs and role != expected:
                raise serializers.ValidationError({field: ["This profile does not match your role."]})
        if "password" in attrs:
            if attrs.get("password_confirm") != attrs["password"]:
                raise serializers.ValidationError({"password_confirm": ["Passwords do not match."]})
        elif "password_confirm" in attrs:
            raise serializers.ValidationError({"password_confirm": ["Provide a new password as well."]})
        return attrs


class PasswordResetConfirmSerializer(PasswordResetRequestSerializer):
    email = None
    uid = serializers.CharField(max_length=128)
    token = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)
    password = serializers.CharField(min_length=8, max_length=128, write_only=True, trim_whitespace=False, help_text=PASSWORD_REQUIREMENTS)
    password_confirm = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": ["Passwords do not match."]})
        return attrs


class PublicUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "full_name", "role", "status")
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(source="date_joined", read_only=True)
    student_profile = StudentProfileSerializer(read_only=True, required=False)
    teacher_profile = TeacherProfileSerializer(read_only=True, required=False)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.role != User.Role.STUDENT:
            data.pop("student_profile", None)
        if instance.role != User.Role.TEACHER:
            data.pop("teacher_profile", None)
        return data

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "full_name", "avatar_url", "phone", "role", "status",
            "created_at", "updated_at", "last_login", "student_profile", "teacher_profile",
        )
        read_only_fields = fields


class CurrentUserSerializer(serializers.Serializer):
    user = UserSerializer(read_only=True)


class UserUpdateResponseSerializer(CurrentUserSerializer):
    requires_login = serializers.BooleanField(read_only=True)


class LoginResponseSerializer(CurrentUserSerializer):
    access = serializers.CharField(read_only=True)


class TokenRefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)


class SessionResponseSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField(read_only=True)
    user = UserSerializer(read_only=True, required=False)
    access = serializers.CharField(read_only=True, required=False)
