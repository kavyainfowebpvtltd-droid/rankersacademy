import logging
import re
from datetime import datetime
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TOTAL_QUESTIONS = 20
TEST_DURATION_MINUTES = 20
SUPPORTED_RUNTIME_QUESTION_TYPES = {"mcq", "tf", "fitb", "int"}
ACADEMY_TIMEZONE = ZoneInfo("Asia/Kolkata")
UTC_TIMEZONE = ZoneInfo("UTC")


def calculate_score_percentage(score: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, round((score * 100) / total))


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


def _academy_localtime(value=None):
    if value is None:
        value = timezone.now()
    return timezone.localtime(value, ACADEMY_TIMEZONE)


def _normalize_scope_value(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _split_scope_values(raw_value) -> set[str]:
    values = set()
    for part in re.split(r"[,/&|]+", str(raw_value or "")):
        normalized = _normalize_scope_value(part)
        if normalized:
            values.add(normalized)
    return values


def get_portal_student_stream_values(portal_student) -> set[str]:
    if not portal_student:
        return set()

    stream_values = _split_scope_values(getattr(portal_student, "stream", ""))
    interested_exams = getattr(portal_student, "interested_exams", []) or []

    for exam in interested_exams:
        exam_text = str(exam or "")
        stream_values.update(_split_scope_values(exam_text))
        exam_upper = exam_text.upper()
        for stream_name in ("JEE", "NEET", "MHTCET"):
            if stream_name in exam_upper:
                stream_values.add(_normalize_scope_value(stream_name))

    return stream_values


def _fuzzy_norm(value) -> str:
    """Removes all whitespace and casefolds for robust comparison."""
    return re.sub(r"\s+", "", str(value or "").strip()).casefold()


def is_test_assigned_to_portal_student(test, portal_student) -> bool:
    if not test or not portal_student:
        return False

    # 1. Batch Check (Fuzzy and supports multiple comma-separated values)
    test_batch_raw = getattr(test, "batch", "")
    student_batch_raw = getattr(portal_student, "batch", "")

    test_batches = _split_scope_values(test_batch_raw)
    if test_batches:
        student_batches = _split_scope_values(student_batch_raw)
        
        # If student has no batch, they don't see batch-restricted tests
        if not student_batches:
            return False
            
        test_batch_fuzzy = {_fuzzy_norm(b) for b in test_batches}
        student_batch_fuzzy = {_fuzzy_norm(b) for b in student_batches}
        
        if test_batch_fuzzy.isdisjoint(student_batch_fuzzy):
            return False

    # 2. Stream Check (Fuzzy)
    test_stream_raw = getattr(test, "stream", "")
    test_streams = _split_scope_values(test_stream_raw)
    
    # If test has no stream restriction, anyone in the batch can see it
    if not test_streams:
        return True

    student_streams = get_portal_student_stream_values(portal_student)
    
    # If student has no stream values, we allow them to see the test 
    # to avoid "missing tests" issues when profiles are incomplete.
    if not student_streams:
        return True

    test_stream_fuzzy = {_fuzzy_norm(s) for s in test_streams}
    student_stream_fuzzy = {_fuzzy_norm(s) for s in student_streams}

    return not test_stream_fuzzy.isdisjoint(student_stream_fuzzy)


def get_test_scheduled_start_at(test):
    if not test or not getattr(test, "scheduled_start_at", None):
        return None

    start_at = _academy_localtime(test.scheduled_start_at)
    test_date = getattr(test, "date", None)
    if not test_date or start_at.date() == test_date:
        return start_at

    # Compatibility for rows created before academy-local scheduling was enforced.
    stored_utc_time = timezone.localtime(test.scheduled_start_at, UTC_TIMEZONE).time()
    corrected = datetime.combine(test_date, stored_utc_time)
    return timezone.make_aware(corrected, ACADEMY_TIMEZONE)


def get_test_launch_window(test):
    start_at = get_test_scheduled_start_at(test)
    if not start_at:
        return None, None, None

    end_at = start_at + timedelta(minutes=get_test_duration_minutes(test))
    launch_opens_at = start_at - timedelta(minutes=10)
    return start_at, end_at, launch_opens_at


def get_test_start_window(test):
    start_at = get_test_scheduled_start_at(test)
    if not start_at:
        return None, None, None

    end_at = start_at + timedelta(minutes=get_test_duration_minutes(test))
    start_button_opens_at = start_at - timedelta(minutes=1)
    return start_at, end_at, start_button_opens_at


def get_test_launch_state(test, now=None):
    if now is None:
        now = _academy_localtime()

    start_at, end_at, launch_opens_at = get_test_launch_window(test)
    if not start_at or not end_at or not launch_opens_at:
        return {
            "scheduled": False,
            "can_launch": True,
            "is_live": False,
            "has_ended": False,
            "message": "",
        }

    if now >= end_at:
        return {
            "scheduled": True,
            "can_launch": False,
            "is_live": False,
            "has_ended": True,
            "message": "This test window has closed.",
        }

    if now < launch_opens_at:
        return {
            "scheduled": True,
            "can_launch": False,
            "is_live": False,
            "has_ended": False,
            "message": "This test opens 10 minutes before the scheduled start time.",
        }

    return {
        "scheduled": True,
        "can_launch": True,
        "is_live": start_at <= now < end_at,
        "has_ended": False,
        "message": "",
    }


def get_test_start_state(test, now=None):
    if now is None:
        now = _academy_localtime()

    start_at, end_at, start_button_opens_at = get_test_start_window(test)
    if not start_at or not end_at or not start_button_opens_at:
        return {
            "scheduled": False,
            "can_start": True,
            "is_live": False,
            "has_ended": False,
            "message": "",
        }

    if now >= end_at:
        return {
            "scheduled": True,
            "can_start": False,
            "is_live": False,
            "has_ended": True,
            "message": "This test window has closed.",
        }

    if now < start_button_opens_at:
        return {
            "scheduled": True,
            "can_start": False,
            "is_live": False,
            "has_ended": False,
            "message": "The Start button activates 1 minute before the scheduled start time.",
        }

    return {
        "scheduled": True,
        "can_start": True,
        "is_live": start_at <= now < end_at,
        "has_ended": False,
        "message": "",
    }


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

    published_tests = queryset.filter(
        status='published',
        scheduled_start_at__isnull=False,
    ).order_by('scheduled_start_at', 'id')
    for test in published_tests:
        if not get_runtime_questions_for_test(test):
            continue
        if get_test_launch_state(test)["can_launch"]:
            return test

    unscheduled_published_tests = queryset.filter(
        status='published',
        scheduled_start_at__isnull=True,
    ).order_by('-created_at')
    for test in unscheduled_published_tests:
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


def get_attempt_end_time(attempt):
    runtime_test = get_runtime_test_for_attempt(attempt)
    time_limit = timedelta(minutes=get_test_duration_minutes(runtime_test))
    return attempt.test_started_at + time_limit


def get_answer_key_visibility_delay():
    hours = getattr(settings, 'ANSWER_KEY_VISIBILITY_DELAY_HOURS', 2)
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        hours = 2
    return timedelta(hours=max(0, hours))


def get_answer_key_base_end_time(attempt):
    runtime_test = get_runtime_test_for_attempt(attempt)
    if runtime_test and getattr(runtime_test, 'scheduled_start_at', None):
        return runtime_test.scheduled_start_at + timedelta(
            minutes=get_test_duration_minutes(runtime_test)
        )
    return get_attempt_end_time(attempt)


def get_answer_key_available_at(attempt):
    return get_answer_key_base_end_time(attempt) + get_answer_key_visibility_delay()


def is_answer_key_available(attempt, now=None):
    if now is None:
        now = timezone.now()
    return now >= get_answer_key_available_at(attempt)


def get_answer_key_delay_hours_display():
    delay = get_answer_key_visibility_delay()
    total_seconds = int(delay.total_seconds())
    if total_seconds % 3600 == 0:
        hours = total_seconds // 3600
        return f"{hours} hour" if hours == 1 else f"{hours} hours"

    minutes = total_seconds // 60
    return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"


def get_attempt_time_remaining_seconds(attempt) -> int:
    remaining = get_attempt_end_time(attempt) - timezone.now()
    return max(0, int(remaining.total_seconds()))


def is_attempt_expired(attempt) -> bool:
    return get_attempt_time_remaining_seconds(attempt) <= 0


def get_saved_progress(attempt):
    state = attempt.progress_state if isinstance(attempt.progress_state, dict) else {}
    answers = state.get('answers', {})
    if not isinstance(answers, dict):
        answers = {}

    current_question_index = state.get('current_question_index', 0)
    try:
        current_question_index = int(current_question_index)
    except (TypeError, ValueError):
        current_question_index = 0

    tab_switch_count = state.get('tab_switch_count', 0)
    try:
        tab_switch_count = int(tab_switch_count)
    except (TypeError, ValueError):
        tab_switch_count = 0

    return {
        'answers': answers,
        'current_question_index': max(0, current_question_index),
        'tab_switch_count': max(0, tab_switch_count),
        'saved_at': state.get('saved_at'),
    }


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


def _allowed_runtime_option_values(question):
    return {
        str(index)
        for index, _option in enumerate(question.options.all())
    }


def normalize_runtime_answer(question, submitted_answer):
    if question.question_type == 'mcq':
        allowed_values = _allowed_runtime_option_values(question)

        if question.is_multi_select:
            if submitted_answer in (None, ''):
                return []
            if not isinstance(submitted_answer, list):
                submitted_answer = [submitted_answer]

            cleaned_values = []
            seen_values = set()
            for value in submitted_answer:
                normalized_value = str(value).strip()
                if normalized_value in allowed_values and normalized_value not in seen_values:
                    cleaned_values.append(normalized_value)
                    seen_values.add(normalized_value)
            return cleaned_values

        if isinstance(submitted_answer, list):
            submitted_answer = submitted_answer[0] if submitted_answer else ''
        normalized_value = str(submitted_answer).strip() if submitted_answer is not None else ''
        return normalized_value if normalized_value in allowed_values else ''

    if question.question_type == 'tf':
        normalized_value = _normalize_text_answer(submitted_answer)
        if normalized_value == 'true':
            return 'True'
        if normalized_value == 'false':
            return 'False'
        return ''

    if question.question_type == 'fitb':
        return str(submitted_answer or '').strip()

    if question.question_type == 'int':
        normalized_integer = _normalize_integer_answer(submitted_answer)
        return '' if normalized_integer is None else str(normalized_integer)

    return submitted_answer


def normalize_runtime_answers(runtime_questions, submitted_answers):
    normalized_answers = {}
    raw_answers = submitted_answers if isinstance(submitted_answers, dict) else {}

    for question in runtime_questions:
        submitted_answer = raw_answers.get(str(question.id))
        if submitted_answer is None:
            submitted_answer = raw_answers.get(question.id)

        normalized_answers[str(question.id)] = normalize_runtime_answer(
            question,
            submitted_answer,
        )

    return normalized_answers


def is_runtime_answer_provided(question, selected_answer) -> bool:
    normalized_answer = normalize_runtime_answer(question, selected_answer)
    if question.question_type == 'mcq' and question.is_multi_select:
        return len(normalized_answer) > 0
    return normalized_answer not in (None, '')


@transaction.atomic
def save_runtime_test_progress(
    attempt_id: int,
    *,
    answers: dict,
    current_question_index: int = 0,
    tab_switch_count: int = 0,
):
    from scholarship_test.models import ScholarshipTestAttempt

    try:
        attempt = ScholarshipTestAttempt.objects.select_related(
            'student',
            'test',
        ).get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return False, "Test attempt not found", None

    if attempt.status in ['completed', 'expired']:
        return False, "Test already submitted", attempt

    runtime_test = get_runtime_test_for_attempt(attempt)
    runtime_questions = get_runtime_questions_for_test(runtime_test)
    if not runtime_test or not runtime_questions:
        return False, "No configured scholarship test is available", attempt

    if is_attempt_expired(attempt):
        return False, "Test time has expired", attempt

    normalized_answers = normalize_runtime_answers(runtime_questions, answers)

    try:
        current_question_index = int(current_question_index or 0)
    except (TypeError, ValueError):
        current_question_index = 0

    try:
        tab_switch_count = int(tab_switch_count or 0)
    except (TypeError, ValueError):
        tab_switch_count = 0

    attempt.progress_state = {
        'answers': normalized_answers,
        'current_question_index': max(0, current_question_index),
        'tab_switch_count': max(0, tab_switch_count),
        'saved_at': timezone.now().isoformat(),
    }
    if attempt.status == 'started':
        attempt.status = 'in_progress'
    attempt.save(update_fields=['progress_state', 'status'])
    return True, "Progress saved", attempt


def is_runtime_answer_correct(question, selected_answer) -> bool:
    selected_answer = normalize_runtime_answer(question, selected_answer)

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

    final_status = 'completed'
    if is_attempt_expired(attempt):
        final_status = 'expired'

    saved_progress = get_saved_progress(attempt)
    combined_answers = dict(saved_progress.get('answers', {}))
    combined_answers.update(answers if isinstance(answers, dict) else {})
    normalized_answers = normalize_runtime_answers(runtime_questions, combined_answers)
    correct_answers = 0
    score = 0
    total_marks = 0

    for question in runtime_questions:
        submitted_answer = normalized_answers.get(str(question.id))
        total_marks += int(question.pos_marks or 0)

        if is_runtime_answer_correct(question, submitted_answer):
            correct_answers += 1
            score += int(question.pos_marks or 0)
        elif is_runtime_answer_provided(question, submitted_answer):
            score -= int(question.neg_marks or 0)
        else:
            score -= int(question.neg_unattempted or 0)

    scholarship_percentage = calculate_scholarship_percentage(
        score, total_marks
    )

    attempt.score = score
    attempt.scholarship_percentage = scholarship_percentage
    attempt.test_completed_at = timezone.now()
    attempt.status = final_status
    attempt.total_questions = len(runtime_questions)
    attempt.total_marks = total_marks
    attempt.test = runtime_test
    attempt.progress_state = {
        'answers': normalized_answers,
        'current_question_index': max(0, len(runtime_questions) - 1),
        'tab_switch_count': saved_progress.get('tab_switch_count', 0),
        'saved_at': timezone.now().isoformat(),
        'submitted_at': timezone.now().isoformat(),
        'correct_answers': correct_answers,
    }
    attempt.save()

    sms_sent = False
    sms_error = None
    if requires_otp_login(attempt.test):
        try:
            sms_sent, sms_error = _send_attempt_result_sms(
                attempt=attempt,
                score=score,
                total_questions=total_marks,
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
    from scholarship_test.models import ScholarshipTestAttempt

    try:
        attempt = ScholarshipTestAttempt.objects.get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return False, "Test attempt not found", None

    saved_progress = get_saved_progress(attempt)
    return submit_runtime_test(attempt_id, saved_progress.get('answers', {}))


def finalize_expired_attempts(selected_test=None):
    from scholarship_test.models import ScholarshipTestAttempt

    attempts = ScholarshipTestAttempt.objects.select_related(
        'student',
        'test',
    ).filter(
        status__in=['started', 'in_progress']
    ).order_by('test_started_at')

    if selected_test:
        attempts = attempts.filter(test=selected_test)

    finalized_attempts = []
    for attempt in attempts:
        if not is_attempt_expired(attempt):
            continue

        runtime_test = get_runtime_test_for_attempt(attempt)
        runtime_questions = get_runtime_questions_for_test(runtime_test)
        if runtime_test and runtime_questions:
            success, _message, updated_attempt = auto_submit_runtime_test(attempt.id)
        else:
            success, _message, updated_attempt = auto_submit_expired_test(attempt.id)

        if success and updated_attempt:
            finalized_attempts.append(updated_attempt)

    return finalized_attempts


def get_test_leaderboard(test, current_attempt=None, limit: int = 5):
    from scholarship_test.models import ScholarshipTestAttempt

    if not test:
        return {
            'top_entries': [],
            'current_entry': None,
        }

    attempts = ScholarshipTestAttempt.objects.select_related('student').filter(
        test=test,
        status__in=['completed', 'expired'],
    ).order_by('-score', 'test_completed_at', 'test_started_at', 'id')

    leaderboard_entries = []
    current_entry = None

    for index, attempt in enumerate(attempts, start=1):
        entry = {
            'rank': index,
            'attempt_id': attempt.id,
            'student_name': attempt.student.name,
            'score': attempt.score,
            'total_marks': attempt.total_marks,
            'is_current_student': bool(current_attempt and attempt.id == current_attempt.id),
        }
        leaderboard_entries.append(entry)

        if current_attempt and attempt.id == current_attempt.id:
            current_entry = entry

    return {
        'top_entries': leaderboard_entries[:limit],
        'current_entry': current_entry,
    }


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
    score_percentage = calculate_score_percentage(score, total)

    if score_percentage == 100:
        return 50
    elif score_percentage >= 90:
        return 45
    elif score_percentage >= 80:
        return 40
    elif score_percentage >= 70:
        return 35
    elif score_percentage >= 60:
        return 30
    elif score_percentage >= 50:
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
    
    return is_attempt_expired(attempt)


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
        launch_state = get_test_launch_state(active_test)
        if not launch_state["can_launch"]:
            return False, launch_state["message"] or "This test is not available right now"
        return True, "You can attempt the test"

    if not student.grade or not student.board:
        return False, "Please select your grade and board"

    # Legacy fallback while older question-bank data still exists.
    questions = get_test_questions(student.grade, student.board)
    if len(questions) < TOTAL_QUESTIONS:
        logger.warning(
            f"Insufficient questions for student {student.id}: "
            f"found {len(questions)}, need {TOTAL_QUESTIONS}"
        )

    return True, "You can attempt the test"
