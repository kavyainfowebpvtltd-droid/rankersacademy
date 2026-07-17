from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify


def uploaded_schedule_path(instance, filename):
    """Store uploaded schedules inside teacher-specific folders."""
    teacher_name = instance.teacher.name if getattr(instance, "teacher", None) else "unassigned"
    teacher_folder = slugify(teacher_name) or "unassigned"
    return f"schedules/uploads/{teacher_folder}/{filename}"


def dpp_pdf_upload_path(instance, filename):
    """Store DPP PDFs inside teacher-specific folders."""
    teacher_name = instance.teacher.name if getattr(instance, "teacher", None) else "unassigned"
    teacher_folder = slugify(teacher_name) or "unassigned"
    return f"schedules/dpp/{teacher_folder}/{filename}"


class SubjectSchedule(models.Model):
    """Subject-wise schedule for teachers"""
    subject = models.CharField(max_length=100)
    grade = models.CharField(max_length=20)
    board = models.CharField(max_length=50)
    batch = models.CharField(max_length=50, default="B1")

    class Meta:
        unique_together = ("subject", "grade", "board", "batch")
        ordering = ["subject"]

    def __str__(self):
        return f"{self.subject} - Grade {self.grade} ({self.board})"


class ScheduleEntry(models.Model):
    """Individual schedule entries for teaching"""
    DURATION_CHOICES = [
        ("1", "1 Lecture"),
        ("2", "2 Lectures"),
        ("3", "3 Lectures"),
        ("4", "4 Lectures"),
        ("FULL", "Full Day"),
    ]

    date = models.DateField()
    subject = models.ForeignKey(SubjectSchedule, on_delete=models.CASCADE, related_name="entries")
    teacher = models.ForeignKey(
        "sds.TeacherAdmin",
        on_delete=models.CASCADE,
        related_name="schedule_entries",
        blank=True,
        null=True
    )
    source_upload = models.ForeignKey(
        "teacherschedule.UploadedSchedule",
        on_delete=models.CASCADE,
        related_name="schedule_entries",
        blank=True,
        null=True,
    )
    topic = models.CharField(max_length=200)
    chapter = models.CharField(max_length=150, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    duration = models.CharField(max_length=20, choices=DURATION_CHOICES, default="1")
    lecture_number = models.PositiveIntegerField(default=1)
    dpp_file = models.FileField(upload_to=dpp_pdf_upload_path, blank=True, null=True)
    lecture_time = models.TimeField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "lecture_number"]
        unique_together = ("date", "subject", "lecture_number")

    def __str__(self):
        return f"{self.date} - {self.subject.subject} - {self.topic}"


class UploadedSchedule(models.Model):
    """Track uploaded schedule files"""
    FILE_TYPE_CHOICES = [
        ("PDF", "PDF"),
        ("EXCEL", "Excel"),
        ("CSV", "CSV"),
    ]

    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES)
    file = models.FileField(upload_to=uploaded_schedule_path)
    grade = models.CharField(max_length=20)
    board = models.CharField(max_length=50)
    batch = models.CharField(max_length=50, default="B1")
    teacher = models.ForeignKey(
        "sds.TeacherAdmin",
        on_delete=models.CASCADE,
        related_name="uploaded_schedules",
        blank=True,
        null=True,
    )
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file_name} - {self.grade} ({self.board})"
