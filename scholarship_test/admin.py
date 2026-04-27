from django.contrib import admin

from .models import *

admin.site.register(ScholarshipGradeBoard)
admin.site.register(ScholarshipSubject)
admin.site.register(ScholarshipQuestion)
admin.site.register(ScholarshipStudent)
admin.site.register(ScholarshipOTP)
admin.site.register(ScholarshipTestAttempt)
admin.site.register(ScholarshipStudentAnswer)
admin.site.register(ScholarshipTest)
admin.site.register(ScholarshipTestFolder)
admin.site.register(ScholarshipTestConfig)
admin.site.register(ScholarshipTestSection)
admin.site.register(ScholarshipTestQuestion)
admin.site.register(ScholarshipTestOption)
admin.site.register(ScholarshipTestAnswer)
admin.site.register(ScholarshipTestImage)