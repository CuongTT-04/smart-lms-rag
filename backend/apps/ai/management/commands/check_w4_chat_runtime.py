"""Read-only preflight; does not build embeddings, call a model or publish sources."""
import json
import hashlib
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from apps.ai.runtime import get_runtime
from apps.documents.exceptions import DocumentError
from apps.documents.models import DocumentVersion, KnowledgeDocument


class Command(BaseCommand):
    help='Kiểm tra cấu hình chat/index/catalog và provenance DB; không gọi LLM hoặc tải model.'

    def add_arguments(self,parser):
        parser.add_argument('--output')

    def handle(self,*args,**options):
        report={'status':'NOT_CONFIGURED','llm_verified':False,'embedding_verified':False,
            'document_count':KnowledgeDocument.objects.filter(removed_at__isnull=True).count(),
            'published_document_count':KnowledgeDocument.objects.filter(removed_at__isnull=True,is_published=True).count()}
        try:
            runtime=get_runtime()
            versions={str(row.pk):row for row in DocumentVersion.objects.select_related('document').filter(pk__in={chunk.version_id for chunk in runtime.catalog.values()})}
            mismatches=[]
            for chunk in runtime.catalog.values():
                version=versions.get(chunk.version_id)
                if (not version or version.removed_at or version.document.removed_at or
                    str(version.document.course_id)!=chunk.course_id or str(version.document_id)!=chunk.document_id or
                    version.checksum_sha256!=chunk.source_checksum or not 1<=chunk.page_number<=version.page_count):
                    mismatches.append(chunk.chunk_id)
            identity={'manifest':runtime.index.manifest(),'index_sha256':hashlib.sha256(runtime.index.serialize()).hexdigest()}
            revision=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
            report.update(status='PROVENANCE_MISMATCH' if mismatches else 'CONFIGURED_NOT_MODEL_VERIFIED',
                chunk_count=len(runtime.catalog), mismatched_chunk_count=len(mismatches),
                index_revision=revision, model=runtime.config['model'])
        except DocumentError as exc:
            report['error_code']=exc.code
        text=json.dumps(report,ensure_ascii=False,indent=2)
        self.stdout.write(text)
        if options['output']:
            path=Path(options['output']);path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text+'\n',encoding='utf-8')
        if report['status']!='CONFIGURED_NOT_MODEL_VERIFIED':
            raise CommandError('W4 runtime chưa đạt preflight; xem báo cáo ở trên.')
