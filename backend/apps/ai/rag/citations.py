"""Normalize labels already present in text; never invent a missing citation."""

import re
import unicodedata

from ..providers.base import GenerationError
from .base import Reference


INSUFFICIENT_MESSAGE = "Tài liệu được cung cấp chưa đủ căn cứ để hỗ trợ yêu cầu này."
_LABEL = re.compile(r"\[([0-9]+)\]")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
VALIDATION_REASONS = frozenset({"EMPTY_OUTPUT", "MIXED_OUTPUT_FORMAT", "UNEXPECTED_CJK",
                                "MISSING_CITATION", "UNKNOWN_CITATION", "CHOICE_FORMAT",
                                "CHOICE_LABEL_TEXT_MISMATCH", "CHOICE_TEXT_NOT_VERBATIM"})


def _invalid(reason, message):
    error = GenerationError("INVALID_GENERATION", message)
    error.validation_reason = reason
    raise error


def choice_options(question):
    """Recognize only explicit ordered A)/B)/... options, never infer correct answers."""
    markers = list(re.finditer(r"\b([A-D])\)\s*", question))
    if not 2 <= len(markers) <= 4 or [m[1] for m in markers] != list("ABCD"[:len(markers)]):
        return {}
    options = {marker[1]: question[marker.end():markers[index + 1].start() if index + 1 < len(markers) else len(question)].strip()
               for index, marker in enumerate(markers)}
    return options if all(options.values()) else {}


def _choice_tokens(text):
    return re.findall(r"\w+|[^\w\s]", unicodedata.normalize("NFC", text).casefold().rstrip(" .;"))


def validate_choice_answer(question, text):
    options = choice_options(question)
    if not options or text.strip() == "INSUFFICIENT_EVIDENCE":
        return
    match = re.match(r"^([A-D])\)\s*(.+)", text.strip(), flags=re.DOTALL)
    if not match or match[1] not in options:
        _invalid("CHOICE_FORMAT", "A multiple-choice answer must select one explicit option.")
    rest = _LABEL.sub("", match[2])
    if re.search(r"\b[A-D]\)", rest):
        _invalid("CHOICE_FORMAT", "A multiple-choice answer lists additional options.")
    tokens = _choice_tokens(rest)
    candidates = [(len(_choice_tokens(option)), label) for label, option in options.items()
                  if tokens[:len(_choice_tokens(option))] == _choice_tokens(option)]
    if not candidates:
        _invalid("CHOICE_TEXT_NOT_VERBATIM", "Selected option wording does not match the question.")
    longest = max(length for length, _ in candidates)
    labels = {label for length, label in candidates if length == longest}
    if match[1] not in labels:
        _invalid("CHOICE_LABEL_TEXT_MISMATCH", "Selected option label and wording disagree.")


def parse_answer(text, contexts, *, reject_cjk_output=True):
    if not isinstance(text, str) or not text.strip():
        _invalid("EMPTY_OUTPUT", "The model returned empty text.")
    text = text.strip()
    if text == "INSUFFICIENT_EVIDENCE":
        return "INSUFFICIENT_EVIDENCE", INSUFFICIENT_MESSAGE, (), ()
    if ("INSUFFICIENT_EVIDENCE" in text or text.startswith(("{", "```"))
            or re.search(r"\[S[0-9]+\]", text)):
        _invalid("MIXED_OUTPUT_FORMAT", "Output mixes incompatible formats or statuses.")
    if reject_cjk_output and _CJK.search(text):
        _invalid("UNEXPECTED_CJK", "Output contains unexpected CJK text for this Vietnamese baseline.")
    labels = list(dict.fromkeys(match.group(1) for match in _LABEL.finditer(text)))
    visible = {index: context.source_id for index, context in enumerate(contexts, 1)}
    if not labels:
        _invalid("MISSING_CITATION", "Citation labels are missing.")
    if any(len(label) > 6 or str(int(label)) != label or int(label) not in visible for label in labels):
        _invalid("UNKNOWN_CITATION", "Citation labels are outside the actual prompt.")
    # Render labels consecutively in first-use order while preserving their source identity.
    mapping = {int(label): index for index, label in enumerate(labels, 1)}
    answer = _LABEL.sub(lambda match: f"[{mapping[int(match.group(1))]}]", text)
    references = tuple(Reference(index, visible[int(label)]) for index, label in enumerate(labels, 1))
    return "ANSWERED", answer, references, tuple(mapping.items())
