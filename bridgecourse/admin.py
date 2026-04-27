from django.contrib import admin
from .models import *


class BridgeLectureAdmin(admin.ModelAdmin):
    list_display = ('topic_name', 'subject', 'day_number', 'lecture_number', 'video_url', 'notes_file', 'created_at')
    list_filter = ('subject', 'created_at')
    search_fields = ('topic_name', 'subject__subject_name')
    ordering = ('-created_at',)
    
    # Use proper form media for file uploads
    class Media:
        css = {
            'all': ('admin/css/forms.css',)
        }


class BridgeSubjectAdmin(admin.ModelAdmin):
    list_display = ('subject_name', 'grade', 'board', 'created_at')
    list_filter = ('grade', 'board')
    search_fields = ('subject_name',)


class BridgeLectureProgressAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'user_name', 'lecture', 'max_watch_time', 'min_watch_time', 'watch_count', 'last_watched_at', 'last_watched_time')
    list_filter = ('last_watched_at',)
    search_fields = ('phone_number', 'user_name', 'lecture__topic_name')
    ordering = ('-last_watched_at',)


admin.site.register(BridgeSubject, BridgeSubjectAdmin)
admin.site.register(BridgeLecture, BridgeLectureAdmin)
admin.site.register(BridgeCourseOTP)
admin.site.register(BridgeLectureProgress, BridgeLectureProgressAdmin)
