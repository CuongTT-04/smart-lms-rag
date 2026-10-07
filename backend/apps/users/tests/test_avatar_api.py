import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient

from apps.users.models import User
from common.testing import authenticate_client


def image_upload(format="JPEG", size=(800, 400), mode="RGB"):
    output = io.BytesIO()
    Image.new(mode, size, "red").save(output, format=format)
    return SimpleUploadedFile("local-image." + format.lower(), output.getvalue(), content_type="image/" + format.lower())


class AvatarAPITests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.directory.name, MEDIA_URL="/media/")
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = User.objects.create_user("avatar_student", password="Ohayo-839!")
        self.client = authenticate_client(APIClient(), self.user)
        self.url = reverse("users:avatar-upload")

    def upload(self, file=None, **extra):
        return self.client.post(self.url, {"avatar": file or image_upload(), **extra}, format="multipart")

    def stored_path(self, url):
        return Path(self.directory.name) / urlsplit(url).path.removeprefix("/media/")

    def test_upload_normalizes_and_updates_only_own_avatar(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.content)
        user = response.json()["user"]
        path = self.stored_path(user["avatar_url"])
        self.assertTrue(path.is_file())
        self.assertIn(str(self.user.pk), str(path))
        with Image.open(path) as image:
            self.assertEqual(image.size, (512, 256))
            self.assertEqual(image.format, "JPEG")
        self.assertEqual(user["username"], "avatar_student")
        self.assertEqual(user["role"], "STUDENT")
        self.assertNotIn("teacher_profile", user)

    def test_png_transparency_and_webp_supported(self):
        for format, mode in [("PNG", "RGBA"), ("WEBP", "RGB")]:
            with self.subTest(format=format):
                response = self.upload(image_upload(format, mode=mode))
                self.assertEqual(response.status_code, 200, response.content)
                with Image.open(self.stored_path(response.json()["user"]["avatar_url"])) as image:
                    self.assertEqual(image.mode, mode)

    def test_rejects_non_images_gif_oversized_dimensions_and_bytes(self):
        files = [
            SimpleUploadedFile("fake.jpg", b"not an image", content_type="image/jpeg"),
            SimpleUploadedFile("unsafe.svg", b"<svg></svg>", content_type="image/svg+xml"),
            image_upload("GIF"), image_upload(size=(4097, 1)),
            SimpleUploadedFile("large.jpg", b"x" * (5 * 1024 * 1024 + 1), content_type="image/jpeg"),
        ]
        for file in files:
            with self.subTest(file=file.name):
                response = self.upload(file)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("avatar", response.json())
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar_url, "")
        self.assertFalse(list(Path(self.directory.name).rglob("*.jpg")))

    def test_authentication_content_type_and_strict_fields(self):
        self.assertEqual(APIClient().post(self.url, {}, format="multipart").status_code, 401)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 415)
        self.assertEqual(self.client.post(self.url, {}, format="multipart").status_code, 400)
        self.assertEqual(self.upload(role="TEACHER").status_code, 400)

    def test_replacing_then_clearing_deletes_owned_files_after_commit(self):
        first = self.upload().json()["user"]["avatar_url"]
        with self.captureOnCommitCallbacks(execute=True):
            second = self.upload().json()["user"]["avatar_url"]
        self.assertFalse(self.stored_path(first).exists())
        self.assertTrue(self.stored_path(second).exists())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(reverse("users:me"), {"avatar_url": ""}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.stored_path(second).exists())

    def test_failed_database_save_removes_new_file(self):
        with patch.object(User, "save", side_effect=RuntimeError("database failure")):
            with self.assertRaises(RuntimeError):
                self.upload()
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar_url, "")
        self.assertFalse(list(Path(self.directory.name).rglob("*.jpg")))

    def test_does_not_delete_another_users_file(self):
        other = User.objects.create_user("other_avatar", password="Ohayo-839!")
        authenticate_client(self.client, other)
        other_url = self.upload().json()["user"]["avatar_url"]
        self.user.avatar_url = other_url
        self.user.save(update_fields=["avatar_url"])
        authenticate_client(self.client, self.user)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.upload().status_code, 200)
        self.assertTrue(self.stored_path(other_url).exists())
