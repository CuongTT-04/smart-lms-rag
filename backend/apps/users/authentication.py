"""Versioned JWT authentication enforcing User.auth_version across all APIs."""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import User


def issue_refresh_token(user):
    refresh = RefreshToken.for_user(user)
    refresh["auth_version"] = user.auth_version
    return refresh


def issue_access_token(user):
    access = AccessToken.for_user(user)
    access["auth_version"] = user.auth_version
    return access


def validate_token_auth_version(user, token):
    if not user.is_active or user.status != User.Status.ACTIVE:
        raise AuthenticationFailed("Account unavailable.")
    token_version = token.get("auth_version")
    if token_version is not None:
        if token_version != user.auth_version:
            raise AuthenticationFailed("Session revoked; sign in again.")
    elif user.auth_version != 1:
        raise AuthenticationFailed("Session revoked; sign in again.")
    return user


class VersionedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        return validate_token_auth_version(user, validated_token)
