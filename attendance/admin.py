from django.contrib import admin

from attendance.models import Attendance, StaffAttendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "date", "status", "check_in", "check_out", "marked_by")
    list_filter = ("status", "date")
    search_fields = ("student__student_name", "student__contact", "student__email")


@admin.register(StaffAttendance)
class StaffAttendanceAdmin(admin.ModelAdmin):
    list_display = ("staff", "date", "status", "check_in", "check_out", "updated_at")
    list_filter = ("status", "date", "staff__role")
    search_fields = ("staff__name", "staff__contact", "staff__email", "staff__username")
