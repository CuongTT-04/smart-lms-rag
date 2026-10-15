import json
import tempfile
from pathlib import Path
from django.test import SimpleTestCase
from django.core.management import call_command
from django.core.management.base import CommandError


class CommandTests(SimpleTestCase):
    def test_mutable_revision_is_rejected_before_model_load(self):
        with tempfile.TemporaryDirectory() as folder:
            config=Path(folder)/'config.json'
            config.write_text(json.dumps({'tokenizer_revision':'main'}))
            with self.assertRaisesRegex(CommandError,'commit SHA'):
                call_command('build_document_chunks',version_id=['00000000-0000-0000-0000-000000000001'],
                             config=str(config),local_files_only=True)
