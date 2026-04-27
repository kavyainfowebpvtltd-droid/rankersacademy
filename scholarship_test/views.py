import json
import logging
import re
from datetime import timedelta
from urllib.parse import urlencode
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone
from django.db import transaction, IntegrityError

from scholarship_test.models import (
    ScholarshipStudent,
    ScholarshipSubject,
    ScholarshipQuestion,
    ScholarshipTestAttempt,
    ScholarshipOTP,
    ScholarshipTestFolder,
    ScholarshipTest,
    ScholarshipTestConfig,
    ScholarshipTestSection,
    ScholarshipTestQuestion,
    ScholarshipTestOption,
    ScholarshipTestAnswer,
    ScholarshipTestImage,
)
from scholarship_test.forms import (
    ScholarshipRegistrationStepOneForm,
    ScholarshipRegistrationStepTwoForm,
    OTPVerificationForm
)
from scholarship_test.services import (
    otp_service,
    test_service,
    sms_service,
    word_import_service,
)

logger = logging.getLogger(__name__)

# Test configuration
TEST_DURATION_MINUTES = 20
TOTAL_QUESTIONS = 20
SELECTED_TEST_SESSION_KEY = 'scholarship_selected_test_id'


def _is_valid_person_name(name: str) -> bool:
    cleaned = (name or '').strip()
    return bool(cleaned) and bool(re.fullmatch(r'[A-Za-z ]+', cleaned))


def _is_rtse_test(test):
    if not test:
        return True

    normalized_name = re.sub(r'[^a-z0-9]+', '', test.name.lower())
    return (
        'rtse' in test.name.lower() and '2026' in test.name
    ) or normalized_name == 'rtse2026scholarshiptest'


def _uses_landing_page(test):
    if _is_rtse_test(test):
        return True

    if not test or not test.name:
        return False

    normalized_name = re.sub(r'[^a-z0-9]+', '', test.name.lower())
    return normalized_name == 'scholarshiptest'


def _get_reference_prefix(test):
    if _is_rtse_test(test):
        return 'RTSE'

    if not test or not test.name:
        return 'TEST'

    tokens = re.findall(r'[A-Z0-9]+', test.name.upper())
    prefix = ''.join(tokens[:2])[:10]
    return prefix or 'TEST'


def _set_selected_test(request, test):
    if test:
        request.session[SELECTED_TEST_SESSION_KEY] = test.id
    else:
        request.session.pop(SELECTED_TEST_SESSION_KEY, None)


def _get_session_selected_test(request):
    test_id = request.session.get(SELECTED_TEST_SESSION_KEY)
    selected_test = test_service.get_test_by_id(test_id)

    if test_id and not selected_test:
        request.session.pop(SELECTED_TEST_SESSION_KEY, None)

    return selected_test


def _get_effective_selected_test(request):
    return _get_session_selected_test(request) or test_service.get_active_test()


def _get_completed_attempt_for_test(student, selected_test):
    attempts = ScholarshipTestAttempt.objects.filter(
        student=student,
        status__in=['completed', 'expired']
    )

    if selected_test:
        attempts = attempts.filter(test=selected_test)

    return attempts.order_by('-test_started_at').first()


def _build_test_display_context(selected_test):
    runtime_questions = test_service.get_runtime_questions_for_test(selected_test)
    question_count = len(runtime_questions) if runtime_questions else TOTAL_QUESTIONS
    duration_minutes = (
        test_service.get_test_duration_minutes(selected_test)
        if selected_test
        else TEST_DURATION_MINUTES
    )

    if duration_minutes >= 60:
        hours = duration_minutes // 60
        minutes = duration_minutes % 60
        if minutes:
            duration_display = f"{hours} hr {minutes} min"
        else:
            duration_display = f"{hours} hr"
    else:
        duration_display = f"{duration_minutes} Minutes"

    test_name = selected_test.name if selected_test else "RTSE-2026 Scholarship Test"
    is_rtse_selected_test = _is_rtse_test(selected_test)

    return {
        'selected_test': selected_test,
        'selected_test_name': test_name,
        'selected_test_question_count': question_count,
        'selected_test_duration_minutes': duration_minutes,
        'selected_test_duration_display': duration_display,
        'is_rtse_selected_test': is_rtse_selected_test,
        'uses_landing_page': _uses_landing_page(selected_test),
        'selected_test_reference_prefix': _get_reference_prefix(selected_test),
    }


def _requires_otp_login(selected_test):
    return test_service.requires_otp_login(selected_test)


def _build_portal_login_url(selected_test):
    login_url = reverse('login')
    if not selected_test:
        return login_url

    launch_url = reverse('scholarship_test:scholarship_launch_test', args=[selected_test.id])
    return f"{login_url}?{urlencode({'next': launch_url})}"


def _normalize_portal_phone(phone):
    digits = re.sub(r'\D', '', str(phone or ''))
    if digits:
        return digits[-10:]
    return ''


def _get_portal_student(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return None

    return getattr(user, 'student', None)


def _sync_portal_student_session(request, selected_test):
    if _requires_otp_login(selected_test):
        return None, None

    portal_student = _get_portal_student(request)
    if not portal_student:
        return None, None

    phone_number = _normalize_portal_phone(portal_student.contact)
    if not phone_number:
        phone_number = f"INT{portal_student.id:08d}"[:15]

    scholarship_student, _ = ScholarshipStudent.objects.get_or_create(
        phone_number=phone_number,
        defaults={
            'name': portal_student.student_name or portal_student.user.username,
            'grade': portal_student.grade or '',
            'board': portal_student.board or '',
            'otp_verified': True,
        },
    )

    updated_fields = []
    desired_name = portal_student.student_name or portal_student.user.username
    desired_grade = portal_student.grade or ''
    desired_board = portal_student.board or ''

    if scholarship_student.name != desired_name:
        scholarship_student.name = desired_name
        updated_fields.append('name')
    if scholarship_student.grade != desired_grade:
        scholarship_student.grade = desired_grade
        updated_fields.append('grade')
    if scholarship_student.board != desired_board:
        scholarship_student.board = desired_board
        updated_fields.append('board')
    if not scholarship_student.otp_verified:
        scholarship_student.otp_verified = True
        updated_fields.append('otp_verified')

    if updated_fields:
        scholarship_student.save(update_fields=updated_fields)

    request.session['scholarship_student_id'] = scholarship_student.id
    request.session['scholarship_student_name'] = scholarship_student.name
    request.session['scholarship_grade'] = scholarship_student.grade
    request.session['scholarship_board'] = scholarship_student.board

    return scholarship_student, portal_student


def _get_non_scholarship_stream(attempt):
    portal_student = getattr(attempt, 'portal_student', None)
    if not portal_student:
        return getattr(attempt.student, 'board', '') or '-'

    interested_exams = getattr(portal_student, 'interested_exams', []) or []
    normalized_exams = [str(exam).strip().upper() for exam in interested_exams if str(exam).strip()]

    matched_streams = []
    for stream_name in ('JEE', 'NEET'):
        if any(stream_name in exam for exam in normalized_exams):
            matched_streams.append(stream_name)

    if matched_streams:
        return ' / '.join(matched_streams)

    board_value = getattr(portal_student, 'board', '') or getattr(attempt.student, 'board', '')
    return board_value or '-'




def scholarship_landing(request):
    selected_test = _get_effective_selected_test(request)
    if selected_test:
        _set_selected_test(request, selected_test)
    context = _build_test_display_context(selected_test)
    return render(request, "scholarship-landing.html", context)

def scholarship_home(request):
    return redirect('scholarship_test:scholarship_register')


def scholarship_launch_test(request, test_id):
    selected_test = test_service.get_test_by_id(test_id)

    if not selected_test:
        messages.error(request, "Selected scholarship test was not found.")
        return redirect('login')

    if not test_service.get_runtime_questions_for_test(selected_test):
        messages.error(request, "This scholarship test is not ready yet.")
        return redirect('login')

    _set_selected_test(request, selected_test)
    if _requires_otp_login(selected_test):
        return redirect('scholarship_test:scholarship_landing')

    scholarship_student, _ = _sync_portal_student_session(request, selected_test)
    if scholarship_student:
        return redirect('scholarship_test:scholarship_dashboard')

    return redirect(_build_portal_login_url(selected_test))


def scholarship_register(request):
    # Check if user already has session
    if 'scholarship_student_id' in request.session:
        return redirect('scholarship_test:scholarship_dashboard')

    selected_test = _get_effective_selected_test(request)
    if _requires_otp_login(selected_test):
        return redirect(f"{reverse('scholarship_test:scholarship_landing')}?show_register=1")

    scholarship_student, _ = _sync_portal_student_session(request, selected_test)
    if scholarship_student:
        return redirect('scholarship_test:scholarship_dashboard')

    return redirect(_build_portal_login_url(selected_test))


def scholarship_register_step2(request):
    
    # Check if already registered
    if 'scholarship_student_id' in request.session:
        return redirect('scholarship_test:scholarship_dashboard')
    
    if request.method == 'POST':
        grade = request.POST.get('grade', '')
        board = request.POST.get('board', '')
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone_number', '')
        
        # Normalize phone
        phone = phone.replace('+91', '').replace(' ', '').replace('-', '')
        if len(phone) > 10:
            phone = phone[-10:]
        
        # Validate
        if not grade or not board or not name or len(phone) != 10:
            return JsonResponse({'success': False, 'error': 'Invalid form data'}, status=400)
        if not _is_valid_person_name(name):
            return JsonResponse(
                {'success': False, 'error': 'Name should contain only letters and spaces'},
                status=400,
            )
        
        # Store in session
        request.session['scholarship_grade'] = grade
        request.session['scholarship_board'] = board
        request.session['scholarship_temp_name'] = name
        request.session['scholarship_temp_phone'] = phone  
        
        # Send OTP
        success, message = otp_service.send_otp(phone)
        
        if success:
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': message}, status=400)
    
    # If not POST, redirect to registration page
    return redirect('scholarship_test:scholarship_register')


@csrf_exempt
def scholarship_send_otp(request):
    
    phone = request.POST.get('phone_number', '')
    
    # Normalize phone
    phone = phone.replace('+91', '').replace(' ', '').replace('-', '')
    if len(phone) > 10:
        phone = phone[-10:]
    
    success, message = otp_service.send_otp(phone)   
    
    if success:
        return JsonResponse({'success': True, 'message': message})
    else:
        return JsonResponse({'success': False, 'error': message}, status=400)


@csrf_exempt
def scholarship_verify_otp(request):
    
    phone = request.POST.get('phone_number', '')
    otp = request.POST.get('otp_code', '')
    is_login = request.POST.get('login', 'false').lower() == 'true'
    
    # Normalize phone
    phone = phone.replace('+91', '').replace(' ', '').replace('-', '')
    if len(phone) > 10:
        phone = phone[-10:]
    
    success, message, student = otp_service.verify_otp(phone, otp)
    
    if success and student:
        # Debug logging
        logger.info(f"=== scholarship_verify_otp called ===")
        logger.info(f"is_login: {is_login}, student.id: {student.id}, current name: '{student.name}'")
        logger.info(f"Session data - temp_name: '{request.session.get('scholarship_temp_name')}', grade: '{request.session.get('scholarship_grade')}', board: '{request.session.get('scholarship_board')}'")
        
       
        if is_login:
            request.session.pop('scholarship_temp_name', None)
            request.session.pop('scholarship_temp_phone', None)
            
           
            if not student.name:
                logger.warning(f"Student {student.id} has empty name, attempting to preserve")
        else:
           
            student.refresh_from_db()
            
            name = request.session.get('scholarship_temp_name') or ''
            name = name.strip()
            grade = request.session.get('scholarship_grade') or ''
            grade = grade.strip()
            board = request.session.get('scholarship_board') or ''
            board = board.strip()
            
            logger.info(f"Registration - name from session: '{name}', grade: '{grade}', board: '{board}'")
            
           
            if name:
                student.name = name
                logger.info(f"Setting student.name to: '{name}'")
            if grade:
                student.grade = grade
            if board:
                student.board = board
            
          
            student.save()
            logger.info(f"Student {student.id} saved with name: '{student.name}'")
            
         
            student.refresh_from_db()
            logger.info(f"After refresh - Student {student.id} name: '{student.name}'")
        
        
        student.otp_verified = True
        student.save()
        logger.info(f"Student {student.id} FINAL saved with name: '{student.name}'" )
        
      
        request.session['scholarship_student_id'] = student.id
        request.session['scholarship_student_name'] = student.name
        request.session['scholarship_grade'] = student.grade
        request.session['scholarship_board'] = student.board
        
        request.session.pop('scholarship_temp_name', None)
        request.session.pop('scholarship_temp_phone', None)
        
        return JsonResponse({'success': True, 'message': 'Registration successful!'})
    else:
        return JsonResponse({'success': False, 'error': message}, status=400)


@csrf_exempt
def scholarship_resend_otp(request):
   
    phone = request.POST.get('phone_number', '')
    
   
    phone = phone.replace('+91', '').replace(' ', '').replace('-', '')
    if len(phone) > 10:
        phone = phone[-10:]
    
    success, message = otp_service.resend_otp(phone)
    
    if success:
        return JsonResponse({'success': True, 'message': message})
    else:
        return JsonResponse({'success': False, 'error': message}, status=400)


def scholarship_dashboard(request):
    selected_test = _get_effective_selected_test(request)
    if selected_test:
        _set_selected_test(request, selected_test)

    scholarship_student, _ = _sync_portal_student_session(request, selected_test)

    student_id = scholarship_student.id if scholarship_student else request.session.get('scholarship_student_id')
    if not student_id:
        if _requires_otp_login(selected_test):
            return redirect('scholarship_test:scholarship_register')
        return redirect(_build_portal_login_url(selected_test))

    try:
        student = ScholarshipStudent.objects.get(id=student_id)
    except ScholarshipStudent.DoesNotExist:
        request.session.clear()
        if _requires_otp_login(selected_test):
            return redirect('scholarship_test:scholarship_register')
        return redirect(_build_portal_login_url(selected_test))

    request.session['scholarship_student_name'] = student.name
    request.session['scholarship_grade'] = student.grade
    request.session['scholarship_board'] = student.board

    completed_attempt = _get_completed_attempt_for_test(student, selected_test)
    if completed_attempt:
        return redirect('scholarship_test:scholarship_success', attempt_id=completed_attempt.id)

    can_attempt, message = test_service.can_attempt_test(student, selected_test)

    context = {
        'student': student,
        'can_attempt': can_attempt,
        'message': message,
        'completed': completed_attempt is not None,
        'attempt': completed_attempt,
        'is_guest': False,
    }
    context.update(_build_test_display_context(selected_test))
    return render(request, 'scholarship-dashboard.html', context)


def scholarship_start_test(request):
    selected_test = _get_effective_selected_test(request)
    if selected_test:
        _set_selected_test(request, selected_test)

    scholarship_student, portal_student = _sync_portal_student_session(request, selected_test)

    student_id = scholarship_student.id if scholarship_student else request.session.get('scholarship_student_id')
    if not student_id:
        if _requires_otp_login(selected_test):
            return redirect('scholarship_test:scholarship_register')
        return redirect(_build_portal_login_url(selected_test))

    try:
        student = ScholarshipStudent.objects.get(id=student_id)
    except ScholarshipStudent.DoesNotExist:
        request.session.clear()
        if _requires_otp_login(selected_test):
            return redirect('scholarship_test:scholarship_register')
        return redirect(_build_portal_login_url(selected_test))

    request.session['scholarship_student_name'] = student.name
    request.session['scholarship_grade'] = student.grade
    request.session['scholarship_board'] = student.board

    completed_attempt = _get_completed_attempt_for_test(student, selected_test)
    if completed_attempt:
        return redirect('scholarship_test:scholarship_success', attempt_id=completed_attempt.id)

    active_test = selected_test or test_service.get_active_test()
    active_runtime_questions = test_service.get_runtime_questions_for_test(active_test)
    if active_test and not active_runtime_questions:
        messages.error(request, "No questions are configured for the selected scholarship test.")
        return redirect('scholarship_test:scholarship_dashboard')

    total_questions = len(active_runtime_questions) if active_runtime_questions else TOTAL_QUESTIONS

    with transaction.atomic():
        attempt = ScholarshipTestAttempt.objects.create(
            student=student,
            test=active_test,
            portal_student=portal_student,
            student_batch=(portal_student.batch if portal_student else ''),
            status='started',
            total_questions=total_questions,
            total_marks=total_questions
        )

    return redirect('scholarship_test:scholarship_test', attempt_id=attempt.id)


def scholarship_test(request, attempt_id):
    selected_test = _get_effective_selected_test(request)
    scholarship_student, _ = _sync_portal_student_session(request, selected_test)

    student_id = scholarship_student.id if scholarship_student else request.session.get('scholarship_student_id')
    if not student_id:
        if _requires_otp_login(selected_test):
            return redirect('scholarship_test:scholarship_register')
        return redirect(_build_portal_login_url(selected_test))
    
    try:
        student = ScholarshipStudent.objects.get(id=student_id)
    except ScholarshipStudent.DoesNotExist:
        request.session.clear()
        if _requires_otp_login(selected_test):
            return redirect('scholarship_test:scholarship_register')
        return redirect(_build_portal_login_url(selected_test))
    
    request.session['scholarship_student_name'] = student.name
    request.session['scholarship_grade'] = student.grade
    request.session['scholarship_board'] = student.board
    
    try:
        attempt = ScholarshipTestAttempt.objects.select_related('test').get(id=attempt_id, student=student)
    except ScholarshipTestAttempt.DoesNotExist:
        messages.error(request, "Test not found")
        return redirect('scholarship_test:scholarship_dashboard')
    
    if attempt.status in ['completed', 'expired']:
        return redirect('scholarship_test:scholarship_success', attempt_id=attempt.id)
    
    runtime_test = test_service.get_runtime_test_for_attempt(attempt)
    runtime_questions = test_service.get_runtime_questions_for_test(runtime_test)
    time_limit_minutes = test_service.get_test_duration_minutes(runtime_test) if runtime_test else TEST_DURATION_MINUTES
    time_limit = timedelta(minutes=time_limit_minutes)
    time_remaining = (attempt.test_started_at + time_limit) - timezone.now()
    
    if time_remaining.total_seconds() <= 0:
        if runtime_test and runtime_questions:
            test_service.auto_submit_runtime_test(attempt.id)
        else:
            test_service.auto_submit_expired_test(attempt.id)
        return redirect('scholarship_test:scholarship_success', attempt_id=attempt.id)

    if runtime_test and runtime_questions:
        questions_data = [
            test_service.serialize_runtime_question(question, index + 1)
            for index, question in enumerate(runtime_questions)
        ]
    else:
        questions = test_service.get_test_questions(
            grade=student.grade,
            board=student.board,
            count=TOTAL_QUESTIONS
        )
        
        if not questions:
            messages.error(request, "No questions available for your grade/board. Please contact admin.")
            return redirect('scholarship_test:scholarship_dashboard')
        
        questions_data = []
        for q in questions:
            questions_data.append({
                'id': q.id,
                'type': 'mcq',
                'sequence': len(questions_data) + 1,
                'question_html': q.question_text,
                'section_name': '',
                'section_instructions': '',
                'multi_select': False,
                'options': [
                    {'value': 'A', 'label': 'A', 'text_html': q.option_a},
                    {'value': 'B', 'label': 'B', 'text_html': q.option_b},
                    {'value': 'C', 'label': 'C', 'text_html': q.option_c},
                    {'value': 'D', 'label': 'D', 'text_html': q.option_d},
                ],
            })
    
    context = {
        'attempt': attempt,
        'student': student,
        'test': runtime_test,
        'questions': questions_data,
        'total_questions': len(questions_data),
        'time_limit': time_limit_minutes,
        'time_remaining_seconds': int(time_remaining.total_seconds())
    }
    context.update(_build_test_display_context(runtime_test))
    
    return render(request, 'scholarship-test.html', context)


@require_POST
@csrf_exempt
def scholarship_submit_test(request, attempt_id):
    selected_test = _get_effective_selected_test(request)
    scholarship_student, _ = _sync_portal_student_session(request, selected_test)

    student_id = scholarship_student.id if scholarship_student else request.session.get('scholarship_student_id')
    if not student_id:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)
    
    try:
        student = ScholarshipStudent.objects.get(id=student_id)
    except ScholarshipStudent.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Student not found'}, status=404)
    
    request.session['scholarship_student_name'] = student.name
    request.session['scholarship_grade'] = student.grade
    request.session['scholarship_board'] = student.board
    
    try:
        attempt = ScholarshipTestAttempt.objects.select_related('test').get(id=attempt_id, student=student)
    except ScholarshipTestAttempt.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Test not found'}, status=404)
    
    if attempt.status in ['completed', 'expired']:
        return JsonResponse({'success': True, 'redirect': reverse('scholarship_test:scholarship_success', args=[attempt.id])})
    
  
    try:
        data = json.loads(request.body)
        answers = data.get('answers', {})
    except json.JSONDecodeError:
        answers = {}
    
    runtime_test = test_service.get_runtime_test_for_attempt(attempt)
    runtime_questions = test_service.get_runtime_questions_for_test(runtime_test)
    if runtime_test and runtime_questions:
        success, message, updated_attempt = test_service.submit_runtime_test(attempt.id, answers)
    else:
        success, message, updated_attempt = test_service.submit_test(attempt.id, answers)
    
    if success:
        return JsonResponse({
            'success': True,
            'redirect': reverse('scholarship_test:scholarship_success', args=[attempt.id])
        })
    else:
        return JsonResponse({'success': False, 'error': message}, status=400)


def scholarship_success(request, attempt_id):
    
    student_id = request.session.get('scholarship_student_id')
    
    try:
        attempt = ScholarshipTestAttempt.objects.select_related('student', 'portal_student').get(id=attempt_id)
        
        student = attempt.student
        
        if student_id and attempt.student.id != student_id:
            request.session['scholarship_student_id'] = student.id
            request.session['scholarship_student_name'] = student.name
            request.session['scholarship_grade'] = student.grade
            request.session['scholarship_board'] = student.board
        
        student.refresh_from_db()
        attempt.refresh_from_db()
        
        request.session['scholarship_student_id'] = student.id
        request.session['scholarship_student_name'] = student.name
        request.session['scholarship_grade'] = student.grade
        request.session['scholarship_board'] = student.board
        _set_selected_test(request, attempt.test)
        
        logger.info(f"Scholarship success - Student: {student.name}, Phone: {student.phone_number}, Score: {attempt.score}")
        
    except ScholarshipTestAttempt.DoesNotExist:
        messages.error(request, "Result not found")
        return redirect('scholarship_test:scholarship_register')
    except ScholarshipStudent.DoesNotExist:
        messages.error(request, "Student not found")
        return redirect('scholarship_test:scholarship_register')
    
    is_scholarship_result = _requires_otp_login(attempt.test)
    score_percentage = test_service.calculate_score_percentage(
        attempt.score,
        attempt.total_questions,
    )
    completed_at_display = (
        timezone.localtime(attempt.test_completed_at).strftime('%d %b %Y, %I:%M %p')
        if attempt.test_completed_at
        else None
    )
    academic_field_label = 'Board' if is_scholarship_result else 'Stream'
    academic_field_value = (
        student.board if is_scholarship_result else _get_non_scholarship_stream(attempt)
    )

    if is_scholarship_result and not attempt.sms_sent and attempt.status in ['completed', 'expired']:
        try:
            if student.phone_number:
                logger.info(f"Retrying SMS send for attempt {attempt.id} to {student.phone_number}")
                sms_result, sms_message = test_service._send_attempt_result_sms(
                    attempt=attempt,
                    score=attempt.score,
                    total_questions=attempt.total_questions,
                    scholarship_percentage=attempt.scholarship_percentage,
                )
                attempt.sms_sent = sms_result
                attempt.sms_error = sms_message if not sms_result else None
                attempt.save(update_fields=['sms_sent', 'sms_error'])
                logger.info(f"SMS retry result: {sms_result}, {sms_message}")
            else:
                attempt.sms_error = "No phone number on student record"
                attempt.save(update_fields=['sms_error'])
        except Exception as e:
            logger.error(f"SMS retry failed: {str(e)}", exc_info=True)
            attempt.sms_error = str(e)
            attempt.save(update_fields=['sms_error'])
    
    context = {
        'attempt': attempt,
        'student': student,
        'sms_sent': attempt.sms_sent,
        'sms_error': attempt.sms_error,
        'is_scholarship_result': is_scholarship_result,
        'result_percentage': score_percentage,
        'completed_at_display': completed_at_display,
        'academic_field_label': academic_field_label,
        'academic_field_value': academic_field_value,
    }
    context.update(_build_test_display_context(attempt.test))
    return render(request, 'scholarship-success.html', context)


def scholarship_logout(request):
    
   
    scholarship_keys = [
        'scholarship_student_id',
        'scholarship_student_name',
        'scholarship_temp_name',
        'scholarship_temp_phone',
        'scholarship_grade',
        'scholarship_board',
        SELECTED_TEST_SESSION_KEY,
    ]
    
    for key in scholarship_keys:
        request.session.pop(key, None)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    return redirect('login.html')

def scholarshiptest_management(request):
    return render(request, "scholarshiptest-management.html")

def scholarship_create_test(request):
    response = render(request, "create_test.html")
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@csrf_exempt
def api_get_tests(request):
    tests = ScholarshipTest.objects.all().order_by('-created_at')
    data = []
    for test in tests:
        data.append({
            'id': test.id,
            'name': test.name,
            'date': test.date.isoformat() if test.date else None,
            'folderId': test.folder.id if test.folder else None,
            'duration_hours': test.duration_hours,
            'duration_minutes': test.duration_minutes,
            'tags': test.tags,
            'status': test.status,
        })
    return JsonResponse({'tests': data})


@csrf_exempt
def api_create_test(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Name is required'}, status=400)
    
    folder_id = data.get('folderId')
    folder = None
    if folder_id:
        try:
            folder = ScholarshipTestFolder.objects.get(id=folder_id)
        except ScholarshipTestFolder.DoesNotExist:
            pass
    
    tags = data.get('tags', '')
    status = data.get('status', 'draft')
    valid_statuses = {choice[0] for choice in ScholarshipTest._meta.get_field('status').choices}
    if status not in valid_statuses:
        return JsonResponse({'error': 'Invalid status'}, status=400)
    try:
        duration_parts = _parse_test_duration(data)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid duration'}, status=400)
    duration_hours, duration_minutes = duration_parts or (1, 0)
    
    test = ScholarshipTest.objects.create(
        name=name,
        folder=folder,
        tags=tags,
        duration_hours=duration_hours,
        duration_minutes=duration_minutes,
        status=status,
    )
    
    ScholarshipTestConfig.objects.create(
        test=test,
        default_pos_marks=2,
        default_neg_marks=1,
    )
    
    return JsonResponse({
        'success': True,
        'test': {
            'id': test.id,
            'name': test.name,
            'date': test.date.isoformat() if test.date else None,
            'folderId': test.folder.id if test.folder else None,
            'duration_hours': test.duration_hours,
            'duration_minutes': test.duration_minutes,
            'tags': test.tags,
            'status': test.status,
        }
    })


@csrf_exempt
def api_update_test(request, test_id):
    if request.method not in ['POST', 'PUT']:
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    try:
        test = ScholarshipTest.objects.get(id=test_id)
    except ScholarshipTest.DoesNotExist:
        return JsonResponse({'error': 'Test not found'}, status=404)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    name = data.get('name')
    if name:
        test.name = name
    
    folder_id = data.get('folderId')
    if folder_id is not None:
        if folder_id:
            try:
                test.folder = ScholarshipTestFolder.objects.get(id=folder_id)
            except ScholarshipTestFolder.DoesNotExist:
                test.folder = None
        else:
            test.folder = None
    
    if 'tags' in data:
        test.tags = data.get('tags', '')
    if 'duration_hours' in data:
        test.duration_hours = data.get('duration_hours')
    if 'duration_minutes' in data:
        test.duration_minutes = data.get('duration_minutes')
    if 'status' in data:
        status = data.get('status')
        valid_statuses = {choice[0] for choice in ScholarshipTest._meta.get_field('status').choices}
        if status not in valid_statuses:
            return JsonResponse({'error': 'Invalid status'}, status=400)
        test.status = status
    
    test.save()
    
    return JsonResponse({'success': True, 'test': {
        'id': test.id,
        'name': test.name,
        'date': test.date.isoformat() if test.date else None,
        'folderId': test.folder.id if test.folder else None,
        'duration_hours': test.duration_hours,
        'duration_minutes': test.duration_minutes,
        'tags': test.tags,
        'status': test.status,
    }})


@csrf_exempt
def api_delete_test(request, test_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    try:
        test = ScholarshipTest.objects.get(id=test_id)
    except ScholarshipTest.DoesNotExist:
        return JsonResponse({'error': 'Test not found'}, status=404)

   
    for image in test.images.all():
        if image.image:
            image.image.delete(save=False)

    test.delete()
    return JsonResponse({'success': True})


@csrf_exempt
def api_get_folders(request):
    folders = ScholarshipTestFolder.objects.all().order_by('name')
    data = []
    for folder in folders:
        data.append({
            'id': folder.id,
            'name': folder.name,
            'tags': folder.tags,
        })
    return JsonResponse({'folders': data})


@csrf_exempt
def api_create_folder(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Name is required'}, status=400)

    if ScholarshipTestFolder.objects.filter(name__iexact=name).exists():
        return JsonResponse(
            {'error': 'A folder with this name already exists. Change the name and try again.'},
            status=400,
        )
    
    tags = data.get('tags', '')
    
    folder = ScholarshipTestFolder.objects.create(
        name=name,
        tags=tags,
    )
    
    return JsonResponse({
        'success': True,
        'folder': {
            'id': folder.id,
            'name': folder.name,
            'tags': folder.tags,
        }
    })


@csrf_exempt
@csrf_exempt
def api_update_folder(request, folder_id):
  
    if request.method not in ['POST', 'PUT']:
        return JsonResponse({'error': 'Invalid method'}, status=405)

    try:
        folder = ScholarshipTestFolder.objects.get(id=folder_id)
    except ScholarshipTestFolder.DoesNotExist:
        return JsonResponse({'error': 'Folder not found'}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Name is required'}, status=400)

    if ScholarshipTestFolder.objects.filter(name__iexact=name).exclude(id=folder_id).exists():
        return JsonResponse(
            {'error': 'A folder with this name already exists. Change the name and try again.'},
            status=400,
        )

    tags = data.get('tags', '')

    try:
        folder.name = name
        folder.tags = tags
        folder.save()
    except IntegrityError:
        return JsonResponse({'error': 'A folder with this name already exists'}, status=400)

    return JsonResponse({
        'success': True,
        'folder': {
            'id': folder.id,
            'name': folder.name,
            'tags': folder.tags,
        }
    })


@csrf_exempt
def api_delete_folder(request, folder_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    try:
        folder = ScholarshipTestFolder.objects.get(id=folder_id)
    except ScholarshipTestFolder.DoesNotExist:
        return JsonResponse({'error': 'Folder not found'}, status=404)

    deleted_tests_count = folder.tests.count()
    folder.tests.all().delete()

    folder.delete()
    return JsonResponse({'success': True, 'deleted_tests_count': deleted_tests_count})


@csrf_exempt
def api_move_test(request, test_id):
    if request.method not in ['POST', 'PUT']:
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    try:
        test = ScholarshipTest.objects.get(id=test_id)
    except ScholarshipTest.DoesNotExist:
        return JsonResponse({'error': 'Test not found'}, status=404)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    folder_id = data.get('folderId')
    if folder_id is not None:
        if folder_id:
            try:
                test.folder = ScholarshipTestFolder.objects.get(id=folder_id)
            except ScholarshipTestFolder.DoesNotExist:
                test.folder = None
        else:
            test.folder = None
        test.save()
    
    return JsonResponse({'success': True})


@csrf_exempt
def api_copy_test(request, test_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    try:
        original_test = ScholarshipTest.objects.get(id=test_id)
    except ScholarshipTest.DoesNotExist:
        return JsonResponse({'error': 'Test not found'}, status=404)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    new_name = data.get('name', '').strip()
    if not new_name:
        new_name = original_test.name + ' (Copy)'
    
    new_test = ScholarshipTest.objects.create(
        name=new_name,
        folder=original_test.folder,
        tags=original_test.tags,
        duration_hours=original_test.duration_hours,
        duration_minutes=original_test.duration_minutes,
        status=original_test.status,
    )
    
    config = ScholarshipTestConfig.objects.get(test=original_test)
    ScholarshipTestConfig.objects.create(
        test=new_test,
        instructions=config.instructions,
        default_pos_marks=config.default_pos_marks,
        default_neg_marks=config.default_neg_marks,
    )
    
    for section in original_test.sections.all():
        new_section = ScholarshipTestSection.objects.create(
            test=new_test,
            name=section.name,
            order=section.order,
            allow_switching=section.allow_switching,
            instructions=section.instructions,
        )
        
        for question in section.questions.all():
            new_question = ScholarshipTestQuestion.objects.create(
                section=new_section,
                question_type=question.question_type,
                question_text=question.question_text,
                passage=question.passage,
                difficulty=question.difficulty,
                pos_marks=question.pos_marks,
                neg_marks=question.neg_marks,
                neg_unattempted=question.neg_unattempted,
                tags=question.tags,
                order=question.order,
                is_multi_select=question.is_multi_select,
            )
            
            for option in question.options.all():
                ScholarshipTestOption.objects.create(
                    question=new_question,
                    option_text=option.option_text,
                    is_correct=option.is_correct,
                    order=option.order,
                )
            
            ScholarshipTestAnswer.objects.create(
                question=new_question,
                correct_answer=question.answers.first().correct_answer if question.answers.exists() else '',
            )

  
    for image in original_test.images.all():
        ScholarshipTestImage.objects.create(
            test=new_test,
            image=image.image, 
            original_filename=image.original_filename,
        )

    return JsonResponse({
        'success': True,
        'test': {
            'id': new_test.id,
            'name': new_test.name,
        }
    })


def _format_test_duration(hours, minutes):
    total = int(hours or 0) + (int(minutes or 0) / 60)
    if total.is_integer():
        return str(int(total))
    return f"{total:.2f}".rstrip('0').rstrip('.')


def _parse_test_duration(data):
    if 'duration_hours' in data or 'duration_minutes' in data:
        hours = int(data.get('duration_hours') or 0)
        minutes = int(data.get('duration_minutes') or 0)
    elif 'duration' in data:
        total = float(data.get('duration') or 0)
        if total < 0:
            raise ValueError("Duration cannot be negative")
        hours = int(total)
        minutes = round((total - hours) * 60)
    else:
        return None

    if minutes < 0:
        raise ValueError("Duration minutes cannot be negative")

    hours += minutes // 60
    minutes = minutes % 60
    return hours, minutes


@csrf_exempt
def api_get_test_details(request, test_id):
    try:
        test = ScholarshipTest.objects.get(id=test_id)
    except ScholarshipTest.DoesNotExist:
        return JsonResponse({'error': 'Test not found'}, status=404)
    
    config = getattr(test, 'config', None)
    
    sections_data = []
    for section in test.sections.all():
        questions_data = []
        for question in section.questions.all():
            question_options = list(question.options.all())
            options_data = [option.option_text for option in question_options]
            correct_option_indexes = [
                idx for idx, option in enumerate(question_options) if option.is_correct
            ]
            
            answer = question.answers.first()
            
            question_data = {
                'id': question.id,
                'type': question.question_type,
                'text': question.question_text,
                'passage': question.passage,
                'difficulty': question.difficulty,
                'pos_marks': question.pos_marks,
                'posMarks': question.pos_marks,
                'neg_marks': question.neg_marks,
                'negMarks': question.neg_marks,
                'neg_unattempted': question.neg_unattempted,
                'negUnattempted': question.neg_unattempted,
                'tags': question.tags.split(',') if question.tags else [],
                'order': question.order,
                'multi_select': question.is_multi_select,
                'multiSelect': question.is_multi_select,
                'options': options_data,
                'correct_options': correct_option_indexes,
                'correctOptions': correct_option_indexes,
                'correct_answer': answer.correct_answer if answer else '',
                'correctAnswer': answer.correct_answer if answer else '',
            }
            
           
            if question.question_type == 'comp':
                try:
                    import json
                    comp_data = json.loads(question.question_text)
                    question_data['text'] = comp_data.get('text', question.question_text)
                    question_data['passage'] = comp_data.get('passage', '')
                    question_data['sub_questions'] = comp_data.get('sub_questions', [])
                except:
                    question_data['sub_questions'] = []
            
            questions_data.append(question_data)
        
        sections_data.append({
            'id': section.id,
            'name': section.name,
            'order': section.order,
            'allow_switching': section.allow_switching,
            'allowSwitching': section.allow_switching,
            'instructions': section.instructions,
            'sectionInstructions': section.instructions,
            'questions': questions_data,
        })
    
    return JsonResponse({
        'test': {
            'id': test.id,
            'name': test.name,
            'duration': _format_test_duration(test.duration_hours, test.duration_minutes),
            'duration_hours': test.duration_hours,
            'duration_minutes': test.duration_minutes,
            'tags': test.tags,
            'instructions': config.instructions if config else '',
            'default_pos_marks': config.default_pos_marks if config else 2,
            'default_neg_marks': config.default_neg_marks if config else 1,
            'sections': sections_data,
        }
    })


@csrf_exempt
def api_save_test_details(request, test_id):
    if request.method not in ['POST', 'PUT']:
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    try:
        test = ScholarshipTest.objects.get(id=test_id)
    except ScholarshipTest.DoesNotExist:
        return JsonResponse({'error': 'Test not found'}, status=404)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    if 'testName' in data:
        test.name = data['testName']
    try:
        duration_parts = _parse_test_duration(data)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid duration'}, status=400)
    if duration_parts is not None:
        test.duration_hours, test.duration_minutes = duration_parts
    if 'tags' in data:
        test.tags = data['tags']
    if 'status' in data:
        status = data.get('status')
        valid_statuses = {choice[0] for choice in ScholarshipTest._meta.get_field('status').choices}
        if status not in valid_statuses:
            return JsonResponse({'error': 'Invalid status'}, status=400)
        test.status = status
    
    test.save()
    
    config, _ = ScholarshipTestConfig.objects.get_or_create(test=test)
    if 'instructions' in data:
        config.instructions = data['instructions']
    if 'default_pos_marks' in data:
        config.default_pos_marks = data['default_pos_marks']
    if 'default_neg_marks' in data:
        config.default_neg_marks = data['default_neg_marks']
    config.save()

    return JsonResponse({'success': True})



@csrf_exempt
def api_save_section(request, test_id):
    if request.method not in ['POST', 'PUT']:
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    try:
        test = ScholarshipTest.objects.get(id=test_id)
    except ScholarshipTest.DoesNotExist:
        return JsonResponse({'error': 'Test not found'}, status=404)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    section_id = data.get('id')
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Name is required'}, status=400)

    allow_switching = data.get('allowSwitching', True)
    instructions = data.get('instructions', '')
    prefer_existing_by_name = data.get('preferExistingByName', False)
    if isinstance(prefer_existing_by_name, str):
        prefer_existing_by_name = prefer_existing_by_name.lower() == 'true'
    else:
        prefer_existing_by_name = bool(prefer_existing_by_name)

    def update_section(section):
        section.name = name
        section.allow_switching = allow_switching
        section.instructions = instructions
        section.save()
        return section

    section_by_id = None
    if section_id:
        try:
            section_by_id = ScholarshipTestSection.objects.get(id=section_id, test=test)
        except (ScholarshipTestSection.DoesNotExist, ValueError, TypeError):
            section_by_id = None

    section_by_name = ScholarshipTestSection.objects.filter(test=test, name=name).first()

    if prefer_existing_by_name and section_by_name:
        target_section = section_by_name
    elif section_by_id:
        if section_by_name and section_by_name.id != section_by_id.id:
            return JsonResponse({'error': 'A section with this name already exists in this test'}, status=400)
        target_section = section_by_id
    elif section_by_name:
        target_section = section_by_name
    else:
        target_section = None

    if target_section:
        try:
            section = update_section(target_section)
        except IntegrityError:
            return JsonResponse({'error': 'A section with this name already exists in this test'}, status=400)
    else:
        max_order = test.sections.order_by('-order').first()
        next_order = (max_order.order + 1) if max_order else 0
        try:
            section = ScholarshipTestSection.objects.create(
                test=test,
                name=name,
                order=next_order,
                allow_switching=allow_switching,
                instructions=instructions,
            )
        except IntegrityError:
            return JsonResponse({'error': 'A section with this name already exists in this test'}, status=400)
    
    return JsonResponse({
        'success': True,
        'section': {
            'id': section.id,
            'name': section.name,
            'order': section.order,
            'allow_switching': section.allow_switching,
            'instructions': section.instructions,
        }
    })


@csrf_exempt
def api_delete_section(request, test_id, section_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    try:
        section = ScholarshipTestSection.objects.get(id=section_id, test_id=test_id)
    except ScholarshipTestSection.DoesNotExist:
        return JsonResponse({'error': 'Section not found'}, status=404)
    
    section.delete()
    return JsonResponse({'success': True})


@csrf_exempt
def api_save_question(request, test_id):
    logger.info(f"api_save_question called - test_id: {test_id}, body: {request.body[:500]}")
    try:
        data = json.loads(request.body)
        logger.info(f"Parsed data: section_id={data.get('section_id')}, sectionId={data.get('sectionId')}, type={data.get('type')}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    question_id = data.get('id')
    section_id = data.get('section_id') or data.get('sectionId')

    if not section_id:
        logger.error(f"Section ID is required - data keys: {list(data.keys())}")
        return JsonResponse({'error': 'Section ID is required'}, status=400)

    try:
        section = ScholarshipTestSection.objects.get(id=section_id, test_id=test_id)
        logger.info(f"Found section: {section.name}")
    except ScholarshipTestSection.DoesNotExist:
        fallback_sections = list(
            ScholarshipTestSection.objects.filter(test_id=test_id).order_by('order', 'id')
        )
        if len(fallback_sections) == 1:
            section = fallback_sections[0]
            logger.warning(
                f"Section id {section_id} not found for test {test_id}; "
                f"falling back to only section id {section.id}"
            )
        else:
            logger.error(
                f"Section not found: id={section_id}, test_id={test_id}, "
                f"available_sections={[s.id for s in fallback_sections]}"
            )
            return JsonResponse(
                {
                    'error': 'Section not found',
                    'requested_section_id': section_id,
                    'available_section_ids': [s.id for s in fallback_sections],
                },
                status=404
            )
    except Exception as e:
        logger.error(f"Error getting section: {str(e)}")
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)

    question_type = data.get('type', 'mcq')

    try:
        if question_id:
            try:
                question = ScholarshipTestQuestion.objects.get(id=question_id, section=section)
                question.question_type = question_type
                question.question_text = data.get('text', '')
                question.passage = data.get('passage', '')
                question.difficulty = data.get('difficulty', 'Medium')
                question.pos_marks = data.get('pos_marks', 2)
                question.neg_marks = data.get('neg_marks', 1)
                question.neg_unattempted = data.get('neg_unattempted', 0)
                question.tags = ','.join(data.get('tags', [])) if isinstance(data.get('tags'), list) else data.get('tags', '')
                question.is_multi_select = data.get('multi_select', False)
                question.save()
            except ScholarshipTestQuestion.DoesNotExist:
                max_order = section.questions.order_by('-order').first()
                next_order = (max_order.order + 1) if max_order else 0
                question = ScholarshipTestQuestion.objects.create(
                    section=section,
                    question_type=question_type,
                    question_text=data.get('text', ''),
                    passage=data.get('passage', ''),
                    difficulty=data.get('difficulty', 'Medium'),
                    pos_marks=data.get('pos_marks', 2),
                    neg_marks=data.get('neg_marks', 1),
                    neg_unattempted=data.get('neg_unattempted', 0),
                    tags=','.join(data.get('tags', [])) if isinstance(data.get('tags'), list) else data.get('tags', ''),
                    order=next_order,
                    is_multi_select=data.get('multi_select', False),
                )
        else:
            max_order = section.questions.order_by('-order').first()
            next_order = (max_order.order + 1) if max_order else 0
            question = ScholarshipTestQuestion.objects.create(
                section=section,
                question_type=question_type,
                question_text=data.get('text', ''),
                passage=data.get('passage', ''),
                difficulty=data.get('difficulty', 'Medium'),
                pos_marks=data.get('pos_marks', 2),
                neg_marks=data.get('neg_marks', 1),
                neg_unattempted=data.get('neg_unattempted', 0),
                tags=','.join(data.get('tags', [])) if isinstance(data.get('tags'), list) else data.get('tags', ''),
                order=next_order,
                is_multi_select=data.get('multi_select', False),
            )

        question.options.all().delete()
        question.answers.all().delete()

        options = data.get('options', [])
        correct_options = data.get('correct_options', [])

        for i, opt_text in enumerate(options):
            is_correct = i in correct_options if isinstance(correct_options, list) else (i == correct_options)
            ScholarshipTestOption.objects.create(
                question=question,
                option_text=opt_text,
                is_correct=is_correct,
                order=i,
            )

        correct_answer = data.get('correct_answer', '')
        if question_type in ['tf', 'fitb', 'int']:
            correct_answer = data.get('correctAnswer', correct_answer)
            ScholarshipTestAnswer.objects.create(
                question=question,
                correct_answer=correct_answer,
            )
        elif question_type == 'comp':
            sub_questions = data.get('sub_questions', [])
            if sub_questions:
                comp_data = {
                    'text': data.get('text', ''),
                    'passage': question.passage,
                    'sub_questions': sub_questions
                }
                question.question_text = json.dumps(comp_data)
                question.save()

        return JsonResponse({
            'success': True,
            'question': {
                'id': question.id,
                'type': question.question_type,
                'text': question.question_text,
            }
        })
    except Exception as e:
        logger.error(f"Error saving question: {str(e)}", exc_info=True)
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)


@csrf_exempt
def api_import_word_questions(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    uploaded_file = request.FILES.get('word_file')
    if not uploaded_file:
        return JsonResponse({'error': 'No Word file was uploaded'}, status=400)

    file_name = uploaded_file.name or ''
    if not file_name.lower().endswith('.docx'):
        return JsonResponse({'error': 'Only .docx Word files are supported'}, status=400)

    try:
        imported_data = word_import_service.import_questions_from_docx(uploaded_file)
    except word_import_service.WordImportError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except Exception as exc:
        logger.error("Word import failed: %s", str(exc), exc_info=True)
        return JsonResponse({'error': 'Failed to import the Word file'}, status=500)

    return JsonResponse({'success': True, 'imported': imported_data})


@csrf_exempt
def api_delete_question(request, test_id, question_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    try:
        question = ScholarshipTestQuestion.objects.get(id=question_id, section__test_id=test_id)
    except ScholarshipTestQuestion.DoesNotExist:
        return JsonResponse({'error': 'Question not found'}, status=404)

    question.delete()
    return JsonResponse({'success': True})


@csrf_exempt
def api_upload_image(request, test_id):
    """Upload image for a test"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    try:
        test = ScholarshipTest.objects.get(id=test_id)
    except ScholarshipTest.DoesNotExist:
        return JsonResponse({'error': 'Test not found'}, status=404)

    if 'image' not in request.FILES:
        return JsonResponse({'error': 'No image file provided'}, status=400)

    image_file = request.FILES['image']

    # Validate file type
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml']
    if image_file.content_type not in allowed_types:
        return JsonResponse({'error': 'Invalid file type. Only images are allowed.'}, status=400)

    # Validate file size (max 5MB)
    max_size = 5 * 1024 * 1024 
    if image_file.size > max_size:
        return JsonResponse({'error': 'File too large. Maximum size is 5MB.'}, status=400)

    # Create the image record
    test_image = ScholarshipTestImage.objects.create(
        test=test,
        image=image_file,
        original_filename=image_file.name,
    )

    return JsonResponse({
        'success': True,
        'image': {
            'id': test_image.id,
            'url': test_image.get_image_url(),
            'filename': test_image.original_filename,
        }
    })


@csrf_exempt
def api_get_test_images(request, test_id):
   
    try:
        test = ScholarshipTest.objects.get(id=test_id)
    except ScholarshipTest.DoesNotExist:
        return JsonResponse({'error': 'Test not found'}, status=404)

    images = test.images.all()
    data = []
    for img in images:
        data.append({
            'id': img.id,
            'url': img.get_image_url(),
            'filename': img.original_filename,
            'uploaded_at': img.uploaded_at.isoformat(),
        })

    return JsonResponse({'images': data})


@csrf_exempt
def api_delete_image(request, test_id, image_id):
   
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    try:
        image = ScholarshipTestImage.objects.get(id=image_id, test_id=test_id)
    except ScholarshipTestImage.DoesNotExist:
        return JsonResponse({'error': 'Image not found'}, status=404)


    if image.image:
        image.image.delete(save=False)

    image.delete()
    return JsonResponse({'success': True})
