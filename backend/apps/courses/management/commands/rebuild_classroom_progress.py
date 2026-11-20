from django.core.management.base import BaseCommand

from apps.courses.models import Classroom
from apps.courses.progress_services import refresh_classroom_progress


class Command(BaseCommand):
    help = 'Tính lại tiến độ học tập cho dữ liệu lớp học hiện có.'

    def add_arguments(self, parser):
        parser.add_argument('--classroom-id', help='Chỉ tính lại cho một lớp cụ thể.')

    def handle(self, *args, **options):
        classroom_id = options.get('classroom_id')
        if classroom_id:
            updated = refresh_classroom_progress(classroom_id=classroom_id)
            self.stdout.write(f'Updated {updated} enrollment(s) for classroom {classroom_id}.')
            return
        total = 0
        for cid in Classroom.objects.values_list('pk', flat=True).order_by('pk'):
            total += refresh_classroom_progress(classroom_id=cid)
        self.stdout.write(f'Updated {total} enrollment(s) across classrooms.')
