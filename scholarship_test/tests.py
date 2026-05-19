import json
import io
from zipfile import ZipFile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from datetime import timedelta

from scholarship_test.models import (
    RankPredictorLead,
    ScholarshipStudent,
    ScholarshipTest,
    ScholarshipTestAttempt,
    ScholarshipTestAnswer,
    ScholarshipTestConfig,
    ScholarshipTestOption,
    ScholarshipTestQuestion,
    ScholarshipTestSection,
)
from scholarship_test.services import test_service
from scholarship_test.services import word_import_service
from sds.models import Student
from sds.views import (
    _build_analysis_dataset_for_test,
    _build_attempt_leaderboard,
    _build_my_tests_payload,
)


class ScholarshipRuntimeTestFlowTests(TestCase):
    def setUp(self):
        self.student = ScholarshipStudent.objects.create(
            name='Aarav',
            phone_number='9876543210',
            grade='10th',
            board='CBSE',
            otp_verified=True,
        )

    def create_runtime_test(self, *, status='published', name='Builder Test'):
        test = ScholarshipTest.objects.create(
            name=name,
            status=status,
            duration_hours=0,
            duration_minutes=30,
            tags='SCHOLARSHIP TEST',
        )
        ScholarshipTestConfig.objects.create(test=test)
        section = ScholarshipTestSection.objects.create(
            test=test,
            name='Mathematics',
            order=0,
        )
        return test, section

    def add_mcq_question(
        self,
        section,
        *,
        text='2 + 2 = ?',
        correct_index=1,
        pos_marks=2,
        neg_marks=1,
        neg_unattempted=0,
    ):
        question = ScholarshipTestQuestion.objects.create(
            section=section,
            question_type='mcq',
            question_text=text,
            order=0,
            pos_marks=pos_marks,
            neg_marks=neg_marks,
            neg_unattempted=neg_unattempted,
        )
        for index, option_text in enumerate(['3', '4', '5', '6']):
            ScholarshipTestOption.objects.create(
                question=question,
                option_text=option_text,
                is_correct=index == correct_index,
                order=index,
            )
        return question

    def test_get_active_test_prefers_published_test(self):
        draft_test, draft_section = self.create_runtime_test(status='draft', name='Draft Test')
        self.add_mcq_question(draft_section)

        published_test, published_section = self.create_runtime_test(
            status='published',
            name='Published Test',
        )
        self.add_mcq_question(published_section)

        active_test = test_service.get_active_test()

        self.assertEqual(active_test.id, published_test.id)
        self.assertNotEqual(active_test.id, draft_test.id)

    @override_settings(ANSWER_KEY_VISIBILITY_DELAY_HOURS=2)
    def test_answer_key_available_two_hours_after_scheduled_test_end(self):
        scheduled_start = timezone.now() - timedelta(hours=2, minutes=29)
        test, section = self.create_runtime_test(name='Scheduled Delay Test')
        test.scheduled_start_at = scheduled_start
        test.save(update_fields=['scheduled_start_at'])
        self.add_mcq_question(section)
        attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=test,
            status='completed',
            test_started_at=scheduled_start,
            test_completed_at=scheduled_start + timedelta(minutes=20),
        )

        available_at = test_service.get_answer_key_available_at(attempt)

        self.assertEqual(
            available_at,
            scheduled_start + timedelta(minutes=30, hours=2),
        )
        self.assertFalse(
            test_service.is_answer_key_available(
                attempt,
                now=available_at - timedelta(seconds=1),
            )
        )
        self.assertTrue(test_service.is_answer_key_available(attempt, now=available_at))

    @override_settings(ANSWER_KEY_VISIBILITY_DELAY_HOURS=2)
    def test_attempt_review_backend_blocks_until_delay_expires(self):
        scheduled_start = timezone.now() - timedelta(hours=1)
        test, section = self.create_runtime_test(name='Locked Review Test')
        test.scheduled_start_at = scheduled_start
        test.save(update_fields=['scheduled_start_at'])
        question = self.add_mcq_question(section)
        attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=test,
            status='completed',
            test_started_at=scheduled_start,
            test_completed_at=scheduled_start + timedelta(minutes=20),
            progress_state={'answers': {str(question.id): '1'}},
        )
        client = Client()
        session = client.session
        session['scholarship_student_id'] = self.student.id
        session.save()

        response = client.get(
            reverse('scholarship_test:scholarship_attempt_review', args=[attempt.id])
        )

        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            'Answer key will be available after 2 hours from test completion.',
            status_code=403,
        )

    @override_settings(ANSWER_KEY_VISIBILITY_DELAY_HOURS=2)
    def test_attempt_review_backend_allows_after_delay_expires(self):
        scheduled_start = timezone.now() - timedelta(hours=3)
        test, section = self.create_runtime_test(name='Unlocked Review Test')
        test.scheduled_start_at = scheduled_start
        test.save(update_fields=['scheduled_start_at'])
        question = self.add_mcq_question(section)
        attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=test,
            status='completed',
            test_started_at=scheduled_start,
            test_completed_at=scheduled_start + timedelta(minutes=20),
            progress_state={'answers': {str(question.id): '1'}},
        )
        client = Client()
        session = client.session
        session['scholarship_student_id'] = self.student.id
        session.save()

        response = client.get(
            reverse('scholarship_test:scholarship_attempt_review', args=[attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Attempted Test Paper and Answer Key')
        self.assertContains(response, '4')

    def test_submit_runtime_test_scores_builder_questions(self):
        runtime_test, section = self.create_runtime_test()
        mcq = self.add_mcq_question(section)
        fitb = ScholarshipTestQuestion.objects.create(
            section=section,
            question_type='fitb',
            question_text='Capital of France is ______.',
            order=1,
            pos_marks=2,
            neg_marks=1,
        )
        ScholarshipTestAnswer.objects.create(question=fitb, correct_answer='Paris')

        attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=runtime_test,
            status='started',
        )

        success, _, updated_attempt = test_service.submit_runtime_test(
            attempt.id,
            {
                str(mcq.id): '1',
                str(fitb.id): 'paris',
            },
        )

        self.assertTrue(success)
        self.assertEqual(updated_attempt.status, 'completed')
        self.assertEqual(updated_attempt.score, 4)
        self.assertEqual(updated_attempt.total_questions, 2)
        self.assertEqual(updated_attempt.total_marks, 4)
        self.assertEqual(updated_attempt.test_id, runtime_test.id)

    def test_submit_runtime_test_applies_negative_and_unattempted_marks(self):
        runtime_test, section = self.create_runtime_test()
        correct_question = self.add_mcq_question(
            section,
            text='Correct question',
            correct_index=1,
            pos_marks=4,
            neg_marks=1,
            neg_unattempted=0,
        )
        wrong_question = self.add_mcq_question(
            section,
            text='Wrong question',
            correct_index=2,
            pos_marks=3,
            neg_marks=2,
            neg_unattempted=0,
        )
        unattempted_question = self.add_mcq_question(
            section,
            text='Unattempted question',
            correct_index=0,
            pos_marks=2,
            neg_marks=1,
            neg_unattempted=1,
        )

        attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=runtime_test,
            status='started',
        )

        success, _, updated_attempt = test_service.submit_runtime_test(
            attempt.id,
            {
                str(correct_question.id): '1',
                str(wrong_question.id): '1',
            },
        )

        self.assertTrue(success)
        self.assertEqual(updated_attempt.score, 1)
        self.assertEqual(updated_attempt.total_marks, 9)
        self.assertEqual(updated_attempt.scholarship_percentage, 20)
        self.assertEqual(
            updated_attempt.progress_state['answers'][str(unattempted_question.id)],
            '',
        )

    def test_scholarship_test_view_renders_builder_questions(self):
        runtime_test, section = self.create_runtime_test()
        mcq = self.add_mcq_question(section, text='<p>Rendered from builder</p>')
        attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=runtime_test,
            status='started',
        )

        client = Client()
        session = client.session
        session['scholarship_student_id'] = self.student.id
        session.save()

        response = client.get(
            reverse('scholarship_test:scholarship_test', args=[attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_questions'], 1)
        self.assertEqual(response.context['test'].id, runtime_test.id)
        self.assertEqual(response.context['questions'][0]['id'], mcq.id)
        self.assertEqual(
            response.context['questions'][0]['question_html'],
            '<p>Rendered from builder</p>',
        )

    def test_launch_view_sets_selected_test_in_session(self):
        runtime_test, section = self.create_runtime_test(name='RTSE-2026 Scholarship Test')
        self.add_mcq_question(section)

        client = Client()
        response = client.get(
            reverse('scholarship_test:scholarship_launch_test', args=[runtime_test.id])
        )

        self.assertRedirects(response, reverse('scholarship_test:scholarship_landing'))
        self.assertEqual(
            client.session.get('scholarship_selected_test_id'),
            runtime_test.id,
        )

    def test_launch_view_redirects_non_rtse_tests_to_dashboard(self):
        runtime_test, section = self.create_runtime_test(name='Weekly Scholarship Mock 1')
        self.add_mcq_question(section)

        client = Client()
        response = client.get(
            reverse('scholarship_test:scholarship_launch_test', args=[runtime_test.id])
        )

        self.assertRedirects(response, reverse('scholarship_test:scholarship_dashboard'))
        self.assertEqual(
            client.session.get('scholarship_selected_test_id'),
            runtime_test.id,
        )

    def test_start_test_uses_selected_test_and_does_not_block_other_completed_tests(self):
        completed_test, completed_section = self.create_runtime_test(name='Completed Test')
        self.add_mcq_question(completed_section)

        selected_test, selected_section = self.create_runtime_test(name='Selected Test')
        self.add_mcq_question(selected_section, text='Selected test question')

        ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=completed_test,
            status='completed',
            score=1,
            total_questions=1,
        )

        client = Client()
        session = client.session
        session['scholarship_student_id'] = self.student.id
        session['scholarship_selected_test_id'] = selected_test.id
        session.save()

        response = client.get(reverse('scholarship_test:scholarship_start_test'))

        latest_attempt = ScholarshipTestAttempt.objects.exclude(
            status='completed'
        ).latest('id')

        self.assertRedirects(
            response,
            reverse('scholarship_test:scholarship_test', args=[latest_attempt.id]),
        )
        self.assertEqual(latest_attempt.test_id, selected_test.id)
        self.assertEqual(latest_attempt.student_id, self.student.id)

    def test_start_test_reuses_existing_in_progress_attempt(self):
        runtime_test, section = self.create_runtime_test(name='Resume Test')
        self.add_mcq_question(section)

        attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=runtime_test,
            status='in_progress',
            progress_state={
                'answers': {},
                'current_question_index': 0,
                'tab_switch_count': 0,
                'saved_at': '2026-05-02T00:00:00Z',
            },
        )

        client = Client()
        session = client.session
        session['scholarship_student_id'] = self.student.id
        session['scholarship_selected_test_id'] = runtime_test.id
        session.save()

        response = client.get(reverse('scholarship_test:scholarship_start_test'))

        self.assertRedirects(
            response,
            reverse('scholarship_test:scholarship_test', args=[attempt.id]),
        )
        self.assertEqual(
            ScholarshipTestAttempt.objects.filter(student=self.student, test=runtime_test).count(),
            1,
        )

    def test_dashboard_allows_access_before_start_but_disables_start_until_one_minute_window(self):
        runtime_test, section = self.create_runtime_test(name='Scheduled Dashboard Test')
        self.add_mcq_question(section)
        ScholarshipTest.objects.filter(id=runtime_test.id).update(
            scheduled_start_at=timezone.now() + timedelta(minutes=5),
            date=timezone.localdate(),
        )
        runtime_test.refresh_from_db()

        client = Client()
        session = client.session
        session['scholarship_student_id'] = self.student.id
        session['scholarship_selected_test_id'] = runtime_test.id
        session.save()

        response = client.get(reverse('scholarship_test:scholarship_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_attempt'])
        self.assertFalse(response.context['can_start_test'])
        self.assertContains(response, "activates 1 minute before")

    def test_start_test_redirects_to_dashboard_before_one_minute_start_window(self):
        runtime_test, section = self.create_runtime_test(name='Delayed Start Test')
        self.add_mcq_question(section)
        ScholarshipTest.objects.filter(id=runtime_test.id).update(
            scheduled_start_at=timezone.now() + timedelta(minutes=5),
            date=timezone.localdate(),
        )
        runtime_test.refresh_from_db()

        client = Client()
        session = client.session
        session['scholarship_student_id'] = self.student.id
        session['scholarship_selected_test_id'] = runtime_test.id
        session.save()

        response = client.get(reverse('scholarship_test:scholarship_start_test'))

        self.assertRedirects(response, reverse('scholarship_test:scholarship_dashboard'))
        self.assertEqual(
            ScholarshipTestAttempt.objects.filter(student=self.student, test=runtime_test).count(),
            0,
        )

    def test_save_progress_persists_answers_and_current_question(self):
        runtime_test, section = self.create_runtime_test()
        question = self.add_mcq_question(section)
        attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=runtime_test,
            status='started',
        )

        client = Client()
        session = client.session
        session['scholarship_student_id'] = self.student.id
        session.save()

        response = client.post(
            reverse('scholarship_test:scholarship_save_test_progress', args=[attempt.id]),
            data=json.dumps({
                'answers': {str(question.id): '1'},
                'current_question_index': 0,
                'tab_switch_count': 2,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'in_progress')
        self.assertEqual(attempt.progress_state['answers'][str(question.id)], '1')
        self.assertEqual(attempt.progress_state['current_question_index'], 0)
        self.assertEqual(attempt.progress_state['tab_switch_count'], 2)

    def test_scholarship_test_view_restores_saved_progress(self):
        runtime_test, section = self.create_runtime_test()
        question = self.add_mcq_question(section)
        attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=runtime_test,
            status='in_progress',
            progress_state={
                'answers': {str(question.id): '1'},
                'current_question_index': 0,
                'tab_switch_count': 1,
                'saved_at': '2026-05-02T00:00:00Z',
            },
        )

        client = Client()
        session = client.session
        session['scholarship_student_id'] = self.student.id
        session.save()

        response = client.get(
            reverse('scholarship_test:scholarship_test', args=[attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['saved_progress']['answers'][str(question.id)], '1')
        self.assertEqual(response.context['saved_progress']['current_question_index'], 0)

    def test_finalize_expired_attempts_stores_results_for_selected_test(self):
        target_test, target_section = self.create_runtime_test(name='Target Test')
        target_question = self.add_mcq_question(
            target_section,
            correct_index=1,
            pos_marks=4,
            neg_marks=1,
        )
        other_test, other_section = self.create_runtime_test(name='Other Test')
        self.add_mcq_question(other_section)

        expired_attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=target_test,
            status='in_progress',
            progress_state={
                'answers': {str(target_question.id): '1'},
                'current_question_index': 0,
                'tab_switch_count': 0,
                'saved_at': timezone.now().isoformat(),
            },
        )
        ScholarshipTestAttempt.objects.filter(id=expired_attempt.id).update(
            test_started_at=timezone.now() - timedelta(minutes=31)
        )
        expired_attempt.refresh_from_db()

        other_attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=other_test,
            status='in_progress',
        )
        ScholarshipTestAttempt.objects.filter(id=other_attempt.id).update(
            test_started_at=timezone.now() - timedelta(minutes=31)
        )

        finalized = test_service.finalize_expired_attempts(target_test)

        expired_attempt.refresh_from_db()
        other_attempt.refresh_from_db()

        self.assertEqual(len(finalized), 1)
        self.assertEqual(finalized[0].id, expired_attempt.id)
        self.assertEqual(expired_attempt.status, 'expired')
        self.assertEqual(expired_attempt.score, 4)
        self.assertEqual(expired_attempt.total_marks, 4)
        self.assertEqual(other_attempt.status, 'in_progress')

    def test_success_page_shows_top_five_leaderboard_and_current_student_rank(self):
        runtime_test, section = self.create_runtime_test(name='Leaderboard Test')
        self.add_mcq_question(section)

        current_attempt = ScholarshipTestAttempt.objects.create(
            student=self.student,
            test=runtime_test,
            status='completed',
            score=15,
            total_questions=1,
            total_marks=20,
            scholarship_percentage=30,
            test_completed_at=timezone.now(),
        )

        for index, score in enumerate([20, 19, 18, 17, 16, 14], start=1):
            other_student = ScholarshipStudent.objects.create(
                name=f'Student {index}',
                phone_number=f'90000000{index:02d}',
                grade='10th',
                board='CBSE',
                otp_verified=True,
            )
            ScholarshipTestAttempt.objects.create(
                student=other_student,
                test=runtime_test,
                status='completed',
                score=score,
                total_questions=1,
                total_marks=20,
                scholarship_percentage=40,
                test_completed_at=timezone.now() + timedelta(seconds=index),
            )

        client = Client()
        session = client.session
        session['scholarship_student_id'] = self.student.id
        session.save()

        response = client.get(
            reverse('scholarship_test:scholarship_success', args=[current_attempt.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['leaderboard_top_entries']), 5)
        self.assertEqual(response.context['leaderboard_top_entries'][0]['student_name'], 'Student 1')
        self.assertEqual(response.context['leaderboard_top_entries'][0]['score'], 20)
        self.assertEqual(response.context['leaderboard_current_entry']['rank'], 7)
        self.assertEqual(response.context['leaderboard_current_entry']['score'], 15)
        self.assertContains(response, 'Leaderboard')
        self.assertContains(response, 'Your Rank: <strong>#7</strong>', html=True)

    def test_dashboard_renders_guest_view_for_non_rtse_selected_test(self):
        runtime_test, section = self.create_runtime_test(name='Scholarship Mock 2')
        self.add_mcq_question(section)

        client = Client()
        session = client.session
        session['scholarship_selected_test_id'] = runtime_test.id
        session.save()

        response = client.get(reverse('scholarship_test:scholarship_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_guest'])
        self.assertEqual(response.context['selected_test'].id, runtime_test.id)


class RankPredictorFlowTests(TestCase):
    def test_rank_predictor_view_starts_locked(self):
        response = self.client.get(reverse('scholarship_test:rank_predictor'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['rank_predictor_unlocked'])
        self.assertEqual(response.context['rank_predictor_default_difficulty'], 'similar')

    @patch('scholarship_test.views.otp_service.send_otp', return_value=(True, 'OTP sent successfully'))
    def test_rank_predictor_send_otp_creates_pending_lead(self, mocked_send_otp):
        response = self.client.post(
            reverse('scholarship_test:rank_predictor_send_otp'),
            {'phone_number': '9876543210'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(RankPredictorLead.objects.filter(phone_number='9876543210').exists())
        lead = RankPredictorLead.objects.get(phone_number='9876543210')
        self.assertFalse(lead.is_verified)
        self.assertIsNotNone(lead.last_otp_requested_at)
        mocked_send_otp.assert_called_once_with('9876543210')

    @patch('scholarship_test.views.otp_service.verify_otp')
    def test_rank_predictor_verify_otp_unlocks_session_and_marks_lead_verified(self, mocked_verify_otp):
        student = ScholarshipStudent.objects.create(
            name='Rank Predictor User',
            phone_number='9876543210',
            grade='',
            board='',
            otp_verified=True,
        )
        RankPredictorLead.objects.create(phone_number='9876543210')
        mocked_verify_otp.return_value = (True, 'OTP verified successfully', student)

        response = self.client.post(
            reverse('scholarship_test:rank_predictor_verify_otp'),
            {'phone_number': '9876543210', 'otp_code': '1234'},
        )

        self.assertEqual(response.status_code, 200)
        lead = RankPredictorLead.objects.get(phone_number='9876543210')
        self.assertTrue(lead.is_verified)
        self.assertEqual(lead.scholarship_student_id, student.id)
        self.assertIsNotNone(lead.verified_at)
        self.assertTrue(self.client.session.get('rank_predictor_unlocked'))
        self.assertEqual(self.client.session.get('rank_predictor_phone'), '9876543210')


class ScholarshipWordImportTests(TestCase):
    def build_docx_upload(self, paragraphs, name='sample.docx'):
        document_xml = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
            '<w:body>',
        ]

        for paragraph in paragraphs:
            text = (
                str(paragraph)
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
            )
            document_xml.append(f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>')

        document_xml.extend(['</w:body>', '</w:document>'])

        buffer = io.BytesIO()
        with ZipFile(buffer, 'w') as archive:
            archive.writestr('word/document.xml', ''.join(document_xml))

        return SimpleUploadedFile(
            name,
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

    def build_docx_upload_with_body_items(self, body_items, name='sample.docx'):
        document_xml = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
            '<w:body>',
        ]

        def escape_xml(value):
            return (
                str(value)
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
            )

        for item in body_items:
            if item['type'] == 'paragraph':
                document_xml.append(
                    f'<w:p><w:r><w:t xml:space="preserve">{escape_xml(item["text"])}</w:t></w:r></w:p>'
                )
                continue

            if item['type'] == 'table':
                document_xml.append('<w:tbl><w:tr>')
                for cell_text in item.get('cells', []):
                    document_xml.append(
                        '<w:tc><w:p><w:r><w:t xml:space="preserve">'
                        + escape_xml(cell_text)
                        + '</w:t></w:r></w:p></w:tc>'
                    )
                document_xml.append('</w:tr></w:tbl>')

        document_xml.extend(['</w:body>', '</w:document>'])

        buffer = io.BytesIO()
        with ZipFile(buffer, 'w') as archive:
            archive.writestr('word/document.xml', ''.join(document_xml))

        return SimpleUploadedFile(
            name,
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

    def test_word_import_service_parses_sample_format(self):
        upload = self.build_docx_upload(
            [
                'Question',
                'The hybridization of the central carbon in CH3C≡N and the bond angle CCN are',
                'Type',
                'multiple_choice',
                'Option',
                'sp2 , 180°',
                'incorrect',
                'Option',
                'Sp, 180°',
                'correct',
                'Option',
                'sp2 , 120°.',
                'incorrect',
                'Option',
                'sp3 , 109°.',
                'incorrect',
                'Solution',
                'Sp, 180°',
                'Marks',
                '4',
                '1',
                'Question',
                'How many vowels are there?',
                'Type',
                'integer',
                'Answer',
                '5',
                'Solution',
                'a e i o u',
                'Marks',
                '2',
                '4',
                'Question',
                'Type in Hindi | Easy Hindi Typing (हिन्दी में टाइप करें)',
                'English paragraph line 1',
                'English paragraph line 2',
                'Type',
                'comprehension',
                'Question',
                'Nested MCQ question',
                'Type',
                'multiple_choice',
                'Option',
                'Alpha',
                'incorrect',
                'Option',
                'Beta',
                'correct',
                'Marks',
                '4',
                '1',
            ]
        )

        imported = word_import_service.import_questions_from_docx(upload)

        self.assertEqual(imported['section_name'], 'sample')
        self.assertEqual(len(imported['questions']), 3)
        self.assertEqual(imported['questions'][0]['type'], 'mcq')
        self.assertEqual(imported['questions'][0]['correct_options'], [1])
        self.assertEqual(imported['questions'][1]['type'], 'int')
        self.assertEqual(imported['questions'][1]['correct_answer'], '5')
        self.assertEqual(imported['questions'][2]['type'], 'comp')
        self.assertEqual(len(imported['questions'][2]['sub_questions']), 1)
        self.assertIn('Nested MCQ question', imported['questions'][2]['sub_questions'][0])

    def test_word_import_api_returns_questions(self):
        client = Client()
        upload = self.build_docx_upload(
            [
                'Question',
                'Imported from API',
                'Type',
                'true_false',
                'Answer',
                'true',
                'Marks',
                '2',
                '0',
            ],
            name='api-import.docx',
        )

        response = client.post(
            reverse('scholarship_test:api_import_word_questions'),
            {'word_file': upload},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['imported']['section_name'], 'api-import')
        self.assertEqual(payload['imported']['questions'][0]['type'], 'tf')

    def test_word_import_service_parses_marker_template_with_unicode_and_comprehension(self):
        upload = self.build_docx_upload(
            [
                'Question',
                'The hybridization of the central carbon in CH3C≡N and the bond angle CCN are',
                'Type',
                'multiple_choice',
                'Option',
                'sp2 , 180°',
                'incorrect',
                'Option',
                'Sp, 180°',
                'correct',
                'Option',
                'sp2 , 120°.',
                'incorrect',
                'Option',
                'sp3 , 109°.',
                'incorrect',
                'Solution',
                'Sp, 180°',
                'Marks',
                '4',
                '1',
                'Question',
                'How many vovels are there?',
                'Type',
                'integer',
                'Answer',
                '5',
                'Solution',
                'a e i o u, they are 5',
                'Marks',
                '2',
                '4',
                'Question',
                'Ashwin is a/an _________ reader and he can read upto _________ chapter(s) a day',
                'Type',
                'fill_ups',
                'Option',
                'good, awesome',
                'Option',
                'range(5:10)',
                'Solution',
                '',
                'Marks',
                '4',
                '1',
                'Question',
                'Is Taj Mahal Awesome?',
                'Type',
                'true_false',
                'Answer',
                'true',
                'Solution',
                'because it is',
                'Marks',
                '2',
                '0',
                'Question',
                'Is Taj Mahal Awesome?',
                'Type',
                'true_false',
                'Answer',
                'false',
                'Solution',
                'because it’s not',
                'Marks',
                '2',
                '5',
                'Question',
                '',
                'Type in Hindi | Easy Hindi Typing (हिन्दी में टाइप करें)',
                'इंग्लिश में टाइप करे स्पेस दबाये यह हिन्दी में परिवर्तित हो जाएगा',
                'Many educationalists consider it a weak and woolly field, too far removed from the practical applications of the real world to be useful.',
                'Type',
                'comprehension',
                'Question',
                'The hybridization of the central carbon in CH3C≡N and the bond angle CCN are',
                'Type',
                'multiple_choice',
                'Option',
                'sp2 , 180°',
                'incorrect',
                'Option',
                'Sp, 180°',
                'correct',
                'Option',
                'sp2 , 120°.',
                'incorrect',
                'Option',
                'sp3 , 109°.',
                'incorrect',
                'Solution',
                'any explanation for the same',
                'Marks',
                '4',
                '1',
                'Question',
                'Ashwin is a/an _________ reader and he can read upto _________ chapter(s) a day',
                'Type',
                'fill_ups',
                'Option',
                'good, awesome',
                'Option',
                'range(5:10)',
                'Solution',
                '',
                'Marks',
                '4',
                '1',
            ],
            name='marker-template-sample.docx',
        )

        imported = word_import_service.import_questions_from_docx(upload)

        self.assertEqual(imported['section_name'], 'marker-template-sample')
        self.assertEqual(len(imported['questions']), 6)
        self.assertEqual(imported['questions'][0]['type'], 'mcq')
        self.assertEqual(imported['questions'][0]['correct_options'], [1])
        self.assertEqual(imported['questions'][1]['type'], 'int')
        self.assertEqual(imported['questions'][2]['correct_answer'], 'good, awesome | range(5:10)')
        self.assertEqual(imported['questions'][3]['correct_answer'], 'true')
        self.assertEqual(imported['questions'][4]['correct_answer'], 'false')
        self.assertEqual(imported['questions'][5]['type'], 'comp')
        self.assertIn('हिन्दी', imported['questions'][5]['text'])
        self.assertEqual(len(imported['questions'][5]['sub_questions']), 2)

    def test_word_import_service_strips_trailing_correct_incorrect_labels_from_options(self):
        upload = self.build_docx_upload(
            [
                'Question',
                'Pick the correct statement',
                'Type',
                'multiple_choice',
                'Option',
                'First option',
                'incorrect.',
                'Option',
                'Second option',
                'Correct',
                'Option',
                'Third option',
                'incorrect)',
                'Marks',
                '4',
                '1',
            ],
            name='status-strip.docx',
        )

        imported = word_import_service.import_questions_from_docx(upload)

        self.assertEqual(
            imported['questions'][0]['options'],
            ['First option', 'Second option', 'Third option'],
        )
        self.assertEqual(imported['questions'][0]['correct_options'], [1])

    def test_word_import_service_parses_full_test_exam_format(self):
        upload = self.build_docx_upload(
            [
                'THE RANKERS ACADEMY',
                'FULL TEST - 09 (PCM)',
                'Date: 19/04/2026',
                'TIME: 3Hr.',
                'PHYSICS',
                '1. Physics question one?',
                '(a) Alpha',
                '(b) Beta',
                '(c) Gamma',
                '(d) Delta',
                'CHEMISTRY',
                '26. Chemistry question two?',
                '(a) First (b) Second',
                '(c) Third (d) Fourth',
                'MATHEMATICS',
                'MULTIPLE CHOICE QUESTIONS',
                '51. Mathematics question three?',
                '(a) 10',
                '(b) 20',
                '(c) 30',
                '(d) 40',
                'NUMERICAL TYPE QUESTIONS',
                '71. Mathematics numerical question?',
            ],
            name='full-test-09.docx',
        )

        imported = word_import_service.import_questions_from_docx(upload)

        self.assertEqual(imported['test_name'], 'FULL TEST - 09 (PCM)')
        self.assertEqual(imported['duration_hours'], 3)
        self.assertEqual(imported['duration_minutes'], 0)
        self.assertEqual(len(imported['sections']), 3)
        self.assertEqual([section['name'] for section in imported['sections']], ['Physics', 'Chemistry', 'Mathematics'])
        self.assertEqual(imported['sections'][0]['questions'][0]['type'], 'mcq')
        self.assertEqual(
            imported['sections'][0]['questions'][0]['options'],
            ['Alpha', 'Beta', 'Gamma', 'Delta'],
        )
        self.assertEqual(imported['sections'][1]['questions'][0]['options'][1], 'Second')
        self.assertEqual(imported['sections'][2]['questions'][0]['type'], 'mcq')
        self.assertEqual(imported['sections'][2]['questions'][1]['type'], 'int')
        self.assertTrue(imported['warnings'])

    def test_word_import_service_parses_class_test_title_and_biology_section(self):
        upload = self.build_docx_upload(
            [
                'THE RANKERS ACADEMY',
                'NEET/JEE (Main & Advance)/ MHTCET/11th + 12th (CBSE/STATE)',
                'Class Test - 02 (PCMB)',
                'Batch: ALPHA BATCH Session: 202527',
                'Date: 19/02/2026',
                'TIME :45 Min.',
                'PHYSICS',
                '1. Physics question?',
                '(a) A',
                '(b) B',
                '(c) C',
                '(d) D',
                'CHEMISTRY',
                '11. Chemistry question?',
                '(a) A1',
                '(b) B1',
                '(c) C1',
                '(d) D1',
                'BIOLOGY',
                '21. Biology question?',
                '(a) A2',
                '(b) B2',
                '(c) C2',
                '(d) D2',
                'MATHEMATICS',
                '21. Mathematics question?',
                '(a) A3',
                '(b) B3',
                '(c) C3',
                '(d) D3',
            ],
            name='alpha-batch-test-02-pcmb.docx',
        )

        imported = word_import_service.import_questions_from_docx(upload)

        self.assertEqual(imported['test_name'], 'Class Test - 02 (PCMB)')
        self.assertEqual(imported['section_name'], 'Class Test - 02 (PCMB)')
        self.assertEqual(imported['duration_hours'], 0)
        self.assertEqual(imported['duration_minutes'], 45)
        self.assertEqual(
            [section['name'] for section in imported['sections']],
            ['Physics', 'Chemistry', 'Biology', 'Mathematics'],
        )
        self.assertEqual(len(imported['sections'][2]['questions']), 1)
        self.assertEqual(imported['sections'][2]['questions'][0]['options'][2], 'C2')

    def test_word_import_service_parses_online_test_minimal_table_format(self):
        upload = self.build_docx_upload_with_body_items(
            [
                {'type': 'paragraph', 'text': 'VECTOR ADDITION - ONLINE TEST'},
                {
                    'type': 'paragraph',
                    'text': '10 Single-Correct MCQs - Each question is followed by its answer',
                },
                {
                    'type': 'paragraph',
                    'text': 'Two forces of magnitudes 8 N and 15 N act at a point. Their resultant has magnitude 17 N. The angle between the two forces is',
                },
                {'type': 'table', 'cells': ['Q1.', 'Resultant Magnitude']},
                {'type': 'table', 'cells': ['(A) 0°', '(B) 45°', '(C) 90°', '(D) 180°']},
                {'type': 'table', 'cells': ['Answer: (C) 90°']},
                {
                    'type': 'paragraph',
                    'text': 'Two equal forces of magnitude F act on a body. The angle between them is 120°. The magnitude of the resultant is',
                },
                {'type': 'table', 'cells': ['Q2.', 'Equal Forces - Parallelogram Law']},
                {'type': 'table', 'cells': ['(A) F/2', '(B) F', '(C) F√2', '(D) F√3']},
                {'type': 'table', 'cells': ['Answer: (B) F']},
            ],
            name='vector-addition-online-test-minimal.docx',
        )

        imported = word_import_service.import_questions_from_docx(upload)

        self.assertEqual(imported['test_name'], 'VECTOR ADDITION - ONLINE TEST')
        self.assertEqual(imported['section_name'], 'VECTOR ADDITION - ONLINE TEST')
        self.assertEqual(len(imported['sections']), 1)
        self.assertEqual(len(imported['sections'][0]['questions']), 2)
        self.assertEqual(imported['sections'][0]['questions'][0]['type'], 'mcq')
        self.assertIn('Two forces of magnitudes 8 N and 15 N', imported['sections'][0]['questions'][0]['text'])
        self.assertEqual(
            imported['sections'][0]['questions'][0]['options'],
            ['0°', '45°', '90°', '180°'],
        )
        self.assertEqual(imported['sections'][0]['questions'][0]['correct_options'], [2])
        self.assertEqual(imported['sections'][0]['questions'][1]['correct_options'], [1])
        self.assertFalse(imported['warnings'])

    def test_word_import_service_parses_online_test_options_answer_and_next_label_in_same_table(self):
        upload = self.build_docx_upload_with_body_items(
            [
                {'type': 'paragraph', 'text': 'CURRENT ELECTRICITY - ONLINE TEST'},
                {
                    'type': 'paragraph',
                    'text': '50 Single-Correct MCQs - Each question is followed by its answer',
                },
                {'type': 'table', 'cells': ['Q1.', '']},
                {'type': 'paragraph', 'text': 'First current electricity question?'},
                {
                    'type': 'table',
                    'cells': [
                        '(A) One',
                        '(B) Two',
                        '(C) Three',
                        '(D) Four',
                        'Answer: (C) Three',
                        'Q2.',
                    ],
                },
                {'type': 'paragraph', 'text': 'Second current electricity question?'},
                {
                    'type': 'table',
                    'cells': [
                        '(A) Red',
                        '(B) Blue',
                        '(C) Green',
                        '(D) Yellow',
                        'Answer: (B) Blue',
                    ],
                },
            ],
            name='current-electricity-online-test.docx',
        )

        imported = word_import_service.import_questions_from_docx(upload)

        questions = imported['sections'][0]['questions']
        self.assertEqual(len(questions), 2)
        self.assertIn('First current electricity question', questions[0]['text'])
        self.assertEqual(questions[0]['options'], ['One', 'Two', 'Three', 'Four'])
        self.assertEqual(questions[0]['correct_options'], [2])
        self.assertIn('Second current electricity question', questions[1]['text'])
        self.assertEqual(questions[1]['options'], ['Red', 'Blue', 'Green', 'Yellow'])
        self.assertEqual(questions[1]['correct_options'], [1])
        self.assertFalse(imported['warnings'])


class ScholarshipSectionApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.test_one = ScholarshipTest.objects.create(
            name='Test One',
            status='draft',
            duration_hours=0,
            duration_minutes=30,
        )
        self.test_two = ScholarshipTest.objects.create(
            name='Test Two',
            status='draft',
            duration_hours=0,
            duration_minutes=30,
        )

    def test_save_section_allows_same_name_in_different_tests(self):
        ScholarshipTestSection.objects.create(
            test=self.test_one,
            name='Mathematics',
            order=0,
        )

        response = self.client.post(
            reverse('scholarship_test:api_save_section', args=[self.test_two.id]),
            data=json.dumps({
                'name': 'Mathematics',
                'allowSwitching': True,
                'instructions': 'Test two instructions',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ScholarshipTestSection.objects.filter(test=self.test_one, name='Mathematics').count(),
            1,
        )
        self.assertEqual(
            ScholarshipTestSection.objects.filter(test=self.test_two, name='Mathematics').count(),
            1,
        )

    def test_bulk_save_prefers_existing_same_name_section_when_client_id_is_stale(self):
        target_section = ScholarshipTestSection.objects.create(
            test=self.test_two,
            name='Mathematics',
            order=0,
            allow_switching=False,
            instructions='Old instructions',
        )
        other_section = ScholarshipTestSection.objects.create(
            test=self.test_two,
            name='Science',
            order=1,
            allow_switching=False,
            instructions='Science instructions',
        )

        response = self.client.post(
            reverse('scholarship_test:api_save_section', args=[self.test_two.id]),
            data=json.dumps({
                'id': other_section.id,
                'name': 'Mathematics',
                'allowSwitching': True,
                'instructions': 'Updated from bulk save',
                'preferExistingByName': True,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        target_section.refresh_from_db()
        other_section.refresh_from_db()
        self.assertEqual(target_section.instructions, 'Updated from bulk save')
        self.assertTrue(target_section.allow_switching)
        self.assertEqual(other_section.name, 'Science')

    def test_direct_rename_still_rejects_duplicate_section_names_in_same_test(self):
        ScholarshipTestSection.objects.create(
            test=self.test_two,
            name='Mathematics',
            order=0,
        )
        other_section = ScholarshipTestSection.objects.create(
            test=self.test_two,
            name='Science',
            order=1,
        )

        response = self.client.post(
            reverse('scholarship_test:api_save_section', args=[self.test_two.id]),
            data=json.dumps({
                'id': other_section.id,
                'name': 'Mathematics',
                'allowSwitching': True,
                'instructions': '',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()['error'],
            'A section with this name already exists in this test',
        )


class ScholarshipCreateTestApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_create_test_persists_selected_date_and_start_time(self):
        response = self.client.post(
            reverse('scholarship_test:api_create_test'),
            data=json.dumps(
                {
                    'name': 'Scheduled Mock Test',
                    'duration_hours': 1,
                    'duration_minutes': 30,
                    'test_date': '2026-05-20',
                    'test_start_time': '09:15',
                    'batch': 'Star 01',
                    'stream': 'NEET',
                    'tags': 'mock, jee',
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        created_test = ScholarshipTest.objects.get(id=payload['test']['id'])
        self.assertEqual(created_test.date.isoformat(), '2026-05-20')
        self.assertIsNotNone(created_test.scheduled_start_at)
        self.assertEqual(created_test.batch, 'Star 01')
        self.assertEqual(created_test.stream, 'NEET')
        local_start = timezone.localtime(
            created_test.scheduled_start_at,
            test_service.ACADEMY_TIMEZONE,
        )
        self.assertEqual(local_start.date().isoformat(), '2026-05-20')
        self.assertEqual(local_start.strftime('%H:%M'), '09:15')

    def test_get_test_details_returns_batch_and_stream(self):
        test = ScholarshipTest.objects.create(
            name='Scoped Test',
            batch='Alpha',
            stream='JEE',
            duration_hours=1,
            duration_minutes=0,
        )
        ScholarshipTestConfig.objects.create(test=test)

        response = self.client.get(
            reverse('scholarship_test:api_get_test_details', args=[test.id])
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['test']['batch'], 'Alpha')
        self.assertEqual(payload['test']['stream'], 'JEE')

    def test_save_test_details_updates_scheduled_start_and_test_date(self):
        test = ScholarshipTest.objects.create(
            name='Timing Test',
            date=timezone.datetime(2026, 5, 20).date(),
            duration_hours=1,
            duration_minutes=0,
        )
        ScholarshipTestConfig.objects.create(test=test)

        response = self.client.post(
            reverse('scholarship_test:api_save_test_details', args=[test.id]),
            data=json.dumps(
                {
                    'scheduled_start_at': '2026-05-25T08:45',
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        test.refresh_from_db()
        self.assertIsNotNone(test.scheduled_start_at)
        local_start = timezone.localtime(
            test.scheduled_start_at,
            test_service.ACADEMY_TIMEZONE,
        )
        self.assertEqual(local_start.date().isoformat(), '2026-05-25')
        self.assertEqual(local_start.strftime('%H:%M'), '08:45')
        self.assertEqual(test.date.isoformat(), '2026-05-25')

    def test_save_test_details_returns_saved_duration_payload(self):
        test = ScholarshipTest.objects.create(
            name='Duration Test',
            duration_hours=0,
            duration_minutes=30,
        )
        ScholarshipTestConfig.objects.create(test=test)

        response = self.client.post(
            reverse('scholarship_test:api_save_test_details', args=[test.id]),
            data=json.dumps(
                {
                    'duration_hours': 0,
                    'duration_minutes': 20,
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['test']['duration_hours'], 0)
        self.assertEqual(payload['test']['duration_minutes'], 20)


@override_settings(ROOT_URLCONF="sds_main.urls")
class PortalStudentScheduledTestFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="student-star01",
            email="student-star01@example.com",
            password="StudentPass@2026",
        )
        self.portal_student = Student.objects.create(
            user=self.user,
            student_name="Portal Student",
            username="student-star01",
            contact="9876500001",
            email="student-star01@example.com",
            school="Rankers School",
            stream="JEE",
            board="CBSE",
            grade="11th",
            batch="Star 01",
            gender="Male",
        )
        self.scholarship_student = ScholarshipStudent.objects.create(
            name=self.portal_student.student_name,
            phone_number=self.portal_student.contact,
            grade=self.portal_student.grade,
            board=self.portal_student.board,
            otp_verified=True,
        )

    def create_runtime_test(
        self,
        *,
        name="Portal Scheduled Test",
        batch="Star 01",
        stream="JEE",
        scheduled_start_at=None,
    ):
        if scheduled_start_at is None:
            scheduled_start_at = timezone.now() - timedelta(minutes=5)

        test = ScholarshipTest.objects.create(
            name=name,
            date=timezone.localtime(scheduled_start_at).date(),
            status="published",
            duration_hours=0,
            duration_minutes=30,
            batch=batch,
            stream=stream,
            scheduled_start_at=scheduled_start_at,
        )
        ScholarshipTestConfig.objects.create(test=test)
        section = ScholarshipTestSection.objects.create(
            test=test,
            name="Mathematics",
            order=0,
        )
        question = ScholarshipTestQuestion.objects.create(
            section=section,
            question_type="mcq",
            question_text="2 + 2 = ?",
            order=0,
            pos_marks=2,
            neg_marks=1,
            neg_unattempted=0,
        )
        for index, option_text in enumerate(["3", "4", "5", "6"]):
            ScholarshipTestOption.objects.create(
                question=question,
                option_text=option_text,
                is_correct=index == 1,
                order=index,
            )
        return test

    def create_runtime_test_with_sections(
        self,
        *,
        name="Portal Multi Subject Test",
        batch="Star 01",
        stream="JEE",
        scheduled_start_at=None,
        section_names=None,
        marks_per_question=10,
    ):
        if scheduled_start_at is None:
            scheduled_start_at = timezone.now() - timedelta(minutes=5)
        if section_names is None:
            section_names = ["Physics", "Chemistry", "Biology"]

        test = ScholarshipTest.objects.create(
            name=name,
            date=timezone.localtime(scheduled_start_at).date(),
            status="published",
            duration_hours=0,
            duration_minutes=30,
            batch=batch,
            stream=stream,
            scheduled_start_at=scheduled_start_at,
        )
        ScholarshipTestConfig.objects.create(test=test)

        questions = []
        for index, section_name in enumerate(section_names):
            section = ScholarshipTestSection.objects.create(
                test=test,
                name=section_name,
                order=index,
            )
            question = ScholarshipTestQuestion.objects.create(
                section=section,
                question_type="mcq",
                question_text=f"{section_name} question",
                order=0,
                pos_marks=marks_per_question,
                neg_marks=0,
                neg_unattempted=0,
            )
            for option_index, option_text in enumerate(["A", "B", "C", "D"]):
                ScholarshipTestOption.objects.create(
                    question=question,
                    option_text=option_text,
                    is_correct=option_index == 1,
                    order=option_index,
                )
            questions.append(question)

        return test, questions

    def test_my_tests_payload_only_uses_tests_assigned_to_student_batch_and_stream(self):
        now = timezone.now()
        completed_match = self.create_runtime_test(
            name="Star 01 JEE Completed",
            batch="Star 01",
            stream="JEE",
            scheduled_start_at=now - timedelta(hours=2),
        )
        upcoming_match = self.create_runtime_test(
            name="Star 01 JEE Upcoming",
            batch="Star 01",
            stream="JEE",
            scheduled_start_at=now + timedelta(minutes=5),
        )
        self.create_runtime_test(
            name="Star 02 NEET Upcoming",
            batch="Star 02",
            stream="NEET",
            scheduled_start_at=now + timedelta(minutes=8),
        )

        ScholarshipTestAttempt.objects.create(
            student=self.scholarship_student,
            portal_student=self.portal_student,
            test=completed_match,
            status="completed",
            score=2,
            total_questions=1,
            total_marks=2,
            test_completed_at=now - timedelta(hours=1, minutes=20),
        )

        payload = _build_my_tests_payload(self.portal_student)

        self.assertEqual(
            [item["external_id"] for item in payload["completedTests"]],
            [completed_match.id],
        )
        self.assertTrue(payload.get("serverNow"))
        self.assertEqual(payload["upcomingTest"]["external_id"], upcoming_match.id)
        self.assertEqual(payload["upcomingTest"]["name"], "Star 01 JEE Upcoming")
        self.assertTrue(payload["upcomingTest"].get("launchWindowOpensAt"))

    def test_my_tests_payload_includes_completed_assigned_tests_without_student_attempt(self):
        now = timezone.now()
        previous_test = self.create_runtime_test(
            name="Star 01 JEE Previous",
            batch="Star 01",
            stream="JEE",
            scheduled_start_at=now - timedelta(hours=5),
        )
        recent_test = self.create_runtime_test(
            name="Star 01 JEE Recent",
            batch="Star 01",
            stream="JEE",
            scheduled_start_at=now - timedelta(hours=3),
        )

        peer_user = User.objects.create_user(
            username="student-star01-peer",
            email="student-star01-peer@example.com",
            password="StudentPass@2026",
        )
        peer_portal_student = Student.objects.create(
            user=peer_user,
            student_name="Peer Student",
            username="student-star01-peer",
            contact="9876500002",
            email="student-star01-peer@example.com",
            school="Rankers School",
            stream="JEE",
            board="CBSE",
            grade="11th",
            batch="Star 01",
            gender="Male",
        )
        peer_scholarship_student = ScholarshipStudent.objects.create(
            name=peer_portal_student.student_name,
            phone_number=peer_portal_student.contact,
            grade=peer_portal_student.grade,
            board=peer_portal_student.board,
            otp_verified=True,
        )
        outsider_user = User.objects.create_user(
            username="student-star02-neet",
            email="student-star02-neet@example.com",
            password="StudentPass@2026",
        )
        outsider_portal_student = Student.objects.create(
            user=outsider_user,
            student_name="Outsider Student",
            username="student-star02-neet",
            contact="9876500003",
            email="student-star02-neet@example.com",
            school="Rankers School",
            stream="NEET",
            board="CBSE",
            grade="11th",
            batch="Star 02",
            gender="Male",
        )
        outsider_scholarship_student = ScholarshipStudent.objects.create(
            name=outsider_portal_student.student_name,
            phone_number=outsider_portal_student.contact,
            grade=outsider_portal_student.grade,
            board=outsider_portal_student.board,
            otp_verified=True,
        )

        ScholarshipTestAttempt.objects.create(
            student=peer_scholarship_student,
            portal_student=peer_portal_student,
            test=previous_test,
            status="completed",
            score=1,
            total_questions=1,
            total_marks=2,
            test_completed_at=now - timedelta(hours=4, minutes=20),
        )
        ScholarshipTestAttempt.objects.create(
            student=peer_scholarship_student,
            portal_student=peer_portal_student,
            test=recent_test,
            status="completed",
            score=2,
            total_questions=1,
            total_marks=2,
            test_completed_at=now - timedelta(hours=2, minutes=20),
        )
        ScholarshipTestAttempt.objects.create(
            student=outsider_scholarship_student,
            portal_student=outsider_portal_student,
            test=recent_test,
            status="completed",
            score=2,
            total_questions=1,
            total_marks=2,
            test_completed_at=now - timedelta(hours=2, minutes=10),
        )

        payload = _build_my_tests_payload(self.portal_student)

        self.assertEqual(
            [item["external_id"] for item in payload["completedTests"]],
            [previous_test.id, recent_test.id],
        )
        self.assertEqual([item["attempted"] for item in payload["completedTests"]], [False, False])
        self.assertEqual([item["attemptId"] for item in payload["completedTests"]], [None, None])
        self.assertEqual(payload["completedTests"][1]["totalStudents"], 2)
        self.assertEqual(
            {item["studentId"] for item in payload["completedTests"][1]["leaderboard"]},
            {
                f"portal-{self.portal_student.id}",
                f"portal-{peer_portal_student.id}",
            },
        )
        self.assertEqual(
            payload["completedTests"][1]["leaderboard"][0]["studentId"],
            f"portal-{peer_portal_student.id}",
        )
        self.assertEqual(payload["completedTests"][1]["leaderboard"][1]["score"], 0)
        self.assertFalse(
            any(
                item["studentId"] == f"portal-{outsider_portal_student.id}"
                for item in payload["completedTests"][1]["leaderboard"]
            )
        )
        self.assertEqual(payload["rewards"]["xp"], 0)

    def test_attempt_leaderboard_exposes_section_names_and_batch_ranks(self):
        now = timezone.now()
        test, questions = self.create_runtime_test_with_sections(
            name="Leaderboard Sections Test",
            scheduled_start_at=now - timedelta(hours=2),
        )

        peer_user = User.objects.create_user(
            username="student-star01-batchmate",
            email="student-star01-batchmate@example.com",
            password="StudentPass@2026",
        )
        peer_portal_student = Student.objects.create(
            user=peer_user,
            student_name="Batch Mate",
            username="student-star01-batchmate",
            contact="9876500006",
            email="student-star01-batchmate@example.com",
            school="Rankers School",
            stream="JEE",
            board="CBSE",
            grade="11th",
            batch="Star 01",
            gender="Male",
        )
        peer_scholarship_student = ScholarshipStudent.objects.create(
            name=peer_portal_student.student_name,
            phone_number=peer_portal_student.contact,
            grade=peer_portal_student.grade,
            board=peer_portal_student.board,
            otp_verified=True,
        )

        first_attempt = ScholarshipTestAttempt.objects.create(
            student=peer_scholarship_student,
            portal_student=peer_portal_student,
            test=test,
            status="completed",
            score=30,
            total_questions=3,
            total_marks=30,
            test_completed_at=now - timedelta(hours=1, minutes=30),
        )
        second_attempt = ScholarshipTestAttempt.objects.create(
            student=self.scholarship_student,
            portal_student=self.portal_student,
            test=test,
            status="completed",
            score=20,
            total_questions=3,
            total_marks=30,
            test_completed_at=now - timedelta(hours=1, minutes=20),
        )

        for question in questions:
            ScholarshipTestAnswer.objects.create(
                attempt=first_attempt,
                question=question,
                selected_option=question.options.get(is_correct=True),
                is_correct=True,
                marks_awarded=question.pos_marks,
            )

        for question in questions[:2]:
            ScholarshipTestAnswer.objects.create(
                attempt=second_attempt,
                question=question,
                selected_option=question.options.get(is_correct=True),
                is_correct=True,
                marks_awarded=question.pos_marks,
            )

        leaderboard = _build_attempt_leaderboard(test)

        self.assertEqual(
            [item["sectionName"] for item in leaderboard["entries"][0]["sectionScores"]],
            ["Physics", "Chemistry", "Biology"],
        )
        self.assertEqual(
            [item["batchRank"] for item in leaderboard["entries"][:2]],
            [1, 2],
        )
        self.assertEqual(leaderboard["entries"][0]["total"], 30)

    def test_analysis_dataset_uses_actual_marks_for_subjects_and_total(self):
        now = timezone.now()
        test, questions = self.create_runtime_test_with_sections(
            name="Analysis Marks Test",
            scheduled_start_at=now - timedelta(hours=2),
        )

        attempt = ScholarshipTestAttempt.objects.create(
            student=self.scholarship_student,
            portal_student=self.portal_student,
            test=test,
            status="completed",
            score=20,
            total_questions=3,
            total_marks=30,
            test_completed_at=now - timedelta(hours=1, minutes=10),
        )

        for question in questions[:2]:
            ScholarshipTestAnswer.objects.create(
                attempt=attempt,
                question=question,
                selected_option=question.options.get(is_correct=True),
                is_correct=True,
                marks_awarded=question.pos_marks,
            )

        scores, _, _ = _build_analysis_dataset_for_test(test)
        current_row = next(row for row in scores if row["studentId"] == f"portal-{self.portal_student.id}")

        self.assertEqual(current_row["Physics"], 10)
        self.assertEqual(current_row["Chemistry"], 10)
        self.assertEqual(current_row["Biology"], 0)
        self.assertEqual(current_row["total"], 20)
        self.assertEqual(current_row["totalMarks"], 30)
        self.assertTrue(current_row["attempted"])

    def test_launch_view_redirects_logged_in_portal_student_to_dashboard_for_rtse_test(self):
        test = self.create_runtime_test(
            name="RTSE-2026 Scholarship Test",
            batch="Star 01",
            stream="JEE",
            scheduled_start_at=timezone.now() - timedelta(minutes=5),
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("scholarship_test:scholarship_launch_test", args=[test.id])
        )

        self.assertRedirects(response, reverse("scholarship_test:scholarship_dashboard"))
        self.assertEqual(
            self.client.session.get("scholarship_selected_test_id"),
            test.id,
        )
        self.assertTrue(self.client.session.get("scholarship_student_id"))

    def test_launch_view_rejects_mismatched_portal_student_assignment(self):
        test = self.create_runtime_test(
            name="Weekly NEET Mock",
            batch="Star 02",
            stream="NEET",
            scheduled_start_at=timezone.now() - timedelta(minutes=5),
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("scholarship_test:scholarship_launch_test", args=[test.id])
        )

        self.assertRedirects(response, reverse("my_tests"))
        messages = list(response.wsgi_request._messages)
        self.assertTrue(
            any("not assigned to your batch and stream" in str(message) for message in messages)
        )

    def test_start_test_blocks_manual_session_tampering_for_unassigned_test(self):
        test = self.create_runtime_test(
            name="Weekly NEET Mock",
            batch="Star 02",
            stream="NEET",
            scheduled_start_at=timezone.now() - timedelta(minutes=5),
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["scholarship_selected_test_id"] = test.id
        session.save()

        response = self.client.get(reverse("scholarship_test:scholarship_start_test"))

        self.assertRedirects(response, reverse("my_tests"))
