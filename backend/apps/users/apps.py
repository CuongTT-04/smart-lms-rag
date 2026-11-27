from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    verbose_name = "Users"

    def ready(self):
        from .email_verification import register_email_verified_hook
        from .teacher_approval import auto_approve_verified_teacher
        register_email_verified_hook(auto_approve_verified_teacher)
