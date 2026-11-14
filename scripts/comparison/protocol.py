"""Offline experiment boundary. No model calls or gold-to-generator path."""
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
import zipfile


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def write_rows(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b''.join(canonical(row) + b'\n' for row in rows))


def project_input(record):
    projected = {key: record[key] for key in ('qa_id', 'question', 'scope_id')}
    if any(not isinstance(v, str) or not v.strip() for v in projected.values()):
        raise ValueError('Empty input identity/question/scope')
    return projected


def validate_cache(row):
    allowed = {'qa_id', 'question', 'scope_id', 'contexts', 'contexts_sha256',
               'query_embedding_seconds', 'search_seconds', 'packing', 'index_sha256'}
    if set(row) - allowed: raise ValueError('Unexpected cache fields (possible gold leakage)')
    project_input(row)
    if 'index_sha256' in row and (not isinstance(row['index_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',row['index_sha256'])):
        raise ValueError('Invalid index hash')
    for key in ('query_embedding_seconds','search_seconds'):
        if key in row and (type(row[key]) not in (int,float) or not math.isfinite(row[key]) or row[key]<0):
            raise ValueError('Invalid retrieval timing')
    contexts = row['contexts']
    if not isinstance(contexts,list): raise ValueError('Contexts must be a list')
    if digest(contexts) != row['contexts_sha256']: raise ValueError('Context hash mismatch')
    ids = []
    for context in contexts:
        if not isinstance(context,dict): raise ValueError('Context must be an object')
        context_fields = {'chunk_id','course_id','text','page_number','rank','score','document_id',
                          'version_id','source_checksum','char_start','char_end','packed_char_end'}
        if set(context) - context_fields: raise ValueError('Unexpected nested context field')
        for key in ('chunk_id','course_id','text','document_id','version_id','source_checksum'):
            if key in context and (not isinstance(context[key],str) or not context[key].strip()):
                raise ValueError('Context identity/text must be nonempty strings')
        for key in ('rank','char_start','char_end','packed_char_end'):
            if key in context and (type(context[key]) is not int or context[key]<0):
                raise ValueError('Context offsets/rank must be integers')
        if 'score' in context and (type(context['score']) not in (int,float) or not math.isfinite(context['score'])):
            raise ValueError('Invalid context score')
        if context['course_id'] != row['scope_id']: raise ValueError('Cross-course context')
        if not context['text'].strip() or type(context['page_number']) is not int or context['page_number'] < 1:
            raise ValueError('Invalid evidence')
        ids.append(context['chunk_id'])
    if len(ids) != len(set(ids)): raise ValueError('Duplicate context')
    if 'packing' in row:
        packing = row['packing']
        allowed_packing = {'method','retrieved_chunks','original_contexts_sha256','truncated','evidence_tokens',
                           'chat_tokens','max_evidence_tokens','max_input_tokens'}
        if not isinstance(packing,dict) or set(packing)-allowed_packing: raise ValueError('Unexpected packing field')
        for key,value in packing.items():
            if key in {'method','original_contexts_sha256'} and not isinstance(value,str): raise ValueError('Invalid packing string')
            if key=='truncated' and type(value) is not bool: raise ValueError('Invalid packing boolean')
            if key in {'evidence_tokens','chat_tokens','max_evidence_tokens','max_input_tokens'} and (type(value) is not int or value<0):
                raise ValueError('Invalid packing token count')
        if not isinstance(packing.get('retrieved_chunks',[]),list): raise ValueError('Invalid packing list')
        for item in packing.get('retrieved_chunks',[]):
            if not isinstance(item,dict) or set(item)-{'chunk_id','document_id','page_number','text_sha256'}:
                raise ValueError('Unexpected retrieved metadata field')
            for key,value in item.items():
                if key=='page_number':
                    if type(value) is not int or value<1: raise ValueError('Invalid retrieved page')
                elif not isinstance(value,str): raise ValueError('Invalid retrieved identity/hash')


def write_bundle(directory, destination):
    directory, destination = Path(directory), Path(destination)
    if destination.exists(): raise FileExistsError(destination)
    files = sorted(p for p in directory.rglob('*') if p.is_file())
    if not files: raise ValueError('Empty bundle')
    manifest = {p.relative_to(directory).as_posix(): {'sha256': file_hash(p), 'bytes': p.stat().st_size} for p in files}
    if 'bundle-manifest.json' in manifest: raise ValueError('Reserved manifest name')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for p in files: archive.write(p, p.relative_to(directory).as_posix())
        archive.writestr('bundle-manifest.json', canonical(manifest))
    result = verify_bundle(destination)
    write_json(destination.with_suffix('.receipt.json'), result)
    return result


def verify_bundle(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)): raise ValueError('Duplicate archive names')
        for name in names:
            part = PurePosixPath(name)
            if part.is_absolute() or '..' in part.parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe archive path')
        manifest = json.loads(archive.read('bundle-manifest.json'))
        if set(names) != set(manifest) | {'bundle-manifest.json'}: raise ValueError('Unlisted/missing file')
        for name, info in manifest.items():
            data = archive.read(name)
            if len(data) != info['bytes'] or hashlib.sha256(data).hexdigest() != info['sha256']:
                raise ValueError(f'Checksum mismatch: {name}')
    return {'status': 'BYTE_INTEGRITY_PASSED', 'zip_sha256': file_hash(path),
            'zip_bytes': Path(path).stat().st_size, 'file_count': len(manifest),
            'semantic_acceptance': 'NOT_ASSERTED'}



