import logging
import re
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

TOTAL_QUESTIONS = 20
TEST_DURATION_MINUTES = 20
SUPPORTED_RUNTIME_QUESTION_TYPES = {"mcq", "tf", "fitb", "int"}


def calculate_score_percentage(score: int, total: int) -> int:
    if total <= 0:
        return 0
    return round((score * 100) / total)


def _send_attempt_result_sms(attempt, score: int, total_questions: int, scholarship_percentage: int):
    from scholarship_test.services.sms_service import (
        send_scholarship_result_sms_dlt,
    )

    student = attempt.student
    if not student.phone_number:
        logger.error(f"Cannot send SMS: Student {student.id} has no phone number")
        return False, "No phone number on student record"

    if requires_otp_login(attempt.test):
        return send_scholarship_result_sms_dlt(
            phone_number=student.phone_number,
            student_name=student.name,
            score=score,
            total_questions=total_questions,
            scholarship_percentage=scholarship_percentage,
        )
    return False, None


def is_rtse_test(test) -> bool:
    if not test or not getattr(test, "name", ""):
        return False

    name_lower = test.name.lower()
    normalized = re.sub(r'[^a-z0-9]+', '', name_lower)
    return (
        ('rtse' in name_lower and '2026' in test.name)
        or normalized == 'rtse2026scholarshiptest'
    )


def is_scholarship_test(test) -> bool:
    if not test or not getattr(test, "name", ""):
        return False

    normalized = re.sub(r'[^a-z0-9]+', '', test.name.lower())
    return normalized == 'scholarshiptest'


def requires_otp_login(test) -> bool:
    return is_rtse_test(test) or is_scholarship_test(test)


def _get_test_queryset():
    from django.db.models import Prefetch
    from scholarship_test.models import (
        ScholarshipTest,
        ScholarshipTestQuestion,
        ScholarshipTestSection,
    )

    question_queryset = (
        ScholarshipTestQuestion.objects.filter(
            question_type__in=SUPPORTED_RUNTIME_QUESTION_TYPES
        )
        .prefetch_related('options', 'answers')
        .order_by('order', 'id')
    )

    section_queryset = ScholarshipTestSection.objects.prefetch_related(
        Prefetch('questions', queryset=question_queryset)
    ).order_by('order', 'id')

    return ScholarshipTest.objects.prefetch_related(
        Prefetch('sections', queryset=section_queryset),
        'config',
    )


def get_active_test():
    queryset = _get_test_queryset()

    published_tests = queryset.filter(status='published').order_by('-created_at')
    for test in published_tests:
        if get_runtime_questions_for_test(test):
            return test

    fallback_tests = queryset.order_by('-created_at')
    for test in fallback_tests:
        if get_runtime_questions_for_test(test):
            return test

    return None


def get_test_by_id(test_id):
    if not test_id:
        return None

    try:
        return _get_test_queryset().get(id=test_id)
    except Exception:
        return None


def get_launchable_tests():
    launchable_tests = []

    for test in _get_test_queryset().order_by('-created_at'):
        runtime_questions = get_runtime_questions_for_test(test)
        if runtime_questions:
            test.runtime_question_count = len(runtime_questions)
            launchable_tests.append(test)

    return launchable_tests


def get_runtime_questions_for_test(test):
    if not test:
        return []

    runtime_questions = []
    for section in test.sections.all():
        for question in section.questions.all():
            if question.question_type in SUPPORTED_RUNTIME_QUESTION_TYPES:
                runtime_questions.append(question)
    return runtime_questions


def get_runtime_test_for_attempt(attempt):
    if getattr(attempt, 'test_id', None):
        return attempt.test
    return get_active_test()


def get_test_duration_minutes(test) -> int:
    if not test:
        return TEST_DURATION_MINUTES

    duration_minutes = (int(test.duration_hours or 0) * 60) + int(
        test.duration_minutes or 0
    )
    return duration_minutes if duration_minutes > 0 else TEST_DURATION_MINUTES


def serialize_runtime_question(question, sequence):
    option_labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    payload = {
        'id': question.id,
        'sequence': sequence,
        'type': question.question_type,
        'question_html': question.question_text,
        'difficulty': question.difficulty,
        'pos_marks': question.pos_marks,
        'neg_marks': question.neg_marks,
        'neg_unattempted': question.neg_unattempted,
        'multi_select': question.is_multi_select,
        'section_name': question.section.name,
        'section_instructions': question.section.instructions,
        'options': [],
    }

    if question.question_type == 'mcq':
        payload['options'] = [
            {
                'value': str(index),
                'label': option_labels[index]
                if index < len(option_labels)
                else str(index + 1),
                'text_html': option.option_text,
            }
            for index, option in enumerate(question.options.all())
        ]
    elif question.question_type == 'tf':
        payload['options'] = [
            {'value': 'True', 'label': 'T', 'text_html': 'True'},
            {'value': 'False', 'label': 'F', 'text_html': 'False'},
        ]
    elif question.question_type == 'fitb':
        payload['input_placeholder'] = 'Type your answer'
    elif question.question_type == 'int':
        payload['input_placeholder'] = 'Enter an integer'

    return payload


def _normalize_text_answer(value):
    if value is None:
        return ''
    return ' '.join(str(value).strip().lower().split())


def _normalize_integer_answer(value):
    if value in (None, ''):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def is_runtime_answer_correct(question, selected_answer) -> bool:
    if question.question_type == 'mcq':
        correct_indexes = {
            str(index)
            for index, option in enumerate(question.options.all())
            if option.is_correct
        }

        if question.is_multi_select:
            if not isinstance(selected_answer, list):
                return False
            selected_indexes = {str(value) for value in selected_answer if value != ''}
            return bool(correct_indexes) and selected_indexes == correct_indexes

        if isinstance(selected_answer, list):
            selected_answer = selected_answer[0] if selected_answer else ''
        return str(selected_answer) in correct_indexes and len(correct_indexes) == 1

    answer = question.answers.first()
    if not answer:
        return False

    if question.question_type == 'tf':
        return _normalize_text_answer(selected_answer) == _normalize_text_answer(
            answer.correct_answer
        )

    if question.question_type == 'fitb':
        return _normalize_text_answer(selected_answer) == _normalize_text_answer(
            answer.correct_answer
        )

    if question.question_type == 'int':
        return _normalize_integer_answer(selected_answer) == _normalize_integer_answer(
            answer.correct_answer
        )

    return False


@transaction.atomic
def submit_runtime_test(attempt_id: int, answers: dict):
    from scholarship_test.models import ScholarshipTestAttempt

    try:
        attempt = ScholarshipTestAttempt.objects.select_related(
            'student',
            'test',
        ).get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return False, "Test attempt not found", None

    if attempt.status == 'completed':
        return False, "Test already submitted", attempt

    runtime_test = get_runtime_test_for_attempt(attempt)
    runtime_questions = get_runtime_questions_for_test(runtime_test)
    if not runtime_test or not runtime_questions:
        return False, "No configured scholarship test is available", attempt

    time_limit = timedelta(minutes=get_test_duration_minutes(runtime_test))
    final_status = 'completed'
    if timezone.now() > attempt.test_started_at + time_limit:
        final_status = 'expired'

    normalized_answers = answers if isinstance(answers, dict) else {}
    score = 0

    for question in runtime_questions:
        submitted_answer = normalized_answers.get(str(question.id))
        if submitted_answer is None:
            submitted_answer = normalized_answers.get(question.id)

        if is_runtime_answer_correct(question, submitted_answer):
            score += 1

    scholarship_percentage = calculate_scholarship_percentage(
        score, len(runtime_questions)
    )

    attempt.score = score
    attempt.scholarship_percentage = scholarship_percentage
    attempt.test_completed_at = timezone.now()
    attempt.status = final_status
    attempt.total_questions = len(runtime_questions)
    attempt.total_marks = len(runtime_questions)
    attempt.test = runtime_test
    attempt.save()

    sms_sent = False
    sms_error = None
    if requires_otp_login(attempt.test):
        try:
            sms_sent, sms_error = _send_attempt_result_sms(
                attempt=attempt,
                score=score,
                total_questions=len(runtime_questions),
                scholarship_percentage=scholarship_percentage,
            )
        except Exception as e:
            logger.error(f"Failed to send result SMS: {str(e)}", exc_info=True)
            sms_error = str(e)

    attempt.sms_sent = sms_sent
    attempt.sms_error = sms_error
    attempt.save(update_fields=['sms_sent', 'sms_error'])

    if final_status == 'expired':
        return True, "Test auto-submitted due to time expiry", attempt

    return True, "Test submitted successfully", attempt


def auto_submit_runtime_test(attempt_id: int):
    return submit_runtime_test(attempt_id, {})


def get_test_questions(grade: str, board: str, subject_id: int = None, count: int = TOTAL_QUESTIONS):

    from scholarship_test.models import ScholarshipQuestion
    
    # Normalize grade and board
    grade_normalized = normalize_grade(grade)
    board_normalized = normalize_board(board)
    
    queryset = ScholarshipQuestion.objects.filter(
        grade__icontains=grade_normalized,
        board__icontains=board_normalized,
        is_active=True
    )
    
   
    if subject_id:
        queryset = queryset.filter(subject_id=subject_id)
    
   
    available_count = queryset.count()
    
    if available_count < count:
        logger.warning(
            f"Insufficient questions available: {available_count} found, {count} requested. "
            f"Grade: {grade_normalized}, Board: {board_normalized}, Subject: {subject_id}"
        )
       
        questions = list(queryset.order_by('?'))
    else:
       
        questions = list(queryset.order_by('?')[:count])
    
    return questions


def calculate_scholarship_percentage(score: int, total: int = TOTAL_QUESTIONS) -> int:
   
   
    if score < 0:
        score = 0
    
    if score == 20:
        return 50
    elif score >= 18:
        return 45
    elif score >= 16:
        return 40
    elif score >= 14:
        return 35
    elif score >= 12:
        return 30
    elif score >= 10:
        return 25
    else:
        return 20 


@transaction.atomic
def submit_test(attempt_id: int, answers: dict):
   
    from scholarship_test.models import ScholarshipTestAttempt, ScholarshipStudentAnswer, ScholarshipQuestion
    
    # Get the attempt
    try:
        attempt = ScholarshipTestAttempt.objects.select_related('student').get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return False, "Test attempt not found", None
    
    # Check if already completed
    if attempt.status == 'completed':
        return False, "Test already submitted", attempt
    
    # Check if time has expired
    time_limit = timedelta(minutes=TEST_DURATION_MINUTES)
    if timezone.now() > attempt.test_started_at + time_limit:
        attempt.status = 'expired'
        attempt.save()
        return False, "Test time has expired", attempt
    
    # Calculate score
    score = 0
    total_questions = 0
    
    # Process each answer
    for question_id_str, selected_option in answers.items():
        try:
            question_id = int(question_id_str)
            question = ScholarshipQuestion.objects.get(id=question_id)
            total_questions += 1
            
            # Check if answer is correct
            is_correct = question.correct_answer == selected_option
            
            if is_correct:
                score += 1
            
            # Save the answer
            ScholarshipStudentAnswer.objects.create(
                attempt=attempt,
                question=question,
                selected_option=selected_option,
                is_correct=is_correct
            )
            
        except (ValueError, ScholarshipQuestion.DoesNotExist) as e:
            logger.error(f"Error processing answer for question {question_id_str}: {str(e)}")
            continue
    
    # Calculate scholarship percentage
    scholarship_percentage = calculate_scholarship_percentage(score, total_questions)
    
    # Update attempt with results
    attempt.score = score
    attempt.scholarship_percentage = scholarship_percentage
    attempt.test_completed_at = timezone.now()
    attempt.status = 'completed'
    attempt.total_questions = total_questions
    attempt.total_marks = total_questions
    attempt.save()
    
    sms_sent = False
    sms_error = None
    if requires_otp_login(attempt.test):
        try:
            sms_sent, sms_error = _send_attempt_result_sms(
                attempt=attempt,
                score=score,
                total_questions=total_questions,
                scholarship_percentage=scholarship_percentage,
            )
            logger.info(f"Result SMS sent: {sms_sent}, {sms_error}")
        except Exception as e:
            logger.error(f"Failed to send result SMS: {str(e)}", exc_info=True)
            sms_error = str(e)
    
    # Store SMS status in attempt for debugging
    attempt.sms_sent = sms_sent
    attempt.sms_error = sms_error
    attempt.save(update_fields=['sms_sent', 'sms_error'])
    
    return True, "Test submitted successfully", attempt


def check_test_expired(attempt_id: int) -> bool:
   
    from scholarship_test.models import ScholarshipTestAttempt
    
    try:
        attempt = ScholarshipTestAttempt.objects.get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return True 
    
    time_limit = timedelta(minutes=TEST_DURATION_MINUTES)
    return timezone.now() > attempt.test_started_at + time_limit


def auto_submit_expired_test(attempt_id: int):
   
    from scholarship_test.models import ScholarshipTestAttempt, ScholarshipStudentAnswer, ScholarshipQuestion
    
    try:
        attempt = ScholarshipTestAttempt.objects.select_related('student').get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return False, "Test attempt not found", None
    
    # Check if already completed
    if attempt.status in ['completed', 'expired']:
        return False, "Test already submitted", attempt
    
   
    existing_answer_ids = set(
        attempt.answers.values_list('question_id', flat=True)
    )
    
   
    student = attempt.student
    questions = get_test_questions(
        grade=student.grade,
        board=student.board,
        count=TOTAL_QUESTIONS
    )
    
  
    answers = {}
    for question in questions:
        if question.id not in existing_answer_ids:
            ScholarshipStudentAnswer.objects.create(
                attempt=attempt,
                question=question,
                selected_option='',
                is_correct=False
            )
        else:
           
            answer = attempt.answers.get(question_id=question.id)
            answers[str(question.id)] = answer.selected_option
    
   
    score = 0
    for answer in attempt.answers.all():
        if answer.is_correct:
            score += 1
    
    scholarship_percentage = calculate_scholarship_percentage(score, len(questions))
    
   
    attempt.score = score
    attempt.scholarship_percentage = scholarship_percentage
    attempt.test_completed_at = timezone.now()
    attempt.status = 'expired'
    attempt.total_questions = len(questions)
    attempt.save()
    
    
    sms_sent = False
    sms_error = None
    if requires_otp_login(attempt.test):
        try:
            sms_sent, sms_error = _send_attempt_result_sms(
                attempt=attempt,
                score=score,
                total_questions=len(questions),
                scholarship_percentage=scholarship_percentage,
            )
            logger.info(f"Result SMS sent for expired test: {sms_sent}, {sms_error}")
        except Exception as e:
            logger.error(f"Failed to send result SMS for expired test: {str(e)}", exc_info=True)
            sms_error = str(e)
    
    # Store SMS status
    attempt.sms_sent = sms_sent
    attempt.sms_error = sms_error
    attempt.save(update_fields=['sms_sent', 'sms_error', 'score', 'scholarship_percentage', 'test_completed_at', 'status', 'total_questions'])
    
    return True, "Test auto-submitted due to time expiry", attempt


def normalize_grade(grade: str) -> str:
   
    if not grade:
        return ""
    
    grade = str(grade).strip()
    
    return grade


def normalize_board(board: str) -> str:
    
    if not board:
        return ""
    
    board = str(board).strip().upper()
    
    if 'CBSE' in board:
        return 'CBSE'
    elif 'STATE' in board or 'SSC' in board or 'ICSE' in board:
        return board
    
    return board


def can_attempt_test(student, selected_test=None) -> tuple:
   
    # Check if OTP is verified
    if not student.otp_verified:
        return False, "Please verify your phone number first"
    
    # Check if student has name, grade, board
    if not student.name:
        return False, "Please complete your registration"
    
    if not student.grade or not student.board:
        return False, "Please select your grade and board"
    
    # Check if already completed a test
    from scholarship_test.models import ScholarshipTestAttempt
    completed_attempts = ScholarshipTestAttempt.objects.filter(
        student=student,
        status__in=['completed', 'expired']
    )

    if selected_test:
        completed_attempts = completed_attempts.filter(test=selected_test)

    completed_attempts = completed_attempts.exists()
    
    if completed_attempts:
        return False, "You have already completed the scholarship test"
    
    active_test = selected_test or get_active_test()
    if active_test:
        runtime_questions = get_runtime_questions_for_test(active_test)
        if not runtime_questions:
            return False, "No scholarship test questions are configured yet"
        return True, "You can attempt the test"

    # Legacy fallback while older question-bank data still exists.
    questions = get_test_questions(student.grade, student.board)
    if len(questions) < TOTAL_QUESTIONS:
        logger.warning(
            f"Insufficient questions for student {student.id}: "
            f"found {len(questions)}, need {TOTAL_QUESTIONS}"
        )

    return True, "You can attempt the test"
