from collections import Counter
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree.ElementTree import Element, SubElement, tostring
from django.utils import timezone
from .assessment_services import attempt_output, expire
from .assessment_questions import is_correct, selected_ids


def dashboard(assessment, params):
    attempts = list(assessment.attempts.select_related('student').prefetch_related('events', 'grade_history').all())
    for attempt in attempts:
        expire(attempt)
    room = assessment.session.classroom
    enrollments = room.enrollments.filter(status__in=['ACTIVE', 'COMPLETED'], student__user__is_active=True,
        student__user__course_memberships__course=room.course, student__user__course_memberships__status='ACTIVE').select_related('student__user')
    users = {str(e.student.user_id): e.student.user for e in enrollments}
    active_ids = set(users)
    users.update({str(a.student_id): a.student for a in attempts})
    search = str(params.get('q', '')).strip().casefold()[:255]
    status_filter = str(params.get('status', ''))
    rows = []
    for sid, user in users.items():
        own = [a for a in attempts if str(a.student_id) == sid]
        submitted = [a for a in own if a.status == 'SUBMITTED']
        latest = submitted[0] if submitted else None
        status = 'NOT_SUBMITTED' if not latest else 'PENDING' if latest.score is None else 'GRADED'
        name = user.full_name or user.username
        if search and search not in f'{name} {user.username}'.casefold():
            continue
        if status_filter and status_filter != status:
            continue
        rows.append({'student_id': sid, 'name': name, 'username': user.username, 'active': sid in active_ids, 'status': status,
            'attempt_count': len(own), 'latest': attempt_output(latest, True) if latest else None,
            'violation_count': sum(a.events.count() for a in own)})
    rows.sort(key=lambda row: (row['name'].casefold(), row['student_id']))
    included = {r['student_id'] for r in rows}
    history = [attempt_output(a, True) for a in attempts if str(a.student_id) in included]
    latest_attempts = [next(a for a in attempts if str(a.pk) == r['latest']['id']) for r in rows if r['latest']]
    scores = [float(a.score) for a in latest_attempts if a.score is not None]
    bins = [{'label': label, 'count': sum(lo <= score < hi for score in scores)} for label, lo, hi in [('0–<2', 0, 2), ('2–<4', 2, 4), ('4–<6', 4, 6), ('6–<8', 6, 8), ('8–10', 8, 11)]]
    questions = [{'id': q['id'], 'prompt': q['prompt'], 'answered': sum(q['id'] in a.answers for a in latest_attempts),
        'correct': sum(is_correct(q, a.answers.get(q['id'])) for a in latest_attempts), 'total': len(latest_attempts)} for q in assessment.questions]
    daily = Counter(timezone.localtime(a.submitted_at).strftime('%d/%m/%Y') for a in latest_attempts)
    return {'summary': {'total': len(rows), 'submitted': len(latest_attempts), 'not_submitted': len(rows)-len(latest_attempts),
        'pending': sum(a.score is None for a in latest_attempts), 'average': round(sum(scores)/len(scores), 2) if scores else None,
        'violations': sum(r['violation_count'] for r in rows)}, 'students': rows, 'attempts': history, 'score_distribution': bins,
        'question_stats': questions, 'submissions_by_day': [{'date': d, 'count': n} for d, n in sorted(daily.items(), key=lambda p: p[0][6:]+p[0][3:5]+p[0][:2])],
        'filters': {'q': params.get('q', ''), 'status': status_filter}}


def local_date(value):
    return timezone.localtime(value).strftime('%d/%m/%Y %H:%M:%S') if value else ''


def export_workbook(assessment, report):
    mode = 'Ôn tập' if assessment.mode == 'PRACTICE' else 'Kiểm tra'
    meta = [[assessment.title, mode], ['Xuất lúc', local_date(timezone.now())], ['Bộ lọc', str(report['filters'])]]
    status_names = {'NOT_SUBMITTED': 'Chưa nộp', 'PENDING': 'Chờ chấm', 'GRADED': 'Đã chấm'}
    sheets = [('Tổng hợp', meta + [['Học viên', 'Tài khoản', 'Trạng thái', 'Số lượt', 'Điểm mới nhất', 'Thời điểm nộp', 'Vi phạm']]
        + [[r['name'], r['username'], status_names[r['status']], r['attempt_count'], r['latest']['score'] if r['latest'] else None,
            local_date(r['latest']['submitted_at']) if r['latest'] else '', r['violation_count']] for r in report['students']])]
    details = meta + [['Học viên', 'Lượt', 'Trạng thái', 'Nộp lúc', 'Điểm', 'Nhận xét', 'Câu hỏi/Bài làm', 'Câu trả lời', 'Điểm câu (thang 10)', 'Tệp', 'Xử lý vi phạm']]
    violations = meta + [['Học viên', 'Lượt', 'Loại vi phạm', 'Thời điểm server', 'Xử lý của giáo viên']]
    for a in report['attempts']:
        base = [a['student_name'], a['number'], 'Đã nộp' if a['status'] == 'SUBMITTED' else 'Đang làm', local_date(a['submitted_at']), a['score'], a['feedback']]
        if assessment.kind == 'QUIZ':
            for q in assessment.questions:
                selected = selected_ids(a['answers'].get(q['id']))
                answer = '; '.join(c['text'] for c in q['choices'] if c['id'] in selected)
                details.append(base + [q['prompt'], answer, round(10/len(assessment.questions), 4) if is_correct(q, a['answers'].get(q['id'])) else 0, '', a['moderation_note']])
        else:
            details.append(base + [assessment.description, a['text'], '', a['file_name'], a['moderation_note']])
        for e in a['events']:
            violations.append([a['student_name'], a['number'], 'Chuyển tab/ẩn trang' if e['kind'] == 'TAB_HIDDEN' else 'Thoát toàn màn hình', local_date(e['created_at']), a['moderation_note']])
    sheets.append(('Chi tiết lượt làm', details))
    stats = meta + [['Chỉ số', 'Giá trị']] + [[k, v] for k, v in report['summary'].items()]
    stats += [['Phân bố điểm', 'Số học viên']] + [[b['label'], b['count']] for b in report['score_distribution']]
    stats += [['Ngày nộp', 'Số học viên']] + [[b['date'], b['count']] for b in report['submissions_by_day']]
    stats += [['Câu hỏi', 'Trả lời đúng', 'Đã trả lời', 'Tổng lượt mới nhất']] + [[q['prompt'], q['correct'], q['answered'], q['total']] for q in report['question_stats']]
    sheets.append(('Thống kê', stats))
    if assessment.mode == 'TEST':
        sheets.append(('Vi phạm', violations))
    return make_xlsx(sheets)


def make_xlsx(sheets):
    """Small OOXML writer: user content is always inlineStr, never a formula."""
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        workbook = Element('workbook', xmlns=ns, attrib={'xmlns:r': rel})
        sheet_list = SubElement(workbook, 'sheets')
        relationships = Element('Relationships', xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        types = Element('Types', xmlns='http://schemas.openxmlformats.org/package/2006/content-types')
        SubElement(types, 'Default', Extension='rels', ContentType='application/vnd.openxmlformats-package.relationships+xml')
        SubElement(types, 'Default', Extension='xml', ContentType='application/xml')
        SubElement(types, 'Override', PartName='/xl/workbook.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
        for i, (name, rows) in enumerate(sheets, 1):
            SubElement(sheet_list, 'sheet', name=name, sheetId=str(i), attrib={'r:id': f'rId{i}'})
            SubElement(relationships, 'Relationship', Id=f'rId{i}', Type=rel+'/worksheet', Target=f'worksheets/sheet{i}.xml')
            SubElement(types, 'Override', PartName=f'/xl/worksheets/sheet{i}.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
            sheet = Element('worksheet', xmlns=ns)
            columns = SubElement(sheet, 'cols')
            SubElement(columns, 'col', min='1', max='20', width='25', customWidth='1')
            data = SubElement(sheet, 'sheetData')
            for row in rows:
                element = SubElement(data, 'row')
                for value in row:
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        cell = SubElement(element, 'c', t='n')
                        SubElement(cell, 'v').text = str(value)
                        continue
                    cell = SubElement(element, 'c', t='inlineStr')
                    text = SubElement(SubElement(cell, 'is'), 't', attrib={'xml:space': 'preserve'})
                    # XML 1.0 excludes control characters; Excel limits cell text to 32767.
                    text.text = ''.join(c for c in str(value if value is not None else '')[:32767] if c in '\t\n\r' or (ord(c) >= 32 and ord(c) not in [0xfffe, 0xffff]))
            archive.writestr(f'xl/worksheets/sheet{i}.xml', tostring(sheet, encoding='utf-8', xml_declaration=True))
        root_rels = Element('Relationships', xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        SubElement(root_rels, 'Relationship', Id='rId1', Type=rel+'/officeDocument', Target='xl/workbook.xml')
        for path, element in [('[Content_Types].xml', types), ('_rels/.rels', root_rels), ('xl/workbook.xml', workbook), ('xl/_rels/workbook.xml.rels', relationships)]:
            archive.writestr(path, tostring(element, encoding='utf-8', xml_declaration=True))
    return output.getvalue()
