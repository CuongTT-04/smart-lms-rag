"""Load only pinned tokenizer assets, never model weights or network fallbacks."""
from importlib.metadata import version
from pathlib import Path
from .contracts import require,sha_file,sha_bytes


def load_tokenizer(folder,contract,tokenizer_spec):
    from transformers import AutoTokenizer
    require(version('transformers')==contract['model']['transformers_version'],'TRANSFORMERS_VERSION')
    folder=Path(folder).resolve()
    for name,info in tokenizer_spec['files'].items():
        path=(folder/name).resolve()
        require(path.is_relative_to(folder) and path.is_file() and sha_file(path)==info['sha256'],'TOKENIZER_ASSET:'+name)
    tok=AutoTokenizer.from_pretrained(folder,local_files_only=True,trust_remote_code=False)
    require(tok.eos_token_id==contract['model']['eos_token_id'] and tok.pad_token_id==contract['model']['pad_token_id'],'TOKENIZER_SPECIAL_IDS')
    require(sha_bytes(tok.chat_template.encode())==contract['model']['chat_template_sha256'],'CHAT_TEMPLATE_HASH')
    return tok
