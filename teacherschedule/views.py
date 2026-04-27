from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta
import json
import csv
import os
import re
from collections import defaultdict

import pandas as pd
from pypdf import PdfReader

from sds.models import TeacherAdmin, Subject
from bridgecourse.models import BridgeSubject
from .models import SubjectSchedule, ScheduleEntry, UploadedSchedule


def serialize_schedule_entry(entry):
    """Convert a schedule entry into JSON-safe data for templates and APIs."""
    return {
        'id': entry.id,
        'date': entry.date.strftime('%Y-%m-%d'),
        'date_display': entry.date.strftime('%d-%m-%Y'),
        'subject': entry.subject.subject,
        'topic': entry.topic,
        'chapter': entry.chapter,
        'notes': entry.notes,
        'teacher': entry.teacher.name if entry.teacher else '-',
        'teacher_id': entry.teacher_id,
        'duration': entry.duration,
        'duration_display': entry.get_duration_display(),
        'dpp': entry.lecture_number,
        'lecture_number': entry.lecture_number,
        'dpp_file_url': entry.dpp_file.url if entry.dpp_file else '',
        'dpp_file_name': os.path.basename(entry.dpp_file.name) if entry.dpp_file else '',
        'lecture_time': entry.lecture_time.strftime('%H:%M') if entry.lecture_time else '',
        'lecture_time_display': entry.lecture_time.strftime('%I:%M %p') if entry.lecture_time else '-',
        'is_completed': entry.is_completed,
        'status_display': 'COMPLETED' if entry.is_completed else 'PENDING',
    }


def serialize_schedule_entries(entries):
    """Serialize schedule entries for JSON output."""
    return [serialize_schedule_entry(entry) for entry in entries]


def serialize_uploaded_file(uploaded_file):
    """Convert an uploaded schedule file into JSON-safe data."""
    teacher_name = uploaded_file.teacher.name if uploaded_file.teacher else "Unassigned"
    return {
        'id': uploaded_file.id,
        'file_name': uploaded_file.file_name,
        'file_type': uploaded_file.get_file_type_display(),
        'file_url': uploaded_file.file.url if uploaded_file.file else '',
        'file_path': uploaded_file.file.name if uploaded_file.file else '',
        'grade': uploaded_file.grade,
        'board': uploaded_file.board,
        'batch': uploaded_file.batch,
        'teacher': teacher_name,
        'teacher_id': uploaded_file.teacher_id,
        'folder_name': teacher_name,
        'uploaded_by': uploaded_file.uploaded_by.get_full_name() or uploaded_file.uploaded_by.username,
        'uploaded_at': uploaded_file.uploaded_at.strftime('%Y-%m-%d %H:%M:%S'),
        'uploaded_at_display': uploaded_file.uploaded_at.strftime('%d-%m-%Y %I:%M %p'),
    }


def delete_uploaded_schedule_record(uploaded_schedule):
    """Remove uploaded schedule metadata and stored file."""
    if uploaded_schedule.file:
        uploaded_schedule.file.delete(save=False)
    uploaded_schedule.delete()


def serialize_uploaded_files(uploaded_files):
    """Serialize uploaded schedule files for JSON output."""
    return [serialize_uploaded_file(uploaded_file) for uploaded_file in uploaded_files]


def normalize_text(value):
    """Normalize extracted text for display."""
    if value is None:
        return ""

    cleaned = str(value).replace("\u2013", "-").replace("\u2014", "-").replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def excel_cell_to_string(value):
    """Format Excel cell values for JSON output."""
    if pd.isna(value):
        return ""
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%d-%m-%Y")
        except Exception:
            pass
    return normalize_text(value)


def read_pdf_lines(file_path):
    """Extract non-empty lines from a PDF file."""
    reader = PdfReader(file_path)
    lines = []

    for page in reader.pages:
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            cleaned = normalize_text(raw_line)
            if cleaned:
                lines.append(cleaned)

    return lines


def chunk_lines(lines, chunk_size=25):
    """Split raw text into smaller blocks for display."""
    return [" ".join(lines[index:index + chunk_size]) for index in range(0, len(lines), chunk_size)]


def parse_chapter_line(line):
    """Parse chapter summary lines from lecture-plan PDFs."""
    parts = [normalize_text(part) for part in line.split("|") if normalize_text(part)]
    return {
        "title": parts[0] if parts else line,
        "schedule": " | ".join(parts[1:]) if len(parts) > 1 else "",
    }


def parse_lecture_block(block_lines):
    """Convert one lecture block into structured lecture data."""
    if not block_lines:
        return None

    cleaned_lines = [normalize_text(line) for line in block_lines if normalize_text(line)]
    if not cleaned_lines:
        return None

    combined = normalize_text(" ".join(cleaned_lines))
    lecture_match = re.match(r"^L(?P<number>\d+)\s+(?P<body>.+)$", combined, re.IGNORECASE)
    if not lecture_match:
        return None

    lecture_number = lecture_match.group("number")
    body = lecture_match.group("body")

    dpp_match = re.search(r"\bDPP\s+(?P<dpp>\d+)\s+(?P<duration>\d+\s*min)\b", body, re.IGNORECASE)
    dpp = dpp_match.group("dpp") if dpp_match else ""
    duration = dpp_match.group("duration") if dpp_match else ""
    description = re.sub(r"\bDPP\s+\d+\s+\d+\s*min\b", "", body, flags=re.IGNORECASE).strip()

    first_line = re.sub(r"^L\d+\s+", "", cleaned_lines[0], flags=re.IGNORECASE).strip()
    if len(cleaned_lines) > 1 and ";" not in first_line:
        title_lines = [first_line]
        for extra_line in cleaned_lines[1:]:
            if ";" in extra_line or "DPP" in extra_line.upper() or len(extra_line.split()) > 8:
                break
            title_lines.append(extra_line)
        title = normalize_text(" ".join(title_lines))
    else:
        title = normalize_text(first_line.split(";", 1)[0])

    return {
        "lecture_no": lecture_number,
        "title": title or description[:80],
        "details": normalize_text(description),
        "dpp": dpp,
        "duration": duration,
    }


def parse_lecture_plan_pdf(lines):
    """Parse lecture-by-lecture PDFs like the Chemistry sample."""
    chapters = []
    lectures = []
    current_block = []

    for line in lines:
        if re.match(r"^Chapter\s+\d+:", line, re.IGNORECASE):
            chapters.append(parse_chapter_line(line))
            continue

        if line.startswith("L#") or line.startswith("CHEMISTRY TEACHING PLAN") or line.startswith("THE RANKERS ACADEMY"):
            continue

        if re.match(r"^L\d+\b", line, re.IGNORECASE):
            lecture = parse_lecture_block(current_block)
            if lecture:
                lectures.append(lecture)
            current_block = [line]
            continue

        if current_block:
            current_block.append(line)

    lecture = parse_lecture_block(current_block)
    if lecture:
        lectures.append(lecture)

    return {
        "parse_type": "lecture_plan",
        "summary": f"{len(lectures)} lectures parsed",
        "chapters": chapters,
        "lectures": lectures,
        "phases": [],
        "sheets": [],
        "text_blocks": [],
    }


def parse_phase_plan_pdf(lines):
    """Parse phase-wise academic planner PDFs like the JEE planner sample."""
    phases = []
    current_phase = None
    ignored_prefixes = (
        "HOLIDAYS:",
        "FACULTY TEACHING PLAN",
        "THE RANKERS ACADEMY",
        "DPP POLICY:",
        "Physics (",
    )

    for line in lines:
        if line.startswith(ignored_prefixes):
            continue

        if re.match(r"^Phase\s+\d+", line, re.IGNORECASE):
            if current_phase:
                phases.append(current_phase)
            current_phase = {
                "phase": line,
                "overview": "",
                "items": [],
                "milestones": [],
            }
            continue

        if not current_phase:
            continue

        if not current_phase["overview"]:
            current_phase["overview"] = line
            continue

        if re.search(r"\bUT\s*\d+\b|Grand Test|Final mock|Last class|DUSSEHRA|DIWALI|SUMMER HOLIDAY|REVISION PLAN", line, re.IGNORECASE):
            current_phase["milestones"].append(line)
        else:
            current_phase["items"].append(line)

    if current_phase:
        phases.append(current_phase)

    return {
        "parse_type": "phase_plan",
        "summary": f"{len(phases)} phases parsed",
        "chapters": [],
        "lectures": [],
        "phases": phases,
        "sheets": [],
        "text_blocks": [],
    }


def parse_excel_schedule(file_path):
    """Parse Excel files into sheet/row data."""
    workbook = pd.ExcelFile(file_path)
    sheets = []

    for sheet_name in workbook.sheet_names:
        dataframe = workbook.parse(sheet_name).fillna("")
        if dataframe.empty and len(dataframe.columns) == 0:
            continue

        columns = [excel_cell_to_string(column) for column in dataframe.columns.tolist()]
        rows = []

        for _, row in dataframe.iterrows():
            values = [excel_cell_to_string(value) for value in row.tolist()]
            if any(value for value in values):
                rows.append(values)

        sheets.append({
            "name": sheet_name,
            "columns": columns,
            "rows": rows,
        })

    return {
        "parse_type": "spreadsheet",
        "summary": f"{len(sheets)} sheet(s) parsed",
        "chapters": [],
        "lectures": [],
        "phases": [],
        "sheets": sheets,
        "text_blocks": [],
    }


def parse_pdf_schedule(file_path):
    """Parse known PDF schedule layouts into structured content."""
    lines = read_pdf_lines(file_path)

    if any(re.match(r"^L\d+\b", line, re.IGNORECASE) for line in lines):
        return parse_lecture_plan_pdf(lines)

    if any(re.match(r"^Phase\s+\d+", line, re.IGNORECASE) for line in lines):
        return parse_phase_plan_pdf(lines)

    return {
        "parse_type": "raw_text",
        "summary": f"{len(lines)} lines extracted",
        "chapters": [],
        "lectures": [],
        "phases": [],
        "sheets": [],
        "text_blocks": chunk_lines(lines[:150]),
    }


def parse_uploaded_schedule(uploaded_schedule):
    """Build display-ready parsed content for an uploaded schedule."""
    serialized = serialize_uploaded_file(uploaded_schedule)

    try:
        if uploaded_schedule.file_type == "PDF":
            parsed_data = parse_pdf_schedule(uploaded_schedule.file.path)
        else:
            parsed_data = parse_excel_schedule(uploaded_schedule.file.path)
    except Exception as exc:
        parsed_data = {
            "parse_type": "raw_text",
            "summary": "File imported, but automatic parsing could not complete.",
            "chapters": [],
            "lectures": [],
            "phases": [],
            "sheets": [],
            "text_blocks": [normalize_text(exc)],
        }

    return {
        **serialized,
        **parsed_data,
    }


def group_parsed_imports_by_teacher(parsed_imports):
    """Group parsed imports by teacher/folder for template rendering."""
    grouped_imports = defaultdict(list)

    for parsed_import in parsed_imports:
        grouped_imports[parsed_import.get("teacher") or "Unassigned"].append(parsed_import)

    groups = []
    for teacher_name, items in grouped_imports.items():
        items.sort(key=lambda item: item["uploaded_at"], reverse=True)
        groups.append({
            "teacher": teacher_name,
            "folder_name": teacher_name,
            "items": items,
            "count": len(items),
        })

    groups.sort(key=lambda group: group["teacher"].lower())
    return groups


def split_teacher_subjects(subjects_text):
    """Split teacher subject text into normalized values."""
    if not subjects_text:
        return []
    return [
        normalize_text(part)
        for part in re.split(r"[,/\n]+", subjects_text)
        if normalize_text(part)
    ]


def infer_subject_name(uploaded_schedule, parsed_import):
    """Infer the subject name for imported content."""
    teacher_subjects = split_teacher_subjects(getattr(uploaded_schedule.teacher, "subjects", ""))
    candidate_text = " ".join([
        normalize_text(uploaded_schedule.file_name),
        normalize_text(parsed_import.get("summary")),
        " ".join(chapter.get("title", "") for chapter in parsed_import.get("chapters", [])[:5]),
        " ".join(lecture.get("title", "") for lecture in parsed_import.get("lectures", [])[:5]),
    ]).lower()

    subject_names = list(Subject.objects.values_list("name", flat=True).distinct())
    for teacher_subject in teacher_subjects:
        if teacher_subject.lower() in candidate_text:
            return teacher_subject

    for subject_name in subject_names:
        if normalize_text(subject_name).lower() in candidate_text:
            return normalize_text(subject_name)

    if teacher_subjects:
        return teacher_subjects[0]
    return "Imported Content"


def get_or_create_subject_schedule_for_upload(uploaded_schedule, parsed_import):
    """Resolve a subject schedule bucket for imported content."""
    subject_name = infer_subject_name(uploaded_schedule, parsed_import)
    teacher = uploaded_schedule.teacher
    grade = uploaded_schedule.grade if uploaded_schedule.grade not in {"", "All"} else (teacher.grade or "General")
    board = uploaded_schedule.board if uploaded_schedule.board not in {"", "General"} else (teacher.board or "General")
    batch = uploaded_schedule.batch if uploaded_schedule.batch else (teacher.batch or "B1")

    subject_schedule, _ = SubjectSchedule.objects.get_or_create(
        subject=subject_name,
        grade=grade,
        board=board,
        batch=batch,
    )
    return subject_schedule


def extract_topics_from_parsed_import(parsed_import):
    """Extract likely schedule topics from parsed import data."""
    topics = []

    for lecture in parsed_import.get("lectures", []):
        title = normalize_text(lecture.get("title"))
        if title:
            topics.append(title)

    for sheet in parsed_import.get("sheets", []):
        columns = [normalize_text(column).lower() for column in sheet.get("columns", [])]
        topic_index = next(
            (index for index, column in enumerate(columns) if column in {"topic", "topics", "lecture", "lecture topic"}),
            None,
        )
        if topic_index is None:
            continue

        for row in sheet.get("rows", []):
            if topic_index < len(row):
                topic = normalize_text(row[topic_index])
                if topic:
                    topics.append(topic)

    seen = set()
    unique_topics = []
    for topic in topics:
        key = topic.lower()
        if key not in seen:
            seen.add(key)
            unique_topics.append(topic)
    return unique_topics


def build_schedule_rows_from_import(uploaded_schedule, parsed_import):
    """Build schedule row payloads from parsed import content."""
    rows = []
    uploaded_date = uploaded_schedule.uploaded_at.date()

    for index, lecture in enumerate(parsed_import.get("lectures", []), start=1):
        topic = normalize_text(lecture.get("title"))
        if not topic:
            continue
        rows.append({
            "date": uploaded_date,
            "topic": topic,
            "chapter": normalize_text(lecture.get("details")),
            "notes": normalize_text(lecture.get("details")),
            "lecture_number": index,
        })

    if not rows and parsed_import.get("sheets"):
        row_index = 1
        for sheet in parsed_import.get("sheets", []):
            columns = [normalize_text(column).lower() for column in sheet.get("columns", [])]
            topic_index = next(
                (index for index, column in enumerate(columns) if column in {"topic", "topics", "lecture", "lecture topic"}),
                None,
            )
            if topic_index is None:
                continue

            for sheet_row in sheet.get("rows", []):
                if topic_index >= len(sheet_row):
                    continue
                topic = normalize_text(sheet_row[topic_index])
                if not topic:
                    continue
                rows.append({
                    "date": uploaded_date,
                    "topic": topic,
                    "chapter": normalize_text(sheet.get("name")),
                    "notes": "",
                    "lecture_number": row_index,
                })
                row_index += 1

    if not rows and parsed_import.get("phases"):
        for index, phase in enumerate(parsed_import.get("phases", []), start=1):
            topic = normalize_text(phase.get("phase"))
            if not topic:
                continue
            rows.append({
                "date": uploaded_date,
                "topic": topic,
                "chapter": normalize_text(phase.get("overview")),
                "notes": " ".join(phase.get("items", [])[:5]),
                "lecture_number": index,
            })

    if not rows:
        fallback_topic = normalize_text(os.path.splitext(uploaded_schedule.file_name)[0]) or "Imported Schedule"
        fallback_notes = " ".join((parsed_import.get("text_blocks") or [])[:3])
        rows.append({
            "date": uploaded_date,
            "topic": fallback_topic,
            "chapter": "",
            "notes": normalize_text(fallback_notes),
            "lecture_number": 1,
        })

    return rows


def link_schedule_entries_to_upload(uploaded_schedule):
    """Associate matching table rows with an uploaded schedule."""
    parsed_import = parse_uploaded_schedule(uploaded_schedule)
    topics = extract_topics_from_parsed_import(parsed_import)
    if not uploaded_schedule.teacher_id or not topics:
        return []

    matching_entries = list(
        ScheduleEntry.objects.filter(
            teacher_id=uploaded_schedule.teacher_id,
            topic__in=topics,
        ).filter(source_upload__isnull=True)
    )

    if not matching_entries:
        return []

    entry_ids = [entry.id for entry in matching_entries]
    ScheduleEntry.objects.filter(id__in=entry_ids).update(source_upload=uploaded_schedule)
    return entry_ids


def create_schedule_entries_for_upload(uploaded_schedule):
    """Create schedule table rows for an uploaded file when needed."""
    parsed_import = parse_uploaded_schedule(uploaded_schedule)
    subject_schedule = get_or_create_subject_schedule_for_upload(uploaded_schedule, parsed_import)
    rows = build_schedule_rows_from_import(uploaded_schedule, parsed_import)
    created_entries = []

    existing_entries = list(
        ScheduleEntry.objects.filter(source_upload=uploaded_schedule).select_related("subject", "teacher")
    )
    if existing_entries:
        return existing_entries

    lecture_numbers_by_date = {}

    for row in rows:
        entry_date = row["date"]
        if entry_date not in lecture_numbers_by_date:
            lecture_numbers_by_date[entry_date] = set(
                ScheduleEntry.objects.filter(
                    date=entry_date,
                    subject=subject_schedule,
                ).values_list("lecture_number", flat=True)
            )

        taken_numbers = lecture_numbers_by_date[entry_date]
        lecture_number = row.get("lecture_number") or 1
        while lecture_number in taken_numbers:
            lecture_number += 1

        topic = normalize_text(row.get("topic"))[:200]
        if not topic:
            continue

        chapter = normalize_text(row.get("chapter"))[:150]
        notes = normalize_text(row.get("notes"))

        entry = ScheduleEntry.objects.create(
            date=entry_date,
            subject=subject_schedule,
            teacher=uploaded_schedule.teacher,
            source_upload=uploaded_schedule,
            topic=topic,
            chapter=chapter,
            notes=notes,
            duration="1",
            lecture_number=lecture_number,
            lecture_time=None,
        )
        taken_numbers.add(lecture_number)
        created_entries.append(entry)

    return list(
        ScheduleEntry.objects.filter(id__in=[entry.id for entry in created_entries]).select_related("subject", "teacher")
    )


def get_teacher_admin(user):
    """Get TeacherAdmin object for a user"""
    try:
        return TeacherAdmin.objects.get(user=user)
    except TeacherAdmin.DoesNotExist:
        return None


def is_admin(user):
    """Check if user is admin or superuser"""
    if user.is_superuser:
        return True
    teacher = get_teacher_admin(user)
    return teacher and teacher.role == "Admin"


def is_teacher(user):
    """Check if user is teacher"""
    if user.is_superuser:
        return False
    teacher = get_teacher_admin(user)
    return teacher and teacher.role == "Teacher"


def get_next_lecture_number(entry_date, subject):
    """Return the next available lecture number for the given date and subject."""
    last_entry = (
        ScheduleEntry.objects.filter(date=entry_date, subject=subject)
        .order_by('-lecture_number')
        .first()
    )
    return (last_entry.lecture_number + 1) if last_entry else 1


@login_required
def index(request):
    """Main view - redirects based on role"""
    # Superuser gets admin view
    if request.user.is_superuser:
        return admin_schedule_management(request)
    
    teacher = get_teacher_admin(request.user)
    
    if not teacher:
        return render(request, 'teacherschedule/notAuthorized.html', {
            'message': 'You are not authorized to view this page.'
        })
    
    if teacher.role == "Admin":
        return admin_schedule_management(request)
    elif teacher.role == "Teacher":
        return teacher_schedule_viewer(request)
    else:
        return render(request, 'teacherschedule/notAuthorized.html', {
            'message': 'Invalid role.'
        })


@login_required
def admin_schedule_management(request):
    """Admin Schedule Management Page"""
    if not is_admin(request.user):
        return render(request, 'teacherschedule/notAuthorized.html', {
            'message': 'Admin access required.'
        })
    
    teachers = TeacherAdmin.objects.filter(role="Teacher")
    subjects = SubjectSchedule.objects.all()
    all_subjects = list(Subject.objects.all().values('name', 'grade', 'board', 'batch').distinct())
    bridge_subjects = [
        {
            'name': subject['subject_name'],
            'grade': subject['grade'],
            'board': subject['board'],
            'batch': 'B1',
        }
        for subject in BridgeSubject.objects.all().values('subject_name', 'grade', 'board')
    ]
    subject_map = {}
    for subject in all_subjects + bridge_subjects:
        key = (
            subject.get('name', ''),
            subject.get('grade', ''),
            subject.get('board', ''),
            subject.get('batch', 'B1'),
        )
        subject_map[key] = {
            'name': subject.get('name', ''),
            'grade': subject.get('grade', ''),
            'board': subject.get('board', ''),
            'batch': subject.get('batch', 'B1') or 'B1',
        }
    all_subjects = sorted(subject_map.values(), key=lambda item: (item['name'].lower(), item['grade'], item['board']))
    
    # Get filter parameters
    filter_subject = request.GET.get('subject', '')
    filter_date_from = request.GET.get('date_from', '')
    filter_date_to = request.GET.get('date_to', '')
    
    entries = ScheduleEntry.objects.select_related('subject', 'teacher').order_by('date', 'lecture_number')
    
    if filter_subject:
        entries = entries.filter(subject__subject=filter_subject)
    if filter_date_from:
        entries = entries.filter(date__gte=filter_date_from)
    if filter_date_to:
        entries = entries.filter(date__lte=filter_date_to)
    
    entries = list(entries[:50])
    uploaded_files = list(
        UploadedSchedule.objects.select_related('uploaded_by', 'teacher').order_by('-uploaded_at')[:50]
    )
    parsed_imports = [parse_uploaded_schedule(uploaded_file) for uploaded_file in uploaded_files]

    context = {
        'teachers': teachers,
        'subjects': subjects,
        'all_subjects': all_subjects,
        'entries': entries,
        'entries_json': serialize_schedule_entries(entries),
        'parsed_imports_json': parsed_imports,
        'parsed_import_groups_json': group_parsed_imports_by_teacher(parsed_imports),
        'filter_subject': filter_subject,
        'filter_date_from': filter_date_from,
        'filter_date_to': filter_date_to,
        'is_superuser': request.user.is_superuser,
    }
    
    return render(request, 'teacherschedule/admin-management.html', context)


@login_required
def teacher_schedule_viewer(request):
    """Teacher Schedule Viewer Page"""
    if not is_teacher(request.user):
        return render(request, 'teacherschedule/notAuthorized.html', {
            'message': 'Teacher access required.'
        })
    
    teacher = get_teacher_admin(request.user)
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    subject_filter = request.GET.get('subject', '')
    
    entries = ScheduleEntry.objects.filter(
        teacher=teacher,
    ).select_related('subject').order_by('date', 'lecture_number')
    
    if date_from:
        entries = entries.filter(date__gte=date_from)
    if date_to:
        entries = entries.filter(date__lte=date_to)
    if subject_filter:
        entries = entries.filter(subject__subject=subject_filter)
    
    # Calculate today's schedule
    today = timezone.now().date()
    today_entries = entries.filter(date=today)
    
    # Subject-wise topics count
    completed_count = entries.filter(is_completed=True).count()
    total_count = entries.count()
    completion_percent = (completed_count / total_count * 100) if total_count > 0 else 0
    uploaded_files = list(
        UploadedSchedule.objects.filter(teacher=teacher).select_related('uploaded_by', 'teacher').order_by('-uploaded_at')[:50]
    )
    parsed_imports = [parse_uploaded_schedule(uploaded_file) for uploaded_file in uploaded_files]
    
    context = {
        'teacher': teacher,
        'entries': entries[:50],
        'today_entries': today_entries,
        'completed_count': completed_count,
        'total_count': total_count,
        'completion_percent': round(completion_percent, 1),
        'date_from': date_from,
        'date_to': date_to,
        'subject_filter': subject_filter,
        'parsed_imports_json': parsed_imports,
    }
    
    return render(request, 'teacherschedule/teacher-viewer.html', context)


@login_required
def add_schedule_entry(request):
    """Add new schedule entry"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    if request.method == 'POST':
        created_entry = None
        try:
            if request.content_type and 'multipart/form-data' in request.content_type:
                data = request.POST
                uploaded_dpp_file = request.FILES.get('dpp_file')
            else:
                data = json.loads(request.body)
                uploaded_dpp_file = None
            
            # Get or create subject
            subject, _ = SubjectSchedule.objects.get_or_create(
                subject=data.get('subject'),
                grade=data.get('grade', '10'),
                board=data.get('board', 'CBSE'),
                batch=data.get('batch', 'B1')
            )

            entry_date = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
            lecture_number = get_next_lecture_number(entry_date, subject)

            if uploaded_dpp_file:
                file_extension = os.path.splitext(uploaded_dpp_file.name)[1].lower()
                if file_extension != '.pdf':
                    return JsonResponse({'error': 'Only PDF files are allowed for DPP upload'}, status=400)
            
            teacher_id = data.get('teacher_id') or None
            is_completed = str(data.get('is_completed', 'false')).lower() == 'true'

            created_entry = ScheduleEntry.objects.create(
                date=entry_date,
                subject=subject,
                topic=data.get('topic', ''),
                chapter=data.get('chapter', ''),
                notes=data.get('notes', ''),
                duration=data.get('duration', '1'),
                lecture_number=lecture_number,
                dpp_file=uploaded_dpp_file,
                lecture_time=datetime.strptime(data.get('lecture_time'), '%H:%M').time() if data.get('lecture_time') else None,
                teacher_id=teacher_id,
                is_completed=is_completed,
            )
            
            entry = ScheduleEntry.objects.select_related('subject', 'teacher').get(id=created_entry.id)
            return JsonResponse({
                'success': True,
                'entry_id': entry.id,
                'entry': serialize_schedule_entry(entry),
            })
        except Exception as e:
            if created_entry and created_entry.dpp_file:
                created_entry.dpp_file.delete(save=False)
            if created_entry and created_entry.pk:
                ScheduleEntry.objects.filter(pk=created_entry.pk).delete()
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def update_schedule_entry(request, entry_id):
    """Update schedule entry"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            entry = get_object_or_404(ScheduleEntry, id=entry_id)
            
            if 'topic' in data:
                entry.topic = data['topic']
            if 'chapter' in data:
                entry.chapter = data['chapter']
            if 'notes' in data:
                entry.notes = data['notes']
            if 'duration' in data:
                entry.duration = data['duration']
            if 'is_completed' in data:
                entry.is_completed = data['is_completed']
            if 'teacher_id' in data:
                entry.teacher_id = data['teacher_id']
            if 'lecture_time' in data:
                entry.lecture_time = datetime.strptime(data['lecture_time'], '%H:%M').time() if data['lecture_time'] else None
            
            entry.save()
            entry = ScheduleEntry.objects.select_related('subject', 'teacher').get(id=entry.id)
            
            return JsonResponse({'success': True, 'entry': serialize_schedule_entry(entry)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def delete_schedule_entry(request, entry_id):
    """Delete schedule entry"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    if request.method == 'POST':
        try:
            entry = get_object_or_404(ScheduleEntry, id=entry_id)
            if entry.dpp_file:
                entry.dpp_file.delete(save=False)
            entry.delete()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def get_calendar_data(request):
    """Get schedule data for calendar view"""
    month = request.GET.get('month')
    year = request.GET.get('year')
    
    if not month or not year:
        today = timezone.now()
        month = today.month
        year = today.year
    else:
        month = int(month)
        year = int(year)
    
    # Get all entries for the month
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date()
    else:
        end_date = datetime(year, month + 1, 1).date()
    
    entries = ScheduleEntry.objects.filter(
        date__gte=start_date,
        date__lt=end_date,
    ).select_related('subject', 'teacher')
    
    # Filter by teacher if teacher user
    if is_teacher(request.user):
        teacher = get_teacher_admin(request.user)
        entries = entries.filter(teacher=teacher)
    
    data = []
    for entry in entries:
        data.append({
            'id': entry.id,
            'date': entry.date.strftime('%Y-%m-%d'),
            'subject': entry.subject.subject,
            'topic': entry.topic,
            'teacher': entry.teacher.name if entry.teacher else '',
            'duration': entry.duration,
            'is_completed': entry.is_completed,
        })
    
    return JsonResponse({'entries': data})


@login_required
def bulk_assign_teacher(request):
    """Bulk assign teacher to schedule entries"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            entry_ids = data.get('entry_ids', [])
            teacher_id = data.get('teacher_id')
            
            ScheduleEntry.objects.filter(id__in=entry_ids).update(teacher_id=teacher_id)
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def export_schedule(request):
    """Export schedule to PDF/Excel"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    export_format = request.GET.get('format', 'excel')
    
    entries = ScheduleEntry.objects.select_related('subject', 'teacher').order_by('date', 'lecture_number')
    
    if export_format == 'excel':
        headers = [
            'Date',
            'Subject',
            'Grade',
            'Topic',
            'Chapter',
            'Teacher',
            'Duration',
            'Lecture #',
            'Lecture Time',
            'Completed',
            'Notes',
        ]
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=schedule.csv'
        writer = csv.writer(response)
        writer.writerow(headers)

        for entry in entries:
            writer.writerow([
                entry.date.strftime('%Y-%m-%d'),
                entry.subject.subject,
                entry.subject.grade,
                entry.topic,
                entry.chapter,
                entry.teacher.name if entry.teacher else '',
                entry.duration,
                entry.lecture_number,
                entry.lecture_time.strftime('%H:%M') if entry.lecture_time else '',
                'Yes' if entry.is_completed else 'No',
                entry.notes,
            ])

        writer.writerow([])
        writer.writerow(['Imported Files'])
        writer.writerow(['Teacher', 'File Name', 'Folder', 'Type', 'Imported At'])

        imported_files = UploadedSchedule.objects.select_related('teacher').order_by('teacher__name', '-uploaded_at')
        for uploaded_file in imported_files:
            writer.writerow([
                uploaded_file.teacher.name if uploaded_file.teacher else 'Unassigned',
                uploaded_file.file_name,
                uploaded_file.teacher.name if uploaded_file.teacher else 'Unassigned',
                uploaded_file.get_file_type_display(),
                uploaded_file.uploaded_at.strftime('%Y-%m-%d %H:%M'),
            ])

        return response
    
    return JsonResponse({'error': 'Invalid format'}, status=400)


@login_required
def import_schedule(request):
    """Upload teacher schedule file"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    uploaded_file = request.FILES.get('schedule_file')
    teacher_id = request.POST.get('teacher_id')
    if not uploaded_file:
        return JsonResponse({'error': 'Please select a file to import'}, status=400)
    if not teacher_id:
        return JsonResponse({'error': 'Please select a teacher for this import'}, status=400)

    file_extension = os.path.splitext(uploaded_file.name)[1].lower()
    allowed_file_types = {
        '.pdf': 'PDF',
        '.xls': 'EXCEL',
        '.xlsx': 'EXCEL',
    }

    if file_extension not in allowed_file_types:
        return JsonResponse({'error': 'Only PDF and Excel files are allowed'}, status=400)

    teacher = get_object_or_404(TeacherAdmin, id=teacher_id, role="Teacher")

    uploaded_schedule = None

    try:
        with transaction.atomic():
            uploaded_schedule = UploadedSchedule.objects.create(
                file_name=uploaded_file.name,
                file_type=allowed_file_types[file_extension],
                file=uploaded_file,
                grade=request.POST.get('grade', 'All'),
                board=request.POST.get('board', 'General'),
                batch=request.POST.get('batch', 'B1'),
                teacher=teacher,
                uploaded_by=request.user,
            )
            linked_entry_ids = link_schedule_entries_to_upload(uploaded_schedule)
            created_entries = create_schedule_entries_for_upload(uploaded_schedule)
            parsed_import = parse_uploaded_schedule(uploaded_schedule)
    except Exception as exc:
        if uploaded_schedule and uploaded_schedule.file:
            uploaded_schedule.file.delete(save=False)
        if uploaded_schedule and uploaded_schedule.pk:
            UploadedSchedule.objects.filter(pk=uploaded_schedule.pk).delete()
        return JsonResponse({'error': str(exc)}, status=400)

    return JsonResponse({
        'success': True,
        'message': f'{uploaded_file.name} imported successfully',
        'parsed_import': parsed_import,
        'linked_entry_ids': linked_entry_ids,
        'entries': serialize_schedule_entries(created_entries),
    })


@login_required
def delete_uploaded_schedule(request, upload_id):
    """Delete a single imported schedule file."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    try:
        uploaded_schedule = get_object_or_404(UploadedSchedule, id=upload_id)
        deleted_entry_ids = list(uploaded_schedule.schedule_entries.values_list('id', flat=True))
        delete_uploaded_schedule_record(uploaded_schedule)
        return JsonResponse({'success': True, 'deleted_entry_ids': deleted_entry_ids})
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)


@login_required
def bulk_delete_uploaded_schedules(request):
    """Delete multiple imported schedule files."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    try:
        data = json.loads(request.body)
        upload_ids = data.get('upload_ids', [])
        uploads = list(UploadedSchedule.objects.filter(id__in=upload_ids))
        deleted_entry_ids = list(
            ScheduleEntry.objects.filter(source_upload_id__in=upload_ids).values_list('id', flat=True)
        )

        for uploaded_schedule in uploads:
            delete_uploaded_schedule_record(uploaded_schedule)

        return JsonResponse({'success': True, 'deleted_count': len(uploads), 'deleted_entry_ids': deleted_entry_ids})
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)


@login_required
def mark_completed(request, entry_id):
    """Mark entry as completed"""
    if request.method == 'POST':
        try:
            entry = get_object_or_404(ScheduleEntry, id=entry_id)
            entry.is_completed = not entry.is_completed
            entry.save()
            return JsonResponse({'success': True, 'is_completed': entry.is_completed})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)
