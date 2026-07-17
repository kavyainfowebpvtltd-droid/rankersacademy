"""
OTP Service for Bridge Course Login
Provides secure OTP generation, sending, and verification
"""

import random
import logging
import re
from datetime import timedelta
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

# OTP Configuration
OTP_LENGTH = 4  # 4-digit OTP
OTP_EXPIRY_MINUTES = 10  # 10 minutes expiry
MAX_RESEND_ATTEMPTS = 3  # Maximum resend attempts per hour
MAX_OTP_REQUESTS_PER_HOUR = 10  # Rate limiting


def _is_valid_person_name(name: str) -> bool:
    cleaned = (name or "").strip()
    return bool(cleaned) and bool(re.fullmatch(r"[A-Za-z ]+", cleaned))


def generate_otp():
    """
    Generate a random 4-digit OTP code.
    """
    return ''.join([str(random.randint(0, 9)) for _ in range(OTP_LENGTH)])


def get_otp_expiry_time():
    """
    Get the expiry time for a new OTP.
    """
    return timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)


def _msg91_send_otp(phone_10: str, otp_code: str = None):
    """
    Send OTP via MSG91 service
    """
    import requests
    
    auth_key = getattr(settings, 'MSG91_AUTH_KEY', None)
    if not auth_key:
        raise RuntimeError("MSG91_AUTH_KEY not configured")
    
    template_id = getattr(settings, 'MSG91_TEMPLATE_LOGIN', None)
    if not template_id:
        template_id = getattr(settings, 'MSG91_TEMPLATE_GENERAL', None)
        if not template_id:
            raise RuntimeError("MSG91_TEMPLATE_LOGIN not configured")
    
    country_code = getattr(settings, 'MSG91_COUNTRY_CODE', '91')
    mobile_with_cc = f"{country_code}{phone_10}"
    
    url = "https://control.msg91.com/api/v5/otp"
    
    query = {
        "mobile": mobile_with_cc,
        "authkey": auth_key,
        "template_id": template_id,
    }
    
    if otp_code:
        query["otp"] = otp_code
    
    # Set OTP expiry
    if hasattr(settings, 'MSG91_OTP_EXPIRY_MINUTES'):
        query["otp_expiry"] = OTP_EXPIRY_MINUTES
    
    headers = {
        "Content-Type": "application/json"
    }
    
    logger.info(f"Sending OTP to {mobile_with_cc}")
    
    try:
        r = requests.post(
            url,
            params=query,
            headers=headers,
            timeout=getattr(settings, "MSG91_TIMEOUT_SECONDS", 30),
        )
        
        logger.info(f"MSG91 response status: {r.status_code}")
        
        if r.status_code >= 400:
            raise RuntimeError(f"MSG91 send OTP failed ({r.status_code})")
        
        return r.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"MSG91 request failed: {str(e)}")
        raise RuntimeError(f"MSG91 request failed: {str(e)}")


def send_otp(phone_number: str, name: str, grade: str, board: str):
    
    from bridgecourse.models import BridgeCourseOTP
    
    # Normalize phone number (keep last 10 digits)
    phone = phone_number.replace('+91', '').replace(' ', '').replace('-', '')
    if len(phone) > 10:
        phone = phone[-10:]
    
    # Validate phone number
    if len(phone) != 10 or not phone.isdigit():
        return False, "Please enter a valid 10-digit mobile number"
    
    # Validate name
    if not name or len(name.strip()) < 2:
        return False, "Please enter a valid name"
    if not _is_valid_person_name(name):
        return False, "Name should contain only letters and spaces"
    
    # Validate grade
    valid_grades = ['8th', '9th', '10th', '11th', '12th']
    if grade not in valid_grades:
        return False, "Please select a valid grade"
    
    # Validate board
    valid_boards = ['State Board', 'CBSE', 'ICSE']
    if board not in valid_boards:
        return False, "Please select a valid board"
    
    # Check rate limiting - max OTP requests per hour
    one_hour_ago = timezone.now() - timedelta(hours=1)
    recent_otps = BridgeCourseOTP.objects.filter(
        phone_number=phone,
        created_at__gte=one_hour_ago
    ).count()
    
    if recent_otps >= MAX_OTP_REQUESTS_PER_HOUR:
        return False, "Too many OTP requests. Please try again after some time."
    
    # Check resend attempts for recent OTP
    recent_otp = BridgeCourseOTP.objects.filter(
        phone_number=phone,
        created_at__gte=timezone.now() - timedelta(minutes=30)
    ).order_by('-created_at').first()
    
    if recent_otp:
        if recent_otp.resend_count >= MAX_RESEND_ATTEMPTS:
            return False, "Maximum resend attempts reached. Please try again after 30 minutes."
    
    # Generate OTP
    otp_code = generate_otp()
    expires_at = get_otp_expiry_time()
    
    # Try to send via MSG91
    msg91_success = False
    try:
        _msg91_send_otp(phone, otp_code)
        msg91_success = True
        logger.info(f"OTP sent successfully via MSG91 to {phone}")
    except Exception as e:
        logger.warning(f"MSG91 sending failed: {str(e)}. Using mock OTP for development.")
      
    try:
        if recent_otp and not recent_otp.is_verified:
            recent_otp.otp_code = otp_code
            recent_otp.expires_at = expires_at
            recent_otp.resend_count = recent_otp.resend_count + 1
            recent_otp.name = name
            recent_otp.grade = grade
            recent_otp.board = board
            recent_otp.save()
            logger.info(f"OTP updated for {phone}: {otp_code}")
        else:
            otp_record = BridgeCourseOTP.objects.create(
                phone_number=phone,
                otp_code=otp_code,
                name=name,
                grade=grade,
                board=board,
                expires_at=expires_at,
                resend_count=0
            )
            logger.info(f"OTP record created for {phone}: {otp_code}")
    except Exception as e:
        logger.error(f"Failed to create OTP record: {str(e)}")
        return False, "Failed to generate OTP. Please try again."
    
    if msg91_success:
        return True, "OTP sent successfully"
    else:
        return True, f"OTP for testing: {otp_code}"


def verify_otp(phone_number: str, otp_code: str):
   
    from bridgecourse.models import BridgeCourseOTP
    
    # Normalize phone number
    phone = phone_number.replace('+91', '').replace(' ', '').replace('-', '')
    if len(phone) > 10:
        phone = phone[-10:]
    
    # Validate inputs
    if len(phone) != 10:
        return False, "Invalid phone number", None
    
    if len(otp_code) != OTP_LENGTH or not otp_code.isdigit():
        return False, "Invalid OTP format", None
    
   
    try:
        otp_record = BridgeCourseOTP.objects.filter(
            phone_number=phone,
            is_verified=False
        ).order_by('-created_at').first()
        
        if not otp_record:
            return False, "No OTP found. Please request a new OTP.", None
        
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        return False, "Database error. Please try again.", None
    
    # Check if OTP is expired
    if otp_record.is_expired():
        return False, "OTP has expired. Please request a new OTP.", None
    
    # Verify OTP
    if otp_record.otp_code != otp_code:
        # Increment failed attempts could be added here
        return False, "Incorrect OTP. Please try again.", None
    
    # Mark OTP as verified
    otp_record.is_verified = True
    otp_record.save()
    
    # Return user data
    user_data = {
        'name': otp_record.name,
        'phone_number': otp_record.phone_number,
        'grade': otp_record.grade,
        'board': otp_record.board,
        'section': 'A'
    }
    
    return True, "OTP verified successfully", user_data


def check_otp_expired(phone_number: str) -> bool:
   
    from bridgecourse.models import BridgeCourseOTP
    
    phone = phone_number.replace('+91', '').replace(' ', '').replace('-', '')
    if len(phone) > 10:
        phone = phone[-10:]
    
    otp_record = BridgeCourseOTP.objects.filter(
        phone_number=phone,
        is_verified=False
    ).order_by('-created_at').first()
    
    if not otp_record:
        return True
    
    return otp_record.is_expired()
