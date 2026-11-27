"""Conservative request checks and bounded reading guidance, not a semantic firewall."""

import re
import unicodedata

from ..providers.base import GenerationError
from .citations import parse_answer


def normalized_text(text):
    normalized = unicodedata.normalize("NFKD", text.casefold()).replace("đ", "d")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(normalized.split())


def instruction_override(text):
    normalized = normalized_text(text)
    override = r'\b(?:bo qua|phot lo|vo hieu hoa|ignore|disregard|override|bypass)\b'
    policy = r'\b(?:quy tac|chinh sach|system|instructions|policies|policy)\b'
    disclose = r'\b(?:tiet lo|bi mat|dap an rieng|reveal|secret|hidden)\b'
    return bool(re.search(override+r'.{0,100}'+policy+r'.{0,150}'+disclose, normalized))


def check_request_policy(question):
    normalized = normalized_text(question)
    # Refuse explicit policy-override requests; do not strip them and answer a rewritten query.
    patterns = (
        r"\b(?:bo qua|phot lo|vo hieu hoa)\b.{0,100}\b(?:chinh sach|chi dan he thong|quy tac he thong)\b",
        r"\b(?:ignore|disregard|override|bypass)\b.{0,100}\b(?:instructions|policy|policies|system rules)\b",
        r"\b(?:tiet lo|in ra|hien thi)\b.{0,50}\b(?:system prompt|prompt he thong)\b",
        r"\b(?:reveal|print|show)\b.{0,50}\b(?:system prompt|hidden instructions)\b",
    )
    if instruction_override(question) or any(re.search(pattern, normalized) for pattern in patterns):
        raise GenerationError("INVALID_REQUEST", "Requests to override generation policy are not supported.")


def check_output_policy(answer, source_texts):
    """Reject explicit override text and identifier echoes from injected source lines.

    This narrow fail-closed check is not an exfiltration detector or a semantic firewall.
    Ordinary technical identifiers outside malicious instruction lines remain allowed.
    """
    if instruction_override(answer):
        raise GenerationError('INVALID_GENERATION', 'Unsafe instruction content in output.')
    identifiers = set()
    for source in source_texts:
        for line in source.splitlines():
            if instruction_override(line):
                identifiers.update(re.findall(r'\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){2,}\b', line))
    normalized = normalized_text(answer)
    if any(normalized_text(identifier) in normalized for identifier in identifiers):
        raise GenerationError('INVALID_GENERATION', 'Injected source identifiers repeated in output.')


def parse_reading_hint(text, contexts):
    """Only an allowlisted action and actual source labels may influence public wording."""
    if text == "INSUFFICIENT_EVIDENCE":
        return parse_answer(text, contexts)
    if not isinstance(text, str):
        raise GenerationError("INVALID_GENERATION", "Hint must select a supported reading action.")
    match = re.fullmatch(r"(READ|COMPARE|OUTLINE) (\[[1-9][0-9]{0,5}\])(?: (\[[1-9][0-9]{0,5}\]))?", text.strip())
    if not match:
        raise GenerationError("INVALID_GENERATION", "Hint action contains unsupported text or format.")
    action, first, second = match.groups()
    if (action == "COMPARE") != (second is not None) or first == second:
        raise GenerationError("INVALID_GENERATION", "Hint source selection does not match its action.")
    if action == "READ":
        answer = f"Hãy đọc đoạn được dẫn và tự xác định câu liên quan trực tiếp đến yêu cầu của đề {first}. " \
                 "Sau đó thử diễn đạt ý đó bằng lời của bạn."
    elif action == "COMPARE":
        answer = f"Hãy đối chiếu hai đoạn được dẫn, ghi lại điểm giống và khác nhau {first} {second}. " \
                 "Dùng kết quả đối chiếu để tự xây dựng câu trả lời."
    else:
        answer = f"Hãy chia yêu cầu của đề thành từng ý nhỏ rồi tìm câu hỗ trợ cho mỗi ý trong đoạn được dẫn {first}. " \
                 "Tự lập dàn ý trước khi viết câu trả lời."
    return parse_answer(answer, contexts)
