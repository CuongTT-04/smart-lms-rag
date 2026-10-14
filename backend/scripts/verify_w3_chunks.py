"""Offline corpus verification with real BGE tokenizer; no embeddings or READY claims.

PDF text for this probe is extracted with pypdf, not mislabeled as Docling output.
Runtime build_document_chunks uses the existing validated Docling extraction.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from uuid import NAMESPACE_URL,uuid5

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.test')
import django
django.setup()
from django.test import override_settings
from pypdf import PdfReader
import requests
from transformers import AutoTokenizer
from apps.documents.chunking import build_version_chunks,load_catalog
from apps.documents.processors.chunker import normalize_page
from apps.documents.retrieval_contracts import ChunkingConfig


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--corpus',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--revision')
    parser.add_argument('--limit',type=int)
    args=parser.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    revision=args.revision
    if not revision:
        response=requests.get('https://huggingface.co/api/models/BAAI/bge-m3',timeout=30)
        response.raise_for_status();revision=response.json()['sha']
    config=ChunkingConfig(tokenizer_revision=revision)
    tokenizer=AutoTokenizer.from_pretrained(config.tokenizer_model,revision=revision,use_fast=True)
    if not tokenizer.is_fast:raise ValueError('Offset mapping requires fast tokenizer.')
    (output/'chunking_config.json').write_text(json.dumps(asdict(config),indent=2),encoding='utf-8')
    results=[];started=time.monotonic()
    paths=sorted(Path(args.corpus).glob('*/*.pdf'))
    if args.limit:paths=paths[:args.limit]
    with override_settings(DOCUMENTS_STORAGE_ROOT=output/'documents'):
        for path in paths:
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            cid=str(uuid5(NAMESPACE_URL,'w3-course:'+path.parent.name))
            did=str(uuid5(NAMESPACE_URL,'w3-document:'+path.parent.name+'/'+path.name))
            vid=str(uuid5(NAMESPACE_URL,did+':'+digest))
            reader=PdfReader(path)
            pages=[{'page_number':i+1,'text':p.extract_text() or '', 'status':'OK'} for i,p in enumerate(reader.pages)]
            envelope={'schema_version':'1.0','course_id':cid,'document_id':did,'version_id':vid,
                      'checksum_sha256':digest,'page_count':len(pages),'pages':pages,
                      'parser':{'name':'pypdf','probe_only':True}}
            extraction_key=f'extracted/{vid}.json'
            extraction=output/'documents'/extraction_key;extraction.parent.mkdir(parents=True,exist_ok=True)
            extraction.write_text(json.dumps(envelope,ensure_ascii=False),encoding='utf-8')
            version=SimpleNamespace(pk=vid,document_id=did,document=SimpleNamespace(course_id=cid,
                title=path.name,removed_at=None),checksum_sha256=digest,page_count=len(pages),
                status='EXTRACTED',removed_at=None,extracted_storage_key=extraction_key)
            artifact=build_version_chunks(version,config,tokenizer)
            catalog=load_catalog(output/'documents'/artifact['manifest_key'])
            for page in pages:
                text=normalize_page(page['text']);covered=set()
                for c in catalog.values():
                    if c.page_number!=page['page_number']:continue
                    assert c.text==text[c.char_start:c.char_end]
                    assert len(tokenizer.encode(c.text,add_special_tokens=False))==c.token_count<=512
                    covered.update(range(c.char_start,c.char_end))
                assert all(i in covered for i,char in enumerate(text) if not char.isspace())
            again=build_version_chunks(version,config,tokenizer)
            assert again==artifact
            row={'subject_code':path.parent.name,'file':path.name,'course_id':cid,'document_id':did,
                 'version_id':vid,'source_checksum':digest,'page_count':len(pages),**artifact}
            results.append(row)
            print(json.dumps({'file':str(path),'pages':len(pages),'chunks':len(catalog)},ensure_ascii=False),flush=True)
    report={'schema_version':'1.0','probe_parser':'pypdf','tokenizer_model':config.tokenizer_model,
            'tokenizer_revision':revision,'config_hash':config.digest,'documents':results,
            'document_count':len(results),'chunk_count':sum(x['chunk_count'] for x in results),
            'elapsed_seconds':round(time.monotonic()-started,3),'rag_ready':False,
            'checks':['real_tokenizer_budget','physical_page_offsets','nonwhitespace_coverage','retry_idempotency','manifest_checksum'],
            'not_tested':['embeddings','vector_index','recall','cross_member_review']}
    (output/'corpus_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='documents'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
