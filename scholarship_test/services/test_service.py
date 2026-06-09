import logging
import hashlib
import re
from datetime import datetime
from functools import lru_cache
from django.conf import settings
from django.db import transaction, connection
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import timedelta
from zoneinfo import ZoneInfo
from sds.models import Student
from utils.media_urls import upload_url

logger = logging.getLogger(__name__)

TOTAL_QUESTIONS = 20
TEST_DURATION_MINUTES = 20
SUPPORTED_RUNTIME_QUESTION_TYPES = {"mcq", "tf", "fitb", "int"}
ACADEMY_TIMEZONE = ZoneInfo("Asia/Kolkata")
UTC_TIMEZONE = ZoneInfo("UTC")
OPTIONAL_ATTEMPT_SECURITY_FIELDS = {
    "started_at",
    "submitted_at",
    "violation_count",
    "security_status",
}
OPTIONAL_ATTEMPT_COMPAT_FIELDS = OPTIONAL_ATTEMPT_SECURITY_FIELDS | {
    "portal_student",
    "progress_state",
    "student_batch",
}
STUDENT_COMPAT_FIELDS = {
    "batch",
    "interested_exams",
    "profile_photo",
    "stream",
    "username",
}


def get_max_security_violations() -> int:
    configured_value = getattr(settings, "EXAM_SECURITY_MAX_VIOLATIONS", 3)
    try:
        configured_value = int(configured_value)
    except (TypeError, ValueError):
        configured_value = 3
    return max(1, configured_value)


def get_attempt_start_time(attempt):
    try:
        started_at = getattr(attempt, "started_at", None)
    except (OperationalError, ProgrammingError):
        started_at = None

    if started_at:
        return started_at

  
    if getattr(attempt, "status", "") != "started":
        return attempt.test_started_at

    return None


def _attempt_deferred_security_fields(attempt):
    try:
      deferred_fields = set(attempt.get_deferred_fields())
    except Exception:
      deferred_fields = set()
    return deferred_fields & OPTIONAL_ATTEMPT_SECURITY_FIELDS


def attempt_can_persist_security_fields(attempt) -> bool:
    return not _attempt_deferred_security_fields(attempt)


def _parse_optional_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _safe_model_field_value(instance, field_name, default=None):
    if not instance:
        return default

    try:
        deferred_fields = set(instance.get_deferred_fields())
    except Exception:
        deferred_fields = set()

    if (
        field_name in deferred_fields
        and (
            not hasattr(instance.__class__, "_meta")
            or not _model_has_columns(instance.__class__, field_name)
        )
    ):
        return default

    values = getattr(instance, "__dict__", {})
    if field_name in values:
        value = values.get(field_name)
    else:
        try:
            value = getattr(instance, field_name)
        except (AttributeError, OperationalError, ProgrammingError):
            return default

    return default if value is None else value


def _attempt_progress_state_data(attempt) -> dict:
    raw_state = _safe_model_field_value(attempt, "progress_state", {})
    return raw_state if isinstance(raw_state, dict) else {}


def get_attempt_started_at_value(attempt):
    started_at = attempt.__dict__.get("started_at")
    if started_at:
        return started_at

    state = _attempt_progress_state_data(attempt)
    parsed = _parse_optional_datetime(state.get("started_at"))
    if parsed is not None:
        return parsed

    return get_attempt_start_time(attempt)


def get_attempt_submitted_at_value(attempt):
    submitted_at = attempt.__dict__.get("submitted_at")
    if submitted_at:
        return submitted_at

    state = _attempt_progress_state_data(attempt)
    parsed = _parse_optional_datetime(state.get("submitted_at"))
    if parsed is not None:
        return parsed

    return None


def get_attempt_violation_count_value(attempt) -> int:
    raw_value = attempt.__dict__.get("violation_count")
    if raw_value is None:
        state = _attempt_progress_state_data(attempt)
        raw_value = state.get("violation_count", 0)
    try:
        return max(0, int(raw_value or 0))
    except (TypeError, ValueError):
        return 0


def get_attempt_security_status_value(attempt) -> str:
    security_status = attempt.__dict__.get("security_status")
    if security_status:
        return str(security_status)

    state = _attempt_progress_state_data(attempt)
    state_status = state.get("security_status")
    if state_status:
        return str(state_status)
    if state.get("security_locked"):
        return "locked"
    if state.get("submitted_at"):
        return "submitted"

    if getattr(attempt, "status", "") in ["completed", "expired"]:
        return "submitted"
    if getattr(attempt, "status", "") == "in_progress":
        return "warning" if get_attempt_violation_count_value(attempt) > 0 else "active"
    return "pending"
SUBJECT_BUCKETS = ("phy", "chm", "bio", "math")


def calculate_score_percentage(score: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, round((score * 100) / total))


def _send_attempt_result_sms(attempt, score: int, total_questions: int, scholarship_percentage: int):
    from scholarship_test.services.sms_service import (
        send_scholarship_result_sms_dlt,
    )

    student = attempt.student
    if not student.phone_number:
        logger.error(f"Cannot send SMS: Student {student.id} has no phone number")
        return False, "No phone number on student record"

    if requires_otp_login(attempt.test):
        return send_scholarship_result_sms_dlt(
            phone_number=student.phone_number,
            student_name=student.name,
            score=score,
            total_questions=total_questions,
            scholarship_percentage=scholarship_percentage,
        )
    return False, None


def is_rtse_test(test) -> bool:
    if not test or not getattr(test, "name", ""):
        return False

    name_lower = test.name.lower()
    normalized = re.sub(r'[^a-z0-9]+', '', name_lower)
    return (
        ('rtse' in name_lower and '2026' in test.name)
        or normalized == 'rtse2026scholarshiptest'
    )


def is_scholarship_test(test) -> bool:
    if not test or not getattr(test, "name", ""):
        return False

    normalized = re.sub(r'[^a-z0-9]+', '', test.name.lower())
    return normalized == 'scholarshiptest'


def requires_otp_login(test) -> bool:
    return is_rtse_test(test) or is_scholarship_test(test)


def _normalize_subject_bucket(subject_name: str) -> str:
    value = re.sub(r"[^a-z]", "", str(subject_name or "").lower())
    if "phy" in value or "physics" in value:
        return "phy"
    if "chem" in value:
        return "chm"
    if "bio" in value or "botany" in value or "zoology" in value:
        return "bio"
    if "math" in value:
        return "math"
    return ""


def recompute_portal_student_leaderboard(portal_student_id: int):
    from scholarship_test.models import ScholarshipStudentLeaderboard, ScholarshipTestAttempt
    from sds.models import Student

    if not portal_student_id:
        return

    try:
        portal_student = Student.objects.get(id=portal_student_id)
    except Student.DoesNotExist:
        return

    attempts = (
        ScholarshipTestAttempt.objects
        .filter(
            portal_student_id=portal_student_id,
            status__in=["completed", "expired"],
            test__isnull=False,
        )
        .defer(
            "started_at",
            "submitted_at",
            "violation_count",
            "security_status",
        )
        .select_related("test")
        .order_by("test_id", "test_completed_at", "id")
    )

    latest_by_test = {}
    for attempt in attempts:
        latest_by_test[attempt.test_id] = attempt

    marks = {bucket: 0 for bucket in SUBJECT_BUCKETS}
    counts = {bucket: 0 for bucket in SUBJECT_BUCKETS}
    for attempt in latest_by_test.values():
        bucket = _normalize_subject_bucket(getattr(attempt.test, "subject", ""))
        if not bucket:
            continue
        marks[bucket] += int(attempt.score or 0)
        counts[bucket] += 1

    total_score = sum(marks.values())
    aggregate, _created = ScholarshipStudentLeaderboard.objects.get_or_create(
        portal_student=portal_student,
        defaults={"student_batch": portal_student.batch or ""},
    )
    aggregate.student_batch = portal_student.batch or ""
    aggregate.phy_marks = marks["phy"]
    aggregate.chm_marks = marks["chm"]
    aggregate.bio_marks = marks["bio"]
    aggregate.math_marks = marks["math"]
    aggregate.phy_tests_count = counts["phy"]
    aggregate.chm_tests_count = counts["chm"]
    aggregate.bio_tests_count = counts["bio"]
    aggregate.math_tests_count = counts["math"]
    aggregate.total_score = total_score
    aggregate.save()

    # Recompute institute ranking once after this student's aggregate update.
    institute_rows = list(
        ScholarshipStudentLeaderboard.objects
        .select_related("portal_student")
        .order_by("-total_score", "updated_at", "portal_student_id")
    )
    for rank, row in enumerate(institute_rows, start=1):
        row.institute_rank = rank
    ScholarshipStudentLeaderboard.objects.bulk_update(institute_rows, ["institute_rank"])

    # Recompute batch ranking for only the impacted batch.
    batch_rows = list(
        ScholarshipStudentLeaderboard.objects
        .filter(student_batch__iexact=aggregate.student_batch or "")
        .order_by("-total_score", "updated_at", "portal_student_id")
    )
    for rank, row in enumerate(batch_rows, start=1):
        row.batch_rank = rank
    if batch_rows:
        ScholarshipStudentLeaderboard.objects.bulk_update(batch_rows, ["batch_rank"])


def _academy_localtime(value=None):
    if value is None:
        value = timezone.now()
    return timezone.localtime(value, ACADEMY_TIMEZONE)


def _normalize_scope_value(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _split_scope_values(raw_value) -> set[str]:
    values = set()
    for part in re.split(r"[,/&|]+", str(raw_value or "")):
        normalized = _normalize_scope_value(part)
        if normalized:
            values.add(normalized)
    return values


def get_portal_student_stream_values(portal_student) -> set[str]:
    if not portal_student:
        return set()

    stream_values = _split_scope_values(_safe_student_field_value(portal_student, "stream", ""))
    interested_exams = _safe_student_field_value(portal_student, "interested_exams", []) or []

    for exam in interested_exams:
        exam_text = str(exam or "")
        stream_values.update(_split_scope_values(exam_text))
        exam_upper = exam_text.upper()
        for stream_name in ("JEE", "NEET", "MHTCET"):
            if stream_name in exam_upper:
                stream_values.add(_normalize_scope_value(stream_name))

    return stream_values


LEADERBOARD_SUBJECT_ORDER = ("Physics", "Chemistry", "Biology", "Maths")
LEADERBOARD_SUBJECT_SHORT_LABELS = {
    "Physics": "PHY",
    "Chemistry": "CHM",
    "Biology": "BIO",
    "Maths": "MATH",
}


def _normalize_leaderboard_subject_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", str(name or "").strip().casefold())
    compact = value.replace(" ", "")
    if "physics" in compact or compact == "phy":
        return "Physics"
    if "chemistry" in compact or compact == "chem":
        return "Chemistry"
    if compact in {"biology", "bio", "botany", "zoology"} or "biology" in compact:
        return "Biology"
    if compact in {"maths", "math", "mathematics", "mathmatics"} or "math" in compact:
        return "Maths"
    return ""


def _short_section_label(name: str) -> str:
    normalized = _normalize_leaderboard_subject_name(name)
    if normalized:
        return LEADERBOARD_SUBJECT_SHORT_LABELS.get(normalized, normalized[:4].upper())

    tokens = [token for token in re.findall(r"[A-Za-z0-9]+", str(name or "")) if token]
    if not tokens:
        return "SEC"
    if len(tokens) >= 2:
        return "".join(token[0] for token in tokens[:3]).upper()
    return tokens[0][:4].upper()


@lru_cache(maxsize=None)
def _model_column_names(model_class):
    try:
        if model_class._meta.db_table not in connection.introspection.table_names():
            return set()
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(
                cursor,
                model_class._meta.db_table,
            )
        return {
            getattr(column, "name", column[0])
            for column in description
        }
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "Unable to inspect %s columns for scholarship test compatibility: %s",
            model_class._meta.db_table,
            exc,
        )
        return set()


def _model_has_columns(model_class, *field_names):
    available_columns = _model_column_names(model_class)
    for field_name in field_names:
        try:
            column_name = model_class._meta.get_field(field_name).column
        except Exception:
            return False
        if column_name not in available_columns:
            return False
    return True


def _missing_concrete_field_names(model_class):
    available_columns = _model_column_names(model_class)
    if not available_columns:
        return []
    return [
        field.name
        for field in model_class._meta.local_concrete_fields
        if not field.primary_key and field.column not in available_columns
    ]


def _optional_attempt_fields_to_defer():
    from scholarship_test.models import ScholarshipTestAttempt

    return tuple(
        sorted(
            set(_missing_concrete_field_names(ScholarshipTestAttempt))
            | {
                field_name
                for field_name in OPTIONAL_ATTEMPT_COMPAT_FIELDS
                if not _model_has_columns(ScholarshipTestAttempt, field_name)
            }
        )
    )


def _schema_safe_attempt_queryset():
    from scholarship_test.models import ScholarshipTestAttempt

    queryset = ScholarshipTestAttempt.objects.all()
    missing_optional_fields = _optional_attempt_fields_to_defer()
    if missing_optional_fields:
        queryset = queryset.defer(*missing_optional_fields)
    return queryset


def _optional_student_fields_to_defer():
    return tuple(
        sorted(
            set(_missing_concrete_field_names(Student))
            | {
                field_name
                for field_name in STUDENT_COMPAT_FIELDS
                if not _model_has_columns(Student, field_name)
            }
        )
    )


def _schema_safe_student_queryset():
    queryset = Student.objects.select_related("user")
    missing_optional_fields = _optional_student_fields_to_defer()
    if missing_optional_fields:
        queryset = queryset.defer(*missing_optional_fields)
    return queryset


def _safe_student_field_value(student, field_name, default=""):
    return _safe_model_field_value(student, field_name, default)


def get_test_total_marks(test) -> int:
    total_marks = 0
    for question in get_runtime_questions_for_test(test):
        marks = int(getattr(question, "pos_marks", 0) or 0)
        total_marks += marks if marks > 0 else 1
    return total_marks


def _infer_test_stream_values(test, portal_student=None) -> set[str]:
    stream_values = set()
    for raw_value in (
        _safe_model_field_value(test, "stream", ""),
        _safe_model_field_value(test, "subject", ""),
        getattr(test, "name", ""),
    ):
        stream_values.update(_split_scope_values(raw_value))

    stream_values.update(get_portal_student_stream_values(portal_student))
    return stream_values


def get_test_section_definitions(test, portal_student=None):
    if not test:
        return []

    section_definitions = []
    for index, section in enumerate(test.sections.all().order_by("order", "id"), start=1):
        questions = list(section.questions.all())
        total_marks = sum(
            int(getattr(question, "pos_marks", 0) or 0)
            if int(getattr(question, "pos_marks", 0) or 0) > 0
            else 1
            for question in questions
        )
        section_name = str(getattr(section, "name", "") or f"Section {index}").strip() or f"Section {index}"
        section_definitions.append(
            {
                "name": section_name,
                "sectionName": section_name,
                "shortLabel": _short_section_label(section_name),
                "total": total_marks,
                "meta": getattr(section, "instructions", "") or "Section score",
            }
        )

    if section_definitions:
        return section_definitions

    stream_values = _infer_test_stream_values(test, portal_student)
    normalized_streams = {_fuzzy_norm(value) for value in stream_values}
    fallback_names = []
    if "neet" in normalized_streams and "jee" not in normalized_streams:
        fallback_names = ["Physics", "Chemistry", "Biology"]
    elif {"jee", "mhtcet"} & normalized_streams:
        fallback_names = ["Physics", "Chemistry", "Maths"]

    return [
        {
            "name": name,
            "sectionName": name,
            "shortLabel": _short_section_label(name),
            "total": 0,
            "meta": "Section score",
        }
        for name in fallback_names
    ]


def _attempt_saved_answers(attempt) -> dict:
    progress_state = _attempt_progress_state_data(attempt)
    saved_answers = progress_state.get("answers", {})
    return saved_answers if isinstance(saved_answers, dict) else {}


def _selected_answer_from_record(answer):
    if not answer:
        return None

    selected_answer = getattr(answer, "selected_option", None)
    if selected_answer in (None, ""):
        selected_answer = getattr(answer, "selected_answer", None)

    if hasattr(selected_answer, "order"):
        try:
            return str(int(selected_answer.order))
        except (TypeError, ValueError):
            return str(selected_answer.order)

    return selected_answer


def build_attempt_section_breakdown(attempt):
    if not attempt:
        return []

    manual_scores = _attempt_progress_state_data(attempt).get("manual_subject_scores")
    if isinstance(manual_scores, dict):
        normalized_manual_scores = {}
        for raw_subject, raw_score in manual_scores.items():
            subject = _normalize_leaderboard_subject_name(raw_subject) or str(raw_subject or "").strip()
            if subject:
                normalized_manual_scores[subject] = raw_score

        ordered_subjects = [
            subject
            for subject in LEADERBOARD_SUBJECT_ORDER
            if subject in normalized_manual_scores
        ]
        ordered_subjects.extend(
            subject
            for subject in normalized_manual_scores
            if subject not in ordered_subjects
        )

        return [
            {
                "name": subject,
                "sectionName": subject,
                "shortLabel": _short_section_label(subject),
                "score": int(normalized_manual_scores.get(subject, 0) or 0),
                "total": 100,
                "percentage": max(0, min(100, int(normalized_manual_scores.get(subject, 0) or 0))),
                "meta": "Manual marks entry",
            }
            for subject in ordered_subjects
        ]

    test = getattr(attempt, "test", None)
    if not test:
        return []

    saved_answers = _attempt_saved_answers(attempt)
    answers_by_question_id = {
        answer.question_id: answer
        for answer in attempt.answers.all()
        if getattr(answer, "question_id", None) is not None
    }
    breakdown = []

    for index, section in enumerate(test.sections.all().order_by("order", "id"), start=1):
        questions = list(section.questions.all())
        total_marks = 0
        scored_marks = 0

        for question in questions:
            positive_marks = int(getattr(question, "pos_marks", 0) or 0)
            positive_marks = positive_marks if positive_marks > 0 else 1
            negative_marks = int(getattr(question, "neg_marks", 0) or 0)
            negative_unattempted_marks = int(getattr(question, "neg_unattempted", 0) or 0)
            total_marks += positive_marks

            answer = answers_by_question_id.get(question.id)
            selected_answer = _selected_answer_from_record(answer)
            if selected_answer in (None, ""):
                selected_answer = saved_answers.get(str(question.id))

            if answer is not None and getattr(answer, "is_correct", None) is True:
                scored_marks += positive_marks
            elif is_runtime_answer_provided(question, selected_answer):
                if answer is not None and getattr(answer, "is_correct", None) is False:
                    scored_marks -= negative_marks
                elif is_runtime_answer_correct(question, selected_answer):
                    scored_marks += positive_marks
                else:
                    scored_marks -= negative_marks
            else:
                scored_marks -= negative_unattempted_marks

        section_name = str(getattr(section, "name", "") or f"Section {index}").strip() or f"Section {index}"
        percentage = round((scored_marks / total_marks) * 100, 1) if total_marks else 0
        breakdown.append(
            {
                "name": section_name,
                "sectionName": section_name,
                "shortLabel": _short_section_label(section_name),
                "score": scored_marks,
                "total": total_marks,
                "percentage": percentage,
                "meta": getattr(section, "instructions", "") or "Section score",
            }
        )

    return breakdown


def build_zero_section_breakdown(test, portal_student=None):
    return [
        {
            **section,
            "score": 0,
            "percentage": 0,
        }
        for section in get_test_section_definitions(test, portal_student=portal_student)
    ]


def _portal_student_photo_url(portal_student):
    profile_photo = _safe_student_field_value(portal_student, "profile_photo", None)
    if not profile_photo:
        return None
    return upload_url(profile_photo, "student_profiles") or None


def _latest_completed_attempts_for_portal_test(test):
    from scholarship_test.models import ScholarshipTestAttempt

    if not _model_has_columns(ScholarshipTestAttempt, "portal_student"):
        logger.warning(
            "Skipping portal attempt lookup because scholarship attempt portal_student column is unavailable."
        )
        return {}

    attempts = (
        _schema_safe_attempt_queryset()
        .filter(test=test, status__in=["completed", "expired"])
        .select_related("student")
        .prefetch_related("answers__question__section", "test__sections__questions")
        .order_by("test_completed_at", "test_started_at", "id")
    )

    latest_by_student_id = {}
    for attempt in attempts:
        portal_student_id = getattr(attempt, "portal_student_id", None)
        if portal_student_id:
            latest_by_student_id[portal_student_id] = attempt
    return latest_by_student_id


def _assigned_portal_students_for_test(test):
    student_queryset = _schema_safe_student_queryset()

    assigned_students = [
        portal_student
        for portal_student in student_queryset
        if is_test_assigned_to_portal_student(test, portal_student)
    ]
    assigned_students.sort(
        key=lambda portal_student: (
            (_safe_student_field_value(portal_student, "student_name", "") or "").casefold(),
            getattr(portal_student, "id", 0),
        )
    )
    return assigned_students


def _subject_score_lookup(section_scores):
    subject_scores = {subject: None for subject in LEADERBOARD_SUBJECT_ORDER}
    for index, section in enumerate(section_scores):
        mapped_subject = _normalize_leaderboard_subject_name(
            section.get("name") or section.get("sectionName")
        )
        if not mapped_subject and index < len(LEADERBOARD_SUBJECT_ORDER):
            mapped_subject = LEADERBOARD_SUBJECT_ORDER[index]
        if mapped_subject in subject_scores:
            raw_score = section.get("score")
            subject_scores[mapped_subject] = (
                None if raw_score in (None, "") else int(raw_score or 0)
            )
    return subject_scores


def get_test_attempt_leaderboard_data(test, current_attempt_id=None, current_portal_student=None, limit=5):
    if not test:
        return {
            "entries": [],
            "topEntries": [],
            "currentEntry": None,
        }

    assigned_students = _assigned_portal_students_for_test(test)
    latest_attempts = _latest_completed_attempts_for_portal_test(test)
    total_marks = get_test_total_marks(test)
    entries = []

    for portal_student in assigned_students:
        attempt = latest_attempts.get(portal_student.id)
        section_scores = (
            build_attempt_section_breakdown(attempt)
            if attempt
            else build_zero_section_breakdown(test, portal_student=portal_student)
        )
        subject_scores = _subject_score_lookup(section_scores)
        score = int(getattr(attempt, "score", 0) or 0) if attempt else 0
        attempt_total_marks = (
            int(getattr(attempt, "total_marks", 0) or 0)
            if attempt and int(getattr(attempt, "total_marks", 0) or 0) > 0
            else total_marks
        )
        student_name = _safe_student_field_value(portal_student, "student_name", "") or getattr(portal_student.user, "username", "")
        entry = {
            "attemptId": attempt.id if attempt else None,
            "studentId": f"portal-{portal_student.id}",
            "studentName": student_name,
            "studentRef": _safe_student_field_value(portal_student, "username", "") or _safe_student_field_value(portal_student, "contact", ""),
            "studentBatch": _safe_student_field_value(portal_student, "batch", "") or "",
            "studentGrade": _safe_student_field_value(portal_student, "grade", "") or "",
            "profilePhotoUrl": _portal_student_photo_url(portal_student),
            "score": score,
            "total": score,
            "totalMarks": attempt_total_marks,
            "sectionScores": section_scores,
            "phyMarks": subject_scores["Physics"],
            "chmMarks": subject_scores["Chemistry"],
            "bioMarks": subject_scores["Biology"],
            "mathMarks": subject_scores["Maths"],
            "batchRank": "NA",
            "instituteRank": "NA",
            "isCurrentStudent": bool(
                current_portal_student and portal_student.id == current_portal_student.id
            ),
            "_attempted": bool(attempt),
            "_completed_at": (
                getattr(attempt, "test_completed_at", None)
                or getattr(attempt, "test_started_at", None)
                or timezone.now()
            ),
            "_sort_name": (student_name or "").casefold(),
        }
        entries.append(entry)

    entries.sort(
        key=lambda entry: (
            0 if entry["_attempted"] else 1,
            -int(entry["score"] or 0),
            entry["_completed_at"] or timezone.now(),
            entry["_sort_name"],
            entry["studentId"],
        )
    )

    current_entry = None
    last_score = None
    last_rank = 0
    attempted_position = 0

    for entry in entries:
        if entry["_attempted"]:
            attempted_position += 1
            if entry["score"] != last_score:
                last_rank = attempted_position
            entry["rank"] = last_rank
            entry["instituteRank"] = last_rank
            last_score = entry["score"]
        else:
            entry["rank"] = "NA"
            entry["instituteRank"] = "NA"

        if entry["isCurrentStudent"] or (
            current_attempt_id and entry.get("attemptId") == current_attempt_id
        ):
            current_entry = entry

    batch_groups = {}
    for entry in entries:
        batch_key = str(entry.get("studentBatch") or "").strip().casefold()
        if batch_key:
            batch_groups.setdefault(batch_key, []).append(entry)

    for group_entries in batch_groups.values():
        last_score = None
        last_rank = 0
        attempted_position = 0
        for entry in group_entries:
            if entry.get("rank") == "NA":
                entry["batchRank"] = "NA"
                continue
            attempted_position += 1
            if entry["score"] != last_score:
                last_rank = attempted_position
            entry["batchRank"] = last_rank
            last_score = entry["score"]

    for entry in entries:
        entry.pop("_attempted", None)
        entry.pop("_completed_at", None)
        entry.pop("_sort_name", None)

    return {
        "entries": entries,
        "topEntries": [entry for entry in entries if entry["rank"] != "NA"][: max(0, int(limit or 0) or 0) or 5],
        "currentEntry": current_entry,
    }


def _fuzzy_norm(value) -> str:
    """Removes all whitespace and casefolds for robust comparison."""
    return re.sub(r"\s+", "", str(value or "").strip()).casefold()


def is_test_assigned_to_portal_student(test, portal_student) -> bool:
    if not test or not portal_student:
        return False

    # 1. Batch Check (Fuzzy and supports multiple comma-separated values)
    test_batch_raw = _safe_model_field_value(test, "batch", "")
    student_batch_raw = _safe_student_field_value(portal_student, "batch", "")

    test_batches = _split_scope_values(test_batch_raw)
    if test_batches:
        student_batches = _split_scope_values(student_batch_raw)
        
        # If student has no batch, they don't see batch-restricted tests
        if not student_batches:
            return False
            
        test_batch_fuzzy = {_fuzzy_norm(b) for b in test_batches}
        student_batch_fuzzy = {_fuzzy_norm(b) for b in student_batches}
        
        if test_batch_fuzzy.isdisjoint(student_batch_fuzzy):
            return False

    # 2. Stream Check (Fuzzy)
    test_stream_raw = _safe_model_field_value(test, "stream", "")
    test_streams = _split_scope_values(test_stream_raw)
    
    # If test has no stream restriction, anyone in the batch can see it
    if not test_streams:
        return True

    student_streams = get_portal_student_stream_values(portal_student)
    
    # If student has no stream values, we allow them to see the test 
    # to avoid "missing tests" issues when profiles are incomplete.
    if not student_streams:
        return True

    test_stream_fuzzy = {_fuzzy_norm(s) for s in test_streams}
    student_stream_fuzzy = {_fuzzy_norm(s) for s in student_streams}

    return not test_stream_fuzzy.isdisjoint(student_stream_fuzzy)


def get_test_scheduled_start_at(test):
    scheduled_start_at = _safe_model_field_value(test, "scheduled_start_at", None)
    if not test or not scheduled_start_at:
        return None

    start_at = _academy_localtime(scheduled_start_at)
    test_date = getattr(test, "date", None)
    if not test_date or start_at.date() == test_date:
        return start_at

    # Compatibility for rows created before academy-local scheduling was enforced.
    stored_utc_time = timezone.localtime(scheduled_start_at, UTC_TIMEZONE).time()
    corrected = datetime.combine(test_date, stored_utc_time)
    return timezone.make_aware(corrected, ACADEMY_TIMEZONE)


def get_test_launch_window(test):
    start_at = get_test_scheduled_start_at(test)
    if not start_at:
        return None, None, None

    end_at = start_at + timedelta(minutes=get_test_duration_minutes(test))
    launch_opens_at = start_at - timedelta(minutes=10)
    return start_at, end_at, launch_opens_at


def get_test_start_window(test):
    start_at = get_test_scheduled_start_at(test)
    if not start_at:
        return None, None, None

    end_at = start_at + timedelta(minutes=get_test_duration_minutes(test))
    start_button_opens_at = start_at - timedelta(minutes=1)
    return start_at, end_at, start_button_opens_at


def get_test_launch_state(test, now=None):
    if now is None:
        now = _academy_localtime()

    start_at, end_at, launch_opens_at = get_test_launch_window(test)
    if not start_at or not end_at or not launch_opens_at:
        return {
            "scheduled": False,
            "can_launch": True,
            "is_live": False,
            "has_ended": False,
            "message": "",
        }

    if now >= end_at:
        return {
            "scheduled": True,
            "can_launch": False,
            "is_live": False,
            "has_ended": True,
            "message": "This test window has closed.",
        }

    if now < launch_opens_at:
        return {
            "scheduled": True,
            "can_launch": False,
            "is_live": False,
            "has_ended": False,
            "message": "This test opens 10 minutes before the scheduled start time.",
        }

    return {
        "scheduled": True,
        "can_launch": True,
        "is_live": start_at <= now < end_at,
        "has_ended": False,
        "message": "",
    }


def get_test_start_state(test, now=None):
    if now is None:
        now = _academy_localtime()

    start_at, end_at, start_button_opens_at = get_test_start_window(test)
    if not start_at or not end_at or not start_button_opens_at:
        return {
            "scheduled": False,
            "can_start": True,
            "is_live": False,
            "has_ended": False,
            "message": "",
        }

    if now >= end_at:
        return {
            "scheduled": True,
            "can_start": False,
            "is_live": False,
            "has_ended": True,
            "message": "This test window has closed.",
        }

    if now < start_button_opens_at:
        return {
            "scheduled": True,
            "can_start": False,
            "is_live": False,
            "has_ended": False,
            "message": "The Start button activates 1 minute before the scheduled start time.",
        }

    return {
        "scheduled": True,
        "can_start": True,
        "is_live": start_at <= now < end_at,
        "has_ended": False,
        "message": "",
    }


def _get_test_queryset():
    from django.db.models import Prefetch
    from scholarship_test.models import (
        ScholarshipTest,
        ScholarshipTestQuestion,
        ScholarshipTestSection,
    )

    question_queryset = (
        ScholarshipTestQuestion.objects.filter(
            question_type__in=SUPPORTED_RUNTIME_QUESTION_TYPES
        )
        .prefetch_related('options', 'answers')
        .order_by('order', 'id')
    )

    section_queryset = ScholarshipTestSection.objects.prefetch_related(
        Prefetch('questions', queryset=question_queryset)
    ).order_by('order', 'id')

    return ScholarshipTest.objects.prefetch_related(
        Prefetch('sections', queryset=section_queryset),
        'config',
    )


def get_active_test():
    queryset = _get_test_queryset()

    published_tests = queryset.filter(
        status='published',
        scheduled_start_at__isnull=False,
    ).order_by('scheduled_start_at', 'id')
    for test in published_tests:
        if not get_runtime_questions_for_test(test):
            continue
        if get_test_launch_state(test)["can_launch"]:
            return test

    unscheduled_published_tests = queryset.filter(
        status='published',
        scheduled_start_at__isnull=True,
    ).order_by('-created_at')
    for test in unscheduled_published_tests:
        if get_runtime_questions_for_test(test):
            return test

    fallback_tests = queryset.order_by('-created_at')
    for test in fallback_tests:
        if get_runtime_questions_for_test(test):
            return test

    return None


def get_test_by_id(test_id):
    if not test_id:
        return None

    try:
        return _get_test_queryset().get(id=test_id)
    except Exception:
        return None


def get_launchable_tests():
    launchable_tests = []

    for test in _get_test_queryset().order_by('-created_at'):
        runtime_questions = get_runtime_questions_for_test(test)
        if runtime_questions:
            test.runtime_question_count = len(runtime_questions)
            launchable_tests.append(test)

    return launchable_tests


def get_runtime_questions_for_test(test):
    if not test:
        return []

    runtime_questions = []
    for section in test.sections.all():
        for question in section.questions.all():
            if question.question_type in SUPPORTED_RUNTIME_QUESTION_TYPES:
                runtime_questions.append(question)
    return runtime_questions


def _stable_runtime_question_order_key(attempt, question):
    attempt_seed = getattr(attempt, "id", None) or getattr(attempt, "student_id", None) or 0
    payload = f"{attempt_seed}:{getattr(question, 'id', 0)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_runtime_questions_for_attempt(attempt):
    runtime_test = get_runtime_test_for_attempt(attempt)
    runtime_questions = list(get_runtime_questions_for_test(runtime_test))
    if not runtime_questions:
        return []

    return sorted(
        runtime_questions,
        key=lambda question: _stable_runtime_question_order_key(attempt, question),
    )


def get_runtime_test_for_attempt(attempt):
    if getattr(attempt, 'test_id', None):
        return attempt.test
    return get_active_test()


def get_test_duration_minutes(test) -> int:
    if not test:
        return TEST_DURATION_MINUTES

    duration_minutes = (int(test.duration_hours or 0) * 60) + int(
        test.duration_minutes or 0
    )
    return duration_minutes if duration_minutes > 0 else TEST_DURATION_MINUTES


def serialize_runtime_question(question, sequence):
    option_labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    payload = {
        'id': question.id,
        'sequence': sequence,
        'type': question.question_type,
        'question_html': question.question_text,
        'difficulty': question.difficulty,
        'pos_marks': question.pos_marks,
        'neg_marks': question.neg_marks,
        'neg_unattempted': question.neg_unattempted,
        'multi_select': question.is_multi_select,
        'section_name': question.section.name,
        'section_instructions': question.section.instructions,
        'options': [],
    }

    if question.question_type == 'mcq':
        payload['options'] = [
            {
                'value': str(index),
                'label': option_labels[index]
                if index < len(option_labels)
                else str(index + 1),
                'text_html': option.option_text,
            }
            for index, option in enumerate(question.options.all())
        ]
    elif question.question_type == 'tf':
        payload['options'] = [
            {'value': 'True', 'label': 'T', 'text_html': 'True'},
            {'value': 'False', 'label': 'F', 'text_html': 'False'},
        ]
    elif question.question_type == 'fitb':
        payload['input_placeholder'] = 'Type your answer'
    elif question.question_type == 'int':
        payload['input_placeholder'] = 'Enter an integer'

    return payload


def get_attempt_end_time(attempt):
    runtime_test = get_runtime_test_for_attempt(attempt)
    time_limit = timedelta(minutes=get_test_duration_minutes(runtime_test))
    start_time = get_attempt_start_time(attempt)
    if start_time is None:
        return None
    return start_time + time_limit


def get_answer_key_visibility_delay():
    # Answer key is now visible immediately after submission.
    return timedelta(seconds=0)


def get_my_tests_attempt_review_visibility_delay():
    hours = getattr(settings, 'MY_TESTS_ATTEMPT_REVIEW_DELAY_HOURS', 1)
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        hours = 1
    return timedelta(hours=max(0, hours))


def get_answer_key_base_end_time(attempt):
    runtime_test = get_runtime_test_for_attempt(attempt)
    scheduled_start_at = _safe_model_field_value(runtime_test, "scheduled_start_at", None)
    if runtime_test and scheduled_start_at:
        return scheduled_start_at + timedelta(
            minutes=get_test_duration_minutes(runtime_test)
        )
    return get_attempt_end_time(attempt)


def get_answer_key_available_at(attempt):
    completed_at = getattr(attempt, "test_completed_at", None)
    if completed_at:
        return completed_at
    return get_answer_key_base_end_time(attempt)


def is_answer_key_available(attempt, now=None):
    return bool(
        attempt
        and getattr(attempt, "status", None) in ["completed", "expired"]
        and getattr(attempt, "test_completed_at", None)
    )


def get_my_tests_attempt_review_available_at(attempt):
    return get_answer_key_base_end_time(attempt) + get_my_tests_attempt_review_visibility_delay()


def is_my_tests_attempt_review_available(attempt, now=None):
    if now is None:
        now = timezone.now()
    return now >= get_my_tests_attempt_review_available_at(attempt)


def get_answer_key_delay_hours_display():
    return "immediately"


def get_attempt_time_remaining_seconds(attempt) -> int:
    attempt_end_time = get_attempt_end_time(attempt)
    if attempt_end_time is None:
        runtime_test = get_runtime_test_for_attempt(attempt)
        return get_test_duration_minutes(runtime_test) * 60

    remaining = attempt_end_time - timezone.now()
    return max(0, int(remaining.total_seconds()))


def is_attempt_expired(attempt) -> bool:
    return get_attempt_end_time(attempt) is not None and get_attempt_time_remaining_seconds(attempt) <= 0


def get_saved_progress(attempt):
    state = _attempt_progress_state_data(attempt)
    answers = state.get('answers', {})
    if not isinstance(answers, dict):
        answers = {}

    current_question_index = state.get('current_question_index', 0)
    try:
        current_question_index = int(current_question_index)
    except (TypeError, ValueError):
        current_question_index = 0

    tab_switch_count = state.get('tab_switch_count', 0)
    try:
        tab_switch_count = int(tab_switch_count)
    except (TypeError, ValueError):
        tab_switch_count = 0

    violation_count = state.get('violation_count', get_attempt_violation_count_value(attempt))
    try:
        violation_count = int(violation_count)
    except (TypeError, ValueError):
        violation_count = get_attempt_violation_count_value(attempt)

    security_locked = state.get(
        'security_locked',
        get_attempt_security_status_value(attempt) == 'locked',
    )

    return {
        'answers': answers,
        'current_question_index': max(0, current_question_index),
        'tab_switch_count': max(0, tab_switch_count),
        'violation_count': max(0, violation_count),
        'security_locked': bool(security_locked),
        'saved_at': state.get('saved_at'),
    }


def _normalize_text_answer(value):
    if value is None:
        return ''
    return ' '.join(str(value).strip().lower().split())


def _normalize_integer_answer(value):
    if value in (None, ''):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _allowed_runtime_option_values(question):
    return {
        str(index)
        for index, _option in enumerate(question.options.all())
    }


def normalize_runtime_answer(question, submitted_answer):
    if question.question_type == 'mcq':
        allowed_values = _allowed_runtime_option_values(question)

        if question.is_multi_select:
            if submitted_answer in (None, ''):
                return []
            if not isinstance(submitted_answer, list):
                submitted_answer = [submitted_answer]

            cleaned_values = []
            seen_values = set()
            for value in submitted_answer:
                normalized_value = str(value).strip()
                if normalized_value in allowed_values and normalized_value not in seen_values:
                    cleaned_values.append(normalized_value)
                    seen_values.add(normalized_value)
            return cleaned_values

        if isinstance(submitted_answer, list):
            submitted_answer = submitted_answer[0] if submitted_answer else ''
        normalized_value = str(submitted_answer).strip() if submitted_answer is not None else ''
        return normalized_value if normalized_value in allowed_values else ''

    if question.question_type == 'tf':
        normalized_value = _normalize_text_answer(submitted_answer)
        if normalized_value == 'true':
            return 'True'
        if normalized_value == 'false':
            return 'False'
        return ''

    if question.question_type == 'fitb':
        return str(submitted_answer or '').strip()

    if question.question_type == 'int':
        normalized_integer = _normalize_integer_answer(submitted_answer)
        return '' if normalized_integer is None else str(normalized_integer)

    return submitted_answer


def normalize_runtime_answers(runtime_questions, submitted_answers):
    normalized_answers = {}
    raw_answers = submitted_answers if isinstance(submitted_answers, dict) else {}

    for question in runtime_questions:
        submitted_answer = raw_answers.get(str(question.id))
        if submitted_answer is None:
            submitted_answer = raw_answers.get(question.id)

        normalized_answers[str(question.id)] = normalize_runtime_answer(
            question,
            submitted_answer,
        )

    return normalized_answers


def is_runtime_answer_provided(question, selected_answer) -> bool:
    normalized_answer = normalize_runtime_answer(question, selected_answer)
    if question.question_type == 'mcq' and question.is_multi_select:
        return len(normalized_answer) > 0
    return normalized_answer not in (None, '')


@transaction.atomic
def activate_runtime_test_attempt(attempt_id: int):
    from scholarship_test.models import ScholarshipTestAttempt

    try:
        attempt = ScholarshipTestAttempt.objects.select_related(
            'student',
            'test',
        ).defer(
            'started_at',
            'submitted_at',
            'violation_count',
            'security_status',
        ).get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return False, "Test attempt not found", None

    if attempt.status in ['completed', 'expired'] or get_attempt_submitted_at_value(attempt):
        return False, "Test already submitted", attempt

    runtime_test = get_runtime_test_for_attempt(attempt)
    runtime_questions = get_runtime_questions_for_attempt(attempt)
    if not runtime_test or not runtime_questions:
        return False, "No configured scholarship test is available", attempt

    now = timezone.now()
    update_fields = []
    can_persist_security_fields = attempt_can_persist_security_fields(attempt)

    if get_attempt_started_at_value(attempt) is None and can_persist_security_fields:
        attempt.started_at = now
        update_fields.append('started_at')

    if attempt.status == 'started':
        attempt.status = 'in_progress'
        update_fields.append('status')

    if can_persist_security_fields and get_attempt_security_status_value(attempt) == 'pending':
        attempt.security_status = 'active'
        update_fields.append('security_status')

    saved_progress = get_saved_progress(attempt)
    attempt.progress_state = {
        'answers': saved_progress.get('answers', {}),
        'current_question_index': saved_progress.get('current_question_index', 0),
        'tab_switch_count': saved_progress.get('tab_switch_count', 0),
        'violation_count': saved_progress.get('violation_count', get_attempt_violation_count_value(attempt)),
        'security_locked': saved_progress.get('security_locked', False),
        'security_status': 'active',
        'started_at': (get_attempt_started_at_value(attempt) or now).isoformat(),
        'saved_at': now.isoformat(),
    }
    update_fields.append('progress_state')
    if not update_fields:
        return True, "Test already active", attempt
    attempt.save(update_fields=update_fields)
    return True, "Test activated", attempt


@transaction.atomic
def save_runtime_test_progress(
    attempt_id: int,
    *,
    answers: dict,
    current_question_index: int = 0,
    tab_switch_count: int = 0,
    violation_count: int = 0,
    security_locked: bool = False,
):
    from scholarship_test.models import ScholarshipTestAttempt

    try:
        attempt = ScholarshipTestAttempt.objects.select_related(
            'student',
            'test',
        ).defer(
            'started_at',
            'submitted_at',
            'violation_count',
            'security_status',
        ).get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return False, "Test attempt not found", None

    if attempt.status in ['completed', 'expired'] or get_attempt_submitted_at_value(attempt):
        return False, "Test already submitted", attempt

    runtime_test = get_runtime_test_for_attempt(attempt)
    runtime_questions = get_runtime_questions_for_attempt(attempt)
    if not runtime_test or not runtime_questions:
        return False, "No configured scholarship test is available", attempt

    if get_attempt_started_at_value(attempt) is None and attempt.status == 'started':
        return False, "Test has not been activated yet", attempt

    if is_attempt_expired(attempt):
        return False, "Test time has expired", attempt

    normalized_answers = normalize_runtime_answers(runtime_questions, answers)

    try:
        current_question_index = int(current_question_index or 0)
    except (TypeError, ValueError):
        current_question_index = 0

    try:
        tab_switch_count = int(tab_switch_count or 0)
    except (TypeError, ValueError):
        tab_switch_count = 0

    try:
        violation_count = int(violation_count or 0)
    except (TypeError, ValueError):
        violation_count = 0

    max_violations = get_max_security_violations()
    merged_violation_count = max(
        int(get_attempt_violation_count_value(attempt) or 0),
        max(0, violation_count),
    )
    security_locked = bool(security_locked or merged_violation_count >= max_violations)
    if security_locked:
        security_status = 'locked'
    elif merged_violation_count > 0:
        security_status = 'warning'
    else:
        security_status = 'active'

    attempt.progress_state = {
        'answers': normalized_answers,
        'current_question_index': max(0, current_question_index),
        'tab_switch_count': max(0, tab_switch_count),
        'violation_count': merged_violation_count,
        'security_locked': security_locked,
        'security_status': security_status,
        'started_at': (
            get_attempt_started_at_value(attempt) or attempt.test_started_at or timezone.now()
        ).isoformat(),
        'saved_at': timezone.now().isoformat(),
    }
    if attempt.status == 'started':
        attempt.status = 'in_progress'
    update_fields = ['progress_state', 'status']
    if attempt_can_persist_security_fields(attempt):
        attempt.violation_count = merged_violation_count
        attempt.security_status = security_status
        update_fields.extend(['violation_count', 'security_status'])
    attempt.save(update_fields=update_fields)
    return True, "Progress saved", attempt


def is_runtime_answer_correct(question, selected_answer) -> bool:
    selected_answer = normalize_runtime_answer(question, selected_answer)

    if question.question_type == 'mcq':
        correct_indexes = {
            str(index)
            for index, option in enumerate(question.options.all())
            if option.is_correct
        }

        if question.is_multi_select:
            if not isinstance(selected_answer, list):
                return False
            selected_indexes = {str(value) for value in selected_answer if value != ''}
            return bool(correct_indexes) and selected_indexes == correct_indexes

        if isinstance(selected_answer, list):
            selected_answer = selected_answer[0] if selected_answer else ''
        return str(selected_answer) in correct_indexes and len(correct_indexes) == 1

    answer = question.answers.first()
    if not answer:
        return False

    if question.question_type == 'tf':
        return _normalize_text_answer(selected_answer) == _normalize_text_answer(
            answer.correct_answer
        )

    if question.question_type == 'fitb':
        return _normalize_text_answer(selected_answer) == _normalize_text_answer(
            answer.correct_answer
        )

    if question.question_type == 'int':
        return _normalize_integer_answer(selected_answer) == _normalize_integer_answer(
            answer.correct_answer
        )

    return False


@transaction.atomic
def submit_runtime_test(
    attempt_id: int,
    answers: dict,
    *,
    violation_count: int | None = None,
    security_locked: bool = False,
    submission_reason: str = '',
):
    from scholarship_test.models import ScholarshipTestAttempt

    try:
        attempt = ScholarshipTestAttempt.objects.select_related(
            'student',
            'test',
        ).defer(
            'started_at',
            'submitted_at',
            'violation_count',
            'security_status',
        ).get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return False, "Test attempt not found", None

    if attempt.status in ['completed', 'expired'] or get_attempt_submitted_at_value(attempt):
        return False, "Test already submitted", attempt

    runtime_test = get_runtime_test_for_attempt(attempt)
    runtime_questions = get_runtime_questions_for_attempt(attempt)
    if not runtime_test or not runtime_questions:
        return False, "No configured scholarship test is available", attempt

    if get_attempt_started_at_value(attempt) is None and attempt.status == 'started':
        return False, "Test has not been activated yet", attempt

    final_status = 'completed'
    if is_attempt_expired(attempt):
        final_status = 'expired'

    saved_progress = get_saved_progress(attempt)
    combined_answers = dict(saved_progress.get('answers', {}))
    combined_answers.update(answers if isinstance(answers, dict) else {})
    normalized_answers = normalize_runtime_answers(runtime_questions, combined_answers)
    if violation_count is None:
        final_violation_count = saved_progress.get('violation_count', get_attempt_violation_count_value(attempt))
    else:
        try:
            final_violation_count = int(violation_count)
        except (TypeError, ValueError):
            final_violation_count = saved_progress.get('violation_count', get_attempt_violation_count_value(attempt))
    final_violation_count = max(int(get_attempt_violation_count_value(attempt) or 0), max(0, final_violation_count))
    max_violations = get_max_security_violations()
    final_security_locked = bool(security_locked or saved_progress.get('security_locked') or final_violation_count >= max_violations)
    correct_answers = 0
    score = 0
    total_marks = 0

    for question in runtime_questions:
        submitted_answer = normalized_answers.get(str(question.id))
        total_marks += int(question.pos_marks or 0)

        if is_runtime_answer_correct(question, submitted_answer):
            correct_answers += 1
            score += int(question.pos_marks or 0)
        elif is_runtime_answer_provided(question, submitted_answer):
            score -= int(question.neg_marks or 0)
        else:
            score -= int(question.neg_unattempted or 0)

    scholarship_percentage = calculate_scholarship_percentage(
        score, total_marks
    )

    attempt.score = score
    attempt.scholarship_percentage = scholarship_percentage
    submitted_at = timezone.now()
    attempt.test_completed_at = submitted_at
    attempt.status = final_status
    attempt.total_questions = len(runtime_questions)
    attempt.total_marks = total_marks
    attempt.test = runtime_test
    final_security_status = 'locked' if final_security_locked else 'submitted'
    attempt.progress_state = {
        'answers': normalized_answers,
        'current_question_index': max(0, len(runtime_questions) - 1),
        'tab_switch_count': saved_progress.get('tab_switch_count', 0),
        'violation_count': final_violation_count,
        'security_locked': final_security_locked,
        'security_status': final_security_status,
        'started_at': (
            get_attempt_started_at_value(attempt) or attempt.test_started_at or submitted_at
        ).isoformat(),
        'saved_at': submitted_at.isoformat(),
        'submitted_at': submitted_at.isoformat(),
        'submission_reason': submission_reason or ('security_violation' if final_security_locked else 'manual_submit'),
        'correct_answers': correct_answers,
    }
    update_fields = [
        'score',
        'scholarship_percentage',
        'test_completed_at',
        'status',
        'total_questions',
        'total_marks',
        'test',
        'progress_state',
    ]
    if attempt_can_persist_security_fields(attempt):
        attempt.submitted_at = submitted_at
        attempt.violation_count = final_violation_count
        attempt.security_status = final_security_status
        update_fields.extend(['submitted_at', 'violation_count', 'security_status'])
    attempt.save(update_fields=update_fields)

    sms_sent = False
    sms_error = None
    if requires_otp_login(attempt.test):
        try:
            sms_sent, sms_error = _send_attempt_result_sms(
                attempt=attempt,
                score=score,
                total_questions=total_marks,
                scholarship_percentage=scholarship_percentage,
            )
        except Exception as e:
            logger.error(f"Failed to send result SMS: {str(e)}", exc_info=True)
            sms_error = str(e)

    attempt.sms_sent = sms_sent
    attempt.sms_error = sms_error
    attempt.save(update_fields=['sms_sent', 'sms_error'])
    if attempt.portal_student_id:
        recompute_portal_student_leaderboard(attempt.portal_student_id)

    if final_status == 'expired':
        return True, "Test auto-submitted due to time expiry", attempt

    return True, "Test submitted successfully", attempt


def auto_submit_runtime_test(
    attempt_id: int,
    *,
    violation_count: int | None = None,
    security_locked: bool = False,
    submission_reason: str = 'time_expired',
):
    from scholarship_test.models import ScholarshipTestAttempt

    try:
        attempt = ScholarshipTestAttempt.objects.defer(
            'started_at',
            'submitted_at',
            'violation_count',
            'security_status',
        ).get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return False, "Test attempt not found", None

    saved_progress = get_saved_progress(attempt)
    return submit_runtime_test(
        attempt_id,
        saved_progress.get('answers', {}),
        violation_count=violation_count,
        security_locked=security_locked,
        submission_reason=submission_reason,
    )


def finalize_expired_attempts(selected_test=None):
    from scholarship_test.models import ScholarshipTestAttempt

    attempts = ScholarshipTestAttempt.objects.select_related(
        'student',
        'test',
    ).defer(
        'started_at',
        'submitted_at',
        'violation_count',
        'security_status',
    ).filter(
        status__in=['started', 'in_progress']
    ).order_by('test_started_at')

    if selected_test:
        attempts = attempts.filter(test=selected_test)

    finalized_attempts = []
    for attempt in attempts:
        if not is_attempt_expired(attempt):
            continue

        runtime_test = get_runtime_test_for_attempt(attempt)
        runtime_questions = get_runtime_questions_for_test(runtime_test)
        if runtime_test and runtime_questions:
            success, _message, updated_attempt = auto_submit_runtime_test(attempt.id)
        else:
            success, _message, updated_attempt = auto_submit_expired_test(attempt.id)

        if success and updated_attempt:
            finalized_attempts.append(updated_attempt)

    return finalized_attempts


def get_test_leaderboard(test, current_attempt=None, limit: int = 5):
    from scholarship_test.models import ScholarshipTestAttempt

    if not test:
        return {
            'top_entries': [],
            'current_entry': None,
        }

    current_portal_student = getattr(current_attempt, "portal_student", None) if current_attempt else None
    if current_portal_student:
        leaderboard = get_test_attempt_leaderboard_data(
            test,
            current_attempt_id=getattr(current_attempt, "id", None),
            current_portal_student=current_portal_student,
            limit=limit,
        )
        return {
            'top_entries': [
                {
                    'rank': entry.get('rank'),
                    'attempt_id': entry.get('attemptId'),
                    'student_name': entry.get('studentName'),
                    'score': entry.get('score'),
                    'total_marks': entry.get('totalMarks'),
                    'is_current_student': entry.get('isCurrentStudent', False),
                }
                for entry in leaderboard.get('topEntries', [])
            ],
            'current_entry': (
                {
                    'rank': leaderboard['currentEntry'].get('rank'),
                    'attempt_id': leaderboard['currentEntry'].get('attemptId'),
                    'student_name': leaderboard['currentEntry'].get('studentName'),
                    'score': leaderboard['currentEntry'].get('score'),
                    'total_marks': leaderboard['currentEntry'].get('totalMarks'),
                    'is_current_student': leaderboard['currentEntry'].get('isCurrentStudent', False),
                }
                if leaderboard.get('currentEntry')
                else None
            ),
        }

    attempts = ScholarshipTestAttempt.objects.select_related('student').defer(
        'started_at',
        'submitted_at',
        'violation_count',
        'security_status',
    ).filter(
        test=test,
        status__in=['completed', 'expired'],
    ).order_by('-score', 'test_completed_at', 'test_started_at', 'id')

    leaderboard_entries = []
    current_entry = None

    for index, attempt in enumerate(attempts, start=1):
        entry = {
            'rank': index,
            'attempt_id': attempt.id,
            'student_name': attempt.student.name,
            'score': attempt.score,
            'total_marks': attempt.total_marks,
            'is_current_student': bool(current_attempt and attempt.id == current_attempt.id),
        }
        leaderboard_entries.append(entry)

        if current_attempt and attempt.id == current_attempt.id:
            current_entry = entry

    return {
        'top_entries': leaderboard_entries[:limit],
        'current_entry': current_entry,
    }


def get_test_questions(grade: str, board: str, subject_id: int = None, count: int = TOTAL_QUESTIONS):

    from scholarship_test.models import ScholarshipQuestion
    
    # Normalize grade and board
    grade_normalized = normalize_grade(grade)
    board_normalized = normalize_board(board)
    
    queryset = ScholarshipQuestion.objects.filter(
        grade__icontains=grade_normalized,
        board__icontains=board_normalized,
        is_active=True
    )
    
   
    if subject_id:
        queryset = queryset.filter(subject_id=subject_id)
    
   
    available_count = queryset.count()
    
    if available_count < count:
        logger.warning(
            f"Insufficient questions available: {available_count} found, {count} requested. "
            f"Grade: {grade_normalized}, Board: {board_normalized}, Subject: {subject_id}"
        )
       
        questions = list(queryset.order_by('?'))
    else:
       
        questions = list(queryset.order_by('?')[:count])
    
    return questions


def calculate_scholarship_percentage(score: int, total: int = TOTAL_QUESTIONS) -> int:
    score_percentage = calculate_score_percentage(score, total)

    if score_percentage == 100:
        return 50
    elif score_percentage >= 90:
        return 45
    elif score_percentage >= 80:
        return 40
    elif score_percentage >= 70:
        return 35
    elif score_percentage >= 60:
        return 30
    elif score_percentage >= 50:
        return 25
    else:
        return 20 


@transaction.atomic
def submit_test(attempt_id: int, answers: dict):
   
    from scholarship_test.models import ScholarshipTestAttempt, ScholarshipStudentAnswer, ScholarshipQuestion
    
    # Get the attempt
    try:
        attempt = ScholarshipTestAttempt.objects.select_related('student').defer(
            'started_at',
            'submitted_at',
            'violation_count',
            'security_status',
        ).get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return False, "Test attempt not found", None
    
    # Check if already completed
    if attempt.status in ['completed', 'expired'] or get_attempt_submitted_at_value(attempt):
        return False, "Test already submitted", attempt
    
    # Check if time has expired
    time_limit = timedelta(minutes=TEST_DURATION_MINUTES)
    if get_attempt_started_at_value(attempt) is None and attempt.status == 'started':
        return False, "Test has not been activated yet", attempt
    attempt_start_time = get_attempt_start_time(attempt) or attempt.test_started_at
    if timezone.now() > attempt_start_time + time_limit:
        attempt.status = 'expired'
        attempt.save(update_fields=['status'])
        return False, "Test time has expired", attempt
    
    # Calculate score
    score = 0
    total_questions = 0
    
    # Process each answer
    for question_id_str, selected_option in answers.items():
        try:
            question_id = int(question_id_str)
            question = ScholarshipQuestion.objects.get(id=question_id)
            total_questions += 1
            
            # Check if answer is correct
            is_correct = question.correct_answer == selected_option
            
            if is_correct:
                score += 1
            
            # Save the answer
            ScholarshipStudentAnswer.objects.create(
                attempt=attempt,
                question=question,
                selected_option=selected_option,
                is_correct=is_correct
            )
            
        except (ValueError, ScholarshipQuestion.DoesNotExist) as e:
            logger.error(f"Error processing answer for question {question_id_str}: {str(e)}")
            continue
    
    # Calculate scholarship percentage
    scholarship_percentage = calculate_scholarship_percentage(score, total_questions)
    
    # Update attempt with results
    attempt.score = score
    attempt.scholarship_percentage = scholarship_percentage
    submitted_at = timezone.now()
    attempt.test_completed_at = submitted_at
    attempt.status = 'completed'
    attempt.total_questions = total_questions
    attempt.total_marks = total_questions
    progress_state = dict(attempt.progress_state or {})
    progress_state['submitted_at'] = submitted_at.isoformat()
    progress_state['security_status'] = 'submitted'
    progress_state['saved_at'] = submitted_at.isoformat()
    attempt.progress_state = progress_state
    update_fields = [
        'score',
        'scholarship_percentage',
        'test_completed_at',
        'status',
        'total_questions',
        'total_marks',
        'progress_state',
    ]
    if attempt_can_persist_security_fields(attempt):
        attempt.submitted_at = submitted_at
        attempt.security_status = 'submitted'
        update_fields.extend(['submitted_at', 'security_status'])
    attempt.save(update_fields=update_fields)
    
    sms_sent = False
    sms_error = None
    if requires_otp_login(attempt.test):
        try:
            sms_sent, sms_error = _send_attempt_result_sms(
                attempt=attempt,
                score=score,
                total_questions=total_questions,
                scholarship_percentage=scholarship_percentage,
            )
            logger.info(f"Result SMS sent: {sms_sent}, {sms_error}")
        except Exception as e:
            logger.error(f"Failed to send result SMS: {str(e)}", exc_info=True)
            sms_error = str(e)
    
    # Store SMS status in attempt for debugging
    attempt.sms_sent = sms_sent
    attempt.sms_error = sms_error
    attempt.save(update_fields=['sms_sent', 'sms_error'])
    if attempt.portal_student_id:
        recompute_portal_student_leaderboard(attempt.portal_student_id)
    
    return True, "Test submitted successfully", attempt


def check_test_expired(attempt_id: int) -> bool:
   
    from scholarship_test.models import ScholarshipTestAttempt
    
    try:
        attempt = ScholarshipTestAttempt.objects.defer(
            'started_at',
            'submitted_at',
            'violation_count',
            'security_status',
        ).get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return True 
    
    return is_attempt_expired(attempt)


def auto_submit_expired_test(attempt_id: int):
   
    from scholarship_test.models import ScholarshipTestAttempt, ScholarshipStudentAnswer, ScholarshipQuestion
    
    try:
        attempt = ScholarshipTestAttempt.objects.select_related('student').defer(
            'started_at',
            'submitted_at',
            'violation_count',
            'security_status',
        ).get(id=attempt_id)
    except ScholarshipTestAttempt.DoesNotExist:
        return False, "Test attempt not found", None
    
    # Check if already completed
    if attempt.status in ['completed', 'expired']:
        return False, "Test already submitted", attempt
    
   
    existing_answer_ids = set(
        attempt.answers.values_list('question_id', flat=True)
    )
    
   
    student = attempt.student
    questions = get_test_questions(
        grade=student.grade,
        board=student.board,
        count=TOTAL_QUESTIONS
    )
    
  
    answers = {}
    for question in questions:
        if question.id not in existing_answer_ids:
            ScholarshipStudentAnswer.objects.create(
                attempt=attempt,
                question=question,
                selected_option='',
                is_correct=False
            )
        else:
           
            answer = attempt.answers.get(question_id=question.id)
            answers[str(question.id)] = answer.selected_option
    
   
    score = 0
    for answer in attempt.answers.all():
        if answer.is_correct:
            score += 1
    
    scholarship_percentage = calculate_scholarship_percentage(score, len(questions))
    
   
    attempt.score = score
    attempt.scholarship_percentage = scholarship_percentage
    submitted_at = timezone.now()
    attempt.test_completed_at = submitted_at
    attempt.status = 'expired'
    attempt.total_questions = len(questions)
    progress_state = dict(attempt.progress_state or {})
    progress_state['submitted_at'] = submitted_at.isoformat()
    progress_state['security_status'] = 'submitted'
    progress_state['saved_at'] = submitted_at.isoformat()
    attempt.progress_state = progress_state
    update_fields = [
        'score',
        'scholarship_percentage',
        'test_completed_at',
        'status',
        'total_questions',
        'progress_state',
    ]
    if attempt_can_persist_security_fields(attempt):
        attempt.submitted_at = submitted_at
        attempt.security_status = 'submitted'
        update_fields.extend(['submitted_at', 'security_status'])
    attempt.save(update_fields=update_fields)
    
    
    sms_sent = False
    sms_error = None
    if requires_otp_login(attempt.test):
        try:
            sms_sent, sms_error = _send_attempt_result_sms(
                attempt=attempt,
                score=score,
                total_questions=len(questions),
                scholarship_percentage=scholarship_percentage,
            )
            logger.info(f"Result SMS sent for expired test: {sms_sent}, {sms_error}")
        except Exception as e:
            logger.error(f"Failed to send result SMS for expired test: {str(e)}", exc_info=True)
            sms_error = str(e)
    
    # Store SMS status
    attempt.sms_sent = sms_sent
    attempt.sms_error = sms_error
    attempt.save(update_fields=['sms_sent', 'sms_error'])
    if attempt.portal_student_id:
        recompute_portal_student_leaderboard(attempt.portal_student_id)
    
    return True, "Test auto-submitted due to time expiry", attempt


def normalize_grade(grade: str) -> str:
   
    if not grade:
        return ""
    
    grade = str(grade).strip()
    
    return grade


def normalize_board(board: str) -> str:
    
    if not board:
        return ""
    
    board = str(board).strip().upper()
    
    if 'CBSE' in board:
        return 'CBSE'
    elif 'STATE' in board or 'SSC' in board or 'ICSE' in board:
        return board
    
    return board


def can_attempt_test(student, selected_test=None) -> tuple:
   
    # Check if OTP is verified
    if not student.otp_verified:
        return False, "Please verify your phone number first"
    
    # Check if student has name, grade, board
    if not student.name:
        return False, "Please complete your registration"
    
    # Check if already completed a test
    from scholarship_test.models import ScholarshipTestAttempt
    completed_attempts = ScholarshipTestAttempt.objects.filter(
        student=student,
        status__in=['completed', 'expired']
    )

    if selected_test:
        completed_attempts = completed_attempts.filter(test=selected_test)

    completed_attempts = completed_attempts.exists()
    
    if completed_attempts:
        return False, "You have already completed the scholarship test"
    
    active_test = selected_test or get_active_test()
    if active_test:
        runtime_questions = get_runtime_questions_for_test(active_test)
        if not runtime_questions:
            return False, "No scholarship test questions are configured yet"
        launch_state = get_test_launch_state(active_test)
        if not launch_state["can_launch"]:
            return False, launch_state["message"] or "This test is not available right now"
        return True, "You can attempt the test"

    if not student.grade or not student.board:
        return False, "Please select your grade and board"

    # Legacy fallback while older question-bank data still exists.
    questions = get_test_questions(student.grade, student.board)
    if len(questions) < TOTAL_QUESTIONS:
        logger.warning(
            f"Insufficient questions for student {student.id}: "
            f"found {len(questions)}, need {TOTAL_QUESTIONS}"
        )

    return True, "You can attempt the test"
