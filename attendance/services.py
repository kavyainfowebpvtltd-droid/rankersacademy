import http.client
import json
import logging
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import models
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from attendance.models import Attendance, StaffAttendance
from sds.models import Student, TeacherAdmin


logger = logging.getLogger(__name__)

INDIA_TZ = ZoneInfo("Asia/Kolkata")
DEFAULT_CHECKIN_CUTOFF = time(8, 45)
ALPHA_CHECKIN_CUTOFF = time(8, 0)
STAFF_CHECKIN_CUTOFF = time(9, 15)
CHECKOUT_CUTOFF = time(17, 0)
NON_TEACHING_BREAK_MINUTES = 30
NON_TEACHING_SLOT_COUNT = 3
NON_TEACHING_MAX_SCANS = NON_TEACHING_SLOT_COUNT * 2
NON_TEACHING_MIN_SLOT1_MINUTES = 210
NON_TEACHING_MAX_SLOT1_MINUTES = 240


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


def _first_scan_value(data: dict, *keys):
    for key in keys:
        value = data.get(key)
        if value:
            return value
    return None


def resolve_student_from_scan(raw_value: str) -> tuple[Student, dict]:
    parsed = parse_scan_payload(raw_value)
    data = parsed["data"]
    raw = parsed["raw"]

    base_qs = Student.objects.select_related("user")

    numeric_id = _first_scan_value(data, "student_id", "id")
    if numeric_id and str(numeric_id).isdigit():
        student = base_qs.filter(id=int(numeric_id)).first()
        if student:
            return student, parsed

    username = _first_scan_value(
        data,
        "username",
        "user",
        "user_name",
        "student_username",
        "student_code",
        "admission_no",
        "admission_number",
    )
    if username:
        student = base_qs.filter(
            models.Q(user__username__iexact=username.strip())
            | models.Q(username__iexact=username.strip())
        ).first()
        if student:
            return student, parsed

    email = _first_scan_value(data, "email", "email_id")
    if email:
        student = base_qs.filter(email__iexact=email.strip()).first()
        if student:
            return student, parsed

    phone = _first_scan_value(
        data,
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

    student = base_qs.filter(
        models.Q(user__username__iexact=raw) | models.Q(username__iexact=raw)
    ).first()
    if student:
        return student, parsed

    student = base_qs.filter(email__iexact=raw).first()
    if student:
        return student, parsed

    name = _first_scan_value(data, "student_name", "name", "student", "full_name")
    batch = _first_scan_value(data, "batch", "student_batch")
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


def resolve_staff_from_scan(raw_value: str) -> tuple[TeacherAdmin, dict]:
    parsed = parse_scan_payload(raw_value)
    data = parsed["data"]
    raw = parsed["raw"]

    base_qs = TeacherAdmin.objects.select_related("user")

    numeric_id = _first_scan_value(data, "staff_id", "teacher_id", "employee_id", "id")
    if numeric_id and str(numeric_id).isdigit():
        staff = base_qs.filter(id=int(numeric_id)).first()
        if staff:
            return staff, parsed

    username = _first_scan_value(
        data,
        "username",
        "user",
        "user_name",
        "staff_username",
        "teacher_username",
        "employee_code",
        "staff_code",
    )
    if username:
        staff = base_qs.filter(
            models.Q(user__username__iexact=username.strip())
            | models.Q(username__iexact=username.strip())
        ).first()
        if staff:
            return staff, parsed

    email = _first_scan_value(data, "email", "email_id")
    if email:
        staff = base_qs.filter(email__iexact=email.strip()).first()
        if staff:
            return staff, parsed

    phone = _first_scan_value(
        data,
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
        staff = base_qs.filter(contact__regex=normalized_phone + r"$").first()
        if staff:
            return staff, parsed

    raw_phone_match = re.search(r"(?<!\d)(\d{10})(?!\d)", raw)
    if raw_phone_match:
        staff = base_qs.filter(contact__regex=raw_phone_match.group(1) + r"$").first()
        if staff:
            return staff, parsed

    if raw.isdigit():
        staff = base_qs.filter(id=int(raw)).first()
        if staff:
            return staff, parsed

    staff = base_qs.filter(
        models.Q(user__username__iexact=raw)
        | models.Q(username__iexact=raw)
        | models.Q(email__iexact=raw)
    ).first()
    if staff:
        return staff, parsed

    name = _first_scan_value(data, "staff_name", "teacher_name", "name", "full_name")
    role = _first_scan_value(data, "role", "designation")
    if name and role:
        matches = list(
            base_qs.filter(
                name__iexact=name.strip(),
                role__iexact=role.strip(),
            )[:2]
        )
        if len(matches) == 1:
            return matches[0], parsed

    if name:
        matches = list(base_qs.filter(name__iexact=name.strip())[:2])
        if len(matches) == 1:
            return matches[0], parsed

    exact_name_matches = list(base_qs.filter(name__iexact=raw)[:2])
    if len(exact_name_matches) == 1:
        return exact_name_matches[0], parsed

    raise ValueError(
        "Staff member could not be identified from this QR code. "
        "Use a QR code containing staff id, username, contact, or email."
    )


def is_teaching_staff(staff: TeacherAdmin) -> bool:
    return (getattr(staff, "role", "") or "").strip().lower() == "teacher"


def _parse_clock_token(raw_value: str) -> time | None:
    token = (raw_value or "").strip().lower().replace(".", "")
    if not token:
        return None

    token = re.sub(r"\s+", " ", token)
    token = re.sub(r"(?<=\d)(am|pm)$", r" \1", token)
    token = token.upper()

    for fmt in ("%I:%M %p", "%I %p", "%I:%M%p", "%I%p", "%H:%M", "%H"):
        try:
            return datetime.strptime(token, fmt).time()
        except ValueError:
            continue
    return None


def parse_staff_working_hours(working_hours: str, target_date: date | None = None) -> dict | None:
    raw_value = (working_hours or "").strip()
    if not raw_value:
        return None

    parts = re.split(r"(?i)\s*(?:-|to)\s*", raw_value, maxsplit=1)
    if len(parts) != 2:
        return None

    start_time = _parse_clock_token(parts[0])
    end_time = _parse_clock_token(parts[1])
    if not start_time or not end_time:
        return None

    slot_date = target_date or get_local_now().date()
    start_dt = datetime.combine(slot_date, start_time, tzinfo=INDIA_TZ)
    end_dt = datetime.combine(slot_date, end_time, tzinfo=INDIA_TZ)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)

    total_minutes = int((end_dt - start_dt).total_seconds() // 60)
    if total_minutes <= 0:
        return None

    productive_minutes = max(total_minutes - NON_TEACHING_BREAK_MINUTES, 0)
    if productive_minutes <= 0:
        return None

    slot1_minutes = min(NON_TEACHING_MAX_SLOT1_MINUTES, productive_minutes)
    if productive_minutes > NON_TEACHING_MIN_SLOT1_MINUTES:
        slot1_minutes = min(
            NON_TEACHING_MAX_SLOT1_MINUTES,
            max(NON_TEACHING_MIN_SLOT1_MINUTES, productive_minutes - 120),
        )
    slot1_minutes = min(slot1_minutes, productive_minutes)

    remaining_minutes = max(productive_minutes - slot1_minutes, 0)
    slot2_minutes = remaining_minutes // 2
    slot3_minutes = remaining_minutes - slot2_minutes

    slot1_end = start_dt + timedelta(minutes=slot1_minutes)
    slot2_start = slot1_end + timedelta(minutes=NON_TEACHING_BREAK_MINUTES)
    slot2_end = slot2_start + timedelta(minutes=slot2_minutes)
    slot3_start = slot2_end

    slot_windows = [
        ("Slot 1", start_dt, slot1_end),
        ("Slot 2", slot2_start, slot2_end),
        ("Slot 3", slot3_start, end_dt),
    ]

    return {
        "display": f"{format_display_time(start_dt.time())} - {format_display_time(end_dt.time())}",
        "start_time": start_dt.time(),
        "end_time": end_dt.time(),
        "checkin_cutoff": (start_dt + timedelta(minutes=15)).time(),
        "total_minutes": total_minutes,
        "slots": [
            {
                "label": label,
                "start": start.time(),
                "end": end.time(),
                "scheduled_display": f"{format_display_time(start.time())} - {format_display_time(end.time())}",
            }
            for label, start, end in slot_windows
        ],
    }


def _load_staff_scan_times(attendance: StaffAttendance | None) -> list[str]:
    if not attendance or not attendance.raw_scan_value:
        return []

    try:
        raw_value = json.loads(attendance.raw_scan_value)
    except (json.JSONDecodeError, TypeError):
        return []

    if isinstance(raw_value, dict):
        raw_value = raw_value.get("scans", [])

    if not isinstance(raw_value, list):
        return []

    scans = []
    for value in raw_value:
        if value is None:
            continue
        scan_value = str(value).strip()
        if scan_value:
            scans.append(scan_value)
    return scans


def _scan_value_to_minutes(value: str) -> int | None:
    try:
        hour, minute = map(int, str(value).split(":", 1))
    except (TypeError, ValueError):
        return None
    return (hour * 60) + minute


def _format_duration(minutes: int) -> str:
    if minutes <= 0:
        return "-"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours and remaining_minutes:
        return f"{hours}h {remaining_minutes}m"
    if hours:
        return f"{hours}h"
    return f"{remaining_minutes}m"


def build_non_teaching_attendance_snapshot(
    staff: TeacherAdmin,
    attendance: StaffAttendance | None = None,
    target_date: date | None = None,
) -> dict:
    slot_date = target_date or getattr(attendance, "date", None) or get_local_now().date()
    schedule = parse_staff_working_hours(getattr(staff, "working_hours", ""), target_date=slot_date)
    scans = _load_staff_scan_times(attendance)

    slots = []
    total_duration_minutes = 0

    for index in range(NON_TEACHING_SLOT_COUNT):
        scan_index = index * 2
        slot_schedule = schedule["slots"][index] if schedule and index < len(schedule["slots"]) else None
        check_in_value = scans[scan_index] if len(scans) > scan_index else "-"
        check_out_value = scans[scan_index + 1] if len(scans) > scan_index + 1 else "-"

        duration_minutes = 0
        if check_in_value != "-" and check_out_value != "-":
            check_in_minutes = _scan_value_to_minutes(check_in_value)
            check_out_minutes = _scan_value_to_minutes(check_out_value)
            if check_in_minutes is not None and check_out_minutes is not None and check_out_minutes >= check_in_minutes:
                duration_minutes = check_out_minutes - check_in_minutes
                total_duration_minutes += duration_minutes

        if check_in_value != "-" and check_out_value != "-":
            state_key = "complete"
            state_label = "Completed"
        elif check_in_value != "-":
            state_key = "progress"
            state_label = "In Progress"
        else:
            state_key = "pending"
            state_label = "Pending"

        slots.append(
            {
                "label": f"Slot {index + 1}",
                "scheduled_display": slot_schedule["scheduled_display"] if slot_schedule else "Working hours not set",
                "check_in_display": format_display_time(_parse_clock_token(check_in_value)) if check_in_value != "-" else "-",
                "check_out_display": format_display_time(_parse_clock_token(check_out_value)) if check_out_value != "-" else "-",
                "duration_display": _format_duration(duration_minutes),
                "state_key": state_key,
                "state_label": state_label,
            }
        )

    next_stage_map = {
        0: "slot1_checkin",
        1: "slot1_checkout",
        2: "slot2_checkin",
        3: "slot2_checkout",
        4: "slot3_checkin",
        5: "slot3_checkout",
    }

    return {
        "working_hours_display": schedule["display"] if schedule else ((getattr(staff, "working_hours", "") or "").strip() or "Not Set"),
        "working_hours_configured": schedule is not None,
        "slots": slots,
        "scan_count": len(scans),
        "next_stage": next_stage_map.get(len(scans), "completed"),
        "is_complete": len(scans) >= NON_TEACHING_MAX_SCANS,
        "total_duration_minutes": total_duration_minutes,
        "total_duration_display": _format_duration(total_duration_minutes),
        "daily_tasks": (attendance.daily_tasks if attendance else "") or "",
        "task_status": (attendance.task_status if attendance else "") or "",
        "checkin_cutoff": schedule["checkin_cutoff"] if schedule else STAFF_CHECKIN_CUTOFF,
    }


def _validate_staff_kiosk_credentials(
    staff: TeacherAdmin,
    username: str | None,
    password: str | None,
) -> str | None:
    entered_username = (username or "").strip()
    entered_password = password or ""

    valid_usernames = {
        value.strip().lower()
        for value in [getattr(staff, "username", ""), getattr(getattr(staff, "user", None), "username", "")]
        if value and str(value).strip()
    }

    if not entered_username or entered_username.lower() not in valid_usernames:
        return "Enter your correct username to continue."

    if not entered_password or not getattr(staff.user, "check_password", lambda _: False)(entered_password):
        return "Invalid staff credentials."

    return None


def _non_teaching_prompt_response(
    staff: TeacherAdmin,
    attendance: StaffAttendance | None,
    stage: str,
    message: str,
    target_date: date,
    *,
    show_task_input: bool = False,
    show_task_status_input: bool = False,
) -> dict:
    snapshot = build_non_teaching_attendance_snapshot(staff, attendance, target_date)
    return {
        "success": False,
        "requiresPrompt": True,
        "promptStage": stage,
        "staff_id": staff.id,
        "staffName": staff.name,
        "staffRole": staff.role,
        "studentName": staff.name,
        "studentClass": f"Staff | {staff.role}",
        "studentBatch": snapshot["working_hours_display"],
        "photoUrl": get_staff_photo_url(staff),
        "message": message,
        "date": format_display_date(target_date),
        "workingHours": snapshot["working_hours_display"],
        "showTaskInput": show_task_input,
        "showTaskStatusInput": show_task_status_input,
        "dailyTasks": snapshot["daily_tasks"],
        "taskStatus": snapshot["task_status"],
    }


def get_student_photo_url(student: Student) -> str:
    if not getattr(student, "profile_photo", None):
        return ""

    try:
        return student.profile_photo.url
    except Exception:
        photo_name = getattr(student.profile_photo, "name", "") or ""
        if not photo_name:
            return ""
        media_url = getattr(settings, "MEDIA_URL", "/media/")
        return urljoin(media_url, photo_name.replace("\\", "/"))


def get_staff_photo_url(staff: TeacherAdmin) -> str:
    if not getattr(staff, "profile_picture", None):
        return ""

    try:
        return staff.profile_picture.url
    except Exception:
        photo_name = getattr(staff.profile_picture, "name", "") or ""
        if not photo_name:
            return ""
        media_url = getattr(settings, "MEDIA_URL", "/media/")
        return urljoin(media_url, photo_name.replace("\\", "/"))


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
        "photoUrl": get_student_photo_url(student),
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


def record_staff_scan(
    raw_value: str,
    scanned_at: str | None = None,
    *,
    username: str | None = None,
    password: str | None = None,
    daily_tasks: str | None = None,
    task_status: str | None = None,
) -> dict:
    staff, parsed = resolve_staff_from_scan(raw_value)
    local_dt = parse_scan_timestamp(scanned_at)
    attendance_date = local_dt.date()
    scan_time = local_dt.time().replace(second=0, microsecond=0)

    if not is_teaching_staff(staff):
        schedule = parse_staff_working_hours(getattr(staff, "working_hours", ""), target_date=attendance_date)
        if schedule is None:
            return {
                "success": False,
                "message": "Working hours are not configured for this staff member. Please update User Management first.",
                "staffName": staff.name,
                "staffRole": staff.role,
            }

        with transaction.atomic():
            attendance, _ = StaffAttendance.objects.select_for_update().get_or_create(
                staff=staff,
                date=attendance_date,
                defaults={
                    "status": "Present",
                    "raw_scan_value": "[]",
                },
            )

            scans = _load_staff_scan_times(attendance)
            scan_count = len(scans)

            if scan_count >= NON_TEACHING_MAX_SCANS:
                snapshot = build_non_teaching_attendance_snapshot(staff, attendance, attendance_date)
                return {
                    "success": False,
                    "message": "All 3 slots for today are already recorded.",
                    "staffName": staff.name,
                    "staffRole": staff.role,
                    "studentName": staff.name,
                    "studentClass": f"Staff | {staff.role}",
                    "studentBatch": snapshot["working_hours_display"],
                    "photoUrl": get_staff_photo_url(staff),
                }

            current_scan_str = scan_time.strftime("%H:%M")
            if scans and scans[-1] == current_scan_str:
                return {
                    "success": False,
                    "message": "This scan was already recorded just now.",
                    "staffName": staff.name,
                    "staffRole": staff.role,
                }

            stage = {
                0: "slot1_checkin",
                1: "slot1_checkout",
                2: "slot2_checkin",
                3: "slot2_checkout",
                4: "slot3_checkin",
                5: "slot3_checkout",
            }[scan_count]

            if scan_count == 0:
                entered_tasks = (daily_tasks or "").strip()
                if not username or not password or not entered_tasks:
                    return _non_teaching_prompt_response(
                        staff,
                        attendance,
                        stage,
                        "Enter your username, password, and tasks for the day to begin Slot 1.",
                        attendance_date,
                        show_task_input=True,
                    )

                validation_error = _validate_staff_kiosk_credentials(staff, username, password)
                if validation_error:
                    return _non_teaching_prompt_response(
                        staff,
                        attendance,
                        stage,
                        validation_error,
                        attendance_date,
                        show_task_input=True,
                    )
                attendance.daily_tasks = entered_tasks

            if scan_count == NON_TEACHING_MAX_SCANS - 1:
                entered_status = (task_status or "").strip()
                if not username or not password or not entered_status:
                    return _non_teaching_prompt_response(
                        staff,
                        attendance,
                        stage,
                        "Enter your username, password, and task status to complete the day.",
                        attendance_date,
                        show_task_status_input=True,
                    )

                validation_error = _validate_staff_kiosk_credentials(staff, username, password)
                if validation_error:
                    return _non_teaching_prompt_response(
                        staff,
                        attendance,
                        stage,
                        validation_error,
                        attendance_date,
                        show_task_status_input=True,
                    )
                attendance.task_status = entered_status

            scans.append(current_scan_str)
            attendance.raw_scan_value = json.dumps(scans)

            action_type = "checkout" if scan_count % 2 == 1 else "checkin"
            slot_number = (scan_count // 2) + 1
            update_fields = ["raw_scan_value", "updated_at"]

            if not attendance.check_in:
                attendance.check_in = scan_time
                attendance.status = "Late" if scan_time > schedule["checkin_cutoff"] else "Present"
                update_fields.extend(["check_in", "status"])

            if len(scans) > 1:
                attendance.check_out = scan_time
                update_fields.append("check_out")

            if scan_count == 0:
                update_fields.append("daily_tasks")
            if scan_count == NON_TEACHING_MAX_SCANS - 1:
                update_fields.append("task_status")

            attendance.save(update_fields=sorted(set(update_fields)))

        snapshot = build_non_teaching_attendance_snapshot(staff, attendance, attendance_date)
        action_label = "Check-out" if action_type == "checkout" else "Check-in"

        return {
            "success": True,
            "staff_id": staff.id,
            "staffName": staff.name,
            "staffRole": staff.role,
            "staffContact": staff.contact,
            "staffEmail": staff.email,
            "studentName": staff.name,
            "studentClass": f"Staff | {staff.role}",
            "studentBatch": snapshot["working_hours_display"],
            "photoUrl": get_staff_photo_url(staff),
            "action": action_type,
            "actionText": f"Slot {slot_number} {action_label} recorded.",
            "message": f"Slot {slot_number} {action_label.lower()} recorded.",
            "timestamp": format_display_time(scan_time),
            "date": format_display_date(attendance_date),
            "status": attendance.status,
            "checkIn": format_display_time(attendance.check_in),
            "checkOut": format_display_time(attendance.check_out),
            "recordId": attendance.id,
            "workingHours": snapshot["working_hours_display"],
            "dailyTasks": snapshot["daily_tasks"],
            "taskStatus": snapshot["task_status"],
        }

    with transaction.atomic():
        attendance, _ = StaffAttendance.objects.select_for_update().get_or_create(
            staff=staff,
            date=attendance_date,
            defaults={
                "status": "Present",
                "raw_scan_value": "[]",
            },
        )

        # Handle raw_scan_value as a list of scan times
        try:
            scans = json.loads(attendance.raw_scan_value)
            if not isinstance(scans, list):
                scans = []
        except (json.JSONDecodeError, TypeError):
            scans = []
        
        # Determine the action and message based on scan count
        scan_count = len(scans)
        lecture_num = (scan_count // 2) + 1
        is_checkout = (scan_count % 2 == 1)
        
        if scan_count >= 8:
            return {
                "success": False, 
                "message": "All 4 lectures (8 scans) for today have already been recorded.",
                "staffName": staff.name
            }

        current_scan_str = scan_time.strftime("%H:%M")
        
        # Prevent double scans within a very short period (e.g., same minute)
        if scans and scans[-1] == current_scan_str:
            return {
                "success": False,
                "message": "This scan was already recorded just now.",
                "staffName": staff.name
            }

        scans.append(current_scan_str)
        attendance.raw_scan_value = json.dumps(scans)

        # Map action for UI feedback
        action_type = "checkout" if is_checkout else "checkin"
        slot_name = f"L{lecture_num}"
        message = f"{slot_name} {'Check-out' if is_checkout else 'Check-in'} recorded."

        update_fields = ["raw_scan_value", "updated_at"]

        # Maintain legacy check_in/check_out for general summary
        if not attendance.check_in:
            attendance.check_in = scan_time
            attendance.status = "Late" if scan_time > STAFF_CHECKIN_CUTOFF else "Present"
            update_fields.extend(["check_in", "status"])
        
        # Always update check_out to the latest scan if it's not the first one
        if len(scans) > 1:
            attendance.check_out = scan_time
            update_fields.append("check_out")

        attendance.save(update_fields=sorted(set(update_fields)))

    return {
        "success": True,
        "staff_id": staff.id,
        "staffName": staff.name,
        "staffRole": staff.role,
        "staffContact": staff.contact,
        "staffEmail": staff.email,
        "studentName": staff.name,
        "studentClass": f"Staff | {staff.role}",
        "studentBatch": staff.contact or staff.email or "",
        "photoUrl": get_staff_photo_url(staff),
        "action": action_type,
        "actionText": message,
        "message": message,
        "timestamp": format_display_time(scan_time),
        "date": format_display_date(attendance_date),
        "status": attendance.status,
        "checkIn": format_display_time(attendance.check_in),
        "checkOut": format_display_time(attendance.check_out),
        "recordId": attendance.id,
    }
