from django.db import models
from django.utils import timezone


class BridgeSubject(models.Model):
    subject_name = models.CharField(max_length=200)
    grade = models.CharField(max_length=50)
    board = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.subject_name} ({self.grade} - {self.board})"

class BridgeLecture(models.Model):
    subject = models.ForeignKey(BridgeSubject, on_delete=models.CASCADE, related_name='lectures')
    day_number = models.IntegerField()
    topic_name = models.CharField(max_length=200)
    lecture_number = models.CharField(max_length=50, blank=True, null=True)
    video_url = models.TextField(blank=True, null=True)
    notes_file = models.FileField(upload_to='bridge_lecture_notes/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.topic_name} - {self.subject.subject_name}"


class BridgeLectureProgress(models.Model):
    phone_number = models.CharField(max_length=15)
    user_name = models.CharField(max_length=100)
    lecture = models.ForeignKey(BridgeLecture, on_delete=models.CASCADE, related_name='watch_progress')
    max_watch_time = models.IntegerField(default=0)  # in seconds
    min_watch_time = models.IntegerField(default=0)  # in seconds
    watch_count = models.IntegerField(default=0)
    last_watched_at = models.DateTimeField(null=True, blank=True)  # Set explicitly from client timestamp
    last_watched_time = models.CharField(max_length=20, blank=True, default='')  # Store time string directly (HH:MM:SS format)
    
    class Meta:
        unique_together = ('phone_number', 'lecture', 'user_name')
        ordering = ['-last_watched_at']
    
    def __str__(self):
        return f"Progress for {self.phone_number} - {self.lecture.topic_name}"

    
#otp 
class BridgeCourseOTP(models.Model):
    phone_number = models.CharField(max_length=15)
    otp_code = models.CharField(max_length=4)
    name = models.CharField(max_length=100)
    grade = models.CharField(max_length=20)
    board = models.CharField(max_length=20)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    resend_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Bridge OTP for {self.phone_number} - {'Verified' if self.is_verified else 'Pending'}"
    
    def is_expired(self):
        return timezone.now() > self.expires_at
