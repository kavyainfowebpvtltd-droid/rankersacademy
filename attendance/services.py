import http.client
import json
import logging
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from attendance.models import Attendance
from sds.models import Student


logger = logging.getLogger(__name__)

INDIA_TZ = ZoneInfo("Asia/Kolkata")
DEFAULT_CHECKIN_CUTOFF = time(8, 45)
ALPHA_CHECKIN_CUTOFF = time(8, 0)
CHECKOUT_CUTOFF = time(17, 0)


def get_local_now():
    return timezone.now().astimezone(INDIA_TZ)


def is_working_day(target_date: date) -> bool:
    return target_date.weekday() < 5


def previous_working_day(target_date: date) -> date:
    current = target_date - timedelta(days=1)
    while not is_working_day(current):
        current -= timedelta(days=1)
    return current


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    return digits[-10:] if len(digits) >= 10 else digits


def format_mobile(phone: str) -> str:
    normalized = normalize_phone(phone)
    if len(normalized) != 10:
        return ""
    return f"{getattr(settings, 'MSG91_COUNTRY_CODE', '91')}{normalized}"


def format_display_time(value: time | None) -> str:
    if not value:
        return "-"
    hour_24 = value.hour
    hour_12 = hour_24 % 12 or 12
    period = "AM" if hour_24 < 12 else "PM"
    return f"{hour_12}:{value.minute:02d} {period}"


def format_display_date(value: date) -> str:
    return value.strftime("%d-%m-%Y")


def parse_scan_timestamp(raw_timestamp: str | None) -> datetime:
    if not raw_timestamp:
        return get_local_now()

    parsed = parse_datetime(str(raw_timestamp).strip())
    if parsed is None:
        return get_local_now()

    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=INDIA_TZ)

    return parsed.astimezone(INDIA_TZ)


def batch_checkin_cutoff(student: Student) -> time:
    normalized_batch = re.sub(r"\s+", "", (student.batch or "").strip().lower())
    if "alpha" in normalized_batch or "aplha" in normalized_batch:
        return ALPHA_CHECKIN_CUTOFF
    return DEFAULT_CHECKIN_CUTOFF


def parse_scan_payload(raw_value: str) -> dict:
    raw_value = (raw_value or "").strip()
    if not raw_value:
        raise ValueError("Scanned QR code is empty.")

    parsed_data = {}

    def normalize_key(key: str) -> str:
        key = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower())
        return key.strip("_")

    if raw_value.startswith("{") and raw_value.endswith("}"):
        try:
            json_data = json.loads(raw_value)
            if isinstance(json_data, dict):
                parsed_data = {
                    normalize_key(key): str(value).strip()
                    for key, value in json_data.items()
                    if value is not None
                }
        except json.JSONDecodeError:
            parsed_data = {}

    if not parsed_data and any(separator in raw_value for separator in [";", "\n", "|", ","]):
        pieces = re.split(r"[;\n|,]+", raw_value)
        for piece in pieces:
            if "=" in piece:
                key, value = piece.split("=", 1)
            elif ":" in piece:
                key, value = piece.split(":", 1)
            else:
                continue
            normalized_key = normalize_key(key)
            if normalized_key:
                parsed_data[normalized_key] = value.strip()

    return {
        "raw": raw_value,
        "data": parsed_data,
    }


def resolve_student_from_scan(raw_value: str) -> tuple[Student, dict]:
    parsed = parse_scan_payload(raw_value)
    data = parsed["data"]
    raw = parsed["raw"]

    base_qs = Student.objects.select_related("user")

    def first_value(*keys):
        for key in keys:
            value = data.get(key)
            if value:
                return value
        return None

    numeric_id = first_value("student_id", "id")
    if numeric_id and str(numeric_id).isdigit():
        student = base_qs.filter(id=int(numeric_id)).first()
        if student:
            return student, parsed

    username = first_value(
        "username",
        "user",
        "user_name",
        "student_username",
        "student_code",
        "admission_no",
        "admission_number",
    )
    if username:
        student = base_qs.filter(user__username__iexact=username.strip()).first()
        if student:
            return student, parsed

    email = first_value("email", "email_id")
    if email:
        student = base_qs.filter(email__iexact=email.strip()).first()
        if student:
            return student, parsed

    phone = first_value(
        "contact",
        "contact_no",
        "contact_number",
        "mobile",
        "mobile_no",
        "mobile_number",
        "phone",
        "phone_no",
        "phone_number",
        "number",
    )
    normalized_phone = normalize_phone(phone)
    if len(normalized_phone) == 10:
        student = base_qs.filter(contact__regex=normalized_phone + r"$").first()
        if student:
            return student, parsed

    raw_phone_match = re.search(r"(?<!\d)(\d{10})(?!\d)", raw)
    if raw_phone_match:
        student = base_qs.filter(contact__regex=raw_phone_match.group(1) + r"$").first()
        if student:
            return student, parsed

    if raw.isdigit():
        student = base_qs.filter(id=int(raw)).first()
        if student:
            return student, parsed

    student = base_qs.filter(user__username__iexact=raw).first()
    if student:
        return student, parsed

    student = base_qs.filter(email__iexact=raw).first()
    if student:
        return student, parsed

    name = first_value("student_name", "name", "student", "full_name")
    batch = first_value("batch", "student_batch")
    if name and batch:
        matches = list(
            base_qs.filter(
                student_name__iexact=name.strip(),
                batch__iexact=batch.strip(),
            )[:2]
        )
        if len(matches) == 1:
            return matches[0], parsed

    if name:
        matches = list(base_qs.filter(student_name__iexact=name.strip())[:2])
        if len(matches) == 1:
            return matches[0], parsed

    exact_name_matches = list(base_qs.filter(student_name__iexact=raw)[:2])
    if len(exact_name_matches) == 1:
        return exact_name_matches[0], parsed

    raise ValueError(
        "Student could not be identified from this QR code. "
        "Use a QR code containing student id, username, contact, or email."
    )


def _attendance_sms_template(event: str) -> str:
    templates = {
        "checkin": getattr(
            settings,
            "MSG91_ATTENDANCE_CHECKIN_TEMPLATE",
            "69e9ebdab7357117ee02be94",
        ),
        "checkout": getattr(
            settings,
            "MSG91_ATTENDANCE_CHECKOUT_TEMPLATE",
            "69e9f17cf301542d5f04c6b2",
        ),
        "late_entry": getattr(
            settings,
            "MSG91_ATTENDANCE_LATE_TEMPLATE",
            "69e9f21e60f3a90e250bd294",
        ),
        "absent": getattr(
            settings,
            "MSG91_ATTENDANCE_ABSENT_TEMPLATE",
            "69e9f2fd177c9eba030ce112",
        ),
    }
    return templates[event]


def send_attendance_sms(student: Student, event: str, event_date: date, event_time: time | None = None) -> bool:
    mobile = format_mobile(student.contact)
    if not mobile:
        logger.warning("Skipping %s SMS for student %s due to invalid phone.", event, student.id)
        return False

    recipient = {
        "mobiles": mobile,
        "name": student.student_name,
    }

    if event in {"checkin", "checkout"} and event_time:
        recipient["time"] = format_display_time(event_time)
        recipient["date"] = format_display_date(event_date)
    elif event == "late_entry" and event_time:
        recipient["time"] = format_display_time(event_time)

    payload = {
        "template_id": _attendance_sms_template(event),
        "short_url": "0",
        "realTimeResponse": "1",
        "recipients": [recipient],
    }

    headers = {
        "accept": "application/json",
        "authkey": getattr(settings, "MSG91_AUTH_KEY", ""),
        "content-type": "application/json",
    }

    if not headers["authkey"]:
        logger.warning("Skipping %s SMS because MSG91_AUTH_KEY is not configured.", event)
        return False

    conn = None
    try:
        conn = http.client.HTTPSConnection(
            "control.msg91.com",
            timeout=getattr(settings, "MSG91_TIMEOUT_SECONDS", 30),
        )
        conn.request("POST", "/api/v5/flow", json.dumps(payload), headers)
        response = conn.getresponse()
        body = response.read().decode("utf-8", errors="replace")
        success = 200 <= response.status < 300
        if not success:
            logger.error("MSG91 %s SMS failed for student %s: %s", event, student.id, body)
        return success
    except Exception:
        logger.exception("MSG91 %s SMS failed for student %s.", event, student.id)
        return False
    finally:
        if conn:
            conn.close()


def _mark_sms_timestamp(attendance: Attendance, event: str, event_dt: datetime):
    timestamp_fields = {
        "checkin": "checkin_sms_sent_at",
        "late_entry": "late_entry_sms_sent_at",
        "checkout": "checkout_sms_sent_at",
        "absent": "absent_sms_sent_at",
    }
    field_name = timestamp_fields[event]
    if getattr(attendance, field_name):
        return
    setattr(attendance, field_name, event_dt)
    attendance.save(update_fields=[field_name])


def process_absent_attendance(target_date: date | None = None, allow_today: bool = False) -> int:
    local_now = get_local_now()
    target_date = target_date or local_now.date()

    if target_date > local_now.date():
        raise ValueError("Attendance cannot be processed for a future date.")

    if not is_working_day(target_date):
        return 0

    if target_date == local_now.date():
        if not allow_today:
            return 0
        if local_now.time() < CHECKOUT_CUTOFF:
            return 0

    existing_student_ids = set(
        Attendance.objects.filter(date=target_date).values_list("student_id", flat=True)
    )

    created_records = []
    for student in Student.objects.exclude(id__in=existing_student_ids).iterator():
        attendance = Attendance.objects.create(
            student=student,
            date=target_date,
            status="Absent",
        )
        created_records.append(attendance)

    event_dt = local_now if target_date == local_now.date() else datetime.combine(
        target_date,
        CHECKOUT_CUTOFF,
        tzinfo=INDIA_TZ,
    )

    for attendance in created_records:
        if send_attendance_sms(attendance.student, "absent", target_date):
            _mark_sms_timestamp(attendance, "absent", event_dt)

    return len(created_records)


def record_kiosk_scan(raw_value: str, scanned_at: str | None = None) -> dict:
    student, _ = resolve_student_from_scan(raw_value)
    local_dt = parse_scan_timestamp(scanned_at)
    attendance_date = local_dt.date()
    scan_time = local_dt.time().replace(second=0, microsecond=0)
    cutoff = batch_checkin_cutoff(student)

    with transaction.atomic():
        attendance, _ = Attendance.objects.select_for_update().get_or_create(
            student=student,
            date=attendance_date,
            defaults={"status": "Present"},
        )

        action = "already_checked_out"
        message = "Attendance already completed for today."
        update_fields = []
        sms_event = None

        if not attendance.check_in:
            attendance.check_in = scan_time
            attendance.check_out = None
            attendance.status = "Late" if scan_time > cutoff else "Present"
            update_fields.extend(["check_in", "check_out", "status"])
            if attendance.status == "Late":
                action = "late_entry"
                message = "Late entry recorded."
                sms_event = "late_entry"
            else:
                action = "checkin"
                message = "Check-in recorded."
                sms_event = "checkin"
        elif not attendance.check_out:
            if scan_time >= CHECKOUT_CUTOFF:
                attendance.check_out = scan_time
                update_fields.append("check_out")
                action = "checkout"
                message = "Check-out recorded."
                sms_event = "checkout"
            else:
                action = "already_checked_in"
                message = "Student is already checked in."

        if update_fields:
            attendance.save(update_fields=sorted(set(update_fields)))

    if sms_event and send_attendance_sms(student, sms_event, attendance_date, scan_time):
        _mark_sms_timestamp(attendance, sms_event, local_dt)

    return {
        "success": True,
        "student_id": student.id,
        "studentName": student.student_name,
        "studentClass": f"Grade {student.grade} ({student.board})",
        "studentBatch": student.batch,
        "photoUrl": "",
        "action": action,
        "actionText": {
            "checkin": "Checked In",
            "late_entry": "Late Entry Recorded",
            "checkout": "Checked Out",
            "already_checked_in": "Already Checked In",
            "already_checked_out": "Already Checked Out",
        }[action],
        "message": message,
        "timestamp": format_display_time(scan_time),
        "date": format_display_date(attendance_date),
        "status": attendance.status,
        "checkIn": format_display_time(attendance.check_in),
        "checkOut": format_display_time(attendance.check_out),
    }
