import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections


class Command(BaseCommand):
    help='Tự động chia đoạn, embedding và cập nhật FAISS cho học liệu đã trích xuất.'

    def add_arguments(self,parser):
        parser.add_argument('--once',action='store_true')
        parser.add_argument('--poll-seconds',type=float,default=5)
        parser.add_argument('--retry-failed',action='store_true')

    def handle(self,*args,**options):
        from apps.ai.embeddings.service import EmbeddingService
        from apps.documents.indexing import configs,enqueue_missing,claim_index_job,process_index_job,prune_index
        config,chunk_config=configs()
        embedding=EmbeddingService(config)
        tokenizer=None
        self.stdout.write('Index worker ready; waiting for extracted PDFs.')
        try:
            while True:
                close_old_connections()
                enqueue_missing(config,chunk_config,retry_failed=options['retry_failed'])
                job=claim_index_job()
                if job:
                    if tokenizer is None:
                        try:
                            from transformers import AutoTokenizer
                            tokenizer=AutoTokenizer.from_pretrained(config.model_id,revision=config.revision,
                                use_fast=True,local_files_only=config.local_files_only,trust_remote_code=False)
                            if not tokenizer.is_fast:raise ValueError('Fast tokenizer required')
                        except Exception:
                            from apps.documents.models import IngestionJob
                            from django.utils import timezone
                            IngestionJob.objects.filter(pk=job.pk,worker_token=job.worker_token).update(
                                status='FAILED',error_code='TOKENIZER_LOAD_FAILED',worker_token=None,finished_at=timezone.now())
                            self.stderr.write('Tokenizer unavailable; job retained for retry.')
                            if options['once']:return
                            time.sleep(30);continue
                    process_index_job(job,embedding,tokenizer,chunk_config)
                    self.stdout.write('Processed index job '+str(job.pk))
                prune_index(config)
                if options['once']:return
                if not job:time.sleep(max(0.1,min(30,options['poll_seconds'])))
        except KeyboardInterrupt:
            self.stdout.write('Index worker stopped.')
