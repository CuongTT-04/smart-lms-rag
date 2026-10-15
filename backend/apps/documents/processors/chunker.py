"""Deterministic, page-local token chunks with exact normalized-text offsets."""
import re
import unicodedata
from uuid import UUID, NAMESPACE_URL, uuid5
from apps.documents.retrieval_contracts import Chunk, ChunkingConfig


def normalize_page(text):
    if not isinstance(text, str):
        raise ValueError('Page text must be a string.')
    return unicodedata.normalize('NFC', text.replace('\r\n', '\n').replace('\r', '\n'))


def validate_envelope(envelope):
    if envelope.get('schema_version') != '1.0':
        raise ValueError('Unsupported extraction schema.')
    for key in ('course_id', 'document_id', 'version_id'):
        UUID(envelope[key])
    if not re.fullmatch(r'[0-9a-f]{64}', envelope.get('checksum_sha256', '')):
        raise ValueError('Invalid source checksum.')
    pages = envelope.get('pages')
    count = envelope.get('page_count')
    if type(count) is not int or count < 1 or not isinstance(pages, list) or len(pages) != count:
        raise ValueError('Extraction must contain all physical pages.')
    if any(type(p.get('page_number')) is not int or p['page_number'] != i+1 for i,p in enumerate(pages)):
        raise ValueError('Invalid physical page sequence.')


def chunk_extraction(envelope, document_title, config: ChunkingConfig, tokenizer):
    validate_envelope(envelope)
    chunks = []
    for page in envelope['pages']:
        text = normalize_page(page['text'])
        if not text.strip():
            continue
        start = 0
        while start < len(text):
            remaining = text[start:]
            offsets = tokenizer(remaining, add_special_tokens=False, return_offsets_mapping=True,
                                truncation=False)['offset_mapping']
            offsets = [(int(a), int(b)) for a,b in offsets if b > a]
            if not offsets:
                if remaining.strip():
                    raise ValueError('Tokenizer produced no offsets for nonempty text.')
                break
            end = len(text) if len(offsets) <= config.max_tokens else start + offsets[config.max_tokens-1][1]
            if end < len(text):
                # Prefer an existing sentence/paragraph boundary in the latter half.
                minimum = start + (end-start)//2
                boundaries = [start+m.end() for m in re.finditer(r'\n\n|[.!?]\s+', text[start:end])]
                eligible = [b for b in boundaries if b >= minimum]
                if eligible:
                    end = eligible[-1]
            # BPE boundary changes can increase the count when a substring is re-encoded.
            tokens = tokenizer.encode(text[start:end], add_special_tokens=False)
            while len(tokens) > config.max_tokens and end > start:
                end -= 1
                tokens = tokenizer.encode(text[start:end], add_special_tokens=False)
            if end <= start or not tokens:
                raise ValueError('Tokenizer cannot produce a progressing chunk within budget.')
            value = text[start:end]
            if value.strip():
                key = f"{envelope['version_id']}:{page['page_number']}:{start}:{end}:{config.digest}"
                chunks.append(Chunk('1.0', str(uuid5(NAMESPACE_URL,key)), envelope['course_id'],
                                    envelope['document_id'], envelope['version_id'], document_title,
                                    page['page_number'], None, len(chunks), value, len(tokens), start,
                                    end, envelope['checksum_sha256'], config.digest))
            if end == len(text):
                break
            chunk_offsets = tokenizer(value, add_special_tokens=False, return_offsets_mapping=True,
                                      truncation=False)['offset_mapping']
            positive = [(int(a),int(b)) for a,b in chunk_offsets if b > a]
            next_start = end
            if config.overlap_tokens and len(positive) > config.overlap_tokens:
                next_start = start + positive[-config.overlap_tokens][0]
            start = next_start if next_start > start else end
    return chunks
