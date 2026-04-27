import json
from html import escape
from io import BytesIO
from datetime import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.mail import EmailMessage
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from attendance.models import Attendance
from attendance.services import (
    format_display_time,
    get_local_now,
    previous_working_day,
    process_absent_attendance,
    record_kiosk_scan,
)
from sds.models import Student


def _teacher_scope_batches(user):
    teacher = user.teacheradmin if hasattr(user, "teacheradmin") else None

    if not teacher:
        batches = list(Student.objects.values_list("batch", flat=True).distinct())
        return teacher, [batch for batch in batches if batch]

    if teacher.grade and teacher.board and teacher.batch:
        return teacher, [teacher.batch]

    if teacher.grade and teacher.board:
        batches = list(
            Student.objects.filter(
                grade=teacher.grade,
                board=teacher.board,
            ).values_list("batch", flat=True).distinct()
        )
        return teacher, [batch for batch in batches if batch]

    batches = list(Student.objects.values_list("batch", flat=True).distinct())
    return teacher, [batch for batch in batches if batch]


def _month_bounds(month_value: str | None):
    local_now = get_local_now()
    today = local_now.date()

    if month_value:
        try:
            year, month_num = map(int, month_value.split("-"))
            start_date = datetime(year, month_num, 1).date()
        except (TypeError, ValueError):
            start_date = datetime(today.year, today.month, 1).date()
    else:
        start_date = datetime(today.year, today.month, 1).date()

    if start_date.month == 12:
        end_date = datetime(start_date.year + 1, 1, 1).date()
    else:
        end_date = datetime(start_date.year, start_date.month + 1, 1).date()

    return start_date, end_date, f"{start_date.year}-{start_date.month:02d}", today


def _attendance_percent(present_like_count: int, total_count: int) -> float:
    if total_count <= 0:
        return 0
    return round((present_like_count / total_count) * 100, 1)


def _build_attendance_rows(start_date, end_date, today):
    students = list(
        Student.objects.all()
        .select_related("user")
        .order_by("student_name")
    )

    monthly_attendances = Attendance.objects.filter(
        student__in=students,
        date__gte=start_date,
        date__lt=end_date,
    ).order_by("date")

    attendance_map = {}
    for record in monthly_attendances:
        attendance_map.setdefault(record.student_id, []).append(record)

    today_records = {
        record.student_id: record
        for record in Attendance.objects.filter(student__in=students, date=today)
    }

    attendance_rows = []
    attendance_details = {}

    for student in students:
        records = attendance_map.get(student.id, [])
        present_count = sum(1 for record in records if record.status == "Present")
        late_count = sum(1 for record in records if record.status == "Late")
        absent_count = sum(1 for record in records if record.status == "Absent")
        total_days = len(records)
        present_like_count = present_count + late_count
        today_record = today_records.get(student.id)

        attendance_rows.append(
            {
                "student": student,
                "present_days": present_count,
                "late_days": late_count,
                "absent_days": absent_count,
                "total_days": total_days,
                "attendance_percent": _attendance_percent(present_like_count, total_days),
                "today_status": today_record.status if today_record else "Not Marked",
                "today_check_in": format_display_time(today_record.check_in) if today_record else "-",
                "today_check_out": format_display_time(today_record.check_out) if today_record else "-",
            }
        )

        attendance_details[str(student.id)] = [
            {
                "date": record.date.strftime("%d %b %Y"),
                "day": record.date.strftime("%A"),
                "status": record.status,
                "check_in": format_display_time(record.check_in),
                "check_out": format_display_time(record.check_out),
            }
            for record in records
        ]

    return attendance_rows, attendance_details


def _attendance_summary(attendance_rows):
    summary_present = sum(row["present_days"] + row["late_days"] for row in attendance_rows)
    summary_total = sum(row["total_days"] for row in attendance_rows)
    summary_avg = _attendance_percent(summary_present, summary_total)
    return summary_present, summary_total, summary_avg


def _attendance_export_bytes(attendance_rows, month_value):
    workbook_rows = [
        [
            "Sr. No.",
            "Student Name",
            "Contact",
            "Batch",
            "Present",
            "Late",
            "Absent",
            "Total",
            "Attendance %",
            "Today Status",
            "Check-in",
            "Check-out",
        ]
    ]

    for index, row in enumerate(attendance_rows, start=1):
        workbook_rows.append(
            [
                str(index),
                row["student"].student_name,
                row["student"].contact,
                row["student"].batch,
                str(row["present_days"]),
                str(row["late_days"]),
                str(row["absent_days"]),
                str(row["total_days"]),
                f'{row["attendance_percent"]}%',
                row["today_status"],
                row["today_check_in"],
                row["today_check_out"],
            ]
        )

    table_html = []
    for row in workbook_rows:
        cells = "".join(f"<td>{escape(str(value))}</td>" for value in row)
        table_html.append(f"<tr>{cells}</tr>")

    html = f"""<html>
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
</head>
<body>
  <table border="1">
    <tr><td colspan="12"><strong>Attendance Export - {escape(month_value)}</strong></td></tr>
    {''.join(table_html)}
  </table>
</body>
</html>"""
    return BytesIO(html.encode("utf-8")).getvalue()


def _attendance_export_recipient(user):
    if hasattr(user, "teacheradmin") and user.teacheradmin.email:
        return user.teacheradmin.email.strip()
    if user.email:
        return user.email.strip()
    return ""


def _attendance_redirect_url(month_value):
    return f"{reverse('attendance')}?month={month_value}"


@login_required
def attendance(request):
    if not (
        request.user.is_superuser
        or (hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role in ["Admin", "Teacher"])
    ):
        return HttpResponseForbidden("Only admins and teachers can access attendance.")

    teacher, batches = _teacher_scope_batches(request.user)

    start_date, end_date, month_value, today = _month_bounds(request.GET.get("month"))

    if today > start_date:
        process_absent_attendance(previous_working_day(today))

    attendance_rows, attendance_details = _build_attendance_rows(start_date, end_date, today)
    summary_present, summary_total, summary_avg = _attendance_summary(attendance_rows)
    paginator = Paginator(attendance_rows, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "attendance.html",
        {
            "batches": batches,
            "attendance_rows": page_obj.object_list,
            "attendance_details_json": json.dumps(attendance_details),
            "month": month_value,
            "teacher": teacher,
            "summary_present": summary_present,
            "summary_total": summary_total,
            "summary_avg": summary_avg,
            "today": today,
            "page_obj": page_obj,
            "paginator": paginator,
        },
    )


@login_required
@require_POST
def export_attendance_email(request):
    if not (
        request.user.is_superuser
        or (hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role in ["Admin", "Teacher"])
    ):
        return HttpResponseForbidden("Only admins and teachers can export attendance.")

    start_date, end_date, month_value, today = _month_bounds(request.POST.get("month"))

    if today > start_date:
        process_absent_attendance(previous_working_day(today))

    recipient_email = _attendance_export_recipient(request.user)
    if not recipient_email:
        messages.error(request, "No registered email found for your account.")
        return redirect(_attendance_redirect_url(month_value))

    attendance_rows, _ = _build_attendance_rows(start_date, end_date, today)
    export_bytes = _attendance_export_bytes(attendance_rows, month_value)
    filename = f"attendance-export-{month_value}.xls"

    email = EmailMessage(
        subject=f"Attendance Export - {month_value}",
        body=(
            "Please find the attendance export attached.\n\n"
            f"Month: {month_value}\n"
            f"Total Students: {len(attendance_rows)}\n\n"
            "Regards,\nRanker's Academy"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient_email],
    )
    email.attach(filename, export_bytes, "application/vnd.ms-excel")

    try:
        email.send(fail_silently=False)
        messages.success(request, f"Attendance export sent to {recipient_email}.")
    except Exception as exc:
        messages.error(request, f"Unable to send attendance export email: {exc}")

    return redirect(_attendance_redirect_url(month_value))


@login_required
@require_POST
def mark_attendance(request):
    if not (
        request.user.is_superuser
        or (hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role in ["Admin", "Teacher"])
    ):
        return JsonResponse({"success": False, "error": "Not allowed"}, status=403)

    student_id = request.POST.get("student_id")
    date_str = request.POST.get("date")
    status = request.POST.get("status")

    if not student_id or not date_str or not status:
        return JsonResponse({"success": False, "error": "Missing required fields"}, status=400)

    if status not in {"Present", "Late", "Absent"}:
        return JsonResponse({"success": False, "error": "Invalid attendance status"}, status=400)

    try:
        attendance_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"success": False, "error": "Invalid date format"}, status=400)

    student = get_object_or_404(Student, id=student_id)
    teacher = request.user.teacheradmin if hasattr(request.user, "teacheradmin") else None

    defaults = {
        "status": status,
        "marked_by": teacher,
    }
    if status == "Absent":
        defaults["check_in"] = None
        defaults["check_out"] = None

    Attendance.objects.update_or_create(
        student=student,
        date=attendance_date,
        defaults=defaults,
    )

    return JsonResponse({"success": True})


@login_required
def view_student_attendance(request, student_id):
    if not (
        request.user.is_superuser
        or (hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role in ["Admin", "Teacher"])
    ):
        return HttpResponseForbidden("Not allowed")

    student = get_object_or_404(Student, id=student_id)
    start_date, end_date, month_value, today = _month_bounds(request.GET.get("month"))

    if today > start_date:
        process_absent_attendance(previous_working_day(today))

    attendances = list(
        Attendance.objects.filter(
            student=student,
            date__gte=start_date,
            date__lt=end_date,
        ).order_by("date")
    )

    present_count = sum(1 for record in attendances if record.status == "Present")
    late_count = sum(1 for record in attendances if record.status == "Late")
    absent_count = sum(1 for record in attendances if record.status == "Absent")
    total_days = len(attendances)
    attendance_percent = _attendance_percent(present_count + late_count, total_days)

    return render(
        request,
        "student-attendance-detail.html",
        {
            "student": student,
            "attendances": attendances,
            "present_count": present_count,
            "late_count": late_count,
            "absent_count": absent_count,
            "total_days": total_days,
            "attendance_percent": attendance_percent,
            "month": month_value,
            "today": today,
        },
    )


@login_required
def my_attendance(request):
    if request.user.is_superuser or (
        hasattr(request.user, "teacheradmin") and request.user.teacheradmin.role in ["Admin", "Teacher"]
    ):
        return HttpResponseForbidden("Students only")

    try:
        student = request.user.student
    except Exception:
        return redirect("login")

    start_date, end_date, month_value, today = _month_bounds(request.GET.get("month"))

    if today > start_date:
        process_absent_attendance(previous_working_day(today))

    attendances = list(
        Attendance.objects.filter(
            student=student,
            date__gte=start_date,
            date__lt=end_date,
        ).order_by("date")
    )

    present_count = sum(1 for record in attendances if record.status == "Present")
    late_count = sum(1 for record in attendances if record.status == "Late")
    absent_count = sum(1 for record in attendances if record.status == "Absent")
    total_days = len(attendances)
    attendance_percent = _attendance_percent(present_count + late_count, total_days)

    return render(
        request,
        "my-attendance.html",
        {
            "student": student,
            "attendances": attendances,
            "present_count": present_count,
            "late_count": late_count,
            "absent_count": absent_count,
            "total_days": total_days,
            "attendance_percent": attendance_percent,
            "month": month_value,
            "today": today,
            "current_month": f"{today.year}-{today.month:02d}",
        },
    )


def qr_kiosk(request):
    return render(request, "qr-kiosk.html")


@csrf_exempt
@require_POST
def kiosk_scan_api(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = request.POST

    barcode = (
        payload.get("barcode")
        or payload.get("qr_data")
        or payload.get("qrData")
        or payload.get("code")
    )
    scanned_at = payload.get("scanned_at") or payload.get("timestamp")

    if not barcode:
        return JsonResponse({"success": False, "message": "No QR code data received."}, status=400)

    try:
        result = record_kiosk_scan(barcode, scanned_at=scanned_at)
        return JsonResponse(result)
    except ValueError as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)
    except Exception:
        return JsonResponse(
            {"success": False, "message": "Unable to process this QR scan right now."},
            status=500,
        )
