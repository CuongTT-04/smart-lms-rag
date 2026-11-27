from datetime import timedelta
import hashlib
import io
import os
from pathlib import Path
import tempfile
import uuid

import cv2
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import numpy as np
from reportlab.pdfgen.canvas import Canvas

from apps.courses.assessment_models import Assessment, AssessmentAttempt
from apps.courses.enrollment_services import join_by_code, withdraw_classroom_enrollment
from apps.courses.models import AccessPolicy, Classroom, ClassroomSession, Course, CourseMember, Enrollment
from apps.courses.progress_models import DocumentCompletion
from apps.courses.progress_services import refresh_classroom_progress
from apps.courses.services import update_course
from apps.courses.video_models import SessionVideo, VideoProgress, VideoQuestion
from apps.documents.models import DocumentVersion, KnowledgeDocument
from apps.documents.processors.watermark import watermarked_pdf_bytes
from apps.documents.storage import private_path
from apps.users.models import TeacherApproval, User

DEMO_NAMESPACE = uuid.UUID('8f7c4f31-6e2b-4c60-9d8a-3b19c5a90901')
DEMO_VIDEO_DURATION = 12.0
DEMO_VIDEO_CHECKPOINT = 5.0


def demo_uuid(key):
    return uuid.uuid5(DEMO_NAMESPACE, key)


def build_demo_pdf_bytes(title):
    stream = io.BytesIO()
    canvas = Canvas(stream)
    canvas.setFont('Helvetica-Bold', 14)
    canvas.drawString(50, 760, f'OHAYO LMS - {title}')
    canvas.setFont('Helvetica', 11)
    canvas.drawString(50, 730, 'Trang 1: Tai lieu minh hoa quy trinh hoc tap va danh dau da hoc W9-01.')
    canvas.showPage()
    canvas.setFont('Helvetica-Bold', 14)
    canvas.drawString(50, 760, f'{title} (Trang 2)')
    canvas.setFont('Helvetica', 11)
    canvas.drawString(50, 730, 'Trang 2: Noi dung phuc vu kiem thu doc va tai hoc lieu PDF nhieu trang.')
    canvas.showPage()
    canvas.save()
    return stream.getvalue()


def build_demo_webm_bytes(duration_seconds=12, fps=1):
    frame_count = max(1, int(duration_seconds * fps))
    fd, temp_path = tempfile.mkstemp(suffix='.webm')
    os.close(fd)
    try:
        writer = cv2.VideoWriter(temp_path, cv2.VideoWriter_fourcc(*'VP80'), float(fps), (160, 90))
        if not writer.isOpened():
            raise CommandError('Không thể khởi tạo bộ mã hóa WebM (VP80) để tạo video demo.')
        try:
            for index in range(frame_count):
                frame = np.full((90, 160, 3), 36 + (index * 12) % 180, dtype=np.uint8)
                cv2.putText(
                    frame,
                    f'W9 {index + 1:02d}s',
                    (20, 52),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2,
                )
                writer.write(frame)
        finally:
            writer.release()
        data = Path(temp_path).read_bytes()
        if len(data) < 64 or not data.startswith(b'\x1aE\xdf\xa3'):
            raise CommandError('Tệp video WebM demo tạo ra không hợp lệ.')
        return data
    finally:
        Path(temp_path).unlink(missing_ok=True)


class Command(BaseCommand):
    help = 'Tạo dữ liệu demo W9-01 cố định trong DB w9_demo_* (chỉ chạy khi W9_DEMO_ENABLED=1).'

    def add_arguments(self, parser):
        parser.add_argument('--anchor', help='Mốc thời gian ISO-8601 làm chuẩn hạn nộp (mặc định: hiện tại).')

    def handle(self, *args, **options):
        if os.environ.get('W9_DEMO_ENABLED') != '1':
            raise CommandError('Từ chối chạy seed: đặt W9_DEMO_ENABLED=1 trong môi trường demo riêng.')

        db_name = str(connections['default'].settings_dict.get('NAME') or '')
        if not db_name.startswith('w9_demo_'):
            raise CommandError('Từ chối chạy seed: tên DB phải bắt đầu bằng w9_demo_.')

        demo_password = os.environ.get('W9_DEMO_PASSWORD', '')
        if len(demo_password) < 8:
            raise CommandError('Thiếu W9_DEMO_PASSWORD hợp lệ (>= 8 ký tự) trong biến môi trường.')

        if options.get('anchor'):
            anchor = parse_datetime(options['anchor'])
            if anchor is None:
                raise CommandError('Giá trị --anchor phải là timestamp ISO-8601 hợp lệ.')
            if timezone.is_naive(anchor):
                anchor = timezone.make_aware(anchor, timezone.get_current_timezone())
        else:
            anchor = timezone.now()

        with transaction.atomic():
            users = self._ensure_users(demo_password)
            t1, t2 = users['t1'], users['t2']
            s1, s2, s3 = users['s1'], users['s2'], users['s3']

            course1 = self._ensure_course(t1, 'w9demo:course:1', 'W9 Demo - Kiến trúc máy tính')
            course2 = self._ensure_course(t2, 'w9demo:course:2', 'W9 Demo - Cơ sở dữ liệu')

            room1 = self._ensure_classroom(course1, 'w9demo:room:1', 'W9 Demo - Lớp chính')
            room2 = self._ensure_classroom(course1, 'w9demo:room:2', 'W9 Demo - Lớp kiểm tra')
            self._ensure_classroom(course2, 'w9demo:room:3', 'W9 Demo - Lớp giáo viên 2')

            e_s1, e_s1_created = self._ensure_enrollment(room1, s1)
            e_s2, e_s2_created = self._ensure_enrollment(room1, s2)
            self._ensure_withdrawn_enrollment(t1, course1, room1, s3)
            _, e_s2_r2_created = self._ensure_enrollment(room2, s2)

            session1 = self._ensure_session(room1, 'w9demo:session:1', 'Buổi 1: Tổng quan CPU', 1, is_draft=False)
            draft_session = self._ensure_session(room1, 'w9demo:session:draft', 'Buổi nháp chưa công bố', 2, is_draft=True)
            session_r2 = self._ensure_session(room2, 'w9demo:session:r2', 'Buổi 1: Kiểm tra và Quá hạn', 1, is_draft=False)

            doc1, ver1 = self._ensure_pdf(t1, course1, session1, 'w9demo:doc:1', 'W9 Demo - Tài liệu tổng hợp')
            self._ensure_pdf(t1, course1, draft_session, 'w9demo:doc:draft', 'W9 Demo - Tài liệu nháp')

            video1, vq1 = self._ensure_video(session1, 'w9demo:video:1', 'W9 Demo - Video bài giảng')

            quiz_practice = self._ensure_assessment(
                session1,
                'w9demo:assess:practice',
                title='W9 Demo - Quiz ôn tập',
                kind='QUIZ',
                mode='PRACTICE',
                due_at=anchor + timedelta(days=7),
                anchor=anchor,
                expected_overdue=False,
                results_published=True,
                questions=[{
                    'id': 'q1',
                    'prompt': '1 + 1 bằng mấy?',
                    'multiple': False,
                    'choices': [{'id': 'a', 'text': '2'}, {'id': 'b', 'text': '3'}],
                    'correct_ids': ['a'],
                }],
            )
            essay_practice = self._ensure_assessment(
                session1,
                'w9demo:assess:text',
                title='W9 Demo - Tự luận ôn tập',
                kind='TEXT',
                mode='PRACTICE',
                due_at=anchor + timedelta(days=7),
                anchor=anchor,
                expected_overdue=False,
                results_published=False,
                questions=[],
            )
            quiz_test = self._ensure_assessment(
                session_r2,
                'w9demo:assess:test',
                title='W9 Demo - Quiz kiểm tra',
                kind='QUIZ',
                mode='TEST',
                due_at=anchor + timedelta(days=5),
                anchor=anchor,
                expected_overdue=False,
                results_published=False,
                questions=[{
                    'id': 'q1',
                    'prompt': 'Khối nào thực hiện phép toán số học?',
                    'multiple': False,
                    'choices': [{'id': 'a', 'text': 'ALU'}, {'id': 'b', 'text': 'RAM'}],
                    'correct_ids': ['a'],
                }],
            )
            overdue_assess = self._ensure_assessment(
                session_r2,
                'w9demo:assess:overdue',
                title='W9 Demo - Bài quá hạn',
                kind='TEXT',
                mode='PRACTICE',
                due_at=anchor - timedelta(days=1),
                anchor=anchor,
                expected_overdue=True,
                results_published=False,
                questions=[],
            )

            # S1 in room1: PDF + Quiz Practice (score 0 published) = 2/4 = 50%, plus DRAFT essay.
            self._ensure_document_completion(e_s1, ver1, allow_create=e_s1_created)
            self._ensure_attempt(
                quiz_practice, s1, 'w9demo:attempt:s1:q1', allow_create=e_s1_created, number=1, status='SUBMITTED',
                answers={'q1': 'b'}, text='', score=0, grade_published=True,
                started_at=anchor - timedelta(hours=2), submitted_at=anchor - timedelta(hours=1),
                expires_at=anchor + timedelta(days=1),
            )
            self._ensure_attempt(
                essay_practice, s1, 'w9demo:attempt:s1:draft', allow_create=e_s1_created, number=1, status='DRAFT',
                answers={}, text='Bản nháp chưa nộp của S1', score=None, grade_published=False,
                started_at=anchor - timedelta(minutes=30), submitted_at=None,
                expires_at=anchor + timedelta(days=7),
            )

            # S2 in room1: PDF + Video + Quiz Practice (2 attempts: 0 -> 10) + TEXT submitted/pending -> 4/4 = 100%.
            self._ensure_document_completion(e_s2, ver1, allow_create=e_s2_created)
            self._ensure_video_progress(
                video1, vq1, s2, completed_at=anchor - timedelta(hours=1), allow_create=e_s2_created
            )

            self._ensure_attempt(
                quiz_practice, s2, 'w9demo:attempt:s2:q1', allow_create=e_s2_created, number=1, status='SUBMITTED',
                answers={'q1': 'b'}, text='', score=0, grade_published=True,
                started_at=anchor - timedelta(hours=3), submitted_at=anchor - timedelta(hours=2, minutes=45),
                expires_at=anchor + timedelta(days=1),
            )
            self._ensure_attempt(
                quiz_practice, s2, 'w9demo:attempt:s2:q2', allow_create=e_s2_created, number=2, status='SUBMITTED',
                answers={'q1': 'a'}, text='', score=10, grade_published=True,
                started_at=anchor - timedelta(hours=2), submitted_at=anchor - timedelta(hours=1, minutes=45),
                expires_at=anchor + timedelta(days=1),
            )
            self._ensure_attempt(
                essay_practice, s2, 'w9demo:attempt:s2:text', allow_create=e_s2_created, number=1, status='SUBMITTED',
                answers={}, text='Bài tự luận hoàn chỉnh chờ giáo viên chấm.', score=None, grade_published=False,
                started_at=anchor - timedelta(hours=1), submitted_at=anchor - timedelta(minutes=20),
                expires_at=anchor + timedelta(days=7),
            )
            self._ensure_attempt(
                quiz_test, s2, 'w9demo:attempt:s2:test', allow_create=e_s2_r2_created, number=1, status='SUBMITTED',
                answers={'q1': 'a'}, text='', score=10, grade_published=False,
                started_at=anchor - timedelta(minutes=40), submitted_at=anchor - timedelta(minutes=10),
                expires_at=anchor + timedelta(days=1),
            )

            refresh_classroom_progress(classroom_id=room1.pk)
            refresh_classroom_progress(classroom_id=room2.pk)

        self.stdout.write(
            f'W9 demo seed ready (anchor={anchor.isoformat()}, db={db_name}, '
            f'room1={room1.pk}, room2={room2.pk}, doc1={doc1.pk}, video1={video1.pk}, overdue={overdue_assess.pk}).'
        )

    def _ensure_users(self, password):
        specs = [
            ('t1', 'w9demo_t1', 'TEACHER', 'Giáo viên Demo 1'),
            ('t2', 'w9demo_t2', 'TEACHER', 'Giáo viên Demo 2'),
            ('s1', 'w9demo_s1', 'STUDENT', 'Học viên Demo 1'),
            ('s2', 'w9demo_s2', 'STUDENT', 'Học viên Demo 2'),
            ('s3', 'w9demo_s3', 'STUDENT', 'Học viên Demo 3'),
        ]
        out = {}
        for key, username, role, full_name in specs:
            user = User.objects.filter(username=username).first()
            created_user = user is None
            if user is None:
                user = User.objects.create_user(
                    username=username,
                    email=f'{username}@demo.local',
                    password=password,
                    role=role,
                    full_name=full_name,
                )
            elif user.role != role or not user.is_active or user.status != User.Status.ACTIVE or user.full_name != full_name:
                raise CommandError(f'Conflict trên tài khoản {username}: thuộc tính đã thay đổi.')
            if role == 'TEACHER':
                from apps.users.teacher_approval import record, snapshot
                approval = TeacherApproval.objects.get(teacher_profile=user.teacher_profile)
                if created_user:
                    before = snapshot(approval, user.teacher_profile)
                    approval.status, approval.source = 'APPROVED', 'LEGACY'
                    approval.reason = 'Explicit teacher fixture in isolated demo database.'
                    approval.approved_at = approval.decided_at = timezone.now()
                    approval.revision += 1
                    approval.save()
                    record(approval, user.teacher_profile, before, 'DEMO_APPROVED', approval.reason)
                elif approval.status != 'APPROVED':
                    raise CommandError(f'Conflict trên tài khoản {username}: trạng thái duyệt đã thay đổi.')
            out[key] = user
        return out

    def _ensure_course(self, owner, key, title):
        cid = demo_uuid(key)
        course = Course.objects.filter(pk=cid).first()
        if course is not None:
            owner_ok = course.memberships.filter(user=owner, role='OWNER', status='ACTIVE').exists()
            if course.title != title or course.status != Course.Status.PUBLISHED or not owner_ok:
                raise CommandError(f'Conflict trên course {cid}: trạng thái hoặc chủ khóa không khớp.')
            return course
        course = Course.objects.create(pk=cid, title=title, description='Dữ liệu demo W9-01', status='DRAFT')
        CourseMember.objects.create(course=course, user=owner, role='OWNER', status='ACTIVE')
        AccessPolicy.objects.create(course=course)
        update_course(actor=owner, course=course, changes={'status': 'PUBLISHED'})
        return course

    def _ensure_classroom(self, course, key, name):
        rid = demo_uuid(key)
        room = Classroom.all_objects.filter(pk=rid).first()
        if room is not None:
            if room.course_id != course.pk or room.name != name or room.removed_at is not None:
                raise CommandError(f'Conflict trên classroom {rid}: tên, khóa hoặc trạng thái đã thay đổi.')
            return room
        return Classroom.objects.create(pk=rid, course=course, name=name)

    def _ensure_enrollment(self, room, student):
        existing = Enrollment.objects.filter(classroom=room, student=student.student_profile).first()
        if existing is not None:
            if existing.status == Enrollment.Status.WITHDRAWN:
                raise CommandError(f'Conflict trên ghi danh {student.username} ở {room.name}: đang ở trạng thái WITHDRAWN.')
            return existing, False
        _, enrollment, _ = join_by_code(actor=student, class_code=room.class_code)
        return enrollment, True

    def _ensure_withdrawn_enrollment(self, teacher, course, room, student):
        existing = Enrollment.objects.filter(classroom=room, student=student.student_profile).first()
        if existing is not None:
            if existing.status != Enrollment.Status.WITHDRAWN:
                raise CommandError(f'Conflict trên ghi danh {student.username} ở {room.name}: trạng thái không còn WITHDRAWN.')
            return existing
        _, enrollment, _ = join_by_code(actor=student, class_code=room.class_code)
        withdraw_classroom_enrollment(actor=teacher, course=course, classroom_id=room.pk, enrollment_id=enrollment.pk)
        return enrollment

    def _ensure_session(self, room, key, title, position, *, is_draft):
        sid = demo_uuid(key)
        session = ClassroomSession.objects.filter(pk=sid).first()
        if session is not None:
            if (
                session.classroom_id != room.pk
                or session.title != title
                or session.is_draft != is_draft
                or session.removed_at is not None
            ):
                raise CommandError(f'Conflict trên session {sid}: dữ liệu buổi học đã thay đổi.')
            return session
        return ClassroomSession.objects.create(pk=sid, classroom=room, title=title, position=position, is_draft=is_draft)

    def _ensure_pdf(self, owner, course, session, key, title):
        did = demo_uuid(key)
        vid = demo_uuid(key + ':v1')
        doc = KnowledgeDocument.objects.filter(pk=did).first()
        if doc is not None:
            ver = DocumentVersion.objects.filter(pk=vid, document=doc).first()
            if (
                doc.course_id != course.pk
                or doc.session_id != session.pk
                or doc.title != title
                or not doc.is_published
                or doc.removed_at is not None
                or doc.published_version_id != vid
                or ver is None
                or ver.removed_at is not None
                or ver.status not in ('EXTRACTED', 'READY')
                or ver.watermark_status != 'READY'
                or not ver.original_storage_key
                or not ver.watermarked_view_key
                or not private_path(ver.original_storage_key).is_file()
                or not private_path(ver.watermarked_view_key).is_file()
            ):
                raise CommandError(f'Conflict trên document {did}: phiên bản, công bố hoặc tệp PDF đã thay đổi.')
            return doc, ver

        pdf_bytes = build_demo_pdf_bytes(title)
        watermarked_bytes = watermarked_pdf_bytes(io.BytesIO(pdf_bytes), str(did), 1)
        checksum = hashlib.sha256(pdf_bytes).hexdigest()
        watermark_checksum = hashlib.sha256(watermarked_bytes).hexdigest()
        storage_key = f'originals/{did}/{vid}.pdf'
        watermark_key = f'watermarked/{did}/{vid}.pdf'

        for rel, content in ((storage_key, pdf_bytes), (watermark_key, watermarked_bytes)):
            target = private_path(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        doc = KnowledgeDocument.objects.create(
            pk=did, course=course, session=session, uploaded_by=owner, title=title, is_published=True
        )
        ver = DocumentVersion.objects.create(
            pk=vid, document=doc, version_number=1, file_name='demo.pdf',
            file_size_bytes=len(pdf_bytes), checksum_sha256=checksum, page_count=2,
            original_storage_key=storage_key, watermarked_view_key=watermark_key,
            watermarked_sha256=watermark_checksum, watermark_status='READY', status='EXTRACTED',
        )
        doc.active_version = ver
        doc.published_version = ver
        doc.save(update_fields=['active_version', 'published_version'])
        return doc, ver

    def _ensure_document_completion(self, enrollment, version, *, allow_create):
        existing = DocumentCompletion.objects.filter(enrollment=enrollment, document_version=version).first()
        if existing is not None:
            return existing
        if not allow_create:
            raise CommandError(
                f'Conflict trên DocumentCompletion của enrollment {enrollment.pk}: dấu hoàn thành đã bị gỡ.'
            )
        return DocumentCompletion.objects.create(enrollment=enrollment, document_version=version)

    def _ensure_video(self, session, key, title):
        vid = demo_uuid(key)
        qid = demo_uuid(key + ':q1')
        video = SessionVideo.objects.filter(pk=vid).first()
        if video is not None:
            question = VideoQuestion.objects.filter(pk=qid, video=video, removed_at__isnull=True).first()
            if (
                video.session_id != session.pk
                or video.title != title
                or not video.is_published
                or video.removed_at is not None
                or video.content_type != 'video/webm'
                or abs(video.duration - DEMO_VIDEO_DURATION) > 0.01
                or not video.file
                or not video.file.storage.exists(video.file.name)
                or question is None
                or question.kind != 'MCQ'
                or question.correct_ids != ['a']
                or abs(question.start_time - DEMO_VIDEO_CHECKPOINT) > 0.01
            ):
                raise CommandError(f'Conflict trên video {vid}: cấu hình, tệp hoặc checkpoint đã thay đổi.')
            return video, question

        video_bytes = build_demo_webm_bytes(duration_seconds=int(DEMO_VIDEO_DURATION), fps=1)
        video = SessionVideo(
            pk=vid, session=session, title=title, description='Video demo W9',
            content_type='video/webm', duration=DEMO_VIDEO_DURATION, is_published=True,
        )
        video.file.save(f'{vid}.webm', ContentFile(video_bytes), save=False)
        video.save()
        question = VideoQuestion.objects.create(
            pk=qid, video=video, kind='MCQ', prompt='Câu hỏi mốc 5s?',
            choices=[{'id': 'a', 'text': 'Đúng'}, {'id': 'b', 'text': 'Sai'}],
            correct_ids=['a'], multiple=False, start_time=DEMO_VIDEO_CHECKPOINT,
        )
        return video, question

    def _ensure_video_progress(self, video, question, student, *, completed_at, allow_create):
        vp = VideoProgress.objects.filter(video=video, student=student).first()
        if vp is not None:
            passed_map = vp.passed if isinstance(vp.passed, dict) else {}
            if vp.completed_at is None or passed_map.get(str(question.pk)) != question.revision:
                raise CommandError(
                    f'Conflict trên VideoProgress của {student.username}: tiến trình video không khớp trạng thái hoàn thành.'
                )
            return vp
        if not allow_create:
            raise CommandError(
                f'Conflict trên VideoProgress của {student.username}: tiến trình video đã bị xóa.'
            )
        return VideoProgress.objects.create(
            video=video,
            student=student,
            position=DEMO_VIDEO_DURATION,
            watched_until=DEMO_VIDEO_DURATION,
            completed_at=completed_at,
            passed={str(question.pk): question.revision},
        )

    def _ensure_assessment(self, session, key, *, title, kind, mode, due_at, anchor, expected_overdue, results_published, questions):
        aid = demo_uuid(key)
        obj = Assessment.objects.filter(pk=aid).first()
        if obj is not None:
            if (
                obj.session_id != session.pk
                or obj.title != title
                or obj.kind != kind
                or obj.mode != mode
                or not obj.is_published
                or obj.removed_at is not None
                or obj.results_published != results_published
                or obj.questions != questions
                or (obj.due_at < anchor) != expected_overdue
            ):
                raise CommandError(f'Conflict trên assessment {aid}: cấu hình hoặc trạng thái công bố đã thay đổi.')
            return obj
        return Assessment.objects.create(
            pk=aid, session=session, title=title, kind=kind, mode=mode,
            questions=questions, due_at=due_at, is_published=True,
            results_published=results_published,
        )

    def _ensure_attempt(self, assessment, student, key, *, allow_create, **fields):
        req_id = demo_uuid(key)
        existing = AssessmentAttempt.objects.filter(assessment=assessment, student=student, request_id=req_id).first()
        if existing is not None:
            existing_score = float(existing.score) if existing.score is not None else None
            expected_score = float(fields['score']) if fields['score'] is not None else None
            if (
                existing.number != fields['number']
                or existing.status != fields['status']
                or existing.grade_published != fields['grade_published']
                or existing.answers != fields.get('answers', {})
                or existing.text != fields.get('text', '')
                or existing_score != expected_score
            ):
                raise CommandError(f'Conflict trên attempt {req_id}: trạng thái, câu trả lời hoặc điểm đã thay đổi.')
            return existing
        if not allow_create:
            raise CommandError(f'Conflict trên attempt {req_id}: lượt làm bài đã bị xóa.')
        attempt = AssessmentAttempt.objects.create(
            pk=demo_uuid(key + ':pk'),
            assessment=assessment,
            student=student,
            request_id=req_id,
            **fields,
        )
        if fields.get('submitted_at'):
            AssessmentAttempt.objects.filter(pk=attempt.pk).update(submitted_at=fields['submitted_at'])
        return attempt
