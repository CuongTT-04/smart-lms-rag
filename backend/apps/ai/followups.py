"""Optional, deterministic follow-ups from current authorized citations; no extra inference."""
import logging
import re
import unicodedata


logger = logging.getLogger(__name__)
CLARIFY = 'Giải thích rõ hơn nội dung vừa nêu trong học liệu.'
CONDENSE = 'Tóm lược các ý chính vừa nêu trong học liệu.'


def normalized(text):
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFC', text).casefold()))


def build_questions(question, citations, history=()):
    asked = {normalized(question), *(normalized(turn['question']) for turn in history or ())}
    candidates, seen = [], set()
    for citation in citations:
        excerpt = citation['excerpt']
        headings = []
        section = citation.get('section_title')
        if section and normalized(section) in normalized(excerpt):
            headings.append(section)
        for line in excerpt.splitlines():
            match = re.fullmatch(r'\s*(?:#{1,6}\s+|(?:[IVX]+|\d+|[a-z])[.)-]\s*)(.+?)\s*', line)
            if match:
                headings.append(match[1])
        for heading in headings:
            heading = heading.strip()
            key = normalized(heading)
            if (not 6 <= len(heading) <= 90 or not 2 <= len(key.split()) <= 16
                    or re.search(r'[\r\n.!?;\[\]{}<>@/\\]|https?:|bỏ qua|ignore|system prompt|mật khẩu|rubric|correct_ids', heading, re.I)
                    or key in seen):
                continue
            seen.add(key)
            candidate = f'Học liệu trình bày những gì về “{heading}”?'
            if normalized(candidate) not in asked:
                candidates.append(candidate)
    questions = candidates[:2]
    for fallback in (CLARIFY, CONDENSE):
        if len(questions) == 3:
            break
        if normalized(fallback) not in asked:
            questions.append(fallback)
    return questions[:3]


def suggested_questions(question, citations, *, mode, status, history=None):
    if mode != 'qa' or status != 'ANSWERED' or not citations:
        return []
    try:
        return build_questions(question, citations, history)
    except Exception:
        # Suggestions are optional: never drop a valid answer or log private source text.
        logger.warning('Optional study follow-ups unavailable.')
        return []
