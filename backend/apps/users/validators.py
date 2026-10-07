from unicodedata import category

from django.core.exceptions import ValidationError


PASSWORD_REQUIREMENTS = (
    "Mật khẩu phải có ít nhất 8 ký tự, bao gồm ít nhất 1 chữ in hoa, "
    "1 chữ số (0-9) và 1 ký tự đặc biệt (không tính khoảng trắng)."
)


class PasswordComplexityValidator:
    def validate(self, password, user=None):
        if (
            len(password) < 8
            or not any(category(char) == "Lu" for char in password)
            or not any(char in "0123456789" for char in password)
            or not any(category(char)[0] in {"P", "S"} for char in password)
        ):
            raise ValidationError(PASSWORD_REQUIREMENTS, code="password_complexity")

    def get_help_text(self):
        return PASSWORD_REQUIREMENTS
