import io
import logging
import re
import uuid
import warnings
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import User


MAX_AVATAR_BYTES = 5 * 1024 * 1024
logger = logging.getLogger(__name__)


def normalized_avatar(upload):
    if upload.size > MAX_AVATAR_BYTES:
        raise ValidationError({"avatar": ["Avatar must not exceed 5 MB."]})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Unsupported image format")
                if max(source.size) > 4096:
                    raise ValueError("Image dimensions exceed 4096 pixels")
                source.verify()
            upload.seek(0)
            with Image.open(upload) as source:
                mode = "RGBA" if "A" in source.getbands() or "transparency" in source.info else "RGB"
                image = ImageOps.exif_transpose(source).convert(mode)
                image.thumbnail((512, 512), Image.Resampling.LANCZOS)
                image.info.clear()
                output = io.BytesIO()
                extension = "png" if mode == "RGBA" else "jpg"
                image.save(output, format="PNG" if extension == "png" else "JPEG", **({"quality": 90} if extension == "jpg" else {}))
                return ContentFile(output.getvalue()), extension
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValidationError({"avatar": ["Upload a valid JPG, PNG or WebP image, at most 4096 pixels per side."]}) from error


def schedule_avatar_cleanup(user, old_url):
    path = unquote(urlsplit(old_url).path)
    prefix = urlsplit(settings.MEDIA_URL).path
    if not prefix.endswith("/"):
        prefix += "/"
    if not path.startswith(prefix):
        return
    name = path[len(prefix):]
    if not re.fullmatch(rf"avatars/{user.pk}/[a-f0-9]{{32}}\.(jpg|png)", name):
        return

    def cleanup():
        try:
            default_storage.delete(name)
        except OSError:
            logger.warning("Old avatar cleanup failed.")
    transaction.on_commit(cleanup)


def upload_avatar(*, actor, upload, absolute_url):
    content, extension = normalized_avatar(upload)
    name = default_storage.save(f"avatars/{actor.pk}/{uuid.uuid4().hex}.{extension}", content)
    try:
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=actor.pk)
            if not user.is_active or user.status != User.Status.ACTIVE or user.password != actor.password:
                raise PermissionDenied("Account or authentication changed; sign in again.")
            old_url = user.avatar_url
            user.avatar_url = absolute_url(default_storage.url(name))
            user.save(update_fields=["avatar_url"])
            schedule_avatar_cleanup(user, old_url)
        return user
    except Exception:
        default_storage.delete(name)
        raise
