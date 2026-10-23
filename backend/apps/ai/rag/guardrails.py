"""Conservative request checks and bounded reading guidance, not a semantic firewall."""

import re
import unicodedata

from ..providers.base import GenerationError
from .citations import parse_answer


def check_request_policy(question):
    normalized = unicodedata.normalize("NFKD", question.casefold()).replace("đ", "d")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = " ".join(normalized.split())
    # Refuse explicit policy-override requests; do not strip them and answer a rewritten query.
    patterns = (
        r"\b(?:bo qua|phot lo|vo hieu hoa)\b.{0,100}\b(?:chinh sach|chi dan he thong|quy tac he thong)\b",
        r"\b(?:ignore|disregard|override|bypass)\b.{0,100}\b(?:instructions|policy|policies|system rules)\b",
        r"\b(?:tiet lo|in ra|hien thi)\b.{0,50}\b(?:system prompt|prompt he thong)\b",
        r"\b(?:reveal|print|show)\b.{0,50}\b(?:system prompt|hidden instructions)\b",
    )
    if any(re.search(pattern, normalized) for pattern in patterns):
        raise GenerationError("INVALID_REQUEST", "Requests to override generation policy are not supported.")


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
