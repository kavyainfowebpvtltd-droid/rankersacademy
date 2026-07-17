from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.utils import timezone
import json
import logging
import re

logger = logging.getLogger(__name__)


def _is_valid_person_name(name: str) -> bool:
    cleaned = (name or "").strip()
    return bool(cleaned) and bool(re.fullmatch(r"^[A-Za-z ]+$", cleaned))




def bridgecourse_management(request):
    return render(request, "bridgecourse-management.html")


def bridge_course(request):
    """Bridge Course page - requires authentication"""
    if not request.session.get('bridge_course_authenticated'):
        from django.shortcuts import redirect
        return redirect('bridgecourse:bridge_course_login')
    user_data = {
        'name': request.session.get('bridge_course_name', ''),
        'grade': request.session.get('bridge_course_grade', ''),
        'board': request.session.get('bridge_course_board', ''),
        'section': request.session.get('bridge_course_section', 'A'),
        'phone': request.session.get('bridge_course_phone', ''),
    }
    return render(request, "bridge-course.html", {'user_data': user_data})


def bridge_course_login(request):
    return render(request, "bridge-course-login.html")


@csrf_protect
@require_POST
def bridge_course_send_otp(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request data'}, status=400)
    board = data.get('board', '').strip()
    grade = data.get('grade', '').strip()
    name = data.get('name', '').strip()
    mobile = data.get('mobile', '').strip()
    if not board:
        return JsonResponse({'success': False, 'error': 'Please select a board'}, status=400)
    if not grade:
        return JsonResponse({'success': False, 'error': 'Please select a class'}, status=400)
    if not name:
        return JsonResponse({'success': False, 'error': 'Please enter your name'}, status=400)
    if not mobile:
        return JsonResponse({'success': False, 'error': 'Please enter your mobile number'}, status=400)
    if not _is_valid_person_name(name):
        return JsonResponse({'success': False, 'error': 'Please enter a valid name (letters and spaces only)'}, status=400)
    if not re.match(r'^[0-9]{10}$', mobile):
        return JsonResponse({'success': False, 'error': 'Please enter a valid 10-digit mobile number'}, status=400)
    from bridgecourse.services import otp_service
    success, message = otp_service.send_otp(mobile, name, grade, board)
    if success:
        logger.info(f"OTP sent successfully to {mobile} for Bridge Course")
        return JsonResponse({'success': True, 'message': message})
    else:
        logger.warning(f"OTP send failed for {mobile}: {message}")
        return JsonResponse({'success': False, 'error': message}, status=400)


@csrf_protect
@require_POST
def bridge_course_verify_otp(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request data'}, status=400)
    mobile = data.get('mobile', '').strip()
    otp = data.get('otp', '').strip()
    if not mobile:
        return JsonResponse({'success': False, 'error': 'Mobile number is required'}, status=400)
    if not otp:
        return JsonResponse({'success': False, 'error': 'Please enter the OTP'}, status=400)
    if not re.match(r'^[0-9]{10}$', mobile):
        return JsonResponse({'success': False, 'error': 'Invalid mobile number format'}, status=400)
    from bridgecourse.services import otp_service
    success, message, user_data = otp_service.verify_otp(mobile, otp)
    if success and user_data:
        request.session['bridge_course_authenticated'] = True
        request.session['bridge_course_name'] = user_data['name']
        request.session['bridge_course_phone'] = user_data['phone_number']
        request.session['bridge_course_grade'] = user_data['grade']
        request.session['bridge_course_board'] = user_data['board']
        request.session['bridge_course_section'] = user_data.get('section', 'A')
        request.session['bridge_course_login_time'] = timezone.now().isoformat()
        request.session.set_expiry(86400)
        logger.info(f"Bridge Course login successful for {mobile}")
        return JsonResponse({
            'success': True,
            'message': 'Login successful',
            'redirect_url': '/bridgecourse/bridge-course/'
        })
    else:
        logger.warning(f"OTP verification failed for {mobile}: {message}")
        return JsonResponse({'success': False, 'error': message}, status=400)


def bridge_course_logout(request):
    keys_to_remove = [
        'bridge_course_authenticated',
        'bridge_course_name',
        'bridge_course_phone',
        'bridge_course_grade',
        'bridge_course_board',
        'bridge_course_login_time',
        'bridge_course_section'
    ]
    for key in keys_to_remove:
        if key in request.session:
            del request.session[key]
    return render(request, "bridge-course-login.html")


def bridge_course_login_only(request):
    """Bridge Course Login page - for existing registered users only"""
    return render(request, "bridge-course-login-only.html")


def bridge_course_register(request):
    """Bridge Course Registration page - for new users"""
    return render(request, "bridge-course-login.html")


@csrf_protect
@require_POST
def bridge_course_check_user(request):
    """Check if user exists with the given mobile number"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request data'}, status=400)
    
    mobile = data.get('mobile', '').strip()
    
    if not mobile:
        return JsonResponse({'success': False, 'error': 'Please enter your mobile number'}, status=400)
    
    if not re.match(r'^[0-9]{10}$', mobile):
        return JsonResponse({'success': False, 'error': 'Please enter a valid 10-digit mobile number'}, status=400)
    
    from bridgecourse.models import BridgeCourseOTP
    
   
    verified_otp = BridgeCourseOTP.objects.filter(
        phone_number=mobile,
        is_verified=True
    ).order_by('-created_at').first()
    
    if not verified_otp:
        return JsonResponse({'success': False, 'error': 'No registered user found with this mobile number. Please register first.'}, status=400)
    
   
    user_data = {
        'name': verified_otp.name,
        'phone_number': verified_otp.phone_number,
        'grade': verified_otp.grade,
        'board': verified_otp.board,
        'section': 'A'
    }
    
    return JsonResponse({'success': True, 'user_data': user_data})


@csrf_protect
@require_POST
def bridge_course_login_send_otp(request):
    """Send OTP for login - only for registered users"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request data'}, status=400)
    
    mobile = data.get('mobile', '').strip()
    
    if not mobile:
        return JsonResponse({'success': False, 'error': 'Please enter your mobile number'}, status=400)
    
    if not re.match(r'^[0-9]{10}$', mobile):
        return JsonResponse({'success': False, 'error': 'Please enter a valid 10-digit mobile number'}, status=400)
    
    from bridgecourse.models import BridgeCourseOTP
    from bridgecourse.services import otp_service
    
    
    verified_otp = BridgeCourseOTP.objects.filter(
        phone_number=mobile,
        is_verified=True
    ).order_by('-created_at').first()
    
    if not verified_otp:
        return JsonResponse({'success': False, 'error': 'No registered user found with this mobile number. Please register first.'}, status=400)
    
   
    name = verified_otp.name
    grade = verified_otp.grade
    board = verified_otp.board
    
   
    success, message = otp_service.send_otp(mobile, name, grade, board)
    
    if success:
        logger.info(f"Login OTP sent successfully to {mobile} for Bridge Course")
        return JsonResponse({'success': True, 'message': message})
    else:
        logger.warning(f"Login OTP send failed for {mobile}: {message}")
        return JsonResponse({'success': False, 'error': message}, status=400)


@csrf_protect
@require_POST
def bridge_course_login_verify_otp(request):
   
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request data'}, status=400)
    
    mobile = data.get('mobile', '').strip()
    otp = data.get('otp', '').strip()
    
    if not mobile:
        return JsonResponse({'success': False, 'error': 'Mobile number is required'}, status=400)
    if not otp:
        return JsonResponse({'success': False, 'error': 'Please enter the OTP'}, status=400)
    if not re.match(r'^[0-9]{10}$', mobile):
        return JsonResponse({'success': False, 'error': 'Invalid mobile number format'}, status=400)
    
    from bridgecourse.models import BridgeCourseOTP
    from bridgecourse.services import otp_service
    
  
    verified_otp = BridgeCourseOTP.objects.filter(
        phone_number=mobile,
        is_verified=True
    ).order_by('-created_at').first()
    
    if not verified_otp:
        return JsonResponse({'success': False, 'error': 'User not found. Please register first.'}, status=400)
    
    # Verify OTP
    success, message, user_data = otp_service.verify_otp(mobile, otp)
    
    if success and user_data:
       
        request.session['bridge_course_authenticated'] = True
        request.session['bridge_course_name'] = verified_otp.name
        request.session['bridge_course_phone'] = verified_otp.phone_number
        request.session['bridge_course_grade'] = verified_otp.grade
        request.session['bridge_course_board'] = verified_otp.board
        request.session['bridge_course_section'] = 'A'
        request.session.set_expiry(86400)
        
        logger.info(f"Bridge Course login successful for {mobile}")
        return JsonResponse({
            'success': True,
            'message': 'Login successful',
            'redirect_url': '/bridgecourse/bridge-course/'
        })
    else:
        logger.warning(f"Login OTP verification failed for {mobile}: {message}")
        return JsonResponse({'success': False, 'error': message}, status=400)


@csrf_exempt
def get_subjects(request):
    from .models import BridgeSubject
    grade = request.GET.get('grade')
    board = request.GET.get('board')
    subjects_qs = BridgeSubject.objects.all()
    if grade:
        subjects_qs = subjects_qs.filter(grade=grade)
    if board:
        subjects_qs = subjects_qs.filter(board=board)
    subjects = subjects_qs.values('id', 'subject_name', 'grade', 'board')
    return JsonResponse(list(subjects), safe=False)


@csrf_exempt
@require_http_methods(["POST"])
def add_subject(request):
    from .models import BridgeSubject
    data = json.loads(request.body)
    subject = BridgeSubject.objects.create(
        subject_name=data.get('subject_name'),
        grade=data.get('grade'),
        board=data.get('board')
    )
    return JsonResponse({'id': subject.id, 'subject_name': subject.subject_name, 'grade': subject.grade, 'board': subject.board})


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_subject(request, subject_id):
    from .models import BridgeSubject
    try:
        subject = BridgeSubject.objects.get(id=subject_id)
        subject.delete()
        return JsonResponse({'success': True})
    except BridgeSubject.DoesNotExist:
        return JsonResponse({'error': 'Subject not found'}, status=404)


@csrf_exempt
def get_lectures(request):
    from .models import BridgeLecture
    subject_id = request.GET.get('subject_id')
    lectures_list = []
    if subject_id:
        lectures = BridgeLecture.objects.filter(subject_id=subject_id)
    else:
        lectures = BridgeLecture.objects.all()
    
    for lecture in lectures:
        lectures_list.append({
            'id': lecture.id,
            'subject_id': lecture.subject_id,
            'day_number': lecture.day_number,
            'topic_name': lecture.topic_name,
            'lecture_number': lecture.lecture_number,
            'video_url': lecture.video_url,
            'notes_file': lecture.notes_file.url if lecture.notes_file else ''
        })
    return JsonResponse(lectures_list, safe=False)


@csrf_exempt
@require_http_methods(["POST"])
def add_lecture(request):
    from .models import BridgeLecture, BridgeSubject
    try:
        subject_id = request.POST.get('subject_id')
        day_number = request.POST.get('day_number')
        topic_name = request.POST.get('topic_name')
        lecture_number = request.POST.get('lecture_number')
        video_url = request.POST.get('video_url')
        notes_file = request.FILES.get('notes_file')
        
        # Validate PDF file
        if notes_file:
            if notes_file.content_type != 'application/pdf':
                return JsonResponse({'error': 'Only PDF files are allowed'}, status=400)
            # Limit file size to 10MB
            if notes_file.size > 10 * 1024 * 1024:
                return JsonResponse({'error': 'File size must be less than 10MB'}, status=400)
        
        # Convert day_number to integer
        try:
            day_number = int(day_number) if day_number else 0
        except (ValueError, TypeError):
            day_number = 0
        
        subject = BridgeSubject.objects.get(id=subject_id)
        
        lecture = BridgeLecture.objects.create(
            subject=subject,
            day_number=day_number,
            topic_name=topic_name,
            lecture_number=lecture_number,
            video_url=video_url,
            notes_file=notes_file
        )
        
        return JsonResponse({
            'id': lecture.id,
            'subject_id': lecture.subject_id,
            'day_number': lecture.day_number,
            'topic_name': lecture.topic_name,
            'lecture_number': lecture.lecture_number,
            'video_url': lecture.video_url,
            'notes_file': lecture.notes_file.url if lecture.notes_file else None
        })
    except BridgeSubject.DoesNotExist:
        return JsonResponse({'error': 'Subject not found'}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': 'Error: ' + str(e)}, status=400)


@csrf_exempt
def update_lecture(request):
    from .models import BridgeLecture
    import sys
    print("UPDATE LECTURE VIEW CALLED", file=sys.stderr)
    print(f"REQUEST METHOD: {request.method}", file=sys.stderr)
    print(f"REQUEST POST: {request.POST}", file=sys.stderr)
    try:
        if request.method != 'POST':
            return JsonResponse({'error': 'Only POST method allowed'}, status=405)
        
        # Get form data
        lecture_id = request.POST.get('lecture_id')
        day_number = request.POST.get('day_number', '')
        topic_name = request.POST.get('topic_name', '')
        lecture_number = request.POST.get('lecture_number', '')
        video_url = request.POST.get('video_url', '')
        notes_file = request.FILES.get('notes_file')
        
        # Debug
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"UPDATE LECTURE - Received: lecture_id={lecture_id}, day={day_number}, topic={topic_name}")
        
        # Only validate lecture_id is provided
        if not lecture_id:
            return JsonResponse({'error': 'Lecture ID is required'}, status=400)
        
        # Convert lecture_id to integer
        try:
            lecture_id = int(lecture_id)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid lecture ID'}, status=400)
        
        # Get the lecture
        try:
            lecture = BridgeLecture.objects.get(id=lecture_id)
        except BridgeLecture.DoesNotExist:
            return JsonResponse({'error': 'Lecture not found'}, status=404)
        
        # Update fields
        if day_number:
            try:
                lecture.day_number = int(day_number)
            except (ValueError, TypeError):
                pass
        if topic_name:
            lecture.topic_name = topic_name
        if lecture_number:
            lecture.lecture_number = lecture_number
        if video_url:
            lecture.video_url = video_url
        if notes_file:
            if notes_file.content_type != 'application/pdf':
                return JsonResponse({'error': 'Only PDF files are allowed'}, status=400)
            if notes_file.size > 10 * 1024 * 1024:
                return JsonResponse({'error': 'File size must be less than 10MB'}, status=400)
            lecture.notes_file = notes_file
        
        lecture.save()
        
        return JsonResponse({
            'id': lecture.id,
            'subject_id': lecture.subject_id,
            'day_number': lecture.day_number,
            'topic_name': lecture.topic_name,
            'lecture_number': lecture.lecture_number,
            'video_url': lecture.video_url,
            'notes_file': lecture.notes_file.url if lecture.notes_file else None
        })
    except BridgeLecture.DoesNotExist:
        return JsonResponse({'error': 'Lecture not found'}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': 'Error: ' + str(e)}, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_lecture(request, lecture_id):
    from .models import BridgeLecture
    try:
        lecture = BridgeLecture.objects.get(id=lecture_id)
        lecture.delete()
        return JsonResponse({'success': True})
    except BridgeLecture.DoesNotExist:
        return JsonResponse({'error': 'Lecture not found'}, status=404)


@csrf_exempt
def get_lecture_notes(request, lecture_id):
    from .models import BridgeLecture
    try:
        lecture = BridgeLecture.objects.get(id=lecture_id)
        if lecture.notes_file:
            return JsonResponse({
                'notes_file': lecture.notes_file.url,
                'notes_file_name': lecture.notes_file.name
            })
        else:
            return JsonResponse({'error': 'No notes file found'}, status=404)
    except BridgeLecture.DoesNotExist:
        return JsonResponse({'error': 'Lecture not found'}, status=404)


@csrf_protect
@require_POST
def track_video_progress(request):
    """
    Track video watch progress for bridge course lectures
    Stores max watch time, min watch time and watch count for each user-lecture combination
    """
    from .models import BridgeLecture, BridgeLectureProgress
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request data'}, status=400)
    
    phone_number = data.get('phone_number', '').strip()
    user_name = data.get('user_name', '').strip()
    lecture_id = data.get('lecture_id')
    watch_time = data.get('watch_time', 0)  # in seconds
    watched_at = data.get('watched_at')  # timestamp when video is watched
    
    # Validate required fields
    if not phone_number:
        return JsonResponse({'success': False, 'error': 'Phone number is required'}, status=400)
    if not lecture_id:
        return JsonResponse({'success': False, 'error': 'Lecture ID is required'}, status=400)
    if not user_name:
        return JsonResponse({'success': False, 'error': 'User name is required'}, status=400)
    
    # Validate phone number format
    if not re.match(r'^[0-9]{10}$', phone_number):
        return JsonResponse({'success': False, 'error': 'Invalid phone number format'}, status=400)
    
    try:
        lecture_id = int(lecture_id)
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid lecture ID'}, status=400)
    
    try:
        lecture = BridgeLecture.objects.get(id=lecture_id)
    except BridgeLecture.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Lecture not found'}, status=404)
    
    # Get or create progress record
    progress, created = BridgeLectureProgress.objects.get_or_create(
        phone_number=phone_number,
        lecture=lecture,
        user_name=user_name,
        defaults={'max_watch_time': 0, 'min_watch_time': 0, 'watch_count': 0}
    )
    
    # Update watch count (increment by 1 each time video is watched)
    progress.watch_count += 1
    
    # Update max watch time if current watch time is greater
    if watch_time > progress.max_watch_time:
        progress.max_watch_time = watch_time
    
    # Update min watch time if current watch time is less (or if min is 0)
    if progress.min_watch_time == 0 or watch_time < progress.min_watch_time:
        progress.min_watch_time = watch_time
    
    # Update last_watched_at with the client-provided timestamp if available
    if watched_at:
        try:
            # Parse the local time string from client (format: YYYY-MM-DD HH:MM:SS)
            from datetime import datetime
            watched_dt = datetime.strptime(watched_at, '%Y-%m-%d %H:%M:%S')
            progress.last_watched_at = watched_dt
            # Also store the time string directly for accurate display
            progress.last_watched_time = watched_at.split(' ')[1] if ' ' in watched_at else watched_at
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid watched_at timestamp: {watched_at}, using server time")
            progress.last_watched_at = timezone.now()
            progress.last_watched_time = timezone.now().strftime('%H:%M:%S')
    else:
        progress.last_watched_at = timezone.now()
        progress.last_watched_time = timezone.now().strftime('%H:%M:%S')
    
    progress.save()
    
    logger.info(f"Video progress tracked for user {user_name} ({phone_number}), lecture {lecture_id}: max_time={progress.max_watch_time}s, min_time={progress.min_watch_time}s, count={progress.watch_count}, watched_at={progress.last_watched_at}")
    
    return JsonResponse({
        'success': True,
        'max_watch_time': progress.max_watch_time,
        'min_watch_time': progress.min_watch_time,
        'watch_count': progress.watch_count
    })
