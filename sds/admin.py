from django.contrib import admin
from .models import *

admin.site.register(Student)
admin.site.register(Subject)
admin.site.register(Chapter)
admin.site.register(Topic)
admin.site.register(Question)
admin.site.register(TeacherAdmin)
admin.site.register(UserTest)
admin.site.register(SubjectCoverage)
admin.site.register(OverallCoverage)
admin.site.register(ChapterImpQuestions)

