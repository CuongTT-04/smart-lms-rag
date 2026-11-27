import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.users.institutions import prepare_institution
from apps.users.models import Institution


class Command(BaseCommand):
    help = 'Seed seven Hanoi institutions without overwriting existing catalog edits.'

    @transaction.atomic
    def handle(self, *args, **options):
        rows = json.loads((Path(__file__).resolve().parents[2] / 'data' / 'institutions.json').read_bytes())
        created = 0
        for row in rows:
            if Institution.objects.filter(code=row['code']).exists():
                continue
            obj = prepare_institution(row)
            obj.save()
            created += 1
        self.stdout.write(f'Created {created}; existing {len(rows) - created}; no existing values overwritten.')
