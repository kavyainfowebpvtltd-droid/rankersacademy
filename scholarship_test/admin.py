from django.contrib import admin

from .models import (
    RankPredictorLead,
    ScholarshipGradeBoard,
    ScholarshipOTP,
    ScholarshipQuestion,
    ScholarshipStudent,
    ScholarshipStudentAnswer,
    ScholarshipSubject,
    ScholarshipTest,
    ScholarshipTestAnswer,
    ScholarshipTestAttempt,
    ScholarshipTestConfig,
    ScholarshipTestFolder,
    ScholarshipTestImage,
    ScholarshipTestOption,
    ScholarshipTestQuestion,
    ScholarshipTestSection,
)


@admin.register(ScholarshipTestAttempt)
class ScholarshipTestAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "student",
        "test",
        "portal_student",
        "status",
        "score",
        "total_questions",
        "total_marks",
        "test_started_at",
        "test_completed_at",
    )
    list_select_related = ("student", "test", "portal_student")
    search_fields = (
        "student__name",
        "student__phone_number",
        "portal_student__student_name",
        "portal_student__username",
        "test__name",
    )
    list_filter = ("status", "test")
    exclude = ("started_at", "submitted_at", "violation_count", "security_status")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related("student", "test", "portal_student").defer(
            "started_at",
            "submitted_at",
            "violation_count",
            "security_status",
        )


admin.site.register(ScholarshipGradeBoard)
admin.site.register(ScholarshipSubject)
admin.site.register(ScholarshipQuestion)
admin.site.register(ScholarshipStudent)
admin.site.register(ScholarshipOTP)
admin.site.register(RankPredictorLead)
admin.site.register(ScholarshipStudentAnswer)
admin.site.register(ScholarshipTest)
admin.site.register(ScholarshipTestFolder)
admin.site.register(ScholarshipTestConfig)
admin.site.register(ScholarshipTestSection)
admin.site.register(ScholarshipTestQuestion)
admin.site.register(ScholarshipTestOption)
admin.site.register(ScholarshipTestAnswer)
admin.site.register(ScholarshipTestImage)
