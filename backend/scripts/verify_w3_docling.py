"""Isolated in-memory DB proof of Docling -> existing envelope -> operator chunk command."""
import argparse
import io
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE']='config.settings.test'
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import override_settings
from apps.courses.models import Course
from apps.documents.models import KnowledgeDocument,DocumentVersion
from apps.documents.processors.parser import extract_pdf
from apps.documents.processors.metadata import write_extraction
from apps.documents.chunking import load_catalog


def main():
    p=argparse.ArgumentParser();p.add_argument('--pdf',required=True);p.add_argument('--output',required=True)
    p.add_argument('--config',required=True);args=p.parse_args()
    if settings.DATABASES['default']['ENGINE']!='django.db.backends.sqlite3' or settings.DATABASES['default']['NAME']!=':memory:':
        raise RuntimeError('This verification must only use an isolated in-memory database.')
    call_command('migrate',verbosity=0)
    output=Path(args.output);root=output/'docling-documents';root.mkdir(parents=True,exist_ok=True)
    result=extract_pdf(Path(args.pdf))
    owner=get_user_model().objects.create_user('w3-probe',role='TEACHER')
    course=Course.objects.create(title='W3 isolated proof')
    doc=KnowledgeDocument.objects.create(course=course,uploaded_by=owner,title='Docling proof')
    original_key='originals/probe.pdf';original=root/original_key;original.parent.mkdir(parents=True,exist_ok=True)
    original.write_bytes(Path(args.pdf).read_bytes())
    version=DocumentVersion.objects.create(document=doc,version_number=1,file_name=Path(args.pdf).name,
        original_storage_key=original_key,file_size_bytes=original.stat().st_size,
        checksum_sha256=result.checksum_sha256,page_count=result.page_count,status='EXTRACTED',
        extracted_storage_key='extracted/probe.json')
    write_extraction(result,{'course_id':course.pk,'document_id':doc.pk,'version_id':version.pk},root/version.extracted_storage_key)
    with override_settings(DOCUMENTS_STORAGE_ROOT=root):
        stdout=io.StringIO()
        call_command('build_document_chunks',version_id=[str(version.pk)],config=args.config,
                     local_files_only=False,stdout=stdout)
        artifact=json.loads(stdout.getvalue())['results'][0]
        catalog=load_catalog(root/artifact['manifest_key'])
        version.refresh_from_db()
        assert version.status=='EXTRACTED' and version.indexed_at is None
    report={'parser':'Docling','parser_version':result.parser_version,'page_count':result.page_count,
        'chunk_count':len(catalog),'source_checksum':result.checksum_sha256,
        'checks':['in_memory_database','real_docling_extraction','real_management_command','verified_chunk_manifest',
                  'extracted_status_preserved','no_indexed_at_claim'],
        'not_tested':['embeddings','FAISS','Recall'],'artifact':artifact}
    (output/'docling_runtime_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
