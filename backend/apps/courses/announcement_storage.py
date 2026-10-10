from pathlib import Path
from django.conf import settings
from django.core.files.storage import FileSystemStorage


class AnnouncementStorage(FileSystemStorage):
    @property
    def base_location(self):
        return Path(getattr(settings, 'ANNOUNCEMENTS_STORAGE_ROOT', Path(settings.BASE_DIR) / '.private' / 'announcements'))

    @property
    def location(self):
        return str(self.base_location.resolve())


def announcement_storage():
    return AnnouncementStorage()
