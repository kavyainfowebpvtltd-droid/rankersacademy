import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def send_scholarship_result_sms(phone_number: str, student_name: str, score: int, 
                                 total_questions: int, scholarship_percentage: int):

    # Normalize phone number
    phone = phone_number.replace('+91', '').replace(' ', '').replace('-', '')
    if len(phone) > 10:
        phone = phone[-10:]
    
    # Prepare SMS message
    message = (
        f"Dear {student_name}, "
        f"Congratulations! You have completed RTSE-2026. "
        f"Your Score: {score}/{total_questions}. "
        f"Scholarship Awarded: {scholarship_percentage}%. "
        f"Contact Ranker's Academy to claim your scholarship. "
        f"Thank you!"
    )
    
    return _send_sms(phone, message)


def send_scholarship_result_sms_dlt(phone_number: str, student_name: str, score: int, 
                                     total_questions: int, scholarship_percentage: int):
    
    import http.client
    import re
    import json

    
   
    phone = re.sub(r'\D', '', str(phone_number))
    
   
    if phone.startswith('91') and len(phone) > 10:
        phone = phone[2:]
    
   
    if not phone or len(phone) != 10 or not phone.isdigit():
        logger.error(f"Invalid phone number format after normalization: '{phone_number}' -> '{phone}'")
        return False, f"Invalid phone number format: {phone_number}"
    
    # Get settings
    auth_key = getattr(settings, 'MSG91_AUTH_KEY', None)
    # Template ID from settings: 1207177329008677759
    template_id = getattr(settings, 'MSG91_TEMPLATE_SCHOLARSHIP_RESULT', '1207177329008677759')
    academy_contact = getattr(settings, 'SCHOLARSHIP_ACADEMY_CONTACT', '8329100890')
    
    if not auth_key:
        logger.error("MSG91_AUTH_KEY not configured")
        return False, "SMS service not configured - missing auth key"
    
  
    academy_contact = re.sub(r'\D', '', str(academy_contact))
    if len(academy_contact) > 10:
        academy_contact = academy_contact[-10:]
    
    logger.info(f"Sending scholarship result SMS to {phone}")
    logger.info(f"Student: {student_name}, Score: {score}/{total_questions}, Scholarship: {scholarship_percentage}%")
    logger.info(f"Template ID: {template_id}, Academy Contact: {academy_contact}")
    
   
    var1 = str(student_name) if student_name else ''
    var2 = str(score) if score is not None else ''
    var3 = str(total_questions) if total_questions is not None else ''
    var4 = str(scholarship_percentage) if scholarship_percentage is not None else ''
    var5 = str(scholarship_percentage) if scholarship_percentage is not None else ''
    var6 = str(academy_contact) if academy_contact else ''
    
    payload = """{{"template_id": "{template_id}", "short_url": "0", "short_url_expiry": "120", "realTimeResponse": "1", "recipients": [{{"mobiles": "91{phone}", "name": "{name}", "score": "{score}", "total": "{total}", "percentage": "{percentage}", "scholarship": "{scholarship}", "mobile": "{mobile}"}}]}}""".format(
        template_id=template_id,
        phone=phone,
        name=var1,
        score=var2,
        total=var3,
        percentage=var4,
        scholarship=var5,
        mobile=var6
    )
    
    headers = {
        'accept': "application/json",
        'authkey': auth_key,
        'content-type': "application/json"
    }
    
    logger.info(f"MSG91 Request Payload: {payload}")
    
   
    try:
        conn = http.client.HTTPSConnection("control.msg91.com")
        conn.request("POST", "/api/v5/flow", payload, headers)
        
        res = conn.getresponse()
        data = res.read()
        response_text = data.decode("utf-8")
        
        logger.info(f"MSG91 HTTP response status: {res.status}")
        logger.info(f"MSG91 HTTP response body: {response_text}")
        
        conn.close()
        
        # Check response
        if res.status == 200:
            # Check if response contains success
            if '"type":"success"' in response_text or '"type" : "success"' in response_text:
                logger.info(f"Scholarship result SMS sent successfully to {phone}")
                return True, "SMS sent successfully"
            elif 'success' in response_text.lower():
                logger.info(f"Scholarship result SMS sent successfully to {phone}")
                return True, "SMS sent successfully"
            else:
                logger.error(f"MSG91 API error: {response_text}")
                return False, f"SMS sending failed: {response_text[:100]}"
        else:
            logger.error(f"MSG91 HTTP error: {res.status}")
            logger.error(f"Response: {response_text}")
            return False, f"HTTP error: {res.status} - {response_text[:100]}"
            
    except Exception as e:
        logger.error(f"MSG91 request failed: {str(e)}", exc_info=True)
        return False, f"SMS service error: {str(e)}"


def _send_sms(phone_number: str, message: str):
    
    logger.info("=" * 60)
    logger.info("DUMMY SMS - Scholarship Result")
    logger.info("=" * 60)
    logger.info(f"To: +91{phone_number}")
    logger.info(f"Message: {message}")
    logger.info("=" * 60)
    
   
    return True, "SMS sent successfully (dummy)"


def _send_sms_msg91(phone_number: str, message: str, template_id: str = None):

    import requests
    
   
    auth_key = getattr(settings, 'MSG91_AUTH_KEY', None)
    if not auth_key:
        logger.error("MSG91_AUTH_KEY not configured")
        return False, "SMS service not configured"
    
   
    if not template_id:
        template_id = getattr(settings, 'MSG91_TEMPLATE_GENERAL', None)
    
  
    country_code = getattr(settings, 'MSG91_COUNTRY_CODE', '91')
    mobile_with_cc = f"{country_code}{phone_number}"
    
    url = "https://api.msg91.com/api/v2/sendsms"
    
    payload = {
        "sender": "RANKER",
        "route": "4",
        "country": country_code,
        "sms": [
            {
                "message": message,
                "to": [mobile_with_cc]
            }
        ]
    }
    
    if template_id:
        payload["template_id"] = template_id
    
    headers = {
        "authkey": auth_key,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('type') == 'success':
                return True, "SMS sent successfully"
            else:
                logger.error(f"MSG91 API error: {data}")
                return False, data.get('message', 'SMS sending failed')
        else:
            logger.error(f"MSG91 HTTP error: {response.status_code}")
            return False, "SMS sending failed"
            
    except requests.exceptions.RequestException as e:
        logger.error(f"MSG91 request failed: {str(e)}")
        return False, "SMS service error"


def send_result_notification(phone_number: str, student_name: str, attempt_id: int):
   
    message = (
        f"Dear {student_name}, "
        f"Your RTSE-2026 results are ready! "
        f"Login to view your score and scholarship percentage. "
        f"Reference: RTSE-{attempt_id}"
    )
    
    return _send_sms(phone_number, message)


def send_success_sms(phone_number: str, var1: str = None, var2: str = None, var3: str = None,
                     var4: str = None, var5: str = None, var6: str = None):
   
    import http.client
    import re
    import json
    
  
    phone = re.sub(r'\D', '', str(phone_number))
    
   
    if phone.startswith('91') and len(phone) > 10:
        phone = phone[2:]
    
   
    if not phone or len(phone) != 10 or not phone.isdigit():
        logger.error(f"Invalid phone number format after normalization: '{phone_number}' -> '{phone}'")
        return False, f"Invalid phone number format: {phone_number}"
    
    auth_key = getattr(settings, 'MSG91_AUTH_KEY', None)
    template_id = getattr(settings, 'MSG91_TEMPLATE_SUCCESS', '69b5210880847f675605d7b3')
    
    if not auth_key:
        logger.error("MSG91_AUTH_KEY not configured")
        return False, "SMS service not configured - missing auth key"
    
    logger.info(f"Sending success SMS to {phone}")
    logger.info(f"VAR1: {var1}, VAR2: {var2}, VAR3: {var3}, VAR4: {var4}, VAR5: {var5}, VAR6: {var6}")
    
    var1_str = str(var1) if var1 else ''
    var2_str = str(var2) if var2 else ''
    var3_str = str(var3) if var3 else ''
    var4_str = str(var4) if var4 else ''
    var5_str = str(var5) if var5 else ''
    var6_str = str(var6) if var6 else ''
    
    payload = """{{"template_id": "{template_id}", "short_url": "0", "short_url_expiry": "120", "realTimeResponse": "1", "recipients": [{{"mobiles": "91{phone}", "name": "{name}", "score": "{score}", "total": "{total}", "percentage": "{percentage}", "scholarship": "{scholarship}", "mobile": "{mobile}"}}]}}""".format(
        template_id=template_id,
        phone=phone,
        name=var1_str,
        score=var2_str,
        total=var3_str,
        percentage=var4_str,
        scholarship=var5_str,
        mobile=var6_str
    )
    
    headers = {
        'accept': "application/json",
        'authkey': auth_key,
        'content-type': "application/json"
    }
    
    logger.info(f"MSG91 Request Payload: {payload}")
    
    try:
        conn = http.client.HTTPSConnection("control.msg91.com")
        conn.request("POST", "/api/v5/flow", payload, headers)
        
        res = conn.getresponse()
        data = res.read()
        response_text = data.decode("utf-8")
        
        logger.info(f"MSG91 HTTP response status: {res.status}")
        logger.info(f"MSG91 HTTP response body: {response_text}")
        
        conn.close()
        
        if res.status == 200:
           
            if '"type":"success"' in response_text or '"type" : "success"' in response_text:
                logger.info(f"Success SMS sent successfully to {phone}")
                return True, "SMS sent successfully"
            elif 'success' in response_text.lower():
                logger.info(f"Success SMS sent successfully to {phone}")
                return True, "SMS sent successfully"
            else:
                logger.error(f"MSG91 API error: {response_text}")
                return False, f"SMS sending failed: {response_text[:100]}"
        else:
            logger.error(f"MSG91 HTTP error: {res.status}")
            logger.error(f"Response: {response_text}")
            return False, f"HTTP error: {res.status} - {response_text[:100]}"
            
    except Exception as e:
        logger.error(f"MSG91 request failed: {str(e)}", exc_info=True)
        return False, f"SMS service error: {str(e)}"


def send_scholarship_success_sms(phone_number: str, student_name: str, score: int,
                                  total_questions: int, scholarship_percentage: int,
                                  academy_contact: str = None):
  
    import re
    
   
    if not academy_contact:
        academy_contact = getattr(settings, 'SCHOLARSHIP_ACADEMY_CONTACT', '8329100890')
    
    academy_contact = re.sub(r'\D', '', str(academy_contact))
    if len(academy_contact) > 10:
        academy_contact = academy_contact[-10:]
    
    return send_success_sms(
        phone_number=phone_number,
        var1=student_name,
        var2=str(score),
        var3=str(total_questions),
        var4=str(scholarship_percentage),
        var5=str(scholarship_percentage),
        var6=academy_contact
    )


def send_test_result_sms_dlt(
    phone_number: str,
    student_name: str,
    test_name: str,
    score: int,
    total_questions: int,
    percentage: int | float,
    academy_contact: str = None,
):
    import re

    if not academy_contact:
        academy_contact = getattr(settings, 'SCHOLARSHIP_ACADEMY_CONTACT', '8329100890')

    academy_contact = re.sub(r'\D', '', str(academy_contact))
    if len(academy_contact) > 10:
        academy_contact = academy_contact[-10:]

    safe_test_name = str(test_name or "Test Result")

    return send_success_sms(
        phone_number=phone_number,
        var1=student_name,
        var2=str(score),
        var3=str(total_questions),
        var4=str(percentage),
        var5=safe_test_name[:30],
        var6=academy_contact,
    )
