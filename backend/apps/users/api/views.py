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
        operation_id="users_register", tags=["Authentication"], summary="Đăng ký tài khoản học viên hoặc giáo viên",
        description="API công khai, không cần đăng nhập. Bắt buộc chọn role là STUDENT (học viên) hoặc TEACHER (giáo viên). Tạo tài khoản ACTIVE và chỉ tạo/trả về hồ sơ tương ứng: student_profile hoặc teacher_profile; không có khóa hồ sơ của vai trò còn lại. learning_goal dành cho học viên; bio và specialization dành cho giáo viên, cho phép bỏ trống. Không chấp nhận ADMIN hay trường phân quyền. Thành công trả 201; cần đăng nhập riêng sau khi đăng ký.",
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
        summary="Yêu cầu liên kết đặt lại mật khẩu", auth=[], request=PasswordResetRequestSerializer,
        description="API công khai, nhận email. Thông thường trả thông báo chung và gửi liên kết qua email, không tiết lộ email có tài khoản hay không. Trong môi trường phát triển, khi DEBUG và PASSWORD_RESET_PREVIEW cùng bật, trả thêm reset_url để điều hướng trực tiếp thay vì gửi email. Không dùng chế độ này với dữ liệu người dùng thật. Giới hạn 5 yêu cầu/IP/giờ và 3 yêu cầu/email/giờ; vượt giới hạn trả 429.",
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
        summary="Đặt mật khẩu mới bằng liên kết khôi phục", auth=[], request=PasswordResetConfirmSerializer,
        description="API công khai. Gửi uid và token lấy từ liên kết đặt lại mật khẩu, cùng password và password_confirm khớp nhau. Mật khẩu tối thiểu 8 ký tự, có chữ in hoa, chữ số và ký tự đặc biệt. Token có thời hạn và không thể dùng lại sau khi đổi mật khẩu thành công. Thành công trả 200, vô hiệu hóa JWT cũ và yêu cầu đăng nhập lại. Giới hạn 20 yêu cầu/IP/giờ; vượt giới hạn trả 429.",
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
        operation_id="users_login", tags=["Authentication"], summary="Đăng nhập bằng tên tài khoản và mật khẩu",
        description="API công khai. Nhận username và password; thành công trả thông tin user cùng access token JWT ngắn hạn, đồng thời lưu refresh token trong cookie HttpOnly. Dùng access token trong mục Authorize của Swagger để gọi API cần xác thực; trình duyệt tự gửi cookie khi làm mới token. Sai thông tin hoặc tài khoản không khả dụng trả 401. Tài khoản bị vô hiệu hóa không thể đăng nhập.",
        request=LoginSerializer, auth=[],
        responses={
            200: LoginResponseSerializer, 400: LOGIN_BAD_REQUEST, 403: FORBIDDEN,
            401: OpenApiResponse(DetailSerializer, description="Tên tài khoản/mật khẩu không đúng hoặc tài khoản không khả dụng."),
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
        summary="Làm mới access token", request=None, auth=[],
        description="Không gửi body hay Bearer token. Trình duyệt cần gửi cookie refresh token nhận khi đăng nhập. Thành công trả access token mới và cập nhật cookie nếu refresh token được xoay vòng. Cookie thiếu, token không hợp lệ/hết hạn hoặc tài khoản không khả dụng trả 401 và xóa cookie; khi đó cần đăng nhập lại.",
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
        summary="Khôi phục phiên đăng nhập trên trình duyệt", request=None, auth=[],
        description="API công khai dùng khi mở hoặc tải lại ứng dụng, không cần Bearer token. Nếu cookie refresh token hợp lệ, trả authenticated=true cùng user và access token. Nếu không có cookie hoặc phiên không hợp lệ, vẫn trả 200 với authenticated=false; cookie không hợp lệ được xóa. Khách chưa đăng nhập không bị coi là lỗi xác thực.",
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
        operation_id="users_logout", tags=["Authentication"], summary="Đăng xuất và thu hồi refresh token",
        description="Yêu cầu Bearer JWT hợp lệ, không gửi body. Thu hồi refresh token trong cookie nếu có và xóa cookie trên trình duyệt. Thành công trả 204 không có body. Frontend phải xóa access token đang giữ; access token đã cấp không bị thu hồi ngay bởi thao tác đăng xuất và có thể còn hiệu lực đến khi hết hạn.",
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
        operation_id="users_me", tags=["Authentication"], summary="Xem thông tin tài khoản hiện tại",
        description="Yêu cầu Bearer JWT. Trả về user của tài khoản đang đăng nhập cùng hồ sơ tương ứng với vai trò: student_profile hoặc teacher_profile. Không nhận user_id để xem tài khoản người khác và không trả mật khẩu hay mật khẩu băm. Token thiếu, không hợp lệ hoặc hết hạn trả 401.",
        responses={200: CurrentUserSerializer, 401: UNAUTHORIZED, 403: FORBIDDEN},
    )
    def get(self, request):
        return Response({"user": UserSerializer(request.user).data})

    @extend_schema(
        operation_id="users_update_me", tags=["Authentication"], summary="Cập nhật tài khoản và hồ sơ theo vai trò",
        description="Yêu cầu Bearer JWT. Cập nhật một phần tài khoản của mình, gửi ít nhất một trường được phép: username, email, full_name, avatar_url, phone, mật khẩu hoặc hồ sơ tương ứng vai trò. Dùng tên trường snake_case. Không được sửa role, status, ID hay quyền hệ thống. student_profile nhận learning_goal; teacher_profile nhận bio và specialization. Đổi email hoặc mật khẩu cần current_password; mật khẩu mới cần password_confirm, tối thiểu 8 ký tự có chữ in hoa, chữ số và ký tự đặc biệt. Server tự băm mật khẩu, không nhận passwordHash. Đổi mật khẩu vô hiệu hóa JWT cũ và trả requires_login=true; các cập nhật khác không buộc đăng nhập lại.",
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
        operation_id="users_upload_avatar", tags=["Authentication"], summary="Tải ảnh đại diện từ máy lên",
        description="Yêu cầu Bearer JWT. Gửi multipart/form-data với trường tệp avatar, không gửi JSON. Chấp nhận JPG, PNG hoặc WebP tối đa 5 MB và 4096 pixel mỗi chiều. Server giải mã, thu nhỏ còn tối đa 512 pixel và mã hóa lại để loại bỏ metadata. Thay ảnh đại diện hiện tại, không đổi vai trò hay hồ sơ; thành công trả 200 cùng user đã cập nhật. Tệp không hợp lệ trả 400, kiểu nội dung không được hỗ trợ trả 415.",
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
