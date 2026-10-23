"""Durable incremental indexing of DB document versions, separate from PDF extraction."""
from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
import logging
from pathlib import Path
import uuid

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from filelock import FileLock
import faiss
import numpy as np

from apps.ai.embeddings.base import EmbeddedChunks, EmbeddingConfig
from apps.ai.retrieval.index import DenseIndex
from apps.ai.retrieval.storage import load_index, save_index
from apps.ai.runtime import setting
from .chunking import atomic_write, build_version_chunks, load_catalog
from .models import DocumentVersion, IngestionJob, KnowledgeDocument
from .retrieval_contracts import ChunkingConfig, canonical_hash
from .storage import private_path

logger=logging.getLogger(__name__)


def configs():
    embedding=EmbeddingConfig.from_file(setting('AI_EMBEDDING_CONFIG'))
    # BGE adds two special tokens; never let encoder silently truncate chunks.
    chunk=ChunkingConfig(tokenizer_revision=embedding.revision,tokenizer_model=embedding.model_id,
        max_tokens=embedding.max_tokens-2,overlap_tokens=min(64,(embedding.max_tokens-2)//4))
    return embedding,chunk


def available_versions():
    return DocumentVersion.objects.filter(removed_at__isnull=True,document__removed_at__isnull=True,
        status__in=('EXTRACTED','READY')).exclude(extracted_storage_key='')


def job_digest(version, embedding, chunk):
    return canonical_hash({'version':str(version.pk),'source':version.checksum_sha256,
        'extraction':version.extracted_storage_key,'title':version.document.title,
        'embedding':embedding.fingerprint(),'chunking':chunk.digest})


def enqueue_missing(embedding, chunk, *, retry_failed=False):
    count=0
    root=index_root()
    published={}
    pointer=root/'current.json'
    if pointer.exists():
        point=json.loads(pointer.read_bytes())
        if not point.get('empty'):
            raw=(root/point['generation']/'manifest.json').read_bytes()
            if hashlib.sha256(raw).hexdigest()!=point['manifest_sha256']:raise ValueError('Snapshot manifest changed')
            published=json.loads(raw)['metadata'].get('version_job_digests',{})
    for version in available_versions().select_related('document').iterator():
        digest=job_digest(version,embedding,chunk)
        job,created=IngestionJob.objects.get_or_create(idempotency_key=digest,
            defaults={'document_version':version,'job_type':'INDEX','payload_digest':digest})
        count+=created
        if job.status in ('SUCCEEDED','CANCELLED') and published.get(str(version.pk))!=digest:
            IngestionJob.objects.filter(pk=job.pk,status=job.status).update(
                status='QUEUED',worker_token=None,attempt_count=0,error_code='')
        if job.status=='FAILED' and (retry_failed or (job.attempt_count<3 and job.finished_at
                and job.finished_at<timezone.now()-timedelta(seconds=30))):
            updates={'status':'QUEUED','error_code':'','worker_token':None}
            if retry_failed:updates['attempt_count']=0
            IngestionJob.objects.filter(pk=job.pk,status='FAILED').update(**updates)
    return count


def claim_index_job():
    # Recover interrupted attempts without destroying the extracted PDF/view.
    IngestionJob.objects.filter(job_type='INDEX',status='RUNNING',lease_expires_at__lt=timezone.now()).update(
        status='FAILED',error_code='INDEX_WORKER_INTERRUPTED',worker_token=None,finished_at=timezone.now())
    for pk in IngestionJob.objects.filter(job_type='INDEX',status='QUEUED').order_by('created_at').values_list('pk',flat=True)[:20]:
        version_id,document_id=IngestionJob.objects.values_list('document_version_id','document_version__document_id').get(pk=pk)
        with transaction.atomic():
            document=KnowledgeDocument.objects.select_for_update().get(pk=document_id)
            version=DocumentVersion.objects.select_for_update().get(pk=version_id)
            job=IngestionJob.objects.select_for_update().get(pk=pk)
            if job.status!='QUEUED':continue
            if version.removed_at or document.removed_at or version.status not in ('EXTRACTED','READY'):
                job.status='CANCELLED';job.finished_at=timezone.now();job.save(update_fields=['status','finished_at']);continue
            job.status='RUNNING';job.worker_token=uuid.uuid4();job.started_at=timezone.now()
            job.lease_expires_at=timezone.now()+timedelta(hours=2);job.attempt_count+=1
            job.save(update_fields=['status','worker_token','started_at','lease_expires_at','attempt_count'])
            return job
    return None


def index_root():
    configured=setting('AI_INDEX_DIRECTORY')
    if not configured:raise ValueError('AI_INDEX_DIRECTORY is required')
    root=Path(configured).resolve()
    root.mkdir(parents=True,exist_ok=True)
    return root


def stored(root, config):
    pointer=root/'current.json'
    if not pointer.exists() or json.loads(pointer.read_bytes()).get('empty'):
        return [],np.empty((0,config.dimension),dtype=np.float32),{},{}
    # load_index checks FAISS bytes, hashes, vector/source mapping and exact config.
    index=load_index(root,config)
    point=json.loads(pointer.read_bytes())
    manifest=json.loads((root/point['generation']/'manifest.json').read_bytes())
    vector_index=faiss.deserialize_index(np.frombuffer(index.serialize(),dtype=np.uint8).copy())
    return (index.export_chunks(),vector_index.reconstruct_n(0,index.count),
        manifest['metadata'].get('catalog_manifest_keys',{}),manifest['metadata'].get('version_job_digests',{}))


def publish(root, records, vectors, manifests, config, digests):
    if not records:
        atomic_write(root/'current.json',b'{"storage_schema_version":"1.0","empty":true}\n')
        return
    matrix=np.ascontiguousarray(vectors,dtype=np.float32)
    index=DenseIndex(records,EmbeddedChunks(tuple(r['chunk_id'] for r in records),matrix,(),config.fingerprint()),config)
    save_index(index,root,metadata={'catalog_manifest_keys':manifests,'version_job_digests':digests,'producer':'document-index-worker-v1'})


def prune_index(config):
    root=index_root()
    with FileLock(str(root/'.writer.lock'),timeout=5):
        records,vectors,manifests,digests=stored(root,config)
        live={str(pk) for pk in available_versions().values_list('pk',flat=True)}
        keep=[i for i,r in enumerate(records) if r['version_id'] in live]
        if len(keep)==len(records):return
        publish(root,[records[i] for i in keep],vectors[keep],
            {k:v for k,v in manifests.items() if k in live},config,{k:v for k,v in digests.items() if k in live})


def process_index_job(job, embedding, tokenizer, chunk_config):
    token=job.worker_token
    try:
        version=DocumentVersion.objects.select_related('document').get(pk=job.document_version_id)
        if job_digest(version,embedding.config,chunk_config)!=job.payload_digest:
            IngestionJob.objects.filter(pk=job.pk,status='RUNNING',worker_token=token).update(status='CANCELLED',worker_token=None,finished_at=timezone.now())
            return
        artifact=build_version_chunks(version,chunk_config,tokenizer)
        records=[asdict(c) for c in load_catalog(private_path(artifact['manifest_key'])).values()]
        root=index_root()
        with FileLock(str(root/'.writer.lock'),timeout=5):
            old,vectors,_,_=stored(root,embedding.config)
        lookup={r['chunk_id']:(r,vectors[i]) for i,r in enumerate(old)}
        missing=[r for r in records if r['chunk_id'] not in lookup or lookup[r['chunk_id']][0]['text']!=r['text']]
        new_vectors={}
        if missing:
            encoded=embedding.embed_chunks(missing)
            new_vectors=dict(zip(encoded.chunk_ids,encoded.vectors))
        new_matrix=np.stack([new_vectors[r['chunk_id']] if r['chunk_id'] in new_vectors else lookup[r['chunk_id']][1] for r in records])
        # Keep a global writer lock only during merge/publish, not model loading/encoding.
        with FileLock(str(root/'.writer.lock'),timeout=30):
            old,vectors,manifests,digests=stored(root,embedding.config)
            with transaction.atomic():
                document=KnowledgeDocument.objects.select_for_update().get(pk=version.document_id)
                current=DocumentVersion.objects.select_for_update().select_related('document').get(pk=version.pk)
                locked=IngestionJob.objects.select_for_update().get(pk=job.pk)
                if (locked.status!='RUNNING' or locked.worker_token!=token or document.removed_at
                        or current.removed_at or current.status not in ('EXTRACTED','READY')
                        or job_digest(current,embedding.config,chunk_config)!=job.payload_digest):
                    if locked.status=='RUNNING' and locked.worker_token==token:
                        locked.status='CANCELLED';locked.worker_token=None;locked.finished_at=timezone.now()
                        locked.save(update_fields=['status','worker_token','finished_at'])
                    return
                live={str(pk) for pk in available_versions().values_list('pk',flat=True)}
                keep=[i for i,r in enumerate(old) if r['version_id'] in live and r['version_id']!=str(version.pk)]
                combined=[old[i] for i in keep]+records
                matrix=np.concatenate([vectors[keep],new_matrix],axis=0)
                manifests={k:v for k,v in manifests.items() if k in live}
                manifests[str(version.pk)]=artifact['manifest_key']
                digests={k:v for k,v in digests.items() if k in live}
                digests[str(version.pk)]=job.payload_digest
                publish(root,combined,matrix,manifests,embedding.config,digests)
                current.status='READY';current.indexed_at=timezone.now()
                current.save(update_fields=['status','indexed_at'])
                locked.status='SUCCEEDED';locked.worker_token=None;locked.finished_at=timezone.now();locked.error_code=''
                locked.save(update_fields=['status','worker_token','finished_at','error_code'])
    except Exception as exc:
        # Never put document text, credentials, local paths or raw model errors into status API.
        code=getattr(exc,'code','INDEX_BUILD_FAILED')
        if code not in {'MODEL_LOAD_FAILED','TOKEN_LIMIT_EXCEEDED','ENCODING_FAILED','SOURCE_CHANGED'}:code='INDEX_BUILD_FAILED'
        IngestionJob.objects.filter(pk=job.pk,status='RUNNING',worker_token=token).update(
            status='FAILED',error_code=code,worker_token=None,finished_at=timezone.now())
        logger.warning('Document indexing failed: job=%s code=%s type=%s',job.pk,code,type(exc).__name__)
