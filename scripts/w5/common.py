"""Strict offline I/O and canonical W5 contracts, independent of Django/model weights."""
import csv
import hashlib
import json
import sys
import tempfile
from functools import lru_cache
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend')) if str(ROOT/'backend') not in sys.path else None


def normalize(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def _nfc(value):
    if isinstance(value, str): return unicodedata.normalize('NFC', value)
    if isinstance(value, list): return [_nfc(v) for v in value]
    if isinstance(value, dict): return {k: _nfc(v) for k, v in value.items()}
    return value


def digest(value):
    return hashlib.sha256(json.dumps(_nfc(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def content_hash(record):
    return digest({k:v for k,v in record.items() if k!='content_sha256'})


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate JSON key: '+key)
        result[key] = value
    return result


def parse_json(text):
    def bad(value): raise ValueError('Non-finite JSON number: '+value)
    return json.loads(text, object_pairs_hook=_unique, parse_constant=bad)


def read_json(path):
    return parse_json(Path(path).read_text(encoding='utf-8-sig'))


def read_jsonl(path):
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip(): raise ValueError(f'Empty JSONL line {number}')
        row = parse_json(line)
        if not isinstance(row, dict): raise ValueError(f'Object required on line {number}')
        rows.append(row)
    if not rows: raise ValueError('Empty dataset')
    return rows


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames): raise ValueError('Invalid CSV headers')
        return list(reader)


def write_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    encoded=json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.w5-report-',delete=False) as f:
        temp=Path(f.name);f.write(encoded)
    try:temp.replace(path)
    finally:
        if temp.exists():temp.unlink()


def within(root, relative):
    root=Path(root).resolve(); path=(root/relative).resolve()
    if not path.is_relative_to(root): raise ValueError('Path outside source root')
    return path


def timestamp(value):
    date=datetime.fromisoformat(value.replace('Z','+00:00'))
    if date.tzinfo is None: raise ValueError('Timezone required')
    return date.astimezone(timezone.utc)


def load_contract(path):
    names={'schema':'schema.json','quality':'quality-policy.json','sources':'source-manifest.json',
        'fixture':'fixture-source.json','exclusion':'benchmark-exclusion-manifest.json','split':'split-policy.json',
        'training':'training-format.json','approval':'review-status.json'}
    values={key:read_json(Path(path)/name) for key,name in names.items()}
    values['allocation']=read_csv(Path(path)/'source_allocation.csv')
    values['fingerprint']=digest(values)
    return values


def projected(record, contract):
    from apps.ai.rag.base import EvidenceContext, ExerciseContext
    from apps.ai.rag.context_builder import build_messages
    fields=contract['quality']['evidence_context_projection']
    contexts=tuple(EvidenceContext.from_value({k:c[k] for k in fields}) for c in record['contexts'])
    exercise=ExerciseContext.from_value(record['exercise'])
    messages=build_messages(record['question'],record['mode'],contexts,exercise,prompt_version=record['prompt_version'])
    return contexts, [dict(m) for m in messages]


def prompt_data_strings(record):
    def strings(value):
        if isinstance(value,str):yield value
        elif isinstance(value,list):
            for item in value:yield from strings(item)
        elif isinstance(value,dict):
            for item in value.values():yield from strings(item)
    yield record['question']
    for ctx in record['contexts']:
        for key in ('source_id','chunk_id','text','document_id','version_id','document_title','section_title'):
            yield from strings(ctx[key])
    yield from strings(record['exercise'])


@lru_cache(maxsize=4096)
def ngrams(text):
    text=normalize(text)
    return frozenset(text[i:i+5] for i in range(max(1,len(text)-4)))


def similarity(a,b):
    a,b=ngrams(a),ngrams(b)
    return len(a&b)/len(a|b) if a|b else 0.0
