from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.users.validators import PasswordComplexityValidator, PASSWORD_REQUIREMENTS


class PasswordPolicyTests(SimpleTestCase):
    def test_required_character_types_and_length(self):
        for password in ("", "Ab1!xyz", "abcdefgh1!", "Abcdefgh!", "Abcdefg1", "Abcdef1 ", "Abcdef1\t", "Abcdef1\u200b", "Abcdef1\u0301"):
            with self.subTest(password=password), self.assertRaises(ValidationError):
                validate_password(password)

    def test_valid_passwords_do_not_require_lowercase_or_ascii_uppercase(self):
        for password in ("Abcdef1!", "ABCDEF1!", "Password1!", "Đabcdef1!", "Abcdef1_", "Abcdef1😀", "  Abcdef1!  "):
            with self.subTest(password=password):
                validate_password(password)

    def test_unicode_password_length_counts_characters_not_encoded_bytes(self):
        with self.assertRaises(ValidationError):
            validate_password("Đ1!😀😀😀😀")
        validate_password("Đ1!😀😀😀😀😀")

    def test_validator_help_describes_the_same_policy_as_its_error(self):
        validator = PasswordComplexityValidator()
        self.assertEqual(validator.get_help_text(), PASSWORD_REQUIREMENTS)
        with self.assertRaises(ValidationError) as context:
            validator.validate("invalid")
        self.assertEqual(context.exception.messages, [PASSWORD_REQUIREMENTS])
