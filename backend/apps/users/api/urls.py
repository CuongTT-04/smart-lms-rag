from django.urls import path

from .views import (
    LoginView, LogoutView, MeView, RegisterView, SessionView, TokenRefreshView,
    PasswordResetRequestView, PasswordResetConfirmView,
    AvatarUploadView,
)


app_name = "users"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("session/", SessionView.as_view(), name="session"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/avatar/", AvatarUploadView.as_view(), name="avatar-upload"),
]
