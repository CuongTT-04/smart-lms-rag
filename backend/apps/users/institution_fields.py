import re
import unicodedata

from django.core.exceptions import ValidationError


LEVELS = ('PRIMARY', 'LOWER_SECONDARY', 'UPPER_SECONDARY', 'COLLEGE', 'UNIVERSITY')


def normalize_search(value):
    value = unicodedata.normalize('NFKD', value.casefold().replace('đ', 'd').replace('Đ', 'D'))
    return ' '.join(re.sub(r'[^\w\s]', ' ', ''.join(c for c in value if not unicodedata.combining(c))).split())


def validate_levels(value):
    if not isinstance(value, list) or not value or len(value) > len(LEVELS) or any(v not in LEVELS for v in value) or len(set(value)) != len(value):
        raise ValidationError('Choose distinct supported education levels.')


def validate_aliases(value):
    if not isinstance(value, list) or len(value) > 20 or any(not isinstance(v, str) or not v.strip() or len(v) > 100 for v in value):
        raise ValidationError('Provide at most 20 non-empty aliases, each at most 100 characters.')
