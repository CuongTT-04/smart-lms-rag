from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.courses.models import Course,CourseMember,Classroom,ClassroomSession,Enrollment
from apps.documents.models import KnowledgeDocument,DocumentVersion
from apps.documents.exceptions import DocumentError
from apps.documents.retrieval_scope import resolve_scope


class ScopeFixture(TestCase):
    def setUp(self):
        User=get_user_model()
        self.owner=User.objects.create_user('w3-owner',role='TEACHER')
        self.student=User.objects.create_user('w3-student',role='STUDENT')
        self.course=Course.objects.create(title='W3',status='PUBLISHED')
        CourseMember.objects.create(course=self.course,user=self.owner,role='OWNER')
        self.member=CourseMember.objects.create(course=self.course,user=self.student,role='STUDENT')
        self.classroom=Classroom.objects.create(course=self.course,name='Class',class_code='W3CLASS')
        self.session=ClassroomSession.objects.create(classroom=self.classroom,title='Session',is_draft=False)
        self.enrollment=Enrollment.objects.create(classroom=self.classroom,student=self.student.student_profile,status='ACTIVE')
        self.doc=KnowledgeDocument.objects.create(course=self.course,session=self.session,uploaded_by=self.owner,title='PDF')
        self.version=DocumentVersion.objects.create(document=self.doc,version_number=1,file_name='a.pdf',
            original_storage_key='a.pdf',file_size_bytes=1,checksum_sha256='a'*64,page_count=1,status='EXTRACTED')
        self.doc.is_published=True;self.doc.published_version=self.version;self.doc.save()


class ScopeTests(ScopeFixture):
    def test_student_published_scope_empty_selection_and_hint(self):
        scope=resolve_scope(self.student,self.course.pk,session_id=self.session.pk,mode='hint')
        self.assertEqual(scope.allowed_version_ids,(str(self.version.pk),))
        self.assertEqual(scope.mode,'hint')
        self.assertEqual(resolve_scope(self.student,self.course.pk,document_ids=[]).allowed_version_ids,())

    def test_draft_unpublished_removed_and_latest_version_are_not_student_sources(self):
        newer=DocumentVersion.objects.create(document=self.doc,version_number=2,file_name='new.pdf',
            original_storage_key='new.pdf',file_size_bytes=1,checksum_sha256='b'*64,page_count=1,status='EXTRACTED')
        self.doc.active_version=newer;self.doc.save()
        self.assertEqual(resolve_scope(self.student,self.course.pk).allowed_version_ids,(str(self.version.pk),))
        self.doc.is_published=False;self.doc.save()
        self.assertEqual(resolve_scope(self.student,self.course.pk).allowed_version_ids,())
        self.assertEqual(resolve_scope(self.owner,self.course.pk,preview=True).allowed_version_ids,(str(newer.pk),))
        with self.assertRaises(DocumentError):resolve_scope(self.student,self.course.pk,preview=True)
        self.session.is_draft=True;self.session.save()
        with self.assertRaises(DocumentError):resolve_scope(self.student,self.course.pk,session_id=self.session.pk)

    def test_revoked_classroom_wrong_ids_and_mode_fail_closed(self):
        self.enrollment.status='WITHDRAWN';self.enrollment.save()
        with self.assertRaises(DocumentError):resolve_scope(self.student,self.course.pk,session_id=self.session.pk)
        self.member.status='REMOVED';self.member.save()
        with self.assertRaises(DocumentError):resolve_scope(self.student,self.course.pk)
        with self.assertRaises(DocumentError):resolve_scope(self.owner,self.course.pk,mode='invalid')

    def test_course_scope_does_not_bypass_session_classroom_membership(self):
        self.enrollment.status='WITHDRAWN';self.enrollment.save()
        self.assertEqual(resolve_scope(self.student,self.course.pk).allowed_version_ids,())

    def test_foreign_document_and_classroom_are_rejected(self):
        foreign=Course.objects.create(title='Foreign',status='PUBLISHED')
        cls=Classroom.objects.create(course=foreign,name='Other',class_code='FOREIGN')
        with self.assertRaises(DocumentError):resolve_scope(self.student,self.course.pk,classroom_id=cls.pk)
        from uuid import uuid4
        with self.assertRaises(DocumentError):resolve_scope(self.student,self.course.pk,document_ids=[str(uuid4())])

    def test_removed_session_or_classroom_is_not_in_course_scope(self):
        self.session.removed_at=timezone.now();self.session.save()
        self.assertEqual(resolve_scope(self.student,self.course.pk).allowed_version_ids,())
        self.session.removed_at=None;self.session.save()
        self.classroom.removed_at=timezone.now();self.classroom.save()
        self.assertEqual(resolve_scope(self.student,self.course.pk).allowed_version_ids,())
