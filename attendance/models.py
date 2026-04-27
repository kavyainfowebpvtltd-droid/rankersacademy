from django.db import models


class Attendance(models.Model):
    STATUS_CHOICES = [
        ("Present", "Present"),
        ("Late", "Late"),
        ("Absent", "Absent"),
    ]

    student = models.ForeignKey("sds.Student", on_delete=models.CASCADE, related_name="attendances")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    checkin_sms_sent_at = models.DateTimeField(null=True, blank=True)
    late_entry_sms_sent_at = models.DateTimeField(null=True, blank=True)
    checkout_sms_sent_at = models.DateTimeField(null=True, blank=True)
    absent_sms_sent_at = models.DateTimeField(null=True, blank=True)
    marked_by = models.ForeignKey("sds.TeacherAdmin", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "date")

    def __str__(self):
        return f"{self.student.student_name} - {self.date} - {self.status}"
