"""Complete literal quote context without rewriting a model's generated claims."""
import re

from .rag.base import EvidenceContext
from .rag.conversation import build_evidence_units


def complete_quote_context(answer, citations):
    prefix = 'Trích học liệu:\n\n'
    if not answer.startswith(prefix):
        return answer
    sources = {item['label']: item for item in citations}
    rows = []
    normalize = lambda text: ' '.join(text.split())
    for number, line in enumerate(answer[len(prefix):].splitlines(), 1):
        match = re.fullmatch(r'\s*' + str(number) + r'\. (.+)', line)
        if not match:
            return answer
        parts = []
        offset = 0
        for piece in re.finditer(r'(.*?)\s+\[(\d+)\]', match[1]):
            text, label = piece[1].strip(), int(piece[2])
            if (label not in sources or not text
                    or normalize(text) not in normalize(sources[label]['excerpt'])):
                return answer
            parts.append((text, label))
            offset = piece.end()
        if not parts or match[1][offset:].strip():
            return answer
        rows.append(parts)
    completed = []
    changed = False
    index = 0
    existing = {normalize(text) for row in rows for text, _ in row}
    while index < len(rows):
        row = rows[index]
        if len(row) == 1 and index + 1 < len(rows):
            text, label = row[0]
            next_text, next_label = rows[index + 1][0]
            source, following = sources[label], sources[next_label]
            transition = bool(re.match(r'^(?:Cùng với|Bên cạnh|Ngoài ra|Đồng thời)\b', text, re.I))
            adjacent = ((source['document_id'], source['version_id']) ==
                        (following['document_id'], following['version_id'])
                        and following['page_number'] == source['page_number'] + 1)
            if transition and not re.search(r'[.!?]$', text) and next_text[:1].islower() and adjacent:
                context = EvidenceContext(source_id='S1', chunk_id=source['chunk_id'],
                    text=source['excerpt'], document_id=source['document_id'], version_id=source['version_id'],
                    document_title=source['document_title'], page_number=source['page_number'])
                units = build_evidence_units([context])
                positions = [i for i, unit in enumerate(units) if normalize(unit['text']) == normalize(text)]
                if len(positions) == 1 and positions[0] > 0:
                    previous = units[positions[0] - 1]['text']
                    if (len(previous) >= 20 and re.search(r'[.!?]$', previous)
                            and not re.match(r'^[-+#]', previous)):
                        if normalize(previous) not in existing:
                            completed.append([(previous, label)])
                            existing.add(normalize(previous))
                        completed.append([*row, *rows[index + 1]])
                        changed = True
                        index += 2
                        continue
        completed.append(row)
        index += 1
    if not changed:
        return answer
    result = prefix + '\n'.join(f'{i}. ' + ' '.join(f'{text} [{label}]' for text, label in row)
                               for i, row in enumerate(completed, 1))
    return result if len(result) <= 12000 else answer
