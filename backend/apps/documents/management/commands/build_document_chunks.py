"""Explicit operator command; no implicit RAG readiness or model download in worker."""
import json
import re
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from apps.documents.chunking import build_version_chunks
from apps.documents.models import DocumentVersion
from apps.documents.retrieval_contracts import ChunkingConfig


class Command(BaseCommand):
    help='Tạo chunk và manifest cho phiên bản PDF đã trích xuất; không công bố hoặc đánh dấu RAG READY.'
    def add_arguments(self,parser):
        parser.add_argument('--version-id',action='append',required=True)
        parser.add_argument('--config',required=True,help='Server/operator-owned JSON configuration file')
        parser.add_argument('--local-files-only',action='store_true')
    def handle(self,*args,**options):
        try:
            config=ChunkingConfig(**json.loads(Path(options['config']).read_text(encoding='utf-8')))
            if not re.fullmatch(r'[0-9a-f]{40}',config.tokenizer_revision):
                raise ValueError('Tokenizer revision must be a resolved 40-character commit SHA.')
            from transformers import AutoTokenizer
            tokenizer=AutoTokenizer.from_pretrained(config.tokenizer_model,revision=config.tokenizer_revision,
                use_fast=True,local_files_only=options['local_files_only'])
            if not tokenizer.is_fast:raise ValueError('Fast tokenizer with offsets is required.')
            results=[]
            for vid in dict.fromkeys(options['version_id']):
                version=DocumentVersion.objects.select_related('document').get(pk=vid)
                results.append({'version_id':str(version.pk),**build_version_chunks(version,config,tokenizer)})
            self.stdout.write(json.dumps({'results':results},ensure_ascii=False))
        except (ValueError,OSError,KeyError,ImportError,DocumentVersion.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
