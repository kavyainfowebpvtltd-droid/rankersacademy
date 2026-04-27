from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Avg, FloatField, OuterRef, Subquery, Value, DecimalField, Count, Prefetch
from django.db.models.functions import Coalesce, Cast
from django.contrib import messages
from django.core.mail import send_mail
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache, cache_control
from django.views.decorators.http import require_POST, require_GET
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.http import JsonResponse, FileResponse, Http404
from django.db import transaction
from django.core.cache import cache
import json
import os
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.db.models import Q
from django.utils import timezone
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image)
from reportlab.pdfgen import canvas
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password

import random
import re
import requests
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, urlsplit

from .models import *
from .password_policy import (
    DEFAULT_ONE_TIME_PASSWORD,
    clear_password_change_flag,
    user_needs_password_change,
)


# Login and Logout Views

def _redirect_authenticated_user_home(user):
    if user_needs_password_change(user):
        return redirect("force_password_change")
    if hasattr(user, "student"):
        return redirect("student-dashboard")
    if _is_admin_or_teacher(user):
        return redirect("admin-dashboard")
    return redirect("login")


SCHOLARSHIP_LAUNCH_PATH_RE = re.compile(r"^/scholarship/launch/(?P<test_id>\d+)/?$")


def _extract_scholarship_launch_test_id(next_url: str):
    path = urlsplit(next_url or "").path
    match = SCHOLARSHIP_LAUNCH_PATH_RE.match(path)
    if not match:
        return None

    try:
        return int(match.group("test_id"))
    except (TypeError, ValueError):
        return None


def _is_password_only_test_next_url(next_url: str) -> bool:
    path = urlsplit(next_url or "").path
    if path.startswith("/test/"):
        return True

    test_id = _extract_scholarship_launch_test_id(next_url)
    if not test_id:
        return False

    try:
        from scholarship_test.services import test_service as scholarship_test_service

        scholarship_test = scholarship_test_service.get_test_by_id(test_id)
        return bool(scholarship_test) and not scholarship_test_service.requires_otp_login(
            scholarship_test
        )
    except Exception:
        return False


@csrf_protect
def login_view(request):
    MAX_LOGIN_ATTEMPTS = getattr(settings, 'MAX_LOGIN_ATTEMPTS', 5)
    LOCKOUT_DURATION_SECONDS = getattr(settings, 'LOGIN_LOCKOUT_SECONDS', 900)
    
    if request.method == "POST":
        identifier = request.POST.get("username")
        password = request.POST.get("password")
        role = request.POST.get("role")

        if not identifier or not password or not role:
            messages.error(request, "All fields are required")
            return redirect("login")

        ip_key = f"login_ip:{request.META.get('REMOTE_ADDR', 'unknown')}"
        ip_data = _cache_get(ip_key)
        if ip_data and ip_data.get('locked', False):
            lockout_end = ip_data.get('lockout_end', 0)
            from django.utils import timezone
            now = timezone.now().timestamp()
            if lockout_end > now:
                remaining = int(lockout_end - now)
                minutes = remaining // 60
                seconds = remaining % 60
                messages.error(request, f"Too many failed attempts. Please try again in {minutes} minutes {seconds} seconds.")
                return redirect("login")
            else:
                cache.delete(ip_key)

        username_key = f"login_attempts:{identifier.lower()}"
        attempt_data = _cache_get(username_key)
        if attempt_data and attempt_data.get('locked', False):
            lockout_end = attempt_data.get('lockout_end', 0)
            from django.utils import timezone
            now = timezone.now().timestamp()
            if lockout_end > now:
                remaining = int(lockout_end - now)
                minutes = remaining // 60
                seconds = remaining % 60
                messages.error(request, f"Account temporarily locked due to too many failed attempts. Please try again in {minutes} minutes {seconds} seconds.")
                return redirect("login")
            else:
                cache.delete(username_key)
                attempt_data = None

        try:
            user_obj = User.objects.get(Q(username=identifier) | Q(email=identifier))
        except User.DoesNotExist:
            _increment_failed_attempts(request, identifier, ip_key, ip_data, username_key, attempt_data)
            messages.error(request, "Invalid credentials")
            return redirect("login")

        user = authenticate(request, username=user_obj.username, password=password)

        if not user or not user.is_active:
            _increment_failed_attempts(request, identifier, ip_key, ip_data, username_key, attempt_data)
            messages.error(request, "Invalid credentials")
            return redirect("login")

        cache.delete(username_key)
        cache.delete(ip_key)
        
        # Get intended redirect URL (if any)
        next_url = request.POST.get('next', '').strip()

        login(request, user)

        if user_needs_password_change(user):
            return redirect("force_password_change")

        # If user is trying to access diagnostic test
        if next_url and _is_password_only_test_next_url(next_url):
            if not hasattr(user, 'student'):
                messages.error(request, "Student profile not found. Please contact admin.")
                return redirect('login')
            # User should be student role
            if role == "Student":
                return redirect(next_url)
            else:
                messages.error(request, "Only students can access the diagnostic test.")
                return redirect('login')

        if role == "Student":
            if hasattr(user, "student"):
                return redirect("student-dashboard")
            messages.error(request, "You are not registered as a student")
            return redirect("login")

        if role == "Teacher/Admin":
            if user.is_superuser or hasattr(user, "teacheradmin"):
                return redirect("admin-dashboard")
            messages.error(request, "You are not authorized")
            return redirect("login")

        messages.error(request, "Invalid role selection")
        return redirect("login")

        if role == "Teacher/Admin":
            if user.is_superuser or hasattr(user, "teacheradmin"):
                return redirect("admin-dashboard")
            messages.error(request, "You are not authorized")
            return redirect("login")

        messages.error(request, "Invalid role selection")
        return redirect("login")

    scholarship_tests = []
    try:
        from scholarship_test.services import test_service as scholarship_test_service
        from scholarship_test.views import _uses_landing_page

        login_url = reverse("login")
        for scholarship_test in scholarship_test_service.get_launchable_tests():
            launch_url = reverse(
                "scholarship_test:scholarship_launch_test",
                args=[scholarship_test.id],
            )
            requires_otp_login = scholarship_test_service.requires_otp_login(
                scholarship_test
            )
            scholarship_tests.append(
                {
                    "id": scholarship_test.id,
                    "name": scholarship_test.name,
                    "question_count": getattr(scholarship_test, "runtime_question_count", 0),
                    "duration_display": scholarship_test.get_duration_display(),
                    "launch_url": launch_url,
                    "access_url": (
                        launch_url
                        if requires_otp_login
                        else f"{login_url}?{urlencode({'next': launch_url})}"
                    ),
                    "entry_mode": "landing" if _uses_landing_page(scholarship_test) else "direct",
                    "login_mode": "otp" if requires_otp_login else "password",
                }
            )
    except Exception:
        scholarship_tests = []

    # Determine if OTP should be hidden: if user is trying to access the diagnostic test
    next_url = request.GET.get('next', '')
    hide_otp = _is_password_only_test_next_url(next_url)
    
    # Regular diagnostic test is always available
    has_regular_test = True
    
    return render(
        request,
        "login.html",
        {
            "available_scholarship_tests": scholarship_tests,
            "hide_otp": hide_otp,
            "test_login_ui": hide_otp,
            "has_regular_test": has_regular_test,
        },
    )


def _increment_failed_attempts(request, identifier, ip_key, ip_data, username_key, attempt_data):
    """Increment failed login attempts and lock if threshold exceeded."""
    MAX_LOGIN_ATTEMPTS = getattr(request, 'MAX_LOGIN_ATTEMPTS', 5)
    LOCKOUT_DURATION_SECONDS = getattr(request, 'LOGIN_LOCKOUT_SECONDS', 900)
    
    from django.utils import timezone
    now = timezone.now().timestamp()
    
    # Get current attempt counts
    ip_attempts = ip_data.get('attempts', 0) if ip_data else 0
    username_attempts = attempt_data.get('attempts', 0) if attempt_data else 0
    
    # Increment attempts
    ip_attempts += 1
    username_attempts += 1
    
    # Check if should lock
    ip_locked = ip_attempts >= MAX_LOGIN_ATTEMPTS
    username_locked = username_attempts >= MAX_LOGIN_ATTEMPTS
    
    if ip_locked:
        lockout_end = now + LOCKOUT_DURATION_SECONDS
        _cache_set(ip_key, {'attempts': ip_attempts, 'locked': True, 'lockout_end': lockout_end}, LOCKOUT_DURATION_SECONDS)
    else:
        _cache_set(ip_key, {'attempts': ip_attempts, 'locked': False}, LOCKOUT_DURATION_SECONDS)
    
    if username_locked:
        lockout_end = now + LOCKOUT_DURATION_SECONDS
        _cache_set(username_key, {'attempts': username_attempts, 'locked': True, 'lockout_end': lockout_end}, LOCKOUT_DURATION_SECONDS)
    else:
        _cache_set(username_key, {'attempts': username_attempts, 'locked': False}, LOCKOUT_DURATION_SECONDS)


@never_cache
@cache_control(no_cache=True, no_store=True, must_revalidate=True, private=True)
def logout_view(request):
    request.session.flush()
    logout(request)
    return redirect("login")


@login_required
@csrf_protect
def force_password_change(request):
    if not user_needs_password_change(request.user):
        return _redirect_authenticated_user_home(request.user)

    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            clear_password_change_flag(user)
            login(request, user)
            messages.success(request, "Password updated successfully.")
            return _redirect_authenticated_user_home(user)
    else:
        form = PasswordChangeForm(request.user)
        form.initial["old_password"] = DEFAULT_ONE_TIME_PASSWORD

    for field_name, field in form.fields.items():
        existing_classes = field.widget.attrs.get("class", "")
        field.widget.attrs["class"] = f"{existing_classes} form-control".strip()
        field.widget.attrs["required"] = "required"

        if field_name == "old_password":
            field.widget.attrs["value"] = DEFAULT_ONE_TIME_PASSWORD
            field.widget.attrs["autocomplete"] = "current-password"
        else:
            field.widget.attrs["autocomplete"] = "new-password"
            field.widget.attrs["minlength"] = "8"

    return render(
        request,
        "force-password-change.html",
        {
            "form": form,
            "temporary_password": DEFAULT_ONE_TIME_PASSWORD,
        },
    )


# Common Helper Functions

def _normalize_phone(phone: str) -> str:
    """Keep last 10 digits."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    return digits[-10:] if len(digits) >= 10 else digits


def _cache_set(key: str, payload: dict, ttl: int):
    cache.set(key, payload, ttl)


def _cache_get(key: str):
    return cache.get(key)


def _msg91_mobile(phone_10: str) -> str:
    return f"{getattr(settings, 'MSG91_COUNTRY_CODE', '91')}{phone_10}"


def _msg91_send_otp(phone_10: str, template_id: str, params: dict | None = None) -> dict:
   
    import logging
    logger = logging.getLogger(__name__)
    
    
    url = "https://control.msg91.com/api/v5/otp"
    
    
    mobile_with_cc = _msg91_mobile(phone_10)
    
    
    payload = {}
    if params:
        
        for i, (key, value) in enumerate(params.items(), start=1):
            payload[f'var{i}'] = value

    query = {
        "mobile": mobile_with_cc,
        "authkey": settings.MSG91_AUTH_KEY,
        "template_id": template_id,
    }
    
    
    if hasattr(settings, 'MSG91_OTP_EXPIRY_MINUTES'):
        query["otp_expiry"] = settings.MSG91_OTP_EXPIRY_MINUTES
    
    headers = {
        "Content-Type": "application/json"
    }

    logger.info(f"Sending OTP to {mobile_with_cc} with template_id: {template_id}")
    logger.info(f"Query params: {query}")
    logger.info(f"Payload: {payload}")

    try:
        r = requests.post(
            url,
            params=query,
            json=payload,
            headers=headers,
            timeout=getattr(settings, "MSG91_TIMEOUT_SECONDS", 30),
        )
        
        logger.info(f"MSG91 response status: {r.status_code}, body: {r.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        raise RuntimeError(f"MSG91 request failed: {str(e)}")

    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    if r.status_code >= 400:
        raise RuntimeError(f"MSG91 send OTP failed ({r.status_code}): {data}")

    
    if isinstance(data, dict):
        if data.get("type") == "error" or data.get("status") == "error":
            raise RuntimeError(f"MSG91 API error: {data}")

    return data


def _msg91_verify_otp(phone_10: str, otp: str) -> dict:
    """MSG91 v5 verify OTP."""
    url = "https://control.msg91.com/api/v5/otp/verify"
    query = {"otp": otp, "mobile": _msg91_mobile(phone_10)}
    headers = {"authkey": settings.MSG91_AUTH_KEY}

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


# OTP login ( MSG91 Template )

@require_POST
@csrf_protect
def send_login_otp(request):
    role = request.POST.get("role")
    phone = _normalize_phone(request.POST.get("phone"))

    if role not in ("Student", "Teacher/Admin"):
        return JsonResponse({"ok": False, "msg": "Invalid role selection"}, status=400)

    if len(phone) != 10:
        return JsonResponse({"ok": False, "msg": "Enter a valid 10-digit mobile number"}, status=400)

    user = None

    if role == "Student":
        student = Student.objects.select_related("user").filter(contact__regex=phone + r"$").first()
        if student and student.user:
            user = student.user

    elif role == "Teacher/Admin":
        ta = TeacherAdmin.objects.select_related("user").filter(contact__regex=phone + r"$").first()
        if ta and ta.user:
            user = ta.user

    if not user:
        return JsonResponse({"ok": False, "msg": "Mobile number not registered for the selected role"}, status=404)

    key = f"otp:login:{phone}"
    ttl = getattr(settings, "OTP_EXPIRY_SECONDS", 600)

    _cache_set(key, {"user_id": user.id, "role": role, "attempts": 0}, ttl)

    try:
        _msg91_send_otp(
            phone,
            template_id=settings.MSG91_TEMPLATE_LOGIN,
            params={"Param1": "login"} 
        )
    except Exception as e:
        cache.delete(key)
        return JsonResponse({"ok": False, "msg": f"Failed to send OTP: {str(e)}"}, status=500)

    return JsonResponse({"ok": True, "msg": "OTP sent successfully"})


@require_POST
@csrf_protect
def verify_login_otp(request):
    phone = _normalize_phone(request.POST.get("phone"))
    otp_in = (request.POST.get("otp") or "").strip()
    role = request.POST.get("role")

    if len(phone) != 10:
        return JsonResponse({"ok": False, "msg": "Invalid phone"}, status=400)
    if not otp_in:
        return JsonResponse({"ok": False, "msg": "OTP is required"}, status=400)

    key = f"otp:login:{phone}"
    data = _cache_get(key)
    if not data:
        return JsonResponse({"ok": False, "msg": "OTP session expired. Please request OTP again."}, status=400)

    if role != data.get("role"):
        return JsonResponse({"ok": False, "msg": "Role mismatch. Please request OTP again."}, status=400)

    max_attempts = getattr(settings, "OTP_MAX_ATTEMPTS", 5)
    attempts = int(data.get("attempts", 0))
    if attempts >= max_attempts:
        cache.delete(key)
        return JsonResponse({"ok": False, "msg": "Too many attempts. Please request OTP again."}, status=429)

    try:
        resp = _msg91_verify_otp(phone, otp_in)
    except Exception:
        data["attempts"] = attempts + 1
        cache.set(key, data, getattr(settings, "OTP_EXPIRY_SECONDS", 600))
        return JsonResponse({"ok": False, "msg": "OTP verification failed"}, status=400)

    if not _is_msg91_verified(resp):
        data["attempts"] = attempts + 1
        cache.set(key, data, getattr(settings, "OTP_EXPIRY_SECONDS", 600))
        return JsonResponse({"ok": False, "msg": "Incorrect OTP"}, status=400)

    user = User.objects.filter(id=data["user_id"], is_active=True).first()
    if not user:
        cache.delete(key)
        return JsonResponse({"ok": False, "msg": "User not found/inactive"}, status=400)

    login(request, user)
    cache.delete(key)

    if user_needs_password_change(user):
        return JsonResponse({"ok": True, "redirect": reverse("force_password_change")})

    if role == "Student":
        return JsonResponse({"ok": True, "redirect": "/dashboard/student-dashboard/"})
    return JsonResponse({"ok": True, "redirect": "/dashboard/admin-dashboard/"})


# OTP Registration (MSG91)

@require_POST
@csrf_protect
def send_register_phone_otp(request):
    phone = _normalize_phone(request.POST.get("phone"))
    if len(phone) != 10:
        return JsonResponse({"ok": False, "msg": "Enter a valid 10-digit mobile number"}, status=400)

    key = f"otp:register:phone:{phone}"
    ttl = getattr(settings, "OTP_EXPIRY_SECONDS", 600)

    _cache_set(key, {"attempts": 0}, ttl)

    try:
        _msg91_send_otp(
            phone,
            template_id=settings.MSG91_TEMPLATE_GENERAL,
            params={"Param1": "register"} 
        )
    except Exception as e:
        cache.delete(key)
        return JsonResponse({"ok": False, "msg": f"Failed to send OTP: {str(e)}"}, status=500)

    return JsonResponse({"ok": True, "msg": "OTP sent successfully"})


@require_POST
@csrf_protect
def verify_register_phone_otp(request):
    phone = _normalize_phone(request.POST.get("phone"))
    otp_in = (request.POST.get("otp") or "").strip()

    if len(phone) != 10:
        return JsonResponse({"ok": False, "msg": "Invalid phone"}, status=400)
    if not otp_in:
        return JsonResponse({"ok": False, "msg": "OTP is required"}, status=400)

    key = f"otp:register:phone:{phone}"
    data = _cache_get(key)
    if not data:
        return JsonResponse({"ok": False, "msg": "OTP expired or not found"}, status=400)

    max_attempts = getattr(settings, "OTP_MAX_ATTEMPTS", 5)
    attempts = int(data.get("attempts", 0))
    if attempts >= max_attempts:
        cache.delete(key)
        return JsonResponse({"ok": False, "msg": "Too many attempts. Request OTP again."}, status=429)

    try:
        resp = _msg91_verify_otp(phone, otp_in)
    except Exception:
        data["attempts"] = attempts + 1
        cache.set(key, data, getattr(settings, "OTP_EXPIRY_SECONDS", 600))
        return JsonResponse({"ok": False, "msg": "OTP verification failed"}, status=400)

    if not _is_msg91_verified(resp):
        data["attempts"] = attempts + 1
        cache.set(key, data, getattr(settings, "OTP_EXPIRY_SECONDS", 600))
        return JsonResponse({"ok": False, "msg": "Incorrect OTP"}, status=400)

    # Mark verified in session
    request.session["reg_phone_verified"] = True
    request.session["reg_phone"] = phone

    cache.delete(key)
    return JsonResponse({"ok": True, "msg": "Phone verified"})


#OTP Reset Password

@require_POST
@csrf_protect
def send_reset_otp(request):
    phone = _normalize_phone(request.POST.get("phone"))
    if len(phone) != 10:
        return JsonResponse({"ok": False, "msg": "Enter a valid 10-digit mobile number"}, status=400)

    student = Student.objects.select_related("user").filter(contact__regex=phone + r"$").first()
    ta = TeacherAdmin.objects.select_related("user").filter(contact__regex=phone + r"$").first()

    user = None
    if student and student.user:
        user = student.user
    elif ta and ta.user:
        user = ta.user

    if not user:
        return JsonResponse({"ok": False, "msg": "Mobile number not registered"}, status=404)

    key = f"otp:reset:{phone}"
    ttl = getattr(settings, "OTP_EXPIRY_SECONDS", 600)

    _cache_set(key, {"user_id": user.id, "attempts": 0, "verified": False}, ttl)

    try:
        _msg91_send_otp(
            phone,
            template_id=settings.MSG91_TEMPLATE_GENERAL,
            params={"Param1": "reset"} 
        )
    except Exception as e:
        cache.delete(key)
        return JsonResponse({"ok": False, "msg": f"Failed to send OTP: {str(e)}"}, status=500)

    return JsonResponse({"ok": True, "msg": "OTP sent for password reset"})


@require_POST
@csrf_protect
def verify_reset_otp(request):
    phone = _normalize_phone(request.POST.get("phone"))
    otp_in = (request.POST.get("otp") or "").strip()

    if len(phone) != 10:
        return JsonResponse({"ok": False, "msg": "Invalid phone"}, status=400)
    if not otp_in:
        return JsonResponse({"ok": False, "msg": "OTP is required"}, status=400)

    key = f"otp:reset:{phone}"
    data = _cache_get(key)
    if not data:
        return JsonResponse({"ok": False, "msg": "OTP expired or not found"}, status=400)

    max_attempts = getattr(settings, "OTP_MAX_ATTEMPTS", 5)
    attempts = int(data.get("attempts", 0))
    if attempts >= max_attempts:
        cache.delete(key)
        return JsonResponse({"ok": False, "msg": "Too many attempts. Please request OTP again."}, status=429)

    try:
        resp = _msg91_verify_otp(phone, otp_in)
    except Exception:
        data["attempts"] = attempts + 1
        cache.set(key, data, getattr(settings, "OTP_EXPIRY_SECONDS", 600))
        return JsonResponse({"ok": False, "msg": "OTP verification failed"}, status=400)

    if not _is_msg91_verified(resp):
        data["attempts"] = attempts + 1
        cache.set(key, data, getattr(settings, "OTP_EXPIRY_SECONDS", 600))
        return JsonResponse({"ok": False, "msg": "Incorrect OTP"}, status=400)

    data["verified"] = True
    cache.set(key, data, getattr(settings, "OTP_EXPIRY_SECONDS", 600))
    return JsonResponse({"ok": True, "msg": "OTP verified. You can set a new password."})


@require_POST
@csrf_protect
def set_new_password(request):
    phone = _normalize_phone(request.POST.get("phone"))
    new_password = request.POST.get("new_password")
    confirm_password = request.POST.get("confirm_password")

    if not new_password or len(new_password) < 6:
        return JsonResponse({"ok": False, "msg": "Password must be at least 6 characters"}, status=400)

    if new_password != confirm_password:
        return JsonResponse({"ok": False, "msg": "Passwords do not match"}, status=400)

    key = f"otp:reset:{phone}"
    data = _cache_get(key)

    if not data or not data.get("verified"):
        return JsonResponse({"ok": False, "msg": "Please verify OTP first"}, status=400)

    user = User.objects.filter(id=data["user_id"], is_active=True).first()
    if not user:
        cache.delete(key)
        return JsonResponse({"ok": False, "msg": "User not found/inactive"}, status=400)

    user.set_password(new_password)
    user.save()
    clear_password_change_flag(user)
    cache.delete(key)

    return JsonResponse({"ok": True, "msg": "Password updated successfully. Please login."})


# OTP Study Material Download

@require_POST
@csrf_protect
def send_study_download_otp(request):
    
    import logging
    logger = logging.getLogger(__name__)
    
    
    logger.info(f"Study download OTP request received")
    logger.info(f"POST data: {dict(request.POST)}")
    
   
    logger.info(f"MSG91_AUTH_KEY present: {hasattr(settings, 'MSG91_AUTH_KEY')}")
    logger.info(f"MSG91_TEMPLATE_LOGIN: {getattr(settings, 'MSG91_TEMPLATE_LOGIN', 'NOT SET')}")
    logger.info(f"MSG91_TEMPLATE_GENERAL: {getattr(settings, 'MSG91_TEMPLATE_GENERAL', 'NOT SET')}")
    logger.info(f"MSG91_STUDY_OTP_TEMPLATE_ID: {getattr(settings, 'MSG91_STUDY_OTP_TEMPLATE_ID', 'NOT SET')}")
    
    phone = _normalize_phone(request.POST.get("mobile"))
    logger.info(f"Normalized phone: {phone}")
    
    if len(phone) != 10:
        logger.warning(f"Invalid phone length: {phone}")
        return JsonResponse({"success": False, "error": "Enter a valid 10-digit mobile number"}, status=400)

    
    key = f"otp:study_download:{phone}"
    ttl = getattr(settings, "OTP_EXPIRY_SECONDS", 600)
    
    _cache_set(key, {"attempts": 0}, ttl)

    
    template_id = getattr(settings, "MSG91_STUDY_OTP_TEMPLATE_ID", None)
    if not template_id:
        
        template_id = settings.MSG91_TEMPLATE_GENERAL
    
    logger.info(f"Sending study download OTP to {phone} with template {template_id}")

    try:
        result = _msg91_send_otp(
            phone,
            template_id=template_id,
            params={"Param1": "study_download"}
        )
        logger.info(f"MSG91 send result: {result}")
    except Exception as e:
        logger.error(f"Failed to send study download OTP: {str(e)}", exc_info=True)
        cache.delete(key)
        return JsonResponse({"success": False, "error": f"Failed to send OTP: {str(e)}"}, status=500)

    return JsonResponse({"success": True})


@require_POST
@csrf_protect
def verify_study_download_otp(request):
    
    phone = _normalize_phone(request.POST.get("mobile"))
    otp_in = (request.POST.get("otp") or "").strip()
    grade = (request.POST.get("grade") or "").strip()
    board = (request.POST.get("board") or "").strip()

    if len(phone) != 10:
        return JsonResponse({"success": False, "error": "Invalid phone"}, status=400)
    if not otp_in:
        return JsonResponse({"success": False, "error": "OTP is required"}, status=400)

    
    grade_normalized = grade.upper().replace("TH", "").replace("TH", "") if grade else ""
    board_normalized = board.upper()
    
   
    try:
        grade_num = int(grade_normalized)
        if grade_num in [10, 12]:
            grade_normalized = str(grade_num)
        else:
            grade_normalized = ""
    except (ValueError, TypeError):
        grade_normalized = ""
    
    
    if "CBSE" in board_normalized:
        board_normalized = "CBSE"
    elif "STATE" in board_normalized:
        board_normalized = "STATE"
    else:
        board_normalized = ""

    key = f"otp:study_download:{phone}"
    data = _cache_get(key)
    if not data:
        return JsonResponse({"success": False, "error": "OTP expired or not found"}, status=400)

    max_attempts = getattr(settings, "OTP_MAX_ATTEMPTS", 5)
    attempts = int(data.get("attempts", 0))
    if attempts >= max_attempts:
        cache.delete(key)
        return JsonResponse({"success": False, "error": "Too many attempts. Request OTP again."}, status=429)

    try:
        resp = _msg91_verify_otp(phone, otp_in)
    except Exception:
        data["attempts"] = attempts + 1
        cache.set(key, data, getattr(settings, "OTP_EXPIRY_SECONDS", 600))
        return JsonResponse({"success": False, "error": "OTP verification failed"}, status=400)

    if not _is_msg91_verified(resp):
        data["attempts"] = attempts + 1
        cache.set(key, data, getattr(settings, "OTP_EXPIRY_SECONDS", 600))
        return JsonResponse({"success": False, "error": "Incorrect OTP"}, status=400)

    
    redirect_url = ""
    
    if grade_normalized == "10" and board_normalized == "STATE":
        redirect_url = "/ssc-state/"
    elif grade_normalized == "10" and board_normalized == "CBSE":
        redirect_url = "/ssc-cbse/"
    elif grade_normalized == "12" and board_normalized == "STATE":
        redirect_url = "/hsc-state/"
    elif grade_normalized == "12" and board_normalized == "CBSE":
        redirect_url = "/hsc-cbse/"
    else:
        cache.delete(key)
        return JsonResponse({"success": False, "error": "Invalid grade/board combination. Only 10th and 12th (State/CBSE) are supported."}, status=400)

    
    cache.delete(key)
    
    return JsonResponse({"success": True, "redirect_url": redirect_url})


# Registration External Students

def _normalize_gender(val: str) -> str:
    val = (val or "").strip().lower()
    if val in ("male", "m"):
        return "Male"
    if val in ("female", "f"):
        return "Female"
    return "Other"


def _is_valid_person_name(name: str) -> bool:
    cleaned = (name or "").strip()
    return bool(cleaned) and bool(re.fullmatch(r"[A-Za-z ]+", cleaned))


def _normalize_grade(val: str) -> str:
   
    v = (val or "").strip()
    mapping = {
        "8": "8th",
        "9": "9th",
        "10": "10th",
        "11": "11th",
        "12": "12th",
        "8th": "8th",
        "9th": "9th",
        "10th": "10th",
        "11th": "11th",
        "12th": "12th",
    }
    return mapping.get(v, v)


def _normalize_board(val: str) -> str:
  
    v = (val or "").strip().lower()
    mapping = {
        "cbse": "CBSE",
        "icse": "ICSE",
        "state": "State",
        "ib": "IB",
        "igcse": "IGCSE",
    }
    return mapping.get(v, val or "")

def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()

def _is_email_taken(email: str) -> bool:
   
    e = _normalize_email(email)
    if not e:
        return False

    return (
        User.objects.filter(Q(username__iexact=e) | Q(email__iexact=e)).exists()
        or Student.objects.filter(email__iexact=e).exists()
        or TeacherAdmin.objects.filter(email__iexact=e).exists()
    )

def _is_phone_taken(phone10: str) -> bool:
   
    p = _normalize_phone(phone10)
    if len(p) != 10:
        return False

    return (
        Student.objects.filter(contact__regex=p + r"$").exists()
        or TeacherAdmin.objects.filter(contact__regex=p + r"$").exists()
    )


# API endpoint to check if phone number is already registered
@require_GET
@csrf_protect
def check_phone_exists(request):
    
    phone = _normalize_phone(request.GET.get("phone", ""))
    
    if len(phone) != 10:
        return JsonResponse({"exists": False, "msg": "Invalid phone number format"}, status=400)
    
    exists = _is_phone_taken(phone)
    return JsonResponse({"exists": exists, "msg": "Phone Number Already Registered" if exists else ""})


# API endpoint to check if email is already registered
@require_GET
@csrf_protect
def check_email_exists(request):
   
    email = _normalize_email(request.GET.get("email", ""))
    
    if not email or "@" not in email:
        return JsonResponse({"exists": False, "msg": "Invalid email format"}, status=400)
    
    exists = _is_email_taken(email)
    return JsonResponse({"exists": exists, "msg": "Email Id Already Registered" if exists else ""})


@csrf_protect
@transaction.atomic
def register_student(request):
    # Check if it's an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.method == "POST":
        full_name = (request.POST.get("fullName") or "").strip()
        dob = request.POST.get("dateOfBirth")
        gender = _normalize_gender(request.POST.get("gender"))

        phone = _normalize_phone(request.POST.get("phone"))
        email = _normalize_email(request.POST.get("email"))

        address = (request.POST.get("address") or "").strip()
        city = (request.POST.get("city") or "").strip()
        state = (request.POST.get("state") or "").strip()
        pincode = (request.POST.get("pincode") or "").strip()

        grade = _normalize_grade(request.POST.get("class"))
        board = _normalize_board(request.POST.get("board"))
        school = (request.POST.get("schoolName") or "").strip()

        exams = request.POST.getlist("interestedExams")

        password = request.POST.get("password")
        confirm = request.POST.get("confirmPassword")

        # ---- validations ----
        if not full_name or not email or not phone or not school or not grade or not board:
            error_msg = "Please fill all required fields"
            if is_ajax:
                return JsonResponse({"ok": False, "msg": error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect("register")

        if not _is_valid_person_name(full_name):
            error_msg = "Full name should contain only letters and spaces"
            if is_ajax:
                return JsonResponse({"ok": False, "msg": error_msg, "field": "fullName"}, status=400)
            messages.error(request, error_msg)
            return redirect("register")

        if len(phone) != 10 or not phone.isdigit():
            error_msg = "Please enter a valid 10-digit phone number"
            if is_ajax:
                return JsonResponse({"ok": False, "msg": error_msg, "field": "phone"}, status=400)
            messages.error(request, error_msg)
            return redirect("register")

        if "@" not in email:
            error_msg = "Please enter a valid email address"
            if is_ajax:
                return JsonResponse({"ok": False, "msg": error_msg, "field": "email"}, status=400)
            messages.error(request, error_msg)
            return redirect("register")

        if not exams:
            error_msg = "Please select at least one interested exam"
            if is_ajax:
                return JsonResponse({"ok": False, "msg": error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect("register")

        if not password or len(password) < 6:
            error_msg = "Password must be at least 6 characters"
            if is_ajax:
                return JsonResponse({"ok": False, "msg": error_msg, "field": "password"}, status=400)
            messages.error(request, error_msg)
            return redirect("register")

        if password != confirm:
            error_msg = "Passwords do not match"
            if is_ajax:
                return JsonResponse({"ok": False, "msg": error_msg, "field": "confirmPassword"}, status=400)
            messages.error(request, error_msg)
            return redirect("register")

        
        if not request.session.get("reg_phone_verified") or request.session.get("reg_phone") != phone:
            error_msg = "Please verify your phone number using OTP"
            if is_ajax:
                return JsonResponse({"ok": False, "msg": error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect("register")

       

        
        if _is_email_taken(email):
            error_msg = "Email Id Already Registered"
            if is_ajax:
                return JsonResponse({"ok": False, "msg": error_msg, "field": "email"}, status=400)
            messages.error(request, "This email is already registered")
            return redirect("register")

        if _is_phone_taken(phone):
            error_msg = "Phone Number Already Registered"
            if is_ajax:
                return JsonResponse({"ok": False, "msg": error_msg, "field": "phone"}, status=400)
            messages.error(request, "This phone number is already registered")
            return redirect("register")

   
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password
        )

        
        Student.objects.create(
            user=user,
            student_name=full_name,
            username=user.username,
            contact=phone,
            email=email,
            school=school,
            board=board,
            grade=grade,
            gender=gender,
            is_external=True,
            dob=dob or None,
            address=address,
            city=city,
            state=state,
            pincode=pincode,
            interested_exams=exams,
        )

       
        request.session.pop("reg_phone_verified", None)
        request.session.pop("reg_phone", None)
        request.session.pop("reg_email_verified", None)
        request.session.pop("reg_email", None)

        # For AJAX request, return success JSON
        if is_ajax:
            return JsonResponse({"ok": True, "msg": "Registration successful", "redirect": "/auth/login/"})
        
        messages.success(request, "Account created successfully")
        return redirect("login")

    return render(request, "register.html")


# User Management

@login_required
def user_management(request):
    
    if not (
        request.user.is_superuser
        or (hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role == "Admin")
    ):
        return HttpResponseForbidden("Only admins can access user management.")
    
    # Order by student_name to ensure consistent ordering
    students = Student.objects.select_related("user").order_by("-id")

    grouped = {}
    for s in students:
        grouped.setdefault(s.batch or "Unassigned", []).append(s)
    
    # Build batch_counts: {batch_name: count_of_students_in_batch}
    batch_counts = {}
    for batch, student_list in grouped.items():
        batch_counts[batch] = len(student_list)

    teachers = TeacherAdmin.objects.select_related("user").order_by("role", "name")

    # Pagination for students
    student_items_per_page = 6
    student_page_num = request.GET.get('student_page', 1)
    student_paginator = Paginator(students, student_items_per_page)
    try:
        students_page = student_paginator.page(student_page_num)
    except PageNotAnInteger:
        students_page = student_paginator.page(1)
    except EmptyPage:
        students_page = student_paginator.page(student_paginator.num_pages)

    # Pagination for teachers
    teacher_items_per_page = 6
    teacher_page_num = request.GET.get('teacher_page', 1)
    teacher_paginator = Paginator(teachers, teacher_items_per_page)
    try:
        teachers_page = teacher_paginator.page(teacher_page_num)
    except PageNotAnInteger:
        teachers_page = teacher_paginator.page(1)
    except EmptyPage:
        teachers_page = teacher_paginator.page(teacher_paginator.num_pages)

    return render(
        request,
        "user-management.html",
        {
            "students": students_page.object_list,              
            "students_grouped": grouped,      
            "teachers": teachers_page.object_list,
            "students_page": students_page,
            "teachers_page": teachers_page,
            "total_students": students.count(),
            "total_teachers": teachers.count(),
            "batch_counts_json": json.dumps(batch_counts),
        },
    )

@csrf_protect
@transaction.atomic
@login_required
def add_user(request):
    if request.method != "POST":
        return redirect("user-management")

    if not (
        request.user.is_superuser
        or (hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role == "Admin")
    ):
        return HttpResponseForbidden("Only admins can add users.")

    user_type = request.POST.get("user_type", "student")
    email = _normalize_email(request.POST.get("email"))
    password = DEFAULT_ONE_TIME_PASSWORD
    name = (request.POST.get("name") or "").strip()
    contact = _normalize_phone(request.POST.get("contact"))

    def _pick_post_value(field_name, prefer_last=False, default=""):
        values = [
            (value or "").strip()
            for value in request.POST.getlist(field_name)
            if (value or "").strip()
        ]
        if not values:
            return default
        return values[-1] if prefer_last else values[0]

    batch = _pick_post_value("batch")

    # Determine username based on user type
    if user_type == "student":
        # Generate username from batch
        if not batch:
            messages.error(request, "Batch is required for student.")
            return redirect("user-management")

        # Parse batch to derive prefix (e.g., "Star 01" -> "S01", "Alpha" -> "A01")
        parts = batch.split()
        first_letter = parts[0][0].upper() if parts else ""
        batch_num = "01"
        if len(parts) >= 2:
            second = parts[1]
            # Extract digits; allow leading zeros
            digits = "".join(filter(str.isdigit, second))
            if digits:
                batch_num = f"{int(digits):02d}"  # ensure two-digit
        prefix = first_letter + batch_num
        constant = "202628"

        # Count existing students with same batch to determine sequence
        existing_count = Student.objects.filter(batch=batch).count()
        seq = existing_count + 1
        seq_str = f"{seq:02d}"

        username = prefix + constant + seq_str

        # Ensure uniqueness in case of race conditions or manual entries
        while User.objects.filter(username=username).exists():
            seq += 1
            seq_str = f"{seq:02d}"
            username = prefix + constant + seq_str
    else:
        username = (request.POST.get("username") or "").strip()
        if not username:
            messages.error(request, "Username is required for teacher/admin.")
            return redirect("user-management")

    if not username or not email or not name:
        messages.error(request, "All required fields must be filled.")
        return redirect("user-management")

    if not _is_valid_person_name(name):
        messages.error(request, "Name should contain only letters and spaces.")
        return redirect("user-management")

    if contact and len(contact) != 10:
        messages.error(request, "Please enter a valid 10-digit phone number.")
        return redirect("user-management")

    if _is_email_taken(email):
        messages.error(request, "This email is already registered.")
        return redirect("user-management")

    if contact and _is_phone_taken(contact):
        messages.error(request, "This phone number is already registered.")
        return redirect("user-management")

  
    if User.objects.filter(Q(username=username) | Q(email=email)).exists():
        messages.error(request, "Username or Email already exists")
        return redirect("user-management")

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        is_staff=(user_type != "student"),
    )

    if user_type == "student":
        student_grade = _pick_post_value("grade")
        student_board = _pick_post_value("board")
        student_batch = _pick_post_value("batch", default="B1") or "B1"
        
       
        if hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role == "Teacher":
            ta = request.user.teacheradmin
           
            if not _teacher_has_scope_config(ta):
                messages.error(request, "Your profile does not have grade/board/batch configured. Please contact admin.")
                return redirect("user-management")
            
           
            t_grade = _norm(ta.grade)
            t_board = _norm(ta.board)
            t_batch = _norm(ta.batch)
            s_grade = _norm(student_grade)
            s_board = _norm(student_board)
            s_batch = _norm(student_batch)
            
          
            grade_matches = False
            for gv in grade_variants(ta.grade):
                if _norm(gv) == s_grade:
                    grade_matches = True
                    break
            
            if not (grade_matches and s_board == t_board and s_batch == t_batch):
                messages.error(request, f"You can only add students in your assigned grade ({ta.grade}), board ({ta.board}), and batch ({ta.batch}).")
                return redirect("user-management")
        
        Student.objects.create(
            user=user,
            student_name=request.POST.get("name"),
            username=username,
            contact=contact,
            email=email,
            school="",
            board=student_board,
            grade=student_grade,
            batch=student_batch,
            gender=request.POST.get("gender"),
            is_external=False,
            must_change_password=True,
        )
        messages.success(request, "Student added successfully")
    else:
        
        if not (request.user.is_superuser or (hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role == "Admin")):
            messages.error(request, "Only admins can add teachers.")
            return redirect("user-management")
        
        # Handle profile picture upload
        profile_pic = request.FILES.get("profile_picture")
        
        teacher = TeacherAdmin.objects.create(
            user=user,
            name=name,
            username=username,
            contact=contact,
            email=email,
            gender=request.POST.get("gender"),
            role=request.POST.get("role"),
            grade=_pick_post_value("grade", prefer_last=True),
            board=_pick_post_value("board", prefer_last=True),
            batch=_pick_post_value("batch", prefer_last=True),
            subjects=request.POST.get("subjects"),
            must_change_password=True,
        )
        
        # Save profile picture if provided
        if profile_pic:
            teacher.profile_picture = profile_pic
            teacher.save()
        
        messages.success(request, "Teacher/Admin added successfully")

    return redirect("user-management")





@login_required
@require_POST
def edit_student(request, id):
   
    if not (
        request.user.is_superuser
        or (hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role == "Admin")
    ):
        return HttpResponseForbidden("Only admins can edit students.")
    
    student = get_object_or_404(Student, id=id)

    
    student_name = (request.POST.get("name") or "").strip()
    if not _is_valid_person_name(student_name):
        messages.error(request, "Name should contain only letters and spaces.")
        return redirect("user-management")

    student.student_name = student_name
    student.username = student.user.username
    student.contact = request.POST.get("contact")
    student.email = request.POST.get("email")
    student.board = request.POST.get("board")
    student.grade = request.POST.get("grade")
    student.batch = request.POST.get("batch") or student.batch  
    student.gender = request.POST.get("gender")
    student.save()

    
    if student.user:
        student.user.email = student.email
        student.user.save(update_fields=["email"])

    messages.success(request, "Student updated successfully")
    return redirect("user-management")


@login_required
@require_POST
def edit_teacher(request, id):
    if not (
        request.user.is_superuser
        or (hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role == "Admin")
    ):
        return HttpResponseForbidden("Not allowed")

    teacher = get_object_or_404(TeacherAdmin, id=id)

    new_username = (request.POST.get("username") or "").strip()
    new_email = (request.POST.get("email") or "").strip().lower()

   
    if new_username and new_username != teacher.user.username:
        if User.objects.filter(username=new_username).exclude(id=teacher.user.id).exists():
            messages.error(request, "Username already exists")
            return redirect("user-management")

    if new_email and new_email != teacher.user.email:
        if User.objects.filter(email=new_email).exclude(id=teacher.user.id).exists():
            messages.error(request, "Email already exists")
            return redirect("user-management")

  
    teacher_name = (request.POST.get("name") or "").strip()
    if not _is_valid_person_name(teacher_name):
        messages.error(request, "Name should contain only letters and spaces.")
        return redirect("user-management")

    teacher.name = teacher_name
    teacher.username = new_username or teacher.username
    teacher.email = new_email or teacher.email
    teacher.contact = request.POST.get("contact")
    teacher.gender = request.POST.get("gender")
    teacher.role = request.POST.get("role")
    teacher.grade = request.POST.get("grade")
    teacher.board = request.POST.get("board")
    teacher.batch = request.POST.get("batch")
    teacher.subjects = request.POST.get("subjects")
    
    # Handle profile picture upload
    if "profile_picture" in request.FILES:
        teacher.profile_picture = request.FILES["profile_picture"]
    
    teacher.save()

   
    if teacher.user:
        if new_username:
            teacher.user.username = new_username
        if new_email:
            teacher.user.email = new_email
        teacher.user.is_staff = True
        teacher.user.save()

    messages.success(request, "User updated successfully")
    return redirect("user-management")


@login_required
@require_POST
def delete_teacher(request, id):
    if not (
        request.user.is_superuser
        or (hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role == "Admin")
    ):
        return HttpResponseForbidden("Not allowed")

    teacher = get_object_or_404(TeacherAdmin, id=id)
    teacher.user.delete()
    messages.success(request, "User deleted successfully")
    return redirect("user-management")


def normalize_board(board: str) -> str:
    return (board or "").strip().upper()

def normalize_grade(grade: str) -> str:
    g = (grade or "").strip().upper()

    roman_map = {
        "I": "1", "II": "2", "III": "3", "IV": "4", "V": "5",
        "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "X": "10",
        "XI": "11", "XII": "12",
    }
    if g in roman_map:
        return roman_map[g]

    m = re.search(r"\d+", g)
    if m:
        return m.group(0)

    return g

def _to_decimal(val, default="0.00"):
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal(default)

def _pct(n, d):
    if not d:
        return Decimal("0.00")
    return (Decimal(n) * Decimal("100.00") / Decimal(d)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

@login_required
@never_cache
@cache_control(no_cache=True, no_store=True, must_revalidate=True, private=True)
def student_dashboard(request):
    if not hasattr(request.user, "student"):
        return _redirect_authenticated_user_home(request.user)

    student = request.user.student

    student_grade_key = normalize_grade(student.grade)
    student_board_key = normalize_board(student.board)

    all_subjects = Subject.objects.all().order_by("name")
    subjects = [
        s for s in all_subjects
        if normalize_grade(s.grade) == student_grade_key and normalize_board(s.board) == student_board_key
    ]

    overall_obj = OverallCoverage.objects.filter(user=request.user).first()
    overall_percent = _to_decimal(overall_obj.overall_percent if overall_obj else "0.00")
    overall_angle = (overall_percent * Decimal("360") / Decimal("100")).quantize(Decimal("0.01"))

    subject_ids = [s.id for s in subjects]
    topic_counts = (
        Topic.objects
        .filter(chapter__subject_id__in=subject_ids)
        .values("chapter__subject_id")
        .annotate(total=Count("id"))
    )
    total_topics_by_subject = {row["chapter__subject_id"]: row["total"] for row in topic_counts}

    coverages = SubjectCoverage.objects.filter(user=request.user, subject_id__in=subject_ids).select_related("subject")
    coverage_by_subject_id = {c.subject_id: c for c in coverages}

    subject_cards = []
    for s in subjects:
        total_topics = total_topics_by_subject.get(s.id, 0)
        cov = coverage_by_subject_id.get(s.id)

        covered_topics = len(cov.covered_topic_ids) if cov else 0
        pending_topics = max(total_topics - covered_topics, 0)

        subject_percent = _pct(covered_topics, total_topics)

        if subject_percent > Decimal("75.00"):
            badge_text = "Excellent"
            badge_class = "badge-excellent"
            bar_class = "progress-excellent"
        elif subject_percent > Decimal("60.00"):
            badge_text = "Good"
            badge_class = "badge-good"
            bar_class = "progress-good"
        else:
            badge_text = "Needs Improvement"
            badge_class = "badge-poor"
            bar_class = "progress-poor"

        subject_cards.append({
            "id": s.id,
            "name": s.name,
            "total_topics": total_topics,
            "covered_topics": covered_topics,
            "pending_topics": pending_topics,
            "percent": str(subject_percent),
            "badge_text": badge_text,
            "badge_class": badge_class,
            "bar_class": bar_class,
        })

    strength_chapters_count = 0
    focus_chapters_count = 0
    weekly_focus_items = []

    chapter_map = {
        str(c.id): {"chapter": c.name, "subject": c.subject.name}
        for c in Chapter.objects.filter(subject_id__in=subject_ids).select_related("subject")
    }

    for cov in coverages:
        for chap_id, stats in (cov.chapter_coverage or {}).items():
            p = _to_decimal(stats.get("percent", "0.00"))
            if p > Decimal("70.00"):
                strength_chapters_count += 1
            if p < Decimal("50.00"):
                focus_chapters_count += 1
            if p < Decimal("40.00"):
                info = chapter_map.get(str(chap_id))
                if info:
                    weekly_focus_items.append({
                        "subject": info["subject"],
                        "chapter": info["chapter"],
                        "percent": str(p),
                    })

    weekly_focus_items = weekly_focus_items[:3]

    tests = UserTest.objects.filter(user=request.user).select_related("subject").order_by("created_at")
    test_subject_ids = list({t.subject_id for t in tests})

    total_topics_for_test_subject = {}
    if test_subject_ids:
        tc = (
            Topic.objects
            .filter(chapter__subject_id__in=test_subject_ids)
            .values("chapter__subject_id")
            .annotate(total=Count("id"))
        )
        total_topics_for_test_subject = {row["chapter__subject_id"]: row["total"] for row in tc}

    scores = []
    for t in tests:
        total_t = total_topics_for_test_subject.get(t.subject_id, 0)
        covered_t = len(t.correct_topics or [])
        scores.append(_pct(covered_t, total_t))

    avg_score = (
        (sum(scores) / Decimal(len(scores))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if scores else Decimal("0.00")
    )

    recent_tests = UserTest.objects.filter(
        user=request.user
    ).select_related("subject").order_by("created_at")[:10]
    
    trend_data = []
    trend_labels = []
    for test in recent_tests:
        total_t = total_topics_for_test_subject.get(test.subject_id, 0)
        if total_t > 0:
            score = (len(test.correct_topics or []) / total_t) * 100
            trend_data.append(round(score, 1))
            trend_labels.append(test.created_at.strftime("%d/%m"))
    
    
    trend_data = list(reversed(trend_data))
    trend_labels = list(reversed(trend_labels))
    
    radar_labels = []
    radar_data = []
    for s in subjects:
        radar_labels.append(s.name)
        cov = coverage_by_subject_id.get(s.id)
        radar_data.append(float(cov.subject_percent) if cov else 0)
    
    test_history = []
    recent_tests_list = UserTest.objects.filter(
        user=request.user
    ).select_related("subject").order_by("-created_at")[:5]
    
    for test in recent_tests_list:
        total_t = total_topics_for_test_subject.get(test.subject_id, 0)
        score = round((len(test.correct_topics or []) / total_t) * 100, 1) if total_t > 0 else 0
        test_history.append({
            "subject": test.subject.name,
            "test_number": test.test_number,
            "score": score,
            "correct": len(test.correct_topics or []),
            "total": total_t,
            "date": test.created_at.strftime("%d %b %Y"),
        })
    
    from datetime import timedelta
    today = timezone.now().date()
    streak = 0
    check_date = today
    
    test_dates = set()
    all_user_tests = UserTest.objects.filter(user=request.user).dates("created_at", "day")
    for test_date in all_user_tests:
        test_dates.add(test_date)
    
    while True:
        if check_date in test_dates:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            if check_date == today and (today - timedelta(days=1)) in test_dates:
                check_date = today - timedelta(days=1)
                continue
            break
    
    predicted_score = None
    if len(trend_data) >= 3:
        n = len(trend_data)
        x_mean = (n - 1) / 2
        y_mean = sum(trend_data) / n
        
        numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(trend_data))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator > 0:
            slope = numerator / denominator
           
            predicted_score = round(y_mean + slope * n, 1)
            
            predicted_score = max(0, min(100, predicted_score))
    
    peer_stats = {"above": 0, "below": 0, "total": 0, "percentile": 50}
    
    peers = Student.objects.filter(
        grade=student.grade,
        board=student.board,
        school=student.school
    ).exclude(user=request.user)
    
    peer_user_ids = list(peers.values_list("user_id", flat=True))
    peer_stats["total"] = len(peer_user_ids)
    
    if peer_user_ids:
        peer_coverages = OverallCoverage.objects.filter(
            user_id__in=peer_user_ids
        ).values_list("overall_percent", flat=True)
        
        peer_scores = [float(s) or 0 for s in peer_coverages]
        student_score = float(overall_percent)
        
        if peer_scores:
            above_count = sum(1 for s in peer_scores if s < student_score)
            peer_stats["above"] = above_count
            peer_stats["below"] = len(peer_scores) - above_count
            
            if len(peer_scores) > 0:
                peer_stats["percentile"] = round((above_count / len(peer_scores)) * 100)
    
    mastery_stats = {
        "mastered": 0,      
        "learning": 0,      
        "not_started": 0   
    }
    
    for cov in coverages:
        for chap_id, stats in (cov.chapter_coverage or {}).items():
            p = _to_decimal(stats.get("percent", "0.00"))
            if p == Decimal("100.00"):
                mastery_stats["mastered"] += 1
            elif p >= Decimal("50.00"):
                mastery_stats["learning"] += 1
            else:
                mastery_stats["not_started"] += 1

    return render(
        request,
        "dashboard/student-dashboard.html",
        {
            "student": student,
            "overall_percent": str(overall_percent),
            "overall_angle": str(overall_angle),
            "strength_chapters_count": strength_chapters_count,
            "focus_chapters_count": focus_chapters_count,
            "avg_score": str(avg_score),
            "subject_cards": subject_cards,
            "weekly_focus_items": weekly_focus_items,
            "trend_data": trend_data,
            "trend_labels": trend_labels,
            "radar_labels": radar_labels,
            "radar_data": radar_data,
            "test_history": test_history,
            "learning_streak": streak,
            "predicted_score": predicted_score,
            "peer_stats": peer_stats,
            "mastery_stats": mastery_stats,
        },
    )

def _is_admin_or_teacher(user):
    return user.is_superuser or hasattr(user, "teacheradmin")

def _display_name(user):
    if hasattr(user, "teacheradmin") and user.teacheradmin.name:
        return user.teacheradmin.name
    full = user.get_full_name()
    return full if full else user.username

def _get_weak_areas(user, threshold=45.0):
    sc_qs = (
        SubjectCoverage.objects.filter(user=user)
        .select_related("subject")
        .only("subject", "chapter_coverage")
    )

    if not sc_qs.exists():
        return []

    chapter_ids = set()
    for sc in sc_qs:
        cc = sc.chapter_coverage or {}
        for k in cc.keys():
            try:
                chapter_ids.add(int(k))
            except Exception:
                pass

    chapters = Chapter.objects.filter(id__in=chapter_ids).only("id", "name")
    chap_name = {c.id: c.name for c in chapters}

    weak = []
    for sc in sc_qs:
        cc = sc.chapter_coverage or {}
        for ch_id_raw, data in cc.items():
            try:
                ch_id = int(ch_id_raw)
            except Exception:
                continue

            percent = 0.0
            if isinstance(data, dict):
                p = data.get("percent", 0)
                try:
                    percent = float(p)
                except Exception:
                    percent = 0.0

            if percent < threshold:
                chn = chap_name.get(ch_id, f"Chapter {ch_id}")
                weak.append(f"{sc.subject.name} - {chn}")

    seen = set()
    out = []
    for item in weak:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out

def _status_from_score(score):
    if score > 85:
        return "Excellent"
    if score > 60 and score < 85:
        return "Good"
    if score < 50:
        return "Poor"
    return "Good"


def _normalize_admin_search_term(term: str) -> str:
    return re.sub(r"\s+", " ", (term or "").strip())


def _is_valid_admin_search_term(term: str) -> bool:
    cleaned = _normalize_admin_search_term(term)
    return not cleaned or bool(re.fullmatch(r"[A-Za-z0-9 @._-]+", cleaned))



@login_required
@never_cache
@cache_control(no_cache=True, no_store=True, must_revalidate=True, private=True)
def admin_dashboard(request):
    if not _is_admin_or_teacher(request.user):
        return _redirect_authenticated_user_home(request.user)

    today = timezone.localdate()
    raw_search = request.GET.get("search") or ""
    search_query = _normalize_admin_search_term(raw_search)
    if raw_search and not _is_valid_admin_search_term(raw_search):
        messages.error(
            request,
            "Search accepts letters, numbers, spaces, and . _ - @ characters.",
        )
        search_query = ""

    students_base = Student.objects.select_related("user").all().order_by("student_name")
    students = _filter_students_by_teacher_scope(request.user, students_base)

    if search_query:
        students = students.filter(
            Q(student_name__icontains=search_query)
            | Q(username__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(contact__icontains=search_query)
            | Q(email__icontains=search_query)
        )
    
    total_students = students.count()
    DECIMAL_OUT = DecimalField(max_digits=10, decimal_places=2)

    students_with_overall = (
        students
        .select_related("user")
        .annotate(
            overall_effective=Coalesce(
                Avg("user__subjectcoverage__subject_percent", output_field=DECIMAL_OUT),
                Value(Decimal("0.00"), output_field=DECIMAL_OUT),
                output_field=DECIMAL_OUT,
            )
        )
    )

    avg_progress_dec = students_with_overall.aggregate(v=Avg("overall_effective", output_field=DECIMAL_OUT))["v"] or Decimal("0.00")
    avg_progress = float(avg_progress_dec)

    need_attention_count = students_with_overall.filter(overall_effective__lt=Decimal("50.00")).count()

    assessments_taken_today = UserTest.objects.filter(
        user__student__in=students,
        created_at__date=today
    ).count()

    overall_by_id = {s.id: float(s.overall_effective or Decimal("0.00")) for s in students_with_overall}

    table_rows = []
    for idx, st in enumerate(students, start=1):
        score = overall_by_id.get(st.id, 0.0)
        status = _status_from_score(score)
        weak_areas = _get_weak_areas(st.user, threshold=45.0)

        table_rows.append(
            {
                "sr": idx,
                "student": st,
                "score": score,
                "score_text": f"{score:.2f}%",
                "status": status,
                "weak_areas": weak_areas,
                "pdf_url": reverse("pdf-report", args=[st.id]) + "?download=1",
            }
        )

    recent_tests = (
        UserTest.objects.filter(user__student__in=students)
        .select_related("user", "subject", "user__student")
        .order_by("-created_at")[:5]
    )

    attention_students = []
    under_40 = (
        students_with_overall
        .filter(overall_effective__lt=Decimal("40.00"))
        .order_by("overall_effective")[:3]
    )

    for st in under_40:
        weak = _get_weak_areas(st.user, threshold=45.0)
        attention_students.append(
            {
                "student": st,
                "score": float(st.overall_effective or Decimal("0.00")),
                "weak_hint": weak[0] if weak else "Low progress",
            }
        )

    # Pagination for student table
    items_per_page = 6
    students_page_num = request.GET.get('students_page', 1)
    students_paginator = Paginator(table_rows, items_per_page)
    try:
        students_page = students_paginator.page(students_page_num)
    except PageNotAnInteger:
        students_page = students_paginator.page(1)
    except EmptyPage:
        students_page = students_paginator.page(students_paginator.num_pages)

    context = {
        "teacher_name": _display_name(request.user),
        "total_students": total_students,
        "avg_progress": round(avg_progress, 2),
        "need_attention_count": need_attention_count,
        "assessments_taken_today": assessments_taken_today,
        "table_rows": students_page.object_list,
        "recent_tests": recent_tests,
        "attention_students": attention_students,
        "today": today,
        "students_page": students_page,
        "search_query": search_query,
        "active_search_query": search_query,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(
            request,
            "dashboard/partials/admin-dashboard-student-table.html",
            context,
        )

    return render(request, "dashboard/admin-dashboard.html", context)


@login_required
def student_needing_attention(request):
    if not _is_admin_or_teacher(request.user):
        return redirect("login")

    students_base = Student.objects.select_related("user").all()
    students = _filter_students_by_teacher_scope(request.user, students_base)

    DECIMAL_OUT = DecimalField(max_digits=10, decimal_places=2)

    qs = (
        students
        .annotate(
            overall_effective=Coalesce(
                Avg("user__subjectcoverage__subject_percent", output_field=DECIMAL_OUT),
                Value(Decimal("0.00"), output_field=DECIMAL_OUT),
                output_field=DECIMAL_OUT,
            )
        )
        .filter(overall_effective__lt=Decimal("40.00"))
        .order_by("overall_effective", "student_name")
    )

    cards = []
    for st in qs:
        percent = float(st.overall_effective or Decimal("0.00"))
        weak = _get_weak_areas(st.user, threshold=45.0)

        cards.append({
            "name": st.student_name,
            "grade": st.grade,
            "roll": st.user.username,
            "score": percent,
            "username": st.user.username,
            "weak_topics": weak[:6],
            "reason": "Low overall progress (below 40%)",
        })

    return render(
        request,
        "student-needing-attentions.html",
        {
            "cards": cards,
            "teacher_name": _display_name(request.user),
        }
    )


@login_required
@require_POST
def delete_student(request, id):
    if not (
        request.user.is_superuser
        or (hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role == "Admin")
    ):
        return HttpResponseForbidden("Only admins can delete students.")

    st = get_object_or_404(Student, id=id)
    
    username = st.user.username

    st.user.delete()
    messages.success(request, f"Student {username} deleted successfully.")
    
    referer = request.META.get('HTTP_REFERER', '')
    if 'user-management' in referer:
        return redirect("user-management")
    return redirect("admin-dashboard")


@login_required
def system_management(request):
    context = {
         "teacher_name": _display_name(request.user),
    }
    return render(request, "system-management.html", context)



def _teacheradmin(user):
    return getattr(user, "teacheradmin", None)

def _is_superadmin(user):
    return bool(user and user.is_superuser)

def _is_admin_user(user):
    ta = _teacheradmin(user)
    return bool(ta and ta.role == "Admin")

def _is_teacher_user(user):
    ta = _teacheradmin(user)
    return bool(ta and ta.role == "Teacher")

def _can_manage_all(user):
   
    return _is_superadmin(user) or _is_admin_user(user)

def _norm(v: str) -> str:
    return (v or "").strip().lower()

def grade_variants(v):
  
    def norm_text(val):
        return (val or "").strip()
    
    def grade_number(val):
       
        g = (val or "").strip().upper()

        roman_map = {
            "I": "1", "II": "2", "III": "3", "IV": "4", "V": "5",
            "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "X": "10",
            "XI": "11", "XII": "12",
        }
        if g in roman_map:
            return roman_map[g]

        m = re.search(r"\d+", g)
        return m.group(0) if m else (val or "").strip()
    
    raw = norm_text(v)
    num = grade_number(v)

    variants = set()
    if raw:
        variants.add(raw)
    if num:
        variants.add(num)
        variants.add(f"{num}th")
        variants.add(f"Grade {num}")
        variants.add(f"Class {num}")

 
    return [x for x in variants if x]

def _teacher_allowed_subject_names(ta: TeacherAdmin):
  
    raw = ta.subjects or ""
    return [_norm(s) for s in raw.split(",") if _norm(s)]

def _teacher_has_scope_config(ta: TeacherAdmin) -> bool:
   
    return bool(_norm(ta.grade) and _norm(ta.board) and _norm(ta.batch))

def _teacher_can_access_subject(user, subject: Subject) -> bool:
   
    ta = _teacheradmin(user)
    if not ta or ta.role != "Teacher":
        return False

    if not _teacher_has_scope_config(ta):
        return False

   
    subject_grade_norm = _norm(subject.grade)
    grade_matches = False
    for gv in grade_variants(ta.grade):
        if _norm(gv) == subject_grade_norm:
            grade_matches = True
            break
    
    if not grade_matches:
        return False
    
    
    if _norm(subject.board) != _norm(ta.board):
        return False
    if _norm(subject.batch) != _norm(ta.batch):
        return False

    allowed_names = _teacher_allowed_subject_names(ta)
    return _norm(subject.name) in allowed_names

def _require_syllabus_page_access(user):
   
    if _can_manage_all(user) or _is_teacher_user(user):
        return True
    return False

def _require_subject_manage_perm(user, subject: Subject):
   
    if _can_manage_all(user):
        return True
    if _teacher_can_access_subject(user, subject):
        return True
    return False




def _get_teacher_scope_filter(teacher_user):
    
    ta = _teacheradmin(teacher_user)
    
   
    if _can_manage_all(teacher_user):
        return None
    
  
    if not ta or ta.role != "Teacher":
        return Q(id=-1) 
    
   
    if not _teacher_has_scope_config(ta):
        return Q(id=-1)
    
  
    t_grade = _norm(ta.grade)
    t_board = _norm(ta.board)
    t_batch = _norm(ta.batch)
    
   
    grade_q = Q()
    for gv in grade_variants(ta.grade):
        grade_q |= Q(grade__iexact=gv)
    
    return grade_q & Q(board__iexact=t_board) & Q(batch__iexact=t_batch)


def _teacher_can_access_student(teacher_user, student: Student) -> bool:
    
    if _can_manage_all(teacher_user):
        return True
    
    ta = _teacheradmin(teacher_user)
    
   
    if not ta or ta.role != "Teacher":
        return False
    
    
    if not _teacher_has_scope_config(ta):
        return False
    
    
    t_grade = _norm(ta.grade)
    t_board = _norm(ta.board)
    t_batch = _norm(ta.batch)
    
    s_grade = _norm(student.grade)
    s_board = _norm(student.board)
    s_batch = _norm(student.batch)
    
   
    grade_matches = False
    for gv in grade_variants(ta.grade):
        if _norm(gv) == s_grade:
            grade_matches = True
            break
    
    return grade_matches and s_board == t_board and s_batch == t_batch


def _filter_students_by_teacher_scope(teacher_user, queryset):
    
    scope_filter = _get_teacher_scope_filter(teacher_user)
    
    if scope_filter is None:
        return queryset  
    
    return queryset.filter(scope_filter)


def _get_teacher_allowed_subjects_queryset(teacher_user):

    ta = _teacheradmin(teacher_user)
    
    
    if _can_manage_all(teacher_user):
        return Subject.objects.all()
    

    if not ta or ta.role != "Teacher":
        return Subject.objects.none()
    
  
    if not _teacher_has_scope_config(ta):
        return Subject.objects.none()
    
    
    grade_q = Q()
    for gv in grade_variants(ta.grade):
        grade_q |= Q(grade__iexact=gv)
    
    scope_q = grade_q & Q(board__iexact=_norm(ta.board)) & Q(batch__iexact=_norm(ta.batch))
    
    subjects_qs = Subject.objects.filter(scope_q)
    
    
    allowed_names = _teacher_allowed_subject_names(ta)
    if allowed_names:
        name_q = Q()
        for nm in allowed_names:
            name_q |= Q(name__iexact=nm)
        subjects_qs = subjects_qs.filter(name_q)
    
    return subjects_qs


# Syllabus Pages

@login_required
def syllabus_management(request):
    user = request.user
    ta = _teacheradmin(user)

    if not _require_syllabus_page_access(user):
        return HttpResponseForbidden("Not allowed")

    qs = Subject.objects.prefetch_related("chapters__topics__mcqs").order_by("grade", "name")

   
    def norm_text(v):
        return (v or "").strip()

    def norm_lower(v):
        return (v or "").strip().lower()

    def norm_upper(v):
        return (v or "").strip().upper()

    def grade_number(v):
        
        g = (v or "").strip().upper()

        roman_map = {
            "I": "1", "II": "2", "III": "3", "IV": "4", "V": "5",
            "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "X": "10",
            "XI": "11", "XII": "12",
        }
        if g in roman_map:
            return roman_map[g]

        m = re.search(r"\d+", g)
        return m.group(0) if m else (v or "").strip()

    def grade_variants(v):
       
        raw = norm_text(v)
        num = grade_number(v)

        variants = set()
        if raw:
            variants.add(raw)
        if num:
            variants.add(num)
            variants.add(f"{num}th")
            variants.add(f"Grade {num}")
            variants.add(f"Class {num}")

       
        return [x for x in variants if x]


    is_teacher = bool(ta and norm_lower(getattr(ta, "role", "")) == "teacher")

    if is_teacher:
        t_grade_raw = norm_text(getattr(ta, "grade", ""))
        t_board = norm_upper(getattr(ta, "board", ""))
        t_batch = norm_text(getattr(ta, "batch", ""))

      
        if not t_grade_raw or not t_board or not t_batch:
            qs = qs.none()
        else:
           
            grade_q = Q()
            for gv in grade_variants(t_grade_raw):
                grade_q |= Q(grade__iexact=gv)

           
            scope_q = grade_q & Q(board__iexact=t_board) & Q(batch__iexact=t_batch)

            qs = qs.filter(scope_q)

          
            allowed_names = _teacher_allowed_subject_names(ta)  
            allowed_names = [norm_lower(x) for x in allowed_names if norm_text(x)]

            if allowed_names:
                name_q = Q()
                for nm in allowed_names:
                    name_q |= Q(name__iexact=nm)
                qs = qs.filter(name_q)
        

    return render(
        request,
        "syllabus-management.html",
        {
            "subjects": qs,
            "can_manage_all": _can_manage_all(user),
            "is_teacher": is_teacher,
        },
    )

# Subject CRUD

@login_required
@require_POST
def add_subject(request):
    if not _can_manage_all(request.user):
        return HttpResponseForbidden("Not allowed")

    Subject.objects.create(
        name=request.POST.get("name"),
        grade=(request.POST.get("grade") or "").strip(),
        board=request.POST.get("board"),
        batch=request.POST.get("batch"),
    )
    return redirect("syllabus-management")


@login_required
@require_POST
def edit_subject(request, id):
    if not _can_manage_all(request.user):
        return HttpResponseForbidden("Not allowed")

    subject = get_object_or_404(Subject, id=id)
    subject.name = request.POST.get("name")
    subject.grade = (request.POST.get("grade") or "").strip()
    subject.board = request.POST.get("board")
    subject.batch = request.POST.get("batch")
    subject.save()
    return redirect("syllabus-management")


@login_required
@require_POST
def delete_subject(request, id):
    if not _can_manage_all(request.user):
        return HttpResponseForbidden("Not allowed")

    get_object_or_404(Subject, id=id).delete()
    return redirect("syllabus-management")



@login_required
@require_POST
def add_chapter(request):
    subject = get_object_or_404(Subject, id=request.POST.get("subject_id"))

    if not _require_subject_manage_perm(request.user, subject):
        return HttpResponseForbidden("Not allowed")

    Chapter.objects.create(subject=subject, name=request.POST.get("name"))
    messages.success(request, "Chapter added successfully")
    return redirect("syllabus-management")


@login_required
@require_POST
def edit_chapter(request, id):
    chapter = get_object_or_404(Chapter, id=id)
    subject = chapter.subject

    if not _require_subject_manage_perm(request.user, subject):
        return HttpResponseForbidden("Not allowed")

    chapter.name = request.POST.get("name")
    chapter.save()
    return redirect("syllabus-management")


@login_required
@require_POST
def delete_chapter(request, id):
    chapter = get_object_or_404(Chapter, id=id)
    subject = chapter.subject

    if not _require_subject_manage_perm(request.user, subject):
        return HttpResponseForbidden("Not allowed")

    chapter.delete()
    return redirect("syllabus-management")



@login_required
@require_POST
def add_topic(request):
    chapter = get_object_or_404(Chapter, id=request.POST.get("chapter_id"))
    subject = chapter.subject

    if not _require_subject_manage_perm(request.user, subject):
        return HttpResponseForbidden("Not allowed")

    Topic.objects.create(chapter=chapter, name=request.POST.get("name"))
    return redirect("syllabus-management")


@login_required
@require_POST
def edit_topic(request, id):
    topic = get_object_or_404(Topic, id=id)
    subject = topic.chapter.subject

    if not _require_subject_manage_perm(request.user, subject):
        return HttpResponseForbidden("Not allowed")

    topic.name = request.POST.get("name")
    topic.save()
    return redirect("syllabus-management")


@login_required
@require_POST
def delete_topic(request, id):
    topic = get_object_or_404(Topic, id=id)
    subject = topic.chapter.subject

    if not _require_subject_manage_perm(request.user, subject):
        return HttpResponseForbidden("Not allowed")

    topic.delete()
    return redirect("syllabus-management")



@login_required
@require_POST
def add_mcq(request):
    topic = get_object_or_404(Topic, id=request.POST.get("topic_id"))
    subject = topic.chapter.subject

    if not _require_subject_manage_perm(request.user, subject):
        return HttpResponseForbidden("Not allowed")

    Question.objects.create(
        topic=topic,
        question=request.POST.get("question"),
        question_image=request.FILES.get("question_image"),
        option_a=request.POST.get("option_a"),
        option_b=request.POST.get("option_b"),
        option_c=request.POST.get("option_c"),
        option_d=request.POST.get("option_d") or "N/A",
        correct_answer=request.POST.get("correct_answer"),
    )
    return redirect("syllabus-management")


@login_required
@require_POST
def edit_mcq(request, id):
    mcq = get_object_or_404(Question, id=id)
    subject = mcq.topic.chapter.subject

    if not _require_subject_manage_perm(request.user, subject):
        return HttpResponseForbidden("Not allowed")

    mcq.question = request.POST.get("question")
    if request.POST.get("remove_question_image") == "1":
        mcq.question_image = None
    elif request.FILES.get("question_image"):
        mcq.question_image = request.FILES.get("question_image")
    mcq.option_a = request.POST.get("option_a")
    mcq.option_b = request.POST.get("option_b")
    mcq.option_c = request.POST.get("option_c")
    mcq.option_d = request.POST.get("option_d") or "N/A"
    mcq.correct_answer = request.POST.get("correct_answer")
    mcq.save()
    return redirect("syllabus-management")


@login_required
@require_POST
def delete_mcq(request, id):
    mcq = get_object_or_404(Question, id=id)
    subject = mcq.topic.chapter.subject

    if not _require_subject_manage_perm(request.user, subject):
        return HttpResponseForbidden("Not allowed")

    mcq.delete()
    return redirect("syllabus-management")



@login_required
@require_POST
def upload_imp_questions(request, chapter_id):
    
    chapter = get_object_or_404(Chapter, id=chapter_id)
    subject = chapter.subject

    if not _require_subject_manage_perm(request.user, subject):
        return HttpResponseForbidden("Not allowed")

    imp_questions_file = request.FILES.get("imp_questions")
    imp_solutions_file = request.FILES.get("imp_solutions")

   
    imp_q, created = ChapterImpQuestions.objects.get_or_create(chapter=chapter)

    
    if imp_questions_file:
        imp_q.imp_questions = imp_questions_file
    if imp_solutions_file:
        imp_q.imp_solutions = imp_solutions_file

    imp_q.save()

    messages.success(request, "Important Questions uploaded successfully!")
    return redirect("syllabus-management")



# Main Test Page

@login_required
def test(request):
    student = get_object_or_404(Student, user=request.user)

    
    subjects = Subject.objects.filter(
        grade__iexact=student.grade.strip(),
        board__iexact=student.board.strip()
    ).order_by("name")

    
    target_subject_id = request.GET.get("subject")
    target_chapter_id = request.GET.get("chapter")
    topics_raw = request.GET.get("topics")  
    allowed_topic_ids = []
    if topics_raw:
        allowed_topic_ids = [int(x) for x in topics_raw.split(",") if x.strip().isdigit()]

    return render(request, "test.html", {
        "subjects": subjects,
        "student": student,
        "target_subject_id": target_subject_id,
        "target_chapter_id": target_chapter_id,
        "allowed_topic_ids": allowed_topic_ids,  
    })



def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_topics_csv(value: str):
   
    if not value:
        return []
    ids = []
    for part in str(value).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


@login_required
def load_subjects(request):
   
    try:
        student = Student.objects.get(user=request.user)

        student_grade_key = normalize_grade(student.grade)
        student_board_key = normalize_board(student.board)

       
        requested_subject_id = _parse_int(request.GET.get("subject"))
        requested_chapter_id = _parse_int(request.GET.get("chapter"))
        requested_topic_ids = _parse_topics_csv(request.GET.get("topics"))
        include_filters = request.GET.get("include_filters") in ("1", "true", "True", "yes", "YES")

        subjects = Subject.objects.all().order_by("name")

       
        matched_subjects = []
        matched_subject_ids = []

        for s in subjects:
            if normalize_grade(s.grade) == student_grade_key and normalize_board(s.board) == student_board_key:
                matched_subjects.append({"id": s.id, "name": s.name})
                matched_subject_ids.append(s.id)

       
        filters_payload = None

        if include_filters:
          
            if requested_subject_id and requested_subject_id in matched_subject_ids:
               
                matched_subjects = [x for x in matched_subjects if x["id"] == requested_subject_id]

                allowed_topic_ids = []

                
                if requested_topic_ids:
                    allowed_topic_ids = list(
                        Topic.objects.filter(
                            id__in=requested_topic_ids,
                            chapter__subject_id=requested_subject_id
                        ).values_list("id", flat=True)
                    )

               
                if requested_chapter_id:
                    chapter_ok = Chapter.objects.filter(
                        id=requested_chapter_id,
                        subject_id=requested_subject_id
                    ).exists()
                    if not chapter_ok:
                        requested_chapter_id = None

                filters_payload = {
                    "subject_id": requested_subject_id,
                    "chapter_id": requested_chapter_id,
                    "allowed_topic_ids": allowed_topic_ids, 
                }

            else:
                
                filters_payload = {
                    "subject_id": None,
                    "chapter_id": None,
                    "allowed_topic_ids": [],
                }

        response = {
            "subjects": matched_subjects,
            "debug": {
                "student_raw": {"grade": student.grade, "board": student.board},
                "student_norm": {"grade": student_grade_key, "board": student_board_key},
                "total_subjects_in_db": subjects.count(),
                "matched_count": len(matched_subjects),
                "matched_subject_ids": matched_subject_ids[:20],
                "first_10_subjects_norm": [
                    {"name": x.name, "grade": normalize_grade(x.grade), "board": normalize_board(x.board)}
                    for x in subjects[:10]
                ],
                "gap_filters_received": {
                    "subject": requested_subject_id,
                    "chapter": requested_chapter_id,
                    "topics": requested_topic_ids,
                    "include_filters": include_filters,
                }
            }
        }

        if include_filters:
            response["filters"] = filters_payload

        return JsonResponse(response)

    except Student.DoesNotExist:
        return JsonResponse({
            "subjects": [],
            "filters": {"subject_id": None, "chapter_id": None, "allowed_topic_ids": []},
            "debug": {"error": "Student row not found for this logged-in user"}
        })

@login_required
def load_chapters(request, subject_id):
   
    subject = get_object_or_404(Subject, id=subject_id)
    chapters = subject.chapters.prefetch_related("topics").all()
    data = []
    for chap in chapters:
        data.append({
            "id": chap.id,
            "name": chap.name,
            "topics": [{"id": t.id, "name": t.name} for t in chap.topics.all()]
        })
    return JsonResponse({"chapters": data})


@login_required
def load_quiz(request, chapter_id):
    
    chapter = get_object_or_404(Chapter, id=chapter_id)
    topics = chapter.topics.all()
    quiz_data = []

    for topic in topics:
        questions = list(topic.mcqs.all())
        if questions:
            q = random.choice(questions)
            quiz_data.append({
                "topic_id": topic.id,
                "question_id": q.id,
                "question": q.question,
                "question_image_url": q.question_image.url if q.question_image else "",
                "options": {
                    "A": q.option_a,
                    "B": q.option_b,
                    "C": q.option_c,
                    "D": q.option_d if q.option_d else "N/A",
                }
            })
    return JsonResponse({"quiz": quiz_data})


@login_required
def submit_quiz(request):
    
    if request.method == "POST":
        data = json.loads(request.body)
        answers = data.get("answers", {})
        chapter_id = data.get("chapter_id")
        correct_topics = []

        chapter = get_object_or_404(Chapter, id=chapter_id)
        for topic_id_str, answer_info in answers.items():
            topic_id = int(topic_id_str)
            question_id = answer_info.get("question_id")
            selected = answer_info.get("selected")

            question = Question.objects.filter(id=question_id, topic_id=topic_id).first()
            if question and question.correct_answer == selected:
                correct_topics.append(topic_id)

        return JsonResponse({"correct_topics": correct_topics})
    return JsonResponse({"error": "Invalid request"}, status=400)




from .models import (
    Student,
    Subject,
    Topic,
    SubjectCoverage,
    OverallCoverage,
    UserTest,
)



def _pct(n, d):
    if d == 0:
        return Decimal("0.00")
    return (Decimal(n) * Decimal("100.00") / Decimal(d)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

def _to_e164_india(phone10: str) -> str:
   
    p = _normalize_phone(phone10)
    if len(p) != 10:
        return ""
    cc = getattr(settings, "WHATSAPP_DEFAULT_COUNTRY_CODE", "91")
    return f"+{cc}{p}"


def _wa_cloud_upload_media(pdf_bytes: bytes, filename: str) -> str:
   
    api_version = getattr(settings, "WHATSAPP_CLOUD_API_VERSION", "v21.0")
    phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")

    if not phone_number_id or not token:
        raise RuntimeError("WhatsApp Cloud config missing (PHONE_NUMBER_ID / ACCESS_TOKEN)")

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/media"

    files = {
        "file": (filename, pdf_bytes, "application/pdf"),
    }
    data = {
        "messaging_product": "whatsapp",
        "type": "application/pdf",
    }
    headers = {
        "Authorization": f"Bearer {token}",
    }

    r = requests.post(url, headers=headers, files=files, data=data, timeout=30)
    j = r.json()
    if not r.ok or "id" not in j:
        raise RuntimeError(f"Media upload failed: {j}")
    return j["id"]

def _wa_cloud_send_template_with_document(
    to_e164: str,
    media_id: str,
    filename: str,
    body_params: list[str] | None = None,
) -> None:
   
    api_version = getattr(settings, "WHATSAPP_CLOUD_API_VERSION", "v21.0")
    phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    template_name = getattr(settings, "WHATSAPP_TEMPLATE_NAME", "")
    template_lang = getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en_US")

    if not phone_number_id or not token:
        raise RuntimeError("WhatsApp Cloud config missing (PHONE_NUMBER_ID / ACCESS_TOKEN)")
    if not template_name:
        raise RuntimeError("WHATSAPP_TEMPLATE_NAME is not set in settings.py")

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    components = []

   
    components.append({
        "type": "header",
        "parameters": [
            {
                "type": "document",
                "document": {
                    "id": media_id,
                    "filename": filename[:240] if filename else "report.pdf",
                }
            }
        ]
    })

   
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(x)[:1024]} for x in body_params]
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164.replace("+", ""), 
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
            "components": components
        }
    }

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    j = r.json()
    if not r.ok or "messages" not in j:
        raise RuntimeError(f"Template send failed: {j}")

def _wa_cloud_send_document_freeform(to_e164: str, media_id: str, caption: str = "") -> None:
   
    api_version = getattr(settings, "WHATSAPP_CLOUD_API_VERSION", "v21.0")
    phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")

    if not phone_number_id or not token:
        raise RuntimeError("WhatsApp Cloud config missing (PHONE_NUMBER_ID / ACCESS_TOKEN)")

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164.replace("+", ""),
        "type": "document",
        "document": {
            "id": media_id,
            "caption": caption[:1024] if caption else "",
        },
    }

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    j = r.json()
    if not r.ok or "messages" not in j:
        raise RuntimeError(f"Freeform send failed: {j}")


def send_report_pdf_on_whatsapp(student_phone10: str, pdf_bytes: bytes, filename: str, message: str) -> None:
   
    enabled = getattr(settings, "WHATSAPP_ENABLED", False)
    mock = getattr(settings, "WHATSAPP_MOCK_MODE", True)

    to_e164 = _to_e164_india(student_phone10)
    if not to_e164:
        raise RuntimeError("Invalid student WhatsApp number")

    if (not enabled) or mock:
        print("\n==============================")
        print("WHATSAPP (MOCK MODE)")
        print("To:", to_e164)
        print("Filename:", filename)
        print("Message:", message)
        print("PDF bytes:", len(pdf_bytes))
        print("==============================\n")
        return

  
    media_id = _wa_cloud_upload_media(pdf_bytes, filename)

   
    body_params = [message] 
    try:
        _wa_cloud_send_template_with_document(
            to_e164=to_e164,
            media_id=media_id,
            filename=filename,
            body_params=body_params,
        )
        return
    except Exception as e:
        
        print("Template send failed, trying free-form fallback:", str(e))
        _wa_cloud_send_document_freeform(to_e164, media_id, caption=message)


def send_report_pdf_on_email(student_email: str, pdf_bytes: bytes, filename: str, student_name: str, subject_name: str, subject_percent: str, overall_percent: str, student_obj=None) -> bool:
   
    from django.core.mail import EmailMessage
    from django.conf import settings
    
    enabled = getattr(settings, "EMAIL_ENABLED", False)
    
    if not enabled:
        print("\n==============================")
        print("EMAIL (DISABLED)")
        print("To:", student_email)
        print("Filename:", filename)
        print("==============================\n")
        return True  # Consider disabled as success to not block the flow
    
    if not student_email or "@" not in student_email:
        print("Email send skipped: invalid email address:", student_email)
        return False
    
    try:
        # Create email subject and body
        subject = f"Your SDS Report - {subject_name} - Score: {subject_percent}%"
        
        body = f"""
Dear {student_name},

Greetings from Ranker's Academy!

Your Self Diagnostic Test (SDS) report is ready.

Subject: {subject_name}
Subject Score: {subject_percent}%
Overall Progress: {overall_percent}%

Please find your detailed PDF report attached to this email.

Keep learning and improving!

Best regards,
Ranker's Academy
"""
        
        # Create email message with attachment
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[student_email],
        )
        
        # Attach PDF file
        email.attach(filename, pdf_bytes, 'application/pdf')
        
        # Send the email
        try:
            email.send(fail_silently=False)
            # Update student model with email tracking fields
            if student_obj:
                from django.utils import timezone
                student_obj.report_email_sent = True
                student_obj.report_email_sent_at = timezone.now()
                student_obj.report_email_error = ""
                student_obj.save(update_fields=['report_email_sent', 'report_email_sent_at', 'report_email_error'])
            return True
        except Exception as e:
            # Update student model with error
            if student_obj:
                student_obj.report_email_sent = False
                student_obj.report_email_error = str(e)
                student_obj.save(update_fields=['report_email_sent', 'report_email_error'])
            print("Email send failed:", str(e))
            return False
        
        print("\n==============================")
        print("EMAIL SENT SUCCESSFULLY")
        print("To:", student_email)
        print("Filename:", filename)
        print("==============================\n")
        
        return True
        
    except Exception as e:
        print("\n==============================")
        print("EMAIL SEND FAILED")
        print("To:", student_email)
        print("Error:", str(e))
        print("==============================\n")
        return False


@login_required
def submit_self_diagnostic(request):
    """
    POST JSON:
    {
      "subject_id": 12,
      "correct_topics": [1,2,3,...]
    }

    Returns JSON:
    {
      "success": True,
      "subject_name": "Physics",
      "subject_percent": "60.00",
      "overall_percent": "20.00",
      "peers_above_count": 3
    }
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)

    subject_id = data.get("subject_id")
    if not subject_id:
        return JsonResponse({"success": False, "error": "subject_id is required"}, status=400)

    
    covered_topic_ids = data.get("correct_topics", [])
    try:
        covered_topic_ids = list(map(int, covered_topic_ids))
    except Exception:
        return JsonResponse({"success": False, "error": "correct_topics must be a list of integers"}, status=400)

    student = get_object_or_404(Student, user=request.user)
    subject = get_object_or_404(Subject, id=subject_id)

   
    student_grade_key = normalize_grade(student.grade)
    student_board_key = normalize_board(student.board)
    subject_grade_key = normalize_grade(subject.grade)
    subject_board_key = normalize_board(subject.board)

    if subject_grade_key != student_grade_key or subject_board_key != student_board_key:
        return JsonResponse(
            {
                "success": False,
                "error": "Subject not allowed for your grade/board",
                "debug": {
                    "student_raw": {"grade": student.grade, "board": student.board},
                    "subject_raw": {"grade": subject.grade, "board": subject.board},
                    "student_norm": {"grade": student_grade_key, "board": student_board_key},
                    "subject_norm": {"grade": subject_grade_key, "board": subject_board_key},
                },
            },
            status=403,
        )

   
    all_topics_qs = Topic.objects.filter(chapter__subject=subject).select_related("chapter")
    total_subject_topics = all_topics_qs.count()

   
    valid_covered_topics = set(
        all_topics_qs.filter(id__in=covered_topic_ids).values_list("id", flat=True)
    )

   
    sc, _ = SubjectCoverage.objects.get_or_create(user=request.user, subject=subject)

    existing_covered = set(map(int, sc.covered_topic_ids or []))
    merged_covered = existing_covered.union(valid_covered_topics)

    covered_count = len(merged_covered)
    subject_percent = _pct(covered_count, total_subject_topics)

   
    chapter_map = {}
    for t in all_topics_qs:
        chap_id = t.chapter_id
        if chap_id not in chapter_map:
            chapter_map[chap_id] = {"total": 0, "covered": 0}
        chapter_map[chap_id]["total"] += 1
        if t.id in merged_covered:
            chapter_map[chap_id]["covered"] += 1

    chapter_coverage = {}
    for chap_id, stats in chapter_map.items():
        chapter_coverage[str(chap_id)] = {
            "total": stats["total"],
            "covered": stats["covered"],
            "percent": str(_pct(stats["covered"], stats["total"])),
        }

   
    sc.covered_topic_ids = sorted(list(merged_covered))
    sc.chapter_coverage = chapter_coverage
    sc.subject_percent = subject_percent
    sc.save(update_fields=["covered_topic_ids", "chapter_coverage", "subject_percent", "updated_at"])

   
    last_test = (
        UserTest.objects.filter(user=request.user, subject=subject)
        .order_by("-test_number")
        .first()
    )
    test_number = (last_test.test_number + 1) if last_test else 1

   
    UserTest.objects.create(
        user=request.user,
        subject=subject,
        test_number=test_number,
        correct_topics=sorted(list(valid_covered_topics)),
    )

   
    subjects_for_grade = Subject.objects.all()
    grade_board_subjects = []
    for s in subjects_for_grade:
        if normalize_grade(s.grade) == student_grade_key and normalize_board(s.board) == student_board_key:
            grade_board_subjects.append(s)

    total_subjects = len(grade_board_subjects)

    coverage_by_subject = {
        scx.subject_id: scx.subject_percent
        for scx in SubjectCoverage.objects.filter(
            user=request.user,
            subject_id__in=[s.id for s in grade_board_subjects]
        )
    }

    total = Decimal("0.00")
    for s in grade_board_subjects:
        total += coverage_by_subject.get(s.id, Decimal("0.00"))

    overall_percent = (
        (total / Decimal(total_subjects)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_subjects
        else Decimal("0.00")
    )

    OverallCoverage.objects.update_or_create(
        user=request.user,
        defaults={
            "grade": student.grade,
            "board": student.board,
            "overall_percent": overall_percent,
        },
    )

   
    peer_users = Student.objects.filter(
        school=student.school,
        grade=student.grade,
        board=student.board,
    ).exclude(user=request.user).values_list("user_id", flat=True)

    peers_above_count = SubjectCoverage.objects.filter(
        user_id__in=list(peer_users),
        subject=subject,
        subject_percent__gt=subject_percent,
    ).count()

       
    try:
       
        phone10 = _normalize_phone(student.contact)

        if len(phone10) == 10:
            pdf_bytes, filename = _generate_pdf_bytes_for_student(student, request.user)

            wa_message = (
                f"Hi {student.student_name}, your SDS report is ready.\n"
                f"Subject: {subject.name}\n"
                f"Subject Score: {subject_percent}%\n"
                f"Overall Progress: {overall_percent}%\n"
                f"Keep learning!"
            )

            send_report_pdf_on_whatsapp(
                student_phone10=phone10,
                pdf_bytes=pdf_bytes,
                filename=filename,
                message=wa_message
            )
        else:
            print("WhatsApp send skipped: invalid phone for user:", student.id, student.contact)

    except Exception as e:
        print("WhatsApp send failed:", str(e))

    return JsonResponse(
        {
            "success": True,
            "subject_name": subject.name,
            "subject_percent": str(subject_percent),
            "overall_percent": str(overall_percent),
            "peers_above_count": peers_above_count,
        }
    )



@login_required
def subject_analysis(request):
    if not hasattr(request.user, "student"):
        return redirect("login")

    student = request.user.student
    student_grade_key = normalize_grade(student.grade)
    student_board_key = normalize_board(student.board)

    all_subjects = Subject.objects.all().order_by("name")
    subjects = [
        s for s in all_subjects
        if normalize_grade(s.grade) == student_grade_key
        and normalize_board(s.board) == student_board_key
    ]

    if not subjects:
        return render(request, "subject-analysis.html", {
            "student": student,
            "subjects": [],
            "selected_subject": None,
            "summary": {"known": 0, "partial": 0, "unknown": 0},
            "chapters_data": [],
        })


    selected_subject_id = request.GET.get("subject")
    selected_subject = None

    if selected_subject_id:
        selected_subject = next((s for s in subjects if str(s.id) == str(selected_subject_id)), None)

    if not selected_subject:
        selected_subject = subjects[0]

    coverages = SubjectCoverage.objects.filter(user=request.user, subject__in=subjects).select_related("subject")
    coverage_by_subject_id = {c.subject_id: c for c in coverages}

    known_count = 0       
    partial_count = 0     
    unknown_count = 0     

    for cov in coverages:
        for chap_id, stats in (cov.chapter_coverage or {}).items():
            p = _to_decimal(stats.get("percent", "0.00"))

            if p == Decimal("100.00"):
                known_count += 1
            elif Decimal("20.00") < p < Decimal("60.00"):
                partial_count += 1
            elif p == Decimal("0.00"):
                unknown_count += 1

    summary = {"known": known_count, "partial": partial_count, "unknown": unknown_count}

    selected_cov = coverage_by_subject_id.get(selected_subject.id)
    covered_topic_ids = set(selected_cov.covered_topic_ids) if selected_cov else set()
    chapter_coverage_map = selected_cov.chapter_coverage if selected_cov else {}

    chapters_qs = (
        Chapter.objects
        .filter(subject=selected_subject)
        .prefetch_related("topics")
        .order_by("id")
    )

    chapters_data = []
    for chap in chapters_qs:
       
        chap_stats = chapter_coverage_map.get(str(chap.id)) or chapter_coverage_map.get(chap.id)

        if chap_stats:
            chap_percent = _to_decimal(chap_stats.get("percent", "0.00"))
        else:
           
            topics = list(chap.topics.all())
            total = len(topics)
            covered = sum(1 for t in topics if t.id in covered_topic_ids)
            chap_percent = _pct(covered, total)

        topics_list = []
        for t in chap.topics.all():
            is_mastered = t.id in covered_topic_ids
            topics_list.append({
                "id": t.id,
                "name": t.name,
                "status": "Mastered" if is_mastered else "Unknown",
            })

        chapters_data.append({
            "id": chap.id,
            "name": chap.name,
            "percent": str(chap_percent),
            "topics": topics_list,
        })

    return render(request, "subject-analysis.html", {
        "student": student,
        "subjects": subjects,
        "selected_subject": selected_subject,
        "summary": summary,
        "chapters_data": chapters_data,
    })




@login_required
def gap_analysis(request):
    student = get_object_or_404(Student, user=request.user)


    student_grade_key = normalize_grade(student.grade)
    student_board_key = normalize_board(student.board)


    all_subjects = Subject.objects.all().order_by("name")
    matched_subject_ids = [
        s.id for s in all_subjects
        if normalize_grade(s.grade) == student_grade_key and normalize_board(s.board) == student_board_key
    ]

    subjects = Subject.objects.filter(id__in=matched_subject_ids).order_by("name")

    subjects = subjects.prefetch_related(
        Prefetch("chapters", queryset=Chapter.objects.prefetch_related("topics"))
    )

    coverage_qs = SubjectCoverage.objects.filter(user=request.user, subject__in=subjects)
    coverage_map = {sc.subject_id: sc for sc in coverage_qs}

    all_topics = Topic.objects.filter(
        chapter__subject__in=subjects
    ).select_related("chapter", "chapter__subject")

    total_topics_all = all_topics.count()

    covered_all = set()
    for sc in coverage_qs:
        covered_all.update(map(int, sc.covered_topic_ids or []))

    unknown_topics_count = max(total_topics_all - len(covered_all), 0)

    subj_percents = []
    for s in subjects:
        sc = coverage_map.get(s.id)
        subj_percents.append(sc.subject_percent if sc else Decimal("0.00"))

    avg_coverage = (
        (sum(subj_percents) / Decimal(len(subj_percents))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if subj_percents
        else Decimal("0.00")
    )

   
    matrix_rows = []
    weak_chapters_count = 0

    for subject in subjects:
        sc = coverage_map.get(subject.id)

       
        covered_ids_for_subject = set(map(int, sc.covered_topic_ids or [])) if sc else set()
        chapter_cov = sc.chapter_coverage if sc else {}

        for chap in subject.chapters.all():
            topics = list(chap.topics.all())
            total_topics = len(topics)

          
            chap_topic_ids = {t.id for t in topics}

            known_ids = chap_topic_ids.intersection(covered_ids_for_subject)
            known = len(known_ids)
            unknown = total_topics - known

            stored = chapter_cov.get(str(chap.id)) if isinstance(chapter_cov, dict) else None
            if stored and "percent" in stored:
                percent = Decimal(str(stored["percent"]))
            else:
                percent = _pct(known, total_topics)

           
            if percent < Decimal("50.00"):
                weak_chapters_count += 1

            if percent == Decimal("100.00"):
                status = "Excellent"
                row_class = "row-excellent"
                bar_class = "bg-success"
                status_class = "status-excellent"
            elif percent >= Decimal("60.00"):
                status = "Good"
                row_class = "row-good"
                bar_class = "bg-warning"
                status_class = "status-good"
            else:
                status = "Needs Work"
                row_class = "row-work"
                bar_class = "bg-warning"
                status_class = "status-work"

            unknown_topic_names = [t.name for t in topics if t.id not in known_ids]
            unknown_topic_ids = [t.id for t in topics if t.id not in known_ids]

            matrix_rows.append({
                "subject": subject,
                "chapter": chap,
                "total_topics": total_topics,
                "known": known,
                "unknown": unknown,
                "percent": percent.quantize(Decimal("0.01")),
                "row_class": row_class,
                "bar_class": bar_class,
                "status": status,
                "status_class": status_class,
                "unknown_topic_names": unknown_topic_names,
                "unknown_topic_ids_csv": ",".join(map(str, unknown_topic_ids)),
            })

    priority_cards = []
    for subject in subjects:
        sc = coverage_map.get(subject.id)
        covered_ids = set(map(int, sc.covered_topic_ids or [])) if sc else set()
        chapter_cov = sc.chapter_coverage if sc else {}

        weakest = None  
        for chap in subject.chapters.all():
            topics = list(chap.topics.all())
            total = len(topics)
            chap_topic_ids = {t.id for t in topics}
            known = len(chap_topic_ids.intersection(covered_ids))

            stored = chapter_cov.get(str(chap.id)) if isinstance(chapter_cov, dict) else None
            if stored and "percent" in stored:
                percent = Decimal(str(stored["percent"]))
            else:
                percent = _pct(known, total)

            if percent <= Decimal("20.00"):
                unknown_topics = [t.name for t in topics if t.id not in covered_ids]
                candidate = (percent, chap, unknown_topics)
                if weakest is None or candidate[0] < weakest[0]:
                    weakest = candidate

        if weakest:
            percent, chap, unknown_topics = weakest
            unknown_topics_preview = ", ".join(unknown_topics[:8])
            priority_cards.append({
                "subject": subject.name,
                "chapter": chap.name,
                "chapter_id": chap.id,
                "subject_id": subject.id,
                "unknown_topics_preview": unknown_topics_preview,
            })

    priority_cards = priority_cards[:4]

    return render(request, "gap-analysis.html", {
        "weak_chapters_count": weak_chapters_count,
        "unknown_topics_count": unknown_topics_count,
        "avg_coverage": avg_coverage,
        "matrix_rows": matrix_rows,
        "priority_cards": priority_cards,
        "student": student,
    })





def _perf_label(score: float) -> str:
    if score >= 75:
        return "Excellent"
    if score >= 50:
        return "Average"
    return "Needs Improvement"


def _safe_int(v, default=0):
    try:
        return int(round(float(v)))
    except Exception:
        return default


def _compute_overall_percent(user) -> float:
    overall_obj = OverallCoverage.objects.filter(user=user).first()
    if overall_obj:
        return float(overall_obj.overall_percent)

    coverages = SubjectCoverage.objects.filter(user=user)
    percents = [float(c.subject_percent) for c in coverages]
    return (sum(percents) / len(percents)) if percents else 0.0


def _compute_previous_overall_from_tests(user) -> int:
 
    coverages = (
        SubjectCoverage.objects
        .filter(user=user)
        .select_related("subject")
        .order_by("subject__name")
    )

    prev_scores = []
    for c in coverages:
        tests = (
            UserTest.objects
            .filter(user=user, subject=c.subject)
            .order_by("-created_at", "-test_number")
        )
        
        # Get the 2nd latest test (previous test)
        test_list = list(tests)
        prev_test = test_list[1] if len(test_list) >= 2 else None
        if not prev_test:
            continue

        correct = set(prev_test.correct_topics or [])
        if not correct:
            continue

        # Get total topics for this subject
        total_topics = Topic.objects.filter(chapter__subject=c.subject).count()
        if total_topics == 0:
            continue

        score = (len(correct) / total_topics) * 100
        prev_scores.append(score)

    if not prev_scores:
        return 0
    return int(round(sum(prev_scores) / len(prev_scores)))


def _build_pdf_subject_sections(user):
   
    coverages = (
        SubjectCoverage.objects
        .filter(user=user)
        .select_related("subject")
        .order_by("subject__name")
    )

    subject_sections = []
    for c in coverages:
        chapter_cov = c.chapter_coverage or {} 

        chapters = Chapter.objects.filter(subject=c.subject).prefetch_related("topics").only("id", "name")
        chapter_name_by_id = {ch.id: ch.name for ch in chapters}
        
        # Build topic lookup for this subject
        topics_by_chapter = {}
        for ch in chapters:
            topics_by_chapter[ch.id] = {t.id: t.name for t in ch.topics.all()}

        covered_topic_ids = set(c.covered_topic_ids or [])

        rows = []
        weak_topics = []

        sorted_items = sorted(
            chapter_cov.items(),
            key=lambda kv: chapter_name_by_id.get(int(kv[0]), "zzz")
        )

        sr = 1
        for chap_id_str, stats in sorted_items:
            try:
                chap_id = int(chap_id_str)
            except Exception:
                continue

            chap_name = chapter_name_by_id.get(chap_id, f"Chapter #{chap_id}")
            total = _safe_int(stats.get("total", 0), 0)
            covered = _safe_int(stats.get("covered", 0), 0)
            percent = _safe_int(stats.get("percent", 0), 0)

            unknown = max(0, total - covered)

            rows.append([
                str(sr),
                chap_name,
                str(total),
                str(covered),
                str(unknown),
                f"{percent}%",
            ])

            if percent < 50:
                chapter_topics = topics_by_chapter.get(chap_id, {})
                for topic_id, topic_name in chapter_topics.items():
                    if topic_id not in covered_topic_ids:
                        weak_topics.append(topic_name)

            sr += 1

        subject_sections.append({
            "subject": c.subject.name.upper(),
            "rows": rows,
            "weak_topics": weak_topics,
        })

    return subject_sections


def _draw_header_footer(canvas, doc):
  
    width, height = A4

    canvas.setFillColor(colors.HexColor("#0D3B66"))
    canvas.rect(0, height - 42 * mm, width, 42 * mm, stroke=0, fill=1)

    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawCentredString(width / 2, height - 20 * mm, "The RANKER'S ACADEMY")

    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(width / 2, height - 28 * mm, "Student Self Diagnostic System")

    canvas.setFillColor(colors.HexColor("#9CA3AF"))
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(width / 2, 12 * mm, "© Ranker's Academy | Student Self Diagnostic Report")

def _generate_pdf_bytes_for_student(student_obj: Student, target_user: User) -> tuple[bytes, str]:
    
    overall_percent = _compute_overall_percent(target_user)
    overall_int = int(round(overall_percent))
    prev_overall_int = _compute_previous_overall_from_tests(target_user)
    subjects = _build_pdf_subject_sections(target_user)

    latest_test = (
        UserTest.objects
        .filter(user=target_user)
        .order_by("-created_at", "-test_number")
        .first()
    )
    test_no = latest_test.test_number if latest_test else None
    test_dt = latest_test.created_at if latest_test else None
    test_dt_str = "-"
    if test_dt:
       
        kolkata_tz = ZoneInfo("Asia/Kolkata")
        utc_tz = ZoneInfo("UTC")
        if test_dt.tzinfo is None:
            test_dt_aware = test_dt.replace(tzinfo=utc_tz)
        else:
            test_dt_aware = test_dt
        test_dt_str = test_dt_aware.astimezone(kolkata_tz).strftime("%d-%m-%Y %I:%M %p")

    student_info = {
        "Student Name": student_obj.student_name or (target_user.get_full_name() or target_user.username),
        "Username": target_user.username,
        "School": student_obj.school or "-",
        "Class": student_obj.grade or "-",
        "Board": student_obj.board or "-",
        "Gender": student_obj.gender or "-",
        "Test No": str(test_no) if test_no else "-",
        "Test Date": test_dt_str,
    }

    verdict = (
        "The student has shown a good understanding of core concepts. Strong performance is observed in most subjects. "
        "However, a few chapters indicate learning gaps that require focused revision. With consistent effort and guided "
        "practice, the student has strong potential to improve further."
    )
    next_steps = (
        "Revise all weak topics identified in the subject-wise analysis. Practice daily to improve accuracy and confidence. "
        "Focus on concept clarity rather than memorization. Attempt regular mock tests and seek teacher guidance for difficult chapters."
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=50 * mm,
        bottomMargin=18 * mm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#0D3B66"),
        alignment=1,
        spaceAfter=10,
    )
    h_style = ParagraphStyle(
        "H",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.HexColor("#0D3B66"),
        spaceBefore=8,
        spaceAfter=6,
    )
    small_style = ParagraphStyle(
        "Small",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#111827"),
    )
    box_text_style = ParagraphStyle(
        "BoxText",
        parent=small_style,
        fontSize=8,
        leading=12,
    )

    story = []
    story.append(Paragraph("Student Self-Diagnostic Test Report", title_style))
    story.append(Spacer(1, 6))

    info_data = [
        [f"Student Name: {student_info['Student Name']}", f"Username: {student_info['Username']}"],
        [f"School: {student_info['School']}", f"Class: {student_info['Class']}"],
        [f"Board: {student_info['Board']}", f"Gender: {student_info['Gender']}"],
        [f"Test No: {student_info['Test No']}", f"Test Date: {student_info['Test Date']}"],
    ]
    info_table = Table(info_data, colWidths=[85 * mm, 85 * mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF6FF")),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#D6E6FF")),
        ("INNERGRID", (0, 0), (-1, -1), 0.0, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Performance Summary", h_style))
    story.append(Spacer(1, 4))

    perf_table = Table(
        [[f"Total Score: {overall_int}%", f"Previous Score: {prev_overall_int}%"]],
        colWidths=[85 * mm, 85 * mm]
    )
    perf_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#D1D5DB")),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(perf_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("SUBJECT WISE REPORT", h_style))
    story.append(Spacer(1, 6))

    for idx, sec in enumerate(subjects):
        story.append(Spacer(1, 6))
        story.append(Paragraph(sec["subject"], ParagraphStyle(
            "Subj",
            parent=h_style,
            fontSize=9,
            textColor=colors.HexColor("#0D3B66"),
            spaceBefore=6,
            spaceAfter=6,
        )))

        table_data = [["Sr No", "Chapter", "Total", "Complete", "Unknown", "Coverage"]] + sec["rows"]

        t = Table(table_data, colWidths=[12 * mm, 65 * mm, 18 * mm, 22 * mm, 22 * mm, 20 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D3B66")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),

            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),

            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

        story.append(Paragraph("<b>Weak Topics</b>", small_style))
        if sec["weak_topics"]:
            for i, w in enumerate(sec["weak_topics"], start=1):
                story.append(Paragraph(f"{i}. {w}", box_text_style))
        else:
            story.append(Paragraph("No weak topics.", box_text_style))

        if idx < len(subjects) - 1 and (idx + 1) % 2 == 0:
            story.append(PageBreak())

    story.append(Spacer(1, 10))
    story.append(Paragraph("FINAL OVERALL REPORT SUMMARY", h_style))
    story.append(Spacer(1, 6))

    summary_box = Table(
        [[Paragraph(
            f"<b>Overall Performance Summary:</b><br/>{verdict}<br/><br/><b>What the Student Should Do Next:</b><br/>{next_steps}",
            box_text_style
        )]],
        colWidths=[170 * mm]
    )
    summary_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF6FF")),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#D6E6FF")),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(summary_box)

    doc.build(story, onFirstPage=_draw_header_footer, onLaterPages=_draw_header_footer)

    pdf_bytes = buffer.getvalue()
    buffer.close()

    filename = f"student_diagnostic_report_{target_user.username}.pdf"
    return pdf_bytes, filename


@login_required
def pdf_report(request, student_id: int):
   
    user = request.user

   
    is_admin_or_teacher = _is_admin_or_teacher(user)
    
    if not is_admin_or_teacher:
        if not hasattr(user, "student") or user.student.id != student_id:
            return HttpResponseForbidden("Not allowed.")
        student_obj = user.student
        target_user = student_obj.user
    else:
        student_obj = get_object_or_404(Student, id=student_id)
        
        if not _can_manage_all(user):
            if not _teacher_can_access_student(user, student_obj):
                return HttpResponseForbidden("You can only access reports for students in your assigned grade/board/batch.")
        
        target_user = student_obj.user

    overall_percent = _compute_overall_percent(target_user)
    overall_int = int(round(overall_percent))
    prev_overall_int = _compute_previous_overall_from_tests(target_user)

    subjects = _build_pdf_subject_sections(target_user)

    latest_test = (
        UserTest.objects
        .filter(user=target_user)
        .order_by("-created_at", "-test_number")
        .first()
    )

    test_no = latest_test.test_number if latest_test else None
    test_dt = latest_test.created_at if latest_test else None
    test_dt_str = "-"
    if test_dt:
        kolkata_tz = ZoneInfo("Asia/Kolkata")
        utc_tz = ZoneInfo("UTC")
        if test_dt.tzinfo is None:
            test_dt_aware = test_dt.replace(tzinfo=utc_tz)
        else:
            test_dt_aware = test_dt
        test_dt_str = test_dt_aware.astimezone(kolkata_tz).strftime("%d-%m-%Y %I:%M %p")

    student_info = {
        "Student Name": student_obj.student_name or (target_user.get_full_name() or target_user.username),
        "Username": target_user.username,
        "School": student_obj.school or "-",
        "Class": student_obj.grade or "-",
        "Board": student_obj.board or "-",
        "Gender": student_obj.gender or "-",
        "Test No": str(test_no) if test_no else "-",
        "Test Date": test_dt_str,
    }

    verdict = (
        "The student has shown a good understanding of core concepts. Strong performance is observed in most subjects. "
        "However, a few chapters indicate learning gaps that require focused revision. With consistent effort and guided "
        "practice, the student has strong potential to improve further."
    )
    next_steps = (
        "Revise all weak topics identified in the subject-wise analysis. Practice daily to improve accuracy and confidence. "
        "Focus on concept clarity rather than memorization. Attempt regular mock tests and seek teacher guidance for difficult chapters."
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=50 * mm,
        bottomMargin=18 * mm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#0D3B66"),
        alignment=1,
        spaceAfter=10,
    )
    h_style = ParagraphStyle(
        "H",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.HexColor("#0D3B66"),
        spaceBefore=8,
        spaceAfter=6,
    )
    small_style = ParagraphStyle(
        "Small",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#111827"),
    )
    box_text_style = ParagraphStyle(
        "BoxText",
        parent=small_style,
        fontSize=8,
        leading=12,
    )

    story = []
    story.append(Paragraph("Student Self-Diagnostic Test Report", title_style))
    story.append(Spacer(1, 6))

    info_data = [
        [f"Student Name: {student_info['Student Name']}", f"Username: {student_info['Username']}"],
        [f"School: {student_info['School']}", f"Class: {student_info['Class']}"],
        [f"Board: {student_info['Board']}", f"Gender: {student_info['Gender']}"],
        [f"Test No: {student_info['Test No']}", f"Test Date: {student_info['Test Date']}"],
    ]
    info_table = Table(info_data, colWidths=[85 * mm, 85 * mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF6FF")),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#D6E6FF")),
        ("INNERGRID", (0, 0), (-1, -1), 0.0, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Performance Summary", h_style))
    story.append(Spacer(1, 4))

    perf_table = Table(
        [[f"Total Score: {overall_int}%", f"Previous Score: {prev_overall_int}%"]],
        colWidths=[85 * mm, 85 * mm]
    )
    perf_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#D1D5DB")),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(perf_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("SUBJECT WISE REPORT", h_style))
    story.append(Spacer(1, 6))

    for idx, sec in enumerate(subjects):
        story.append(Spacer(1, 6))
        story.append(Paragraph(sec["subject"], ParagraphStyle(
            "Subj",
            parent=h_style,
            fontSize=9,
            textColor=colors.HexColor("#0D3B66"),
            spaceBefore=6,
            spaceAfter=6,
        )))

        table_data = [["Sr No", "Chapter", "Total", "Complete", "Unknown", "Coverage"]] + sec["rows"]

        t = Table(table_data, colWidths=[12 * mm, 65 * mm, 18 * mm, 22 * mm, 22 * mm, 20 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D3B66")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),

            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),

            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

        story.append(Paragraph("<b>Weak Topics</b>", small_style))
        if sec["weak_topics"]:
            for i, w in enumerate(sec["weak_topics"], start=1):
                story.append(Paragraph(f"{i}. {w}", box_text_style))
        else:
            story.append(Paragraph("No weak topics.", box_text_style))

        if idx < len(subjects) - 1 and (idx + 1) % 2 == 0:
            story.append(PageBreak())

    story.append(Spacer(1, 10))
    story.append(Paragraph("FINAL OVERALL REPORT SUMMARY", h_style))
    story.append(Spacer(1, 6))

    summary_box = Table(
        [[Paragraph(
            f"<b>Overall Performance Summary:</b><br/>{verdict}<br/><br/><b>What the Student Should Do Next:</b><br/>{next_steps}",
            box_text_style
        )]],
        colWidths=[170 * mm]
    )
    summary_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF6FF")),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#D6E6FF")),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(summary_box)

    doc.build(story, onFirstPage=_draw_header_footer, onLaterPages=_draw_header_footer)

    pdf_bytes = buffer.getvalue()
    buffer.close()


    send_whatsapp = request.GET.get("send_whatsapp", "0") == "1"
    if send_whatsapp:
        try:
            phone10 = _normalize_phone(student_obj.contact)
            if len(phone10) == 10:
                wa_message = (
                    f"Hi {student_info['Student Name']}, your SDS PDF report is ready \n"
                    f"Total Score: {overall_int}%\n"
                    f"Test No: {student_info['Test No']} | Test Date: {student_info['Test Date']}\n"
                    f"Please check the attached report and focus on weak topics."
                )

                filename_for_wa = f"student_diagnostic_report_{target_user.username}.pdf"

                send_report_pdf_on_whatsapp(
                    student_phone10=phone10,
                    pdf_bytes=pdf_bytes,
                    filename=filename_for_wa,
                    message=wa_message
                )
            else:
                print("WhatsApp send skipped: invalid student phone:", student_obj.id, student_obj.contact)
        except Exception as e:
            print("WhatsApp send failed:", str(e))

  

    download = request.GET.get("download", "0") == "1"
    filename = f"student_diagnostic_report_{target_user.username}.pdf"
    disposition = "attachment" if download else "inline"

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return resp


def _build_printable_report_context(student_obj: Student, target_user: User, generated_at: str | None = None) -> dict:
    overall_percent = _compute_overall_percent(target_user)
    overall_int = int(round(overall_percent))
    prev_overall_int = _compute_previous_overall_from_tests(target_user)

    latest_test = (
        UserTest.objects
        .filter(user=target_user)
        .order_by("-created_at", "-test_number")
        .first()
    )

    test_no = latest_test.test_number if latest_test else None
    test_dt = latest_test.created_at if latest_test else None
    test_dt_str = "-"
    if test_dt:
        kolkata_tz = ZoneInfo("Asia/Kolkata")
        utc_tz = ZoneInfo("UTC")
        if test_dt.tzinfo is None:
            test_dt_aware = test_dt.replace(tzinfo=utc_tz)
        else:
            test_dt_aware = test_dt
        test_dt_str = test_dt_aware.astimezone(kolkata_tz).strftime("%d-%m-%Y %I:%M %p")

    subject_sections = _build_pdf_subject_sections(target_user)
    subjects = []
    for sec in subject_sections:
        chapters = []
        for row in sec["rows"]:
            chapters.append({
                "name": row[1],
                "total": int(row[2]),
                "correct": int(row[3]),
                "unknown": int(row[4]),
                "coverage": row[5],
            })
        subjects.append({
            "name": sec["subject"],
            "chapters": chapters,
            "weak_topics": sec["weak_topics"],
        })

    logo_url = ""
    try:
        from django.templatetags.static import static
        logo_url = static('img/logo.webp')
    except Exception:
        try:
            logo_url = f"{settings.STATIC_URL}img/logo.webp"
        except Exception:
            logo_url = "/static/img/logo.webp"

    generated_at_dt = timezone.now().astimezone(ZoneInfo("Asia/Kolkata"))
    generated_at_str = generated_at or f"{generated_at_dt.month}/{generated_at_dt.day}/{str(generated_at_dt.year)[-2:]}, {generated_at_dt.strftime('%I:%M %p').lstrip('0')}"

    return {
        "student_name": student_obj.student_name or (target_user.get_full_name() or target_user.username),
        "username": target_user.username,
        "school": student_obj.school or "-",
        "class": student_obj.grade or "-",
        "board": student_obj.board or "-",
        "gender": student_obj.gender or "-",
        "test_no": str(test_no) if test_no else "1",
        "test_date": test_dt_str,
        "total_score": f"{overall_int}%",
        "previous_score": f"{prev_overall_int}%",
        "generated_at": generated_at_str,
        "subjects": subjects,
        "logo_url": logo_url,
    }


def _resolve_printable_logo_path() -> str | None:
    candidates = [
        os.path.join(settings.BASE_DIR, "sds_main", "static", "img", "logo.webp"),
        os.path.join(settings.BASE_DIR, "sds_main", "static", "img", "logo-crop.png"),
        os.path.join(settings.BASE_DIR, "sds_main", "static", "img", "Rankers_logo.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _generate_printable_layout_pdf_bytes(student_obj: Student, target_user: User, generated_at: str | None = None) -> tuple[bytes, str]:
    context = _build_printable_report_context(student_obj, target_user, generated_at=generated_at)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PrintableTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=colors.HexColor("#1E3A8A"),
        alignment=1,
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "PrintableSubtitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#1F2937"),
        alignment=1,
        spaceAfter=10,
    )
    timestamp_style = ParagraphStyle(
        "TimestampStyle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#1F2937"),
        alignment=0,
        spaceAfter=18,
    )
    summary_heading_style = ParagraphStyle(
        "SummaryHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.HexColor("#1F2937"),
        spaceAfter=6,
    )
    label_style = ParagraphStyle(
        "LabelStyle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#6B7280"),
        leading=12,
    )
    value_style = ParagraphStyle(
        "ValueStyle",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.HexColor("#1F2937"),
        leading=12,
    )
    section_style = ParagraphStyle(
        "SectionStyle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.HexColor("#1E3A8A"),
        spaceAfter=6,
    )
    subject_style = ParagraphStyle(
        "SubjectStyle",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=4,
        spaceAfter=8,
    )
    small_style = ParagraphStyle(
        "SmallPrintable",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        textColor=colors.HexColor("#1F2937"),
        leading=11,
    )
    weak_title_style = ParagraphStyle(
        "WeakTitle",
        parent=small_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#EF4444"),
        spaceAfter=2,
    )
    footer_left_style = ParagraphStyle(
        "FooterLeft",
        parent=small_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1E3A8A"),
    )
    footer_right_style = ParagraphStyle(
        "FooterRight",
        parent=small_style,
        alignment=2,
        textColor=colors.HexColor("#6B7280"),
    )
    copyright_style = ParagraphStyle(
        "Copyright",
        parent=small_style,
        alignment=1,
        fontSize=7.5,
        textColor=colors.HexColor("#9CA3AF"),
    )

    story = []
    story.append(Paragraph(context["generated_at"], timestamp_style))
    logo_path = _resolve_printable_logo_path()
    if logo_path:
        logo = Image(logo_path, width=30 * mm, height=30 * mm)
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 1))
    story.append(Paragraph("THE RANKERS ACADEMY", title_style))
    divider = Table([[""]], colWidths=[50 * mm], rowHeights=[1.5 * mm])
    divider.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1E3A8A")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    divider.hAlign = "CENTER"
    story.append(divider)
    story.append(Spacer(1, 3))
    story.append(Paragraph("Student Self-Diagnostic Test Report", subtitle_style))

    info_rows = [
        [Paragraph("Student Name", label_style), Paragraph(context["student_name"], value_style),
         Paragraph("Username", label_style), Paragraph(context["username"], value_style)],
        [Paragraph("School", label_style), Paragraph(context["school"], value_style),
         Paragraph("Class", label_style), Paragraph(str(context["class"]), value_style)],
        [Paragraph("Board", label_style), Paragraph(context["board"], value_style),
         Paragraph("Gender", label_style), Paragraph(context["gender"], value_style)],
        [Paragraph("Test No", label_style), Paragraph(str(context["test_no"]), value_style),
         Paragraph("Test Date", label_style), Paragraph(context["test_date"], value_style)],
    ]
    info_table = Table(info_rows, colWidths=[28 * mm, 57 * mm, 28 * mm, 57 * mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F4F6")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Performance Summary", summary_heading_style))
    score_table = Table(
        [
            [
                Paragraph("Total Score", label_style),
                Paragraph("Previous Score", label_style),
            ],
            [
                Paragraph("<font color='#1E3A8A' size='16'><b>%s</b></font>" % context["total_score"], value_style),
                Paragraph("<font color='#1F2937' size='16'><b>%s</b></font>" % context["previous_score"], value_style),
            ],
        ],
        colWidths=[87 * mm, 87 * mm],
    )
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 12))

    for subject in context["subjects"]:
        story.append(Paragraph(subject["name"], subject_style))
        table_data = [["Sr No", "Chapter", "Total", "Correct", "Unknown", "Coverage"]]
        for idx, chapter in enumerate(subject["chapters"], start=1):
            table_data.append([
                f"{idx:02d}",
                chapter["name"],
                str(chapter["total"]),
                str(chapter["correct"]),
                str(chapter["unknown"]),
                str(chapter["coverage"]),
            ])

        report_table = Table(table_data, colWidths=[14 * mm, 73 * mm, 18 * mm, 22 * mm, 22 * mm, 22 * mm])
        report_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(report_table)
        story.append(Spacer(1, 6))

        weak_topic_lines = [Paragraph("Weak Topics", weak_title_style)]
        if subject["weak_topics"]:
            for idx, topic in enumerate(subject["weak_topics"], start=1):
                weak_topic_lines.append(Paragraph(f"{idx:02d}. {topic}", small_style))
        else:
            weak_topic_lines.append(Paragraph("No weak topics.", small_style))

        weak_table = Table([[weak_topic_lines]], colWidths=[171 * mm])
        weak_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
            ("LINEBEFORE", (0, 0), (0, -1), 2, colors.HexColor("#EF4444")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(weak_table)
        story.append(Spacer(1, 10))

    footer_left_content = [Paragraph("THE RANKERS ACADEMY", footer_left_style)]
    if logo_path:
        footer_logo = Image(logo_path, width=16 * mm, height=16 * mm)
        footer_logo.hAlign = "LEFT"
        footer_left_content.insert(0, footer_logo)

    footer = Table([[
        footer_left_content,
        Paragraph("Plot No. 10, Buty Layout Laxmi Nagar, Nagpur- 440022<br/>info@therankersacademy.com<br/>+91 8329100890", footer_right_style),
    ]], colWidths=[75 * mm, 96 * mm])
    footer.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.HexColor("#E5E7EB")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(footer)
    story.append(Spacer(1, 6))
    story.append(Paragraph("Copyright (c) 2026 The Ranker's Academy, All Rights Reserved | Student Self Diagnostic Report", copyright_style))

    doc.build(story)

    pdf_bytes = buffer.getvalue()
    buffer.close()
    filename = f"student_diagnostic_report_{target_user.username}.pdf"
    return pdf_bytes, filename


@login_required
def print_report(request, student_id: int):
    
    user = request.user

    is_admin_or_teacher = _is_admin_or_teacher(user)
    
    if not is_admin_or_teacher:
        if not hasattr(user, "student") or user.student.id != student_id:
            return HttpResponseForbidden("Not allowed.")
        student_obj = user.student
        target_user = student_obj.user
    else:
        student_obj = get_object_or_404(Student, id=student_id)
        
        if not _can_manage_all(user):
            if not _teacher_can_access_student(user, student_obj):
                return HttpResponseForbidden("You can only access reports for students in your assigned grade/board/batch.")
        
        target_user = student_obj.user

    context = _build_printable_report_context(student_obj, target_user)

    response = render(request, "printable_report.html", context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@require_POST
@csrf_protect
@login_required
def send_report_email_api(request):
   
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        data = json.loads(request.body)
        student_id = data.get('student_id')
        
        if not student_id:
            return JsonResponse({'success': False, 'msg': 'Student ID is required'}, status=400)
        
        # Get the student
        student = get_object_or_404(Student, id=student_id)
        
        # Check permission - user must be the student or admin/teacher
        if not (
            request.user.is_superuser
            or (hasattr(request.user, 'teacheradmin') and request.user.teacheradmin.role in ('Admin', 'Teacher'))
            or (hasattr(request.user, 'student') and request.user.student.id == student.id)
        ):
            return JsonResponse({'success': False, 'msg': 'Permission denied'}, status=403)
        
        # Check if student has email
        if not student.email:
            return JsonResponse({'success': False, 'msg': 'Student does not have an email address'}, status=400)

        target_user = student.user
        send_time = timezone.now().astimezone(ZoneInfo("Asia/Kolkata"))
        generated_at = f"{send_time.month}/{send_time.day}/{str(send_time.year)[-2:]}, {send_time.strftime('%I:%M %p').lstrip('0')}"
        pdf_bytes, filename = _generate_printable_layout_pdf_bytes(student, target_user, generated_at=generated_at)
        overall_percent = f"{_compute_overall_percent(target_user):.1f}"

        email_sent = send_report_pdf_on_email(
            student_email=student.email,
            pdf_bytes=pdf_bytes,
            filename=filename,
            student_name=student.student_name or target_user.get_full_name() or target_user.username,
            subject_name="All Subjects",
            subject_percent=overall_percent,
            overall_percent=overall_percent,
            student_obj=student,
        )

        if not email_sent:
            return JsonResponse({'success': False, 'msg': 'Failed to send report email'}, status=500)

        logger.info(f"Report email sent successfully for student {student_id}")

        return JsonResponse({
            'success': True,
            'msg': 'Report sent successfully to your email address.'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Error scheduling PDF generation: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'msg': f'Error: {str(e)}'}, status=500)


@login_required
def report(request):
    user = request.user

    student_obj = Student.objects.filter(user=user).first()

    coverages = (
        SubjectCoverage.objects
        .filter(user=user)
        .select_related("subject")
        .order_by("subject__name")
    )

    overall_obj = OverallCoverage.objects.filter(user=user).first()
    if overall_obj:
        overall_percent = float(overall_obj.overall_percent)
    else:
        percents = [float(c.subject_percent) for c in coverages]
        overall_percent = (sum(percents) / len(percents)) if percents else 0.0

    overall_percent_int = int(round(overall_percent))

    subject_percents = [float(c.subject_percent) for c in coverages]
    top_count = sum(1 for p in subject_percents if p > 85)
    good_count = sum(1 for p in subject_percents if (p > 60 and p < 85))
    focus_count = sum(1 for p in subject_percents if p < 60)

    subject_ids = [c.subject_id for c in coverages]

    topics = (
        Topic.objects
        .filter(chapter__subject_id__in=subject_ids)
        .select_related("chapter", "chapter__subject")
    )

    topics_by_subject = {}
    for t in topics:
        sid = t.chapter.subject_id
        topics_by_subject.setdefault(sid, []).append(t)

    total_topics_map = {}
    for t in topics:
        sid = t.chapter.subject_id
        total_topics_map[sid] = total_topics_map.get(sid, 0) + 1

    q_counts = (
        Question.objects
        .filter(topic_id__in=[t.id for t in topics])
        .values("topic_id")
        .annotate(total=Count("id"))
    )
    question_count_by_topic = {x["topic_id"]: x["total"] for x in q_counts}

    
    latest_score_map = {}
    latest_correct_map = {} 
    latest_attempted_map = {} 

    for c in coverages:
        latest_test = (
            UserTest.objects
            .filter(user=user, subject=c.subject)
            .order_by("-created_at", "-test_number")
            .first()
        )

        total_topics = total_topics_map.get(c.subject_id, 0)
        if not latest_test or total_topics == 0:
            latest_score_map[c.subject_id] = 0
            latest_correct_map[c.subject_id] = set()
            latest_attempted_map[c.subject_id] = set()
        else:
            correct_ids = set(latest_test.correct_topics or [])
            latest_correct_map[c.subject_id] = correct_ids

            attempted_ids = set(getattr(latest_test, "attempted_topics", []) or [])
            latest_attempted_map[c.subject_id] = attempted_ids

            latest_score_map[c.subject_id] = int(round((len(correct_ids) / total_topics) * 100))

    labels = [c.subject.name for c in coverages]
    current_progress = [int(round(float(c.subject_percent))) for c in coverages]
    latest_scores = [latest_score_map.get(c.subject_id, 0) for c in coverages]
    remaining = [max(0, 100 - p) for p in current_progress]

    chart_payload = {
        "labels": labels,
        "current_progress": current_progress,
        "latest_scores": latest_scores,
        "remaining": remaining,
    }

    focus_recs = []
    strength_recs = []

    for c in coverages:
        percent = float(c.subject_percent)
        covered_ids = set(c.covered_topic_ids or [])
        subject_topics = topics_by_subject.get(c.subject_id, [])

        if percent < 50:
            remaining_topics = [t for t in subject_topics if t.id not in covered_ids]
            focus_recs.append({
                "subject": c.subject.name,
                "percent": int(round(percent)),
                "topics": [f"{t.chapter.name} → {t.name}" for t in remaining_topics],
            })

        if percent > 85:
            covered_topics = [t for t in subject_topics if t.id in covered_ids]
            strength_recs.append({
                "subject": c.subject.name,
                "percent": int(round(percent)),
                "topics": [f"{t.chapter.name} → {t.name}" for t in covered_topics],
            })

    pdf_subjects = []
    for c in coverages:
        sid = c.subject_id
        covered_ids = set(c.covered_topic_ids or [])
        correct_ids = latest_correct_map.get(sid, set())
        attempted_ids = latest_attempted_map.get(sid, set())

        rows = []
        weak_list = []
        not_attempted_list = []

        for t in topics_by_subject.get(sid, []):
            total_q = question_count_by_topic.get(t.id, 0)

            has_attempted_tracking = len(attempted_ids) > 0

            if has_attempted_tracking:
                if t.id not in attempted_ids:
                    status = "Not Attempted"
                    correct_q = 0
                    accuracy = "NA" if total_q == 0 else "0%"
                    not_attempted_list.append(f"{t.chapter.name} → {t.name}")
                else:
                    if t.id in correct_ids:
                        status = "Strong"
                        correct_q = total_q
                        accuracy = "100%" if total_q > 0 else "NA"
                    else:
                        status = "Weak"
                        correct_q = 0
                        accuracy = "0%" if total_q > 0 else "NA"
                        weak_list.append(f"{t.chapter.name} → {t.name}")
            else:
                if t.id in covered_ids:
                    status = "Strong"
                    correct_q = total_q
                    accuracy = "100%" if total_q > 0 else "NA"
                else:
                    status = "Not Attempted"
                    correct_q = 0
                    accuracy = "NA" if total_q == 0 else "0%"
                    not_attempted_list.append(f"{t.chapter.name} → {t.name}")

            if status in ("Weak", "Not Attempted"):
                rows.append([
                    t.chapter.name,          
                    t.name,                  
                    total_q,
                    correct_q,
                    accuracy,
                    status
                ])

        pdf_subjects.append({
            "name": c.subject.name,
            "rows": rows,
            "weak": weak_list,
            "not_attempted": not_attempted_list,
        })

    pdf_payload = {
        "academy": "Rankers Academy",
        "title": "Student Diagnostic Report",
        "student": {
            "name": student_obj.student_name if student_obj else user.get_full_name() or user.username,
            "exam": "Foundation Test",
            "age": "",
            "testDate": "",
            "class": student_obj.grade if student_obj else "",
            "rollNumber": "",
            "gender": student_obj.gender if student_obj else "",
        },
        "overall": {
            "score": round(overall_percent, 2),
            "level": _perf_label(overall_percent),
        },
        "subjects": pdf_subjects,
        "verdict": "The student shows partial syllabus coverage. Focused improvement in weak and not attempted areas is recommended to enhance performance.",
        "footer": "Generated by Rankers Academy | Personalized Learning Diagnostics",
    }

    context = {
        "overall_percent": overall_percent_int,
        "top_count": top_count,
        "good_count": good_count,
        "focus_count": focus_count,
        "chart_payload": chart_payload,
        "focus_recs": focus_recs,
        "strength_recs": strength_recs,
        "pdf_payload": pdf_payload,
        "student":student_obj,
    }
    return render(request, "report.html", context)

def ssc_state(request):
    subjects = Subject.objects.filter(
        grade__icontains='10',
        board__icontains='State'
    ).prefetch_related('chapters').order_by('name')
    
    study_material = {}
    for subject in subjects:
        chapters_data = []
        for chapter in subject.chapters.all():
            imp_q = ChapterImpQuestions.objects.filter(chapter=chapter).first()
            chapters_data.append({
                'id': chapter.id,
                'name': chapter.name,
                'imp_questions_url': imp_q.imp_questions.url if imp_q and imp_q.imp_questions else None,
                'imp_solutions_url': imp_q.imp_solutions.url if imp_q and imp_q.imp_solutions else None,
            })
        study_material[subject.name] = chapters_data
    
    return render(request, '10th_state.html', {'study_material': study_material})

def ssc_cbse(request):
    subjects = Subject.objects.filter(
        grade__icontains='10',
        board__icontains='CBSE'
    ).prefetch_related('chapters').order_by('name')
    
    study_material = {}
    for subject in subjects:
        chapters_data = []
        for chapter in subject.chapters.all():
            imp_q = ChapterImpQuestions.objects.filter(chapter=chapter).first()
            chapters_data.append({
                'id': chapter.id,
                'name': chapter.name,
                'imp_questions_url': imp_q.imp_questions.url if imp_q and imp_q.imp_questions else None,
                'imp_solutions_url': imp_q.imp_solutions.url if imp_q and imp_q.imp_solutions else None,
            })
        study_material[subject.name] = chapters_data
    
    return render(request, '10th_cbse.html', {'study_material': study_material})

def hsc_state(request):
    subjects = Subject.objects.filter(
        grade__icontains='12',
        board__icontains='State'
    ).prefetch_related('chapters').order_by('name')
    
    study_material = {}
    for subject in subjects:
        chapters_data = []
        for chapter in subject.chapters.all():
            imp_q = ChapterImpQuestions.objects.filter(chapter=chapter).first()
            chapters_data.append({
                'id': chapter.id,
                'name': chapter.name,
                'imp_questions_url': imp_q.imp_questions.url if imp_q and imp_q.imp_questions else None,
                'imp_solutions_url': imp_q.imp_solutions.url if imp_q and imp_q.imp_solutions else None,
            })
        study_material[subject.name] = chapters_data
    
    return render(request, '12th_state.html', {'study_material': study_material})

def hsc_cbse(request):
    subjects = Subject.objects.filter(
        grade__icontains='12',
        board__icontains='CBSE'
    ).prefetch_related('chapters').order_by('name')
    
    study_material = {}
    for subject in subjects:
        chapters_data = []
        for chapter in subject.chapters.all():
            imp_q = ChapterImpQuestions.objects.filter(chapter=chapter).first()
            chapters_data.append({
                'id': chapter.id,
                'name': chapter.name,
                'imp_questions_url': imp_q.imp_questions.url if imp_q and imp_q.imp_questions else None,
                'imp_solutions_url': imp_q.imp_solutions.url if imp_q and imp_q.imp_solutions else None,
            })
        study_material[subject.name] = chapters_data
    
    return render(request, '12th_cbse.html', {'study_material': study_material})





STATE_ALIASES = {
    "STATE", "STATE BOARD", "STATEBOARD", "SSC", "MSBSHSE", "MAHARASHTRA", "MAHARASHTRA BOARD",
}
CBSE_ALIASES = {
    "CBSE", "CENTRAL BOARD OF SECONDARY EDUCATION",
}

def _normalize_grade(raw: str) -> str:
    
    if raw is None:
        return ""
    g = str(raw).strip().lower().replace(" ", "")

    if g in {"10", "10th", "tenth", "x"}:
        return "10"
    if g in {"12", "12th", "twelfth", "xii"}:
        return "12"

    digits = "".join(ch for ch in g if ch.isdigit())
    if digits in {"10", "12"}:
        return digits

    return ""

def _normalize_board(raw: str) -> str:
    
    if raw is None:
        return ""
    b = str(raw).strip().upper()
    b_compact = b.replace(".", "").replace("-", " ").replace("_", " ")
    b_compact = " ".join(b_compact.split()) 

    if "CBSE" in b_compact:
        return "CBSE"
    if "STATE" in b_compact or "SSC" in b_compact or "MAHARASHTRA" in b_compact or "MSBSHSE" in b_compact:
        return "STATE"

    if b_compact in CBSE_ALIASES:
        return "CBSE"
    if b_compact in STATE_ALIASES:
        return "STATE"

    return ""

@login_required
def study_material_redirect(request):
   
    user = request.user

    student = getattr(user, "student", None)
    if not student:
        raise Http404("Student profile not found for this user.")

    raw_grade = (student.grade or "").strip()
    raw_board = (student.board or "").strip()
    grade = _normalize_grade(raw_grade)
    board = _normalize_board(raw_board)

    grade_digits = "".join(ch for ch in raw_grade if ch.isdigit())
    board_upper = raw_board.upper()

    candidate_pairs = []

    def add_candidate(g, b):
        pair = (g, b)
        if g and b and pair not in candidate_pairs:
            candidate_pairs.append(pair)

    add_candidate(grade, board)

    if grade_digits in {"10", "12"}:
        add_candidate(grade_digits, board)

    # Entrance-exam students like MHTCET usually need senior-secondary material.
    if "MHTCET" in board_upper:
        add_candidate("12", "STATE")
    if "NEET" in board_upper:
        add_candidate("12", "NEET")
        add_candidate("12", "STATE")
    if "JEE" in board_upper:
        add_candidate("8", "JEE")

    if grade_digits == "11":
        add_candidate("12", board)
        add_candidate("12", "STATE")

    add_candidate("12", "STATE")

    selected_pair = None
    subjects = Subject.objects.none()
    for candidate_grade, candidate_board in candidate_pairs:
        candidate_subjects = Subject.objects.filter(
            grade__icontains=candidate_grade,
            board__icontains=candidate_board
        ).prefetch_related('chapters').order_by('name')
        if candidate_subjects.exists():
            selected_pair = (candidate_grade, candidate_board)
            subjects = candidate_subjects
            break

    if selected_pair is None:
        selected_pair = candidate_pairs[0] if candidate_pairs else ("12", "STATE")

    selected_grade, selected_board = selected_pair

    template_map = {
        ("10", "STATE"): "10th_state.html",
        ("10", "CBSE"): "10th_cbse.html",
        ("12", "STATE"): "12th_state.html",
        ("12", "CBSE"): "12th_cbse.html",
        ("12", "NEET"): "12th_state.html",
        ("12", "MHTCET"): "12th_state.html",
        ("8", "JEE"): "10th_cbse.html",
    }

    template_name = template_map.get((selected_grade, selected_board), "12th_state.html")
    
    study_material = {}
    for subject in subjects:
        chapters_data = []
        for chapter in subject.chapters.all():
            imp_q = ChapterImpQuestions.objects.filter(chapter=chapter).first()
            chapters_data.append({
                'id': chapter.id,
                'name': chapter.name,
                'imp_questions_url': imp_q.imp_questions.url if imp_q and imp_q.imp_questions else None,
                'imp_solutions_url': imp_q.imp_solutions.url if imp_q and imp_q.imp_solutions else None,
            })
        study_material[subject.name] = chapters_data

    return render(request, template_name, {
        "student": student, 
        "grade": selected_grade, 
        "board": selected_board,
        "requested_grade": raw_grade,
        "requested_board": raw_board,
        "study_material": study_material
    })



@login_required
def api_student_progress(request):
   
    from django.http import JsonResponse
    from .models import SubjectCoverage, OverallCoverage, Subject, Chapter, Topic
    
    user = request.user
    
    overall = OverallCoverage.objects.filter(user=user).first()
    overall_percent = float(overall.overall_percent) if overall else 0.0
    
    grade = overall.grade if overall else ""
    board = overall.board if overall else ""
    
    subject_coverages = SubjectCoverage.objects.filter(user=user).select_related('subject')
    
    subjects_data = []
    for sc in subject_coverages:
        subject = sc.subject
        
        chapters = Chapter.objects.filter(subject=subject).prefetch_related('topics')
        chapter_details = []
        
        for chapter in chapters:
            topics = chapter.topics.all()
            total_topics = topics.count()
            
            chapter_cov = sc.chapter_coverage.get(str(chapter.id), {})
            covered_topics = chapter_cov.get('covered', 0)
            chapter_percent = chapter_cov.get('percent', 0)
            
            chapter_details.append({
                'id': chapter.id,
                'name': chapter.name,
                'total_topics': total_topics,
                'covered_topics': covered_topics,
                'percent': float(chapter_percent)
            })
        
        subjects_data.append({
            'id': subject.id,
            'name': subject.name,
            'grade': subject.grade,
            'board': subject.board,
            'percent': float(sc.subject_percent),
            'chapters': chapter_details
        })
    
    from .models import UserTest
    tests = UserTest.objects.filter(user=user).select_related('subject').order_by('-created_at')[:10]
    
    test_history = []
    for test in tests:
        test_history.append({
            'id': test.id,
            'subject': test.subject.name,
            'test_number': test.test_number,
            'correct_count': len(test.correct_topics),
            'attempted_count': len(test.attempted_topics),
            'created_at': test.created_at.isoformat()
        })
    
    return JsonResponse({
        'success': True,
        'data': {
            'overall_percent': overall_percent,
            'grade': grade,
            'board': board,
            'subjects': subjects_data,
            'test_history': test_history
        }
    })
