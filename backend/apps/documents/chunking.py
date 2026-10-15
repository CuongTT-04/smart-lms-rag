"""Validated chunk artifacts; deliberately does not publish or mark RAG READY."""
from dataclasses import asdict
import hashlib
import json
import os
import tempfile
from pathlib import Path
from .processors.chunker import chunk_extraction
from .retrieval_contracts import Chunk, canonical_hash
from .storage import private_path


def atomic_write(path, content):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    name=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.tmp',delete=False) as stream:
            name=stream.name;stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if name and os.path.exists(name):os.unlink(name)


def build_version_chunks(version, config, tokenizer):
    if (version.removed_at or version.document.removed_at or
            version.status not in ('EXTRACTED','READY') or not version.extracted_storage_key):
        raise ValueError('Version is not an available extracted source.')
    source=private_path(version.extracted_storage_key)
    source_bytes=source.read_bytes();envelope=json.loads(source_bytes)
    for field,expected in [('course_id',version.document.course_id),('document_id',version.document_id),
                           ('version_id',version.pk),('checksum_sha256',version.checksum_sha256),
                           ('page_count',version.page_count)]:
        if str(envelope.get(field))!=str(expected):raise ValueError(f'Extraction mismatch: {field}')
    original_key=getattr(version,'original_storage_key',None)
    if original_key and hashlib.sha256(private_path(original_key).read_bytes()).hexdigest()!=version.checksum_sha256:
        raise ValueError('Original source checksum mismatch.')
    chunks=chunk_extraction(envelope,version.document.title,config,tokenizer)
    if not chunks:raise ValueError('No usable text chunks.')
    # Content/config address allows safe rebuilds and independent generations.
    extraction_hash=hashlib.sha256(source_bytes).hexdigest()
    generation=canonical_hash({'extraction':extraction_hash,'config':config.digest,'title':version.document.title})
    prefix=f'chunks/{version.pk}/{generation}'
    content=('\n'.join(json.dumps(asdict(c),ensure_ascii=False,sort_keys=True) for c in chunks)+'\n').encode('utf-8')
    manifest={'schema_version':'1.0','version_id':str(version.pk),'document_id':str(version.document_id),
              'course_id':str(version.document.course_id),'source_checksum':version.checksum_sha256,
              'extraction_checksum':extraction_hash,'chunking_config':asdict(config),
              'chunking_config_hash':config.digest,'page_count':version.page_count,
              'chunk_count':len(chunks),'chunks_key':prefix+'/chunks.jsonl',
              'chunks_checksum':hashlib.sha256(content).hexdigest(),'rag_ready':False}
    atomic_write(private_path(manifest['chunks_key']),content)
    manifest_key=prefix+'/manifest.json'
    atomic_write(private_path(manifest_key),(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8'))
    return {'manifest_key':manifest_key,'chunks_key':manifest['chunks_key'],
            'chunk_count':len(chunks),'chunks_checksum':manifest['chunks_checksum']}


def load_catalog(manifest_path):
    """Only call with server-owned manifest paths, never a client file path."""
    manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    if manifest.get('schema_version')!='1.0' or canonical_hash(manifest['chunking_config'])!=manifest['chunking_config_hash']:
        raise ValueError('Invalid chunk manifest configuration.')
    content=private_path(manifest['chunks_key']).read_bytes()
    if hashlib.sha256(content).hexdigest()!=manifest['chunks_checksum']:
        raise ValueError('Chunk checksum mismatch.')
    catalog={}
    for line in content.decode('utf-8').splitlines():
        c=Chunk(**json.loads(line))
        if (c.chunk_id in catalog or c.schema_version!='1.0' or c.version_id!=manifest['version_id']
                or c.document_id!=manifest['document_id'] or c.course_id!=manifest['course_id']
                or c.source_checksum!=manifest['source_checksum']
                or c.chunking_config_hash!=manifest['chunking_config_hash']
                or type(c.page_number) is not int or not 1<=c.page_number<=manifest['page_count']
                or not c.text.strip() or c.char_start<0 or c.char_end<=c.char_start
                or type(c.token_count) is not int or not 0<c.token_count<=manifest['chunking_config']['max_tokens']):
            raise ValueError('Invalid chunk provenance or duplicate ID.')
        catalog[c.chunk_id]=c
    if len(catalog)!=manifest['chunk_count']:raise ValueError('Chunk count mismatch.')
    return catalog
