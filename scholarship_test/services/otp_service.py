
import random
import logging
from datetime import timedelta
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

# OTP Configuration
OTP_LENGTH = 4  # 4-digit OTP as per requirements
OTP_EXPIRY_MINUTES = 5  # 5 minutes expiry
MAX_RESEND_ATTEMPTS = 3  # Maximum resend attempts


def generate_otp():
    
    return ''.join([str(random.randint(0, 9)) for _ in range(OTP_LENGTH)])


def get_otp_expiry_time():
   
    return timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)


def _msg91_send_otp(phone_10: str, template_id: str = None):
   
    import requests
    
    # Get MSG91 configuration
    auth_key = getattr(settings, 'MSG91_AUTH_KEY', None)
    if not auth_key:
        raise RuntimeError("MSG91_AUTH_KEY not configured")
    
    if not template_id:
        template_id = getattr(settings, 'MSG91_TEMPLATE_GENERAL', None)
        if not template_id:
            raise RuntimeError("MSG91_TEMPLATE_GENERAL not configured")
    
    country_code = getattr(settings, 'MSG91_COUNTRY_CODE', '91')
    mobile_with_cc = f"{country_code}{phone_10}"
    
    url = "https://control.msg91.com/api/v5/otp"
    
    query = {
        "mobile": mobile_with_cc,
        "authkey": auth_key,
        "template_id": template_id,
    }
    
    # Set OTP expiry
    if hasattr(settings, 'MSG91_OTP_EXPIRY_MINUTES'):
        query["otp_expiry"] = OTP_EXPIRY_MINUTES
    
    headers = {
        "Content-Type": "application/json"
    }
    
    logger.info(f"Sending OTP to {mobile_with_cc} with template_id: {template_id}")
    
    try:
        r = requests.post(
            url,
            json=query,
            headers=headers,
            timeout=getattr(settings, "MSG91_TIMEOUT_SECONDS", 30),
        )
        
        logger.info(f"MSG91 response status: {r.status_code}, body: {r.text}")
        
        if r.status_code >= 400:
            raise RuntimeError(f"MSG91 send OTP failed ({r.status_code}): {r.text}")
        
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        
        if isinstance(data, dict):
            if data.get("type") == "error" or data.get("status") == "error":
                raise RuntimeError(f"MSG91 API error: {data}")
        
        return data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        raise RuntimeError(f"MSG91 request failed: {str(e)}")


def _msg91_verify_otp(phone_10: str, otp: str):
   
    import requests
    
    auth_key = getattr(settings, 'MSG91_AUTH_KEY', None)
    if not auth_key:
        raise RuntimeError("MSG91_AUTH_KEY not configured")
    
    country_code = getattr(settings, 'MSG91_COUNTRY_CODE', '91')
    mobile_with_cc = f"{country_code}{phone_10}"
    
    url = "https://control.msg91.com/api/v5/otp/verify"
    query = {"otp": otp, "mobile": mobile_with_cc}
    headers = {"authkey": auth_key}
    
    r = requests.get(
        url,
        params=query,
        headers=headers,
        timeout=getattr(settings, "MSG91_TIMEOUT_SECONDS", 10),
    )
    
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    
    if r.status_code >= 400:
        raise RuntimeError(f"MSG91 verify OTP failed ({r.status_code}): {data}")
    
    return data


def _is_msg91_verified(resp: dict) -> bool:
   
    t = str(resp.get("type", "")).lower()
    s = str(resp.get("status", "")).lower()
    msg = str(resp.get("message", "")).lower()
    
    if t in ("success", "verified", "ok"):
        return True
    if s in ("success", "verified", "ok"):
        return True
    if "verified" in msg and "not" not in msg:
        return True
    
    if t in ("error", "failure", "failed") or s in ("error", "failure", "failed"):
        return False
    
    return False


def send_otp(phone_number: str, student=None):
   
    from scholarship_test.models import ScholarshipOTP
    
   
    phone = phone_number.replace('+91', '').replace(' ', '').replace('-', '')
    if len(phone) > 10:
        phone = phone[-10:]
    
    # Validate phone number
    if len(phone) != 10 or not phone.isdigit():
        return False, "Please enter a valid 10-digit mobile number"
    
    # Check resend attempts
    recent_otps = ScholarshipOTP.objects.filter(
        phone_number=phone,
        created_at__gte=timezone.now() - timedelta(minutes=30)
    ).order_by('-created_at')
    
    if recent_otps.exists():
        last_otp = recent_otps.first()
        if last_otp.resend_count >= MAX_RESEND_ATTEMPTS:
            return False, "Maximum resend attempts reached. Please try again after 30 minutes."
    
    # Generate OTP
    otp_code = generate_otp()
    expires_at = get_otp_expiry_time()
    
    # Try to send via MSG91
    try:
        _msg91_send_otp(phone)
        logger.info(f"OTP sent successfully via MSG91 to {phone}")
    except Exception as e:
       
        logger.warning(f"MSG91 sending failed: {str(e)}. Using mock OTP for development.")
    
    # Store OTP in database
    try:
        otp_record = ScholarshipOTP.objects.create(
            student=student,
            phone_number=phone,
            otp_code=otp_code,
            expires_at=expires_at,
            resend_count=0
        )
        logger.info(f"OTP record created for {phone}: {otp_code}")
    except Exception as e:
        logger.error(f"Failed to create OTP record: {str(e)}")
        return False, "Failed to generate OTP. Please try again."
    
    return True, "OTP sent successfully"


def verify_otp(phone_number: str, otp_code: str):
   
    from scholarship_test.models import ScholarshipOTP, ScholarshipStudent
    
    # Normalize phone number
    phone = phone_number.replace('+91', '').replace(' ', '').replace('-', '')
    if len(phone) > 10:
        phone = phone[-10:]
    
    # Validate inputs
    if len(phone) != 10:
        return False, "Invalid phone number", None
    
    if len(otp_code) != OTP_LENGTH or not otp_code.isdigit():
        return False, "Invalid OTP format", None
    
    # Get the most recent unverified OTP for this phone
    try:
        otp_record = ScholarshipOTP.objects.filter(
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
    
    msg91_verified = False
    try:
        resp = _msg91_verify_otp(phone, otp_code)
        msg91_verified = _is_msg91_verified(resp)
        logger.info(f"MSG91 verification result: {msg91_verified}")
    except Exception as e:
        logger.warning(f"MSG91 verification failed: {str(e)}. Using local verification.")
    
    if not msg91_verified:
        if otp_record.otp_code != otp_code:
            return False, "Incorrect OTP. Please try again.", None
    
    # Mark OTP as verified
    otp_record.is_verified = True
    otp_record.save()
    

    student, created = ScholarshipStudent.objects.get_or_create(
        phone_number=phone,
        defaults={
            'name': '',
            'grade': '',
            'board': '',
            'otp_verified': True
        }
    )
    
    # Log for debugging
    if created:
        logger.info(f"New student created with phone: {phone}")
    else:
        logger.info(f"Existing student found with phone: {phone}, name: {student.name}")
    
    # Always mark as OTP verified
    student.otp_verified = True
    
   
    student.save()
    
    return True, "OTP verified successfully", student


def resend_otp(phone_number: str):
   
    from scholarship_test.models import ScholarshipOTP
    
    # Normalize phone number
    phone = phone_number.replace('+91', '').replace(' ', '').replace('-', '')
    if len(phone) > 10:
        phone = phone[-10:]
    
    # Check if there's a recent OTP
    recent_otp = ScholarshipOTP.objects.filter(
        phone_number=phone,
        created_at__gte=timezone.now() - timedelta(minutes=30)
    ).order_by('-created_at').first()
    
    if recent_otp:
        if recent_otp.resend_count >= MAX_RESEND_ATTEMPTS:
            return False, "Maximum resend attempts reached. Please try again after 30 minutes."
        
        # Increment resend count
        recent_otp.resend_count += 1
        recent_otp.save()
    
    # Send new OTP
    return send_otp(phone)


def check_otp_expired(phone_number: str) -> bool:
   
    from scholarship_test.models import ScholarshipOTP
    
    phone = phone_number.replace('+91', '').replace(' ', '').replace('-', '')
    if len(phone) > 10:
        phone = phone[-10:]
    
    otp_record = ScholarshipOTP.objects.filter(
        phone_number=phone,
        is_verified=False
    ).order_by('-created_at').first()
    
    if not otp_record:
        return True  
    
    return otp_record.is_expired()
