"""W3 contracts shared by chunking and the separately supplied retriever."""
from dataclasses import asdict, dataclass
import hashlib
import json


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ChunkingConfig:
    tokenizer_revision: str
    tokenizer_model: str = 'BAAI/bge-m3'
    max_tokens: int = 512
    overlap_tokens: int = 64
    normalization: str = 'NFC-LF-v1'
    schema_version: str = '1.0'

    def __post_init__(self):
        if not self.tokenizer_revision or not self.tokenizer_model:
            raise ValueError('Tokenizer model and revision are required.')
        if (type(self.max_tokens) is not int or type(self.overlap_tokens) is not int
                or self.max_tokens < 1 or not 0 <= self.overlap_tokens < self.max_tokens):
            raise ValueError('Require 0 <= overlap_tokens < max_tokens.')
        if self.normalization != 'NFC-LF-v1' or self.schema_version != '1.0':
            raise ValueError('Unsupported normalization/schema.')

    @property
    def digest(self):
        return canonical_hash(asdict(self))


@dataclass(frozen=True)
class Chunk:
    schema_version: str
    chunk_id: str
    course_id: str
    document_id: str
    version_id: str
    document_title: str
    page_number: int
    section_title: str | None
    chunk_order: int
    text: str
    token_count: int
    char_start: int
    char_end: int
    source_checksum: str
    chunking_config_hash: str


@dataclass(frozen=True)
class RetrievalScope:
    user_id: str
    course_id: str
    classroom_id: str | None
    session_id: str | None
    document_ids: tuple[str, ...] | None
    allowed_version_ids: tuple[str, ...]
    mode: str = 'qa'
    preview: bool = False
