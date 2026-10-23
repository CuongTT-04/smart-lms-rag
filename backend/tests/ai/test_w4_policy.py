from datetime import timedelta
from uuid import uuid4
from django.utils import timezone
from apps.courses.assessment_models import Assessment, AssessmentAttempt
from apps.ai.policy import enforce_chat_policy
from apps.documents.exceptions import DocumentError
from tests.documents.test_retrieval_scope import ScopeFixture


class ChatPolicyTests(ScopeFixture):
    def values(self, **extra):
        return {'course_id': str(self.course.pk), 'session_id': str(self.session.pk),
                'question': 'Gợi ý?', 'mode': 'qa', **extra}

    def assessment(self, **extra):
        return Assessment.objects.create(session=self.session, title='Quiz', mode='TEST', kind='QUIZ',
            due_at=timezone.now()+timedelta(hours=1), is_published=True,
            questions=[{'id': str(uuid4()), 'prompt': 'Câu hỏi', 'choices': [{'id':'a','text':'A'}],
                        'correct_ids': ['a'], 'hint': 'Secret'}], **extra)

    def attempt(self, assessment, **extra):
        return AssessmentAttempt.objects.create(assessment=assessment, student=self.student,
            request_id=uuid4(), number=1, expires_at=timezone.now()+timedelta(minutes=10), **extra)

    def test_test_blocks_qa_and_hint_then_submission_unblocks(self):
        assessment = self.assessment()
        attempt = self.attempt(assessment)
        for mode in ('qa', 'hint'):
            with self.assertRaises(DocumentError) as caught:
                enforce_chat_policy(self.student, self.values(mode=mode))
            self.assertEqual(caught.exception.code, 'AI_NOT_ALLOWED')
        attempt.status='SUBMITTED'; attempt.save()
        self.assertIsNone(enforce_chat_policy(self.student, self.values()))

    def test_expired_quiz_is_finalized_and_does_not_block(self):
        attempt = self.attempt(self.assessment())
        attempt.expires_at=timezone.now()-timedelta(seconds=1); attempt.save()
        self.assertIsNone(enforce_chat_policy(self.student, self.values()))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'SUBMITTED')

    def test_hint_returns_only_public_question_fields(self):
        assessment = self.assessment(); assessment.mode='PRACTICE'; assessment.save()
        question = assessment.questions[0]
        context = enforce_chat_policy(self.student, self.values(mode='hint',
            assessment_id=str(assessment.pk), question_id=question['id']))
        self.assertEqual(context['question']['prompt'], 'Câu hỏi')
        self.assertNotIn('correct_ids', str(context))
        self.assertNotIn('Secret', str(context))
        self.enrollment.status='WITHDRAWN'; self.enrollment.save()
        with self.assertRaises(DocumentError):
            enforce_chat_policy(self.student, self.values(mode='hint', assessment_id=str(assessment.pk), question_id=question['id']))
