"""Authenticated, read-only W5 intake and shared W6 data contracts."""
import hashlib
import io
import json
import re
import stat
import unicodedata
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[2]
SPLITS=('train','validation','instruction_holdout')
ARCHIVE_MEMBERS={'dataset-config.json','manifest.json','metadata.jsonl',*(s+'.jsonl' for s in SPLITS)}


def require(condition,code):
    if not condition:raise ValueError(code)


def _nfc(value):
    if isinstance(value,str):return unicodedata.normalize('NFC',value)
    if isinstance(value,list):return [_nfc(v) for v in value]
    if isinstance(value,dict):return {k:_nfc(v) for k,v in value.items()}
    return value


def canonical(value):
    return json.dumps(_nfc(value),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()


def sha_bytes(value):return hashlib.sha256(value).hexdigest()


def sha_file(path):return sha_bytes(Path(path).read_bytes())


def loads(text):
    def pairs(items):
        result={}
        for k,v in items:
            require(k not in result,'DUPLICATE_JSON_KEY');result[k]=v
        return result
    def bad(value):raise ValueError('NONFINITE_JSON:'+value)
    return json.loads(text,object_pairs_hook=pairs,parse_constant=bad)


def jsonl(data):
    result=[]
    for line in data.decode('utf-8-sig').splitlines():
        require(bool(line.strip()),'EMPTY_JSONL_LINE')
        value=loads(line);require(isinstance(value,dict),'JSONL_OBJECT_REQUIRED');result.append(value)
    return result


def read_json(path):return loads(Path(path).read_text(encoding='utf-8-sig'))


def write_once(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        require(path.read_bytes()==data,'OUTPUT_EXISTS_DIFFERENT:'+str(path));return
    with path.open('xb') as stream:stream.write(data)


def write_json(path,value):
    write_once(path,(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())


def write_jsonl(path,rows):write_once(path,b''.join(canonical(row)+b'\n' for row in rows))


def within(root,relative):
    require(isinstance(relative,str) and not Path(relative).is_absolute(),'RELATIVE_PATH_REQUIRED')
    root=Path(root).resolve();path=(root/relative).resolve()
    require(path.is_relative_to(root),'PATH_OUTSIDE_ROOT');return path


def validate_payload(row):
    require(isinstance(row,dict) and set(row)=={'prompt','completion'},'PAYLOAD_FIELDS')
    require(isinstance(row['prompt'],list) and [m.get('role') for m in row['prompt']]==['system','user'],'PROMPT_ROLES')
    require(isinstance(row['completion'],list) and len(row['completion'])==1 and row['completion'][0].get('role')=='assistant','COMPLETION_ROLE')
    for message in row['prompt']+row['completion']:
        require(set(message)=={'role','content'} and isinstance(message['content'],str) and message['content'].strip(),'MESSAGE_FIELDS')
    user=loads(row['prompt'][-1]['content'])
    require(isinstance(user,dict) and set(user)=={'question','mode','evidence','exercise'},'USER_FIELDS')
    require(isinstance(user['question'],str) and user['question'].strip(),'QUESTION_REQUIRED')
    require(user['mode'] in ('qa','hint') and isinstance(user['evidence'],list) and user['evidence'],'EVIDENCE_REQUIRED')
    for index,context in enumerate(user['evidence'],1):
        require(context.get('source_id')==f'S{index}' and type(context.get('citation_label')) is int and context['citation_label']==index,'SOURCE_LABEL_BINDING')
    return user


def load_archive(path,expected):
    """Verify bytes and split/sidecar bindings before exposing any row; no extractall."""
    path=Path(path);require(path.stat().st_size<=16*1024*1024,'ARCHIVE_TOO_LARGE')
    raw=path.read_bytes();require(sha_bytes(raw)==expected['archive_sha256'],'ARCHIVE_HASH')
    with ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist();names=[i.filename for i in infos]
        require(len(names)==len(set(names)) and set(names)==ARCHIVE_MEMBERS,'ARCHIVE_MEMBERS')
        require(sum(i.file_size for i in infos)<=32*1024*1024,'ARCHIVE_EXPANDED_SIZE')
        require(all(not stat.S_ISLNK(i.external_attr>>16) and not i.is_dir() for i in infos),'ARCHIVE_FILE_TYPE')
        files={i.filename:z.read(i) for i in infos}
    manifest=loads(files['manifest.json']);cfg=loads(files['dataset-config.json'])
    require(set(manifest['files'])==ARCHIVE_MEMBERS-{'manifest.json'},'MANIFEST_MEMBERS')
    for name,info in manifest['files'].items():
        require(info['size_bytes']==len(files[name]) and info['sha256']==sha_bytes(files[name]),'MEMBER_INTEGRITY:'+name)
    for obj in (manifest,cfg):
        require(obj['record_count']==expected['record_count'] and obj['split_counts']==expected['split_counts'],'ARCHIVE_COUNTS')
        require(obj['source_package_manifest_sha256']==expected['source_package_manifest_sha256'],'SOURCE_PACKAGE_HASH')
    rows={s:jsonl(files[s+'.jsonl']) for s in SPLITS}
    require({s:len(v) for s,v in rows.items()}==expected['split_counts'],'SPLIT_BINDING')
    metadata=jsonl(files['metadata.jsonl']);require(len(metadata)==expected['record_count'],'METADATA_COUNT')
    seen=set();positions=set();groups={};families={};records=[]
    for m in metadata:
        rid=m['record_id'];split=m['split'];index=m['row_index']
        require(isinstance(rid,str) and rid not in seen,'DUPLICATE_RECORD_ID');seen.add(rid)
        require(split in SPLITS and type(index) is int and 0<=index<len(rows[split]) and (split,index) not in positions,'SPLIT_BINDING')
        positions.add((split,index));row=rows[split][index]
        require(digest(row)==m['sft_sha256'],'PAYLOAD_HASH_BINDING:'+rid)
        require(isinstance(m['content_sha256'],str) and bool(re.fullmatch(r'[a-f0-9]{64}',m['content_sha256'])),'CONTENT_HASH')
        require(m['task_type'] in ('qa','summary','hint','insufficient_evidence') and m['author_member'] in ('A','B'),'RECORD_METADATA')
        user=validate_payload(row)
        require(user['mode']==('hint' if m['task_type']=='hint' else 'qa'),'TASK_MODE')
        require(len(m['sources'])==len(user['evidence']),'SOURCE_METADATA_COUNT')
        for source,context in zip(m['sources'],user['evidence']):
            require(all(source[k]==context[k] for k in ('source_id','document_id','version_id','page_number')),'SOURCE_METADATA_BINDING')
            require(sha_bytes(context['text'].encode())==source['text_sha256'],'SOURCE_TEXT_HASH')
        require(isinstance(m['source_group_ids'],list) and m['source_group_ids'],'SOURCE_GROUP_REQUIRED')
        for group in m['source_group_ids']:
            require(group not in groups or groups[group]==split,'SOURCE_SPLIT_LEAKAGE');groups[group]=split
        family=m['variant_family_id']
        require(isinstance(family,str) and family,'FAMILY_REQUIRED')
        require(family not in families or families[family]==split,'FAMILY_SPLIT_LEAKAGE');families[family]=split
        records.append({'payload':row,'metadata':m})
    lookup={r['metadata']['record_id']:r['metadata'] for r in records}
    for m in lookup.values():
        parent=m.get('parent_record_id')
        if parent:require(parent in lookup and lookup[parent]['split']==m['split'],'PARENT_SPLIT_LEAKAGE')
    require(len(positions)==sum(len(v) for v in rows.values()),'SPLIT_BINDING')
    for field,key in [('course_code','course_counts'),('task_type','task_counts')]:
        if key in cfg:require(dict(Counter(m[field] for m in metadata))==cfg[key],'DECLARED_COUNTS:'+key)
    return dict(records=records,config=cfg,manifest=manifest,files=files,archive_sha256=sha_bytes(raw),
                source_group_splits=groups,variant_family_splits=families)


class SourceVerifier:
    def __init__(self,source_manifest,repo=ROOT):
        self.root=Path(repo);self.sources=source_manifest['sources'];self.cache={};self.pdfs={};self.checked=set()
        self.by_identity={(s['document_id'],s['version_id']):s for s in self.sources}
        require(len(self.by_identity)==len(self.sources),'DUPLICATE_SOURCE_IDENTITY')

    def check_registry(self):
        for source in self.sources:
            path=within(self.root,source['relative_path'])
            require(path.is_file() and sha_file(path)==source['source_checksum'],'PDF_CHECKSUM:'+source['source_group_id'])

    def check(self,row):
        from pypdf import PdfReader
        m=row['metadata'];user=validate_payload(row['payload'])
        for src,ctx in zip(m['sources'],user['evidence']):
            source=self.by_identity.get((ctx['document_id'],ctx['version_id']))
            require(source is not None and source['source_group_id'] in m['source_group_ids'],'UNKNOWN_PDF_IDENTITY')
            require(source['source_checksum']==src['source_checksum'] and source['course_code']==m['course_code'],'PDF_METADATA_MISMATCH')
            key=source['source_group_id'];path=within(self.root,source['relative_path'])
            if key not in self.pdfs:
                require(sha_file(path)==source['source_checksum'],'PDF_CHECKSUM:'+key)
                self.pdfs[key]=PdfReader(path)
                require(len(self.pdfs[key].pages)==source['page_count'],'PDF_PAGE_COUNT')
            page=ctx['page_number'];require(type(page) is int and 1<=page<=source['page_count'],'PDF_PAGE_NUMBER')
            if (key,page) not in self.cache:self.cache[key,page]=self.pdfs[key].pages[page-1].extract_text() or ''
            compact=lambda text:''.join(unicodedata.normalize('NFC',text).split())
            require(compact(ctx['text']) and compact(ctx['text']) in compact(self.cache[key,page]),'SOURCE_EXCERPT_MISMATCH')
            self.checked.add((key,page))


def assert_source_snapshot(contract):
    for name,expected in contract['source_code_sha256'].items():
        data=within(ROOT,name).read_bytes().replace(b'\r\n',b'\n')
        require(sha_bytes(data)==expected,'CODE_SNAPSHOT_MISMATCH:'+name)
