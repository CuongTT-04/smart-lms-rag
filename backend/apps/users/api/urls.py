from django.urls import path

from .views import (
    CsrfTokenView,
    EmailVerificationConfirmView,
    EmailVerificationSendView,
    LoginView, LogoutView, MeView, RegisterView, SessionView, TokenRefreshView,
    PasswordResetRequestView, PasswordResetConfirmView,
    AvatarUploadView,
)


app_name = "users"

urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="csrf"),
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("email-verification/send/", EmailVerificationSendView.as_view(), name="email-verification-send"),
    path("email-verification/confirm/", EmailVerificationConfirmView.as_view(), name="email-verification-confirm"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("session/", SessionView.as_view(), name="session"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/avatar/", AvatarUploadView.as_view(), name="avatar-upload"),
]
