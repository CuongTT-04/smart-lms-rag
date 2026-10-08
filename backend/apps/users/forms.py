from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "full_name", "avatar_url", "phone", "status")


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = (
            "username", "password", "email", "full_name", "avatar_url", "phone", "status",
            "is_staff", "is_superuser", "groups", "user_permissions",
        )
