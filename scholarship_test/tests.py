import json
import io
from zipfile import ZipFile
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

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

    def add_mcq_question(self, section, *, text='2 + 2 = ?', correct_index=1):
        question = ScholarshipTestQuestion.objects.create(
            section=section,
            question_type='mcq',
            question_text=text,
            order=0,
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

    def test_submit_runtime_test_scores_builder_questions(self):
        runtime_test, section = self.create_runtime_test()
        mcq = self.add_mcq_question(section)
        fitb = ScholarshipTestQuestion.objects.create(
            section=section,
            question_type='fitb',
            question_text='Capital of France is ______.',
            order=1,
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
        self.assertEqual(updated_attempt.score, 2)
        self.assertEqual(updated_attempt.total_questions, 2)
        self.assertEqual(updated_attempt.test_id, runtime_test.id)

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
