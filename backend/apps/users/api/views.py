from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.utils import get_md5_hash_password

from apps.users.models import User
from apps.users.avatars import upload_avatar
from apps.users.services import authenticate_user, register_user, request_password_reset, confirm_password_reset, update_user_profile
from apps.users.throttles import PasswordResetRequestThrottle, PasswordResetEmailThrottle, PasswordResetConfirmThrottle
from common.schema import AVATAR_BAD_REQUEST, FORBIDDEN, LOGIN_BAD_REQUEST, REGISTER_BAD_REQUEST, RESET_BAD_REQUEST, USER_UPDATE_BAD_REQUEST, DetailSerializer, UNAUTHORIZED

from .serializers import (
    CurrentUserSerializer, LoginResponseSerializer, LoginSerializer,
    RegistrationSerializer, SessionResponseSerializer, TokenRefreshResponseSerializer, UserSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    PasswordResetResponseSerializer,
    UserUpdateSerializer, UserUpdateResponseSerializer,
    AvatarUploadSerializer,
)


def set_refresh_cookie(response, refresh):
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        str(refresh),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.JWT_REFRESH_COOKIE_SECURE,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
        path=settings.JWT_REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response):
    response.delete_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        path=settings.JWT_REFRESH_COOKIE_PATH,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
    )


def refresh_unauthorized(detail):
    response = Response({"detail": detail}, status=status.HTTP_401_UNAUTHORIZED)
    clear_refresh_cookie(response)
    return response


def active_user_from_access(access):
    try:
        user = User.objects.get(pk=access["user_id"])
    except (User.DoesNotExist, KeyError) as error:
        raise AuthenticationFailed("Account unavailable.") from error
    if not user.is_active:
        raise AuthenticationFailed("Account unavailable.")
    if jwt_settings.CHECK_REVOKE_TOKEN and access.get(jwt_settings.REVOKE_TOKEN_CLAIM) != get_md5_hash_password(user.password):
        raise AuthenticationFailed("Password changed; sign in again.")
    return user


@method_decorator(never_cache, name="dispatch")
class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="users_register", tags=["Authentication"], summary="Register a student or teacher account",
        description="Choose STUDENT or TEACHER (required). Creates an ACTIVE account with only its matching profile, returned as student_profile or teacher_profile; the other key is omitted. learning_goal is student-only; bio and specialization are teacher-only (blank values allowed). ADMIN and permission fields are rejected. Sign in separately after registration.",
        request=RegistrationSerializer, auth=[],
        responses={201: CurrentUserSerializer, 400: REGISTER_BAD_REQUEST},
    )
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = register_user(**serializer.validated_data)
        except IntegrityError as error:
            identifiers = serializer.validated_data
            if User.objects.filter(
                Q(username__iexact=identifiers["username"]) | Q(email__iexact=identifiers["email"])
            ).exists():
                raise ValidationError({"detail": "Username or email is already registered."}) from error
            raise
        return Response({"user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


@method_decorator(never_cache, name="dispatch")
class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRequestThrottle, PasswordResetEmailThrottle]

    @extend_schema(
        operation_id="users_password_reset_request", tags=["Authentication"],
        summary="Request a password reset email", auth=[], request=PasswordResetRequestSerializer,
        description="Normally returns a generic message and sends a link by email. Development-only DEBUG + PASSWORD_RESET_PREVIEW returns reset_url for direct navigation instead of sending email. Never use preview with real user data. Limited to 5 requests/IP/hour and 3 requests/email/hour.",
        responses={200: PasswordResetResponseSerializer, 400: RESET_BAD_REQUEST, 429: DetailSerializer},
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        link = request_password_reset(**serializer.validated_data)
        data = {"detail": "If the email belongs to an eligible account, password reset instructions will be sent."}
        if settings.DEBUG and settings.PASSWORD_RESET_PREVIEW and link:
            data["reset_url"] = link
        return Response(data)


@method_decorator(never_cache, name="dispatch")
class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetConfirmThrottle]

    @extend_schema(
        operation_id="users_password_reset_confirm", tags=["Authentication"],
        summary="Set a new password using a reset link", auth=[], request=PasswordResetConfirmSerializer,
        description="Supply uid and token from the email. Tokens expire and cannot be reused. Success revokes old JWTs and requires a new login. Limited to 20 requests/IP/hour.",
        responses={200: DetailSerializer, 400: RESET_BAD_REQUEST, 429: DetailSerializer},
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            confirm_password_reset(**serializer.validated_data)
        except DjangoValidationError as error:
            raise ValidationError(error.message_dict) from error
        response = Response({"detail": "Password reset successfully. Please sign in again."})
        clear_refresh_cookie(response)
        return response


@method_decorator(never_cache, name="dispatch")
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="users_login", tags=["Authentication"], summary="Login with username/password",
        description="Returns a short-lived access token and sets an HttpOnly refresh-token cookie. Disabled accounts cannot login.",
        request=LoginSerializer, auth=[],
        responses={
            200: LoginResponseSerializer, 400: LOGIN_BAD_REQUEST, 403: FORBIDDEN,
            401: OpenApiResponse(DetailSerializer, description="Invalid credentials or unavailable account."),
        },
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate_user(**serializer.validated_data)
        if user is None:
            return Response(
                {"detail": "Invalid credentials or account unavailable."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        refresh = RefreshToken.for_user(user)
        response = Response({"user": UserSerializer(user).data, "access": str(refresh.access_token)})
        set_refresh_cookie(response, refresh)
        return response


@method_decorator(never_cache, name="dispatch")
class TokenRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="users_token_refresh", tags=["Authentication"],
        summary="Refresh access token", request=None, auth=[],
        responses={200: TokenRefreshResponseSerializer, 401: UNAUTHORIZED},
    )
    def post(self, request):
        refresh_value = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not refresh_value:
            return refresh_unauthorized("Refresh token missing.")
        serializer = TokenRefreshSerializer(data={"refresh": refresh_value})
        try:
            active_user_from_access(RefreshToken(refresh_value).access_token)
            serializer.is_valid(raise_exception=True)
            access = AccessToken(serializer.validated_data["access"])
            active_user_from_access(access)
        except (TokenError, AuthenticationFailed):
            return refresh_unauthorized("Refresh token invalid, expired, or unavailable.")
        response = Response({"access": serializer.validated_data["access"]})
        if refresh := serializer.validated_data.get("refresh"):
            set_refresh_cookie(response, refresh)
        return response


@method_decorator(never_cache, name="dispatch")
class SessionView(APIView):
    """Restore a browser session without treating an anonymous visitor as an error."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="users_session", tags=["Authentication"],
        summary="Restore browser session", request=None, auth=[],
        responses={200: SessionResponseSerializer},
    )
    def get(self, request):
        refresh_value = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not refresh_value:
            return Response({"authenticated": False})
        try:
            refresh = RefreshToken(refresh_value)
            access = refresh.access_token
            user = active_user_from_access(access)
        except (TokenError, AuthenticationFailed):
            response = Response({"authenticated": False})
            clear_refresh_cookie(response)
            return response
        return Response({
            "authenticated": True,
            "user": UserSerializer(user).data,
            "access": str(access),
        })


@method_decorator(never_cache, name="dispatch")
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="users_logout", tags=["Authentication"], summary="Logout and revoke refresh token",
        request=None, responses={204: None, 401: UNAUTHORIZED, 403: FORBIDDEN},
    )
    def post(self, request):
        refresh_value = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if refresh_value:
            try:
                RefreshToken(refresh_value).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


@method_decorator(never_cache, name="dispatch")
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="users_me", tags=["Authentication"], summary="Get current account",
        responses={200: CurrentUserSerializer, 401: UNAUTHORIZED, 403: FORBIDDEN},
    )
    def get(self, request):
        return Response({"user": UserSerializer(request.user).data})

    @extend_schema(
        operation_id="users_update_me", tags=["Authentication"], summary="Update own account and role-specific profile",
        description="Partial update, at least one editable field required. Role, status, IDs and privilege fields cannot be changed. Use snake_case fields. Changing email or password requires current_password; password also requires password_confirm. Password is hashed server-side. Password changes revoke existing JWTs and set requires_login=true.",
        request=UserUpdateSerializer,
        responses={200: UserUpdateResponseSerializer, 400: USER_UPDATE_BAD_REQUEST, 401: UNAUTHORIZED, 403: FORBIDDEN},
    )
    def patch(self, request):
        try:
            user, password_changed = update_user_profile(actor=request.user, changes=request.data)
        except DjangoValidationError as error:
            raise ValidationError(error.message_dict) from error
        except IntegrityError as error:
            # Validation and the unique database constraint both protect concurrent requests.
            duplicate = {}
            if isinstance(request.data, dict):
                for field in ("username", "email"):
                    value = request.data.get(field)
                    if isinstance(value, str) and User.objects.filter(**{f"{field}__iexact": value.strip()}).exclude(pk=request.user.pk).exists():
                        duplicate[field] = [f"This {field} is already registered."]
            if duplicate:
                raise ValidationError(duplicate) from error
            raise
        response = Response({"user": UserSerializer(user).data, "requires_login": password_changed})
        if password_changed:
            clear_refresh_cookie(response)
        return response


@method_decorator(never_cache, name="dispatch")
class AvatarUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        operation_id="users_upload_avatar", tags=["Authentication"], summary="Upload own avatar",
        description="Multipart field avatar: JPG, PNG or WebP up to 5 MB and 4096 pixels per side. Decoded, resized to at most 512 pixels and re-encoded with metadata removed. Replaces the current avatar without changing role or profile.",
        request=AvatarUploadSerializer,
        responses={200: CurrentUserSerializer, 400: AVATAR_BAD_REQUEST, 401: UNAUTHORIZED, 403: FORBIDDEN, 415: DetailSerializer},
    )
    def post(self, request):
        serializer = AvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = upload_avatar(actor=request.user, upload=serializer.validated_data["avatar"], absolute_url=request.build_absolute_uri)
        except DjangoValidationError as error:
            raise ValidationError(error.message_dict) from error
        return Response({"user": UserSerializer(user).data})
