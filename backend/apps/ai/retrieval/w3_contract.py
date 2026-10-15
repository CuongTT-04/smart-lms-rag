"""Compatibility check: chunk budget excludes special tokens, encoder includes them."""


def validate_token_budget(chunking, embedding, *, special_tokens):
    if (type(special_tokens) is not int or special_tokens < 0
            or chunking.tokenizer_model != embedding.model_id
            or chunking.tokenizer_revision != embedding.revision
            or chunking.max_tokens + special_tokens != embedding.max_tokens):
        raise ValueError('Chunk tokenizer/revision/budget must match encoder including special tokens.')
