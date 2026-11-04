"""Authenticate the locked pilot and recompute its tokenizer boundaries on CPU."""
import hashlib
import json
from pathlib import Path
import unicodedata


def require(condition, code):
    if not condition:
        raise ValueError(code)


def read_json(path):
    return loads(Path(path).read_text(encoding='utf-8'))


def loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('NONFINITE_JSON')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def canonical(value):
    def normalize(item):
        if isinstance(item, str):
            return unicodedata.normalize('NFC', item)
        if isinstance(item, list):
            return [normalize(v) for v in item]
        if isinstance(item, dict):
            return {k: normalize(v) for k, v in item.items()}
        return item
    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha_file(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def within(root, name):
    root = Path(root).resolve()
    require(isinstance(name, str) and '\\' not in name and ':' not in name,
            'UNSAFE_MEMBER_PATH')
    path = (root / name).resolve()
    require(path.is_relative_to(root) and path != root, 'MEMBER_OUTSIDE_ROOT')
    return path


def read_rows(path):
    rows = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        require(bool(line.strip()), 'EMPTY_JSONL_ROW')
        row = loads(line)
        require(isinstance(row, dict), 'INVALID_JSONL_ROW')
        rows.append(row)
    return rows


def tokenize_payload(payload, tokenizer, limits):
    prompt = tokenizer.apply_chat_template(payload['prompt'], tokenize=True,
                                            add_generation_prompt=True)
    full = tokenizer.apply_chat_template(payload['prompt'] + payload['completion'],
                                          tokenize=True, add_generation_prompt=False)
    require(isinstance(full, list) and isinstance(prompt, list)
            and all(type(n) is int for n in full + prompt), 'TOKENIZER_IDS')
    require(full[:len(prompt)] == prompt, 'CHAT_TEMPLATE_PREFIX')
    completion = full[len(prompt):]
    require(completion.count(tokenizer.eos_token_id) == 1, 'COMPLETION_EOS')
    eos = len(prompt) + completion.index(tokenizer.eos_token_id)
    tail = full[eos + 1:]
    require(eos > len(prompt), 'EMPTY_COMPLETION')
    require(not tail or tail == tokenizer.encode('\n', add_special_tokens=False), 'POST_EOS_TEXT')
    require(len(prompt) <= limits['max_prompt_tokens']
            and len(completion) <= limits['max_completion_tokens']
            and len(full) <= limits['max_sequence_tokens'], 'TOKEN_BUDGET')
    return dict(input_ids=full, attention_mask=[1] * len(full),
                labels=[-100] * len(prompt) + full[len(prompt):eos + 1] + [-100] * len(tail),
                prompt_tokens=len(prompt), completion_tokens=len(completion),
                sequence_tokens=len(full), eos_position=eos,
                supervised_tokens=eos + 1 - len(prompt))


def authenticate(folder, config):
    folder = Path(folder).resolve()
    manifest_path = folder / 'manifest.json'
    require(sha_file(manifest_path) == config['data_manifest_sha256'], 'MANIFEST_HASH')
    manifest = read_json(manifest_path)
    for name, info in manifest['files'].items():
        path = within(folder, name)
        require(path.is_file() and path.stat().st_size == info['size_bytes']
                and sha_file(path) == info['sha256'], 'DATA_INTEGRITY:' + name)
    contract = read_json(folder / 'training-contract.json')
    require(digest(contract) == config['contract_sha256'] == manifest['contract_sha256'],
            'CONTRACT_HASH')
    require(config['model_id'] == contract['model']['model_id']
            and config['revision'] == contract['model']['revision']
            == contract['model']['tokenizer_revision'], 'MODEL_IDENTITY')
    selection = read_json(folder / 'selection.json')
    require(set(selection['splits']) == {'train', 'validation'}, 'PILOT_SPLITS')
    ids = selection['splits']['train'] + selection['splits']['validation']
    require(len(ids) == len(set(ids)) and not set(ids) & set(selection['excluded_holdout_ids']),
            'DUPLICATE_OR_HOLDOUT_ID')
    require(manifest['counts'] == {'train': 128, 'validation': 32}
            and manifest['holdout_payload_included'] is False, 'PILOT_COUNTS')
    return contract, manifest, selection


def load_pilot(folder, tokenizer_folder, config):
    from importlib.metadata import version
    from transformers import AutoTokenizer
    folder = Path(folder).resolve()
    contract, manifest, selection = authenticate(folder, config)
    reference = read_json(folder / 'tokenizer-reference.json')
    for name, expected in reference['packages'].items():
        require(version(name) == expected, 'TOKENIZER_LIBRARY_VERSION:' + name)
    for name, info in reference['files'].items():
        path = within(tokenizer_folder, name)
        require(path.is_file() and path.stat().st_size == info['size_bytes']
                and sha_file(path) == info['sha256'], 'TOKENIZER_ASSET:' + name)
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_folder, local_files_only=True,
                                               trust_remote_code=False)
    require(tokenizer.eos_token_id == contract['model']['eos_token_id']
            and tokenizer.pad_token_id == contract['model']['pad_token_id']
            and hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()
            == contract['model']['chat_template_sha256'], 'TOKENIZER_IDENTITY')
    result = {}
    for split in ('train', 'validation'):
        tokens = read_rows(folder / ('tokenized-' + split + '.jsonl'))
        payloads = read_rows(folder / (split + '.jsonl'))
        metadata = read_rows(folder / (split + '.metadata.jsonl'))
        require(len(tokens) == len(payloads) == len(metadata) == manifest['counts'][split],
                'SPLIT_COUNT')
        result[split] = []
        for index, (row, payload, meta) in enumerate(zip(tokens, payloads, metadata)):
            rid = selection['splits'][split][index]
            require(row['record_id'] == meta['source_record_id'] == rid
                    and meta['split'] == split and meta['row_index'] == index, 'ROW_BINDING')
            require(digest(payload) == meta['training_payload_sha256'], 'PAYLOAD_HASH')
            require(row == dict(record_id=rid, **tokenize_payload(payload, tokenizer,
                                                                contract['token_limits'])),
                    'TOKEN_LABEL_RECOMPUTATION')
            # Do not allow IDs or provenance to reach model.forward().
            result[split].append({k: row[k] for k in ('input_ids', 'attention_mask', 'labels')})
    return result, tokenizer, contract
