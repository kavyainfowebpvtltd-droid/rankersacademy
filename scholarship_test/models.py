

from django.db import models
from django.utils import timezone


class ScholarshipGradeBoard(models.Model):
  
    grade = models.CharField(max_length=20, help_text="e.g., 10th, 11th, 12th")
    board = models.CharField(max_length=20, help_text="e.g., CBSE, State, ICSE")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['grade', 'board']
        ordering = ['grade', 'board']

    def __str__(self):
        return f"{self.grade} - {self.board}"


class ScholarshipSubject(models.Model):
   
    grade = models.CharField(max_length=20, help_text="e.g., 10th, 11th, 12th")
    board = models.CharField(max_length=20, help_text="e.g., CBSE, State, ICSE")
    name = models.CharField(max_length=100, help_text="e.g., Mathematics, Science")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['grade', 'board', 'name']
        unique_together = ['grade', 'board', 'name']

    def __str__(self):
        return f"{self.name} ({self.grade} - {self.board})"


class ScholarshipQuestion(models.Model):
   
    ANSWER_CHOICES = [
        ('A', 'Option A'),
        ('B', 'Option B'),
        ('C', 'Option C'),
        ('D', 'Option D'),
    ]

    grade = models.CharField(max_length=20, help_text="e.g., 10th, 11th, 12th")
    board = models.CharField(max_length=20, help_text="e.g., CBSE, State, ICSE")
    subject = models.ForeignKey(
        ScholarshipSubject,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    question_text = models.TextField(help_text="The question content")
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    correct_answer = models.CharField(max_length=1, choices=ANSWER_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['subject', 'created_at']
        indexes = [
            models.Index(fields=['grade', 'board']),
            models.Index(fields=['subject']),
        ]

    def __str__(self):
        return f"Q{self.id}: {self.question_text[:50]}..."


class ScholarshipStudent(models.Model):
    
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15, unique=True)
    grade = models.CharField(max_length=20)
    board = models.CharField(max_length=20)
    otp_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.phone_number})"


class ScholarshipOTP(models.Model):
   
    student = models.ForeignKey(
        ScholarshipStudent,
        on_delete=models.CASCADE,
        related_name='otps',
        null=True,
        blank=True
    )
    phone_number = models.CharField(max_length=15)
    otp_code = models.CharField(max_length=4)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    resend_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP for {self.phone_number} - {'Verified' if self.is_verified else 'Pending'}"

    def is_expired(self):
        return timezone.now() > self.expires_at


class ScholarshipTestAttempt(models.Model):
   
    STATUS_CHOICES = [
        ('started', 'Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
    ]

    student = models.ForeignKey(
        ScholarshipStudent,
        on_delete=models.CASCADE,
        related_name='test_attempts'
    )
    test = models.ForeignKey(
        'ScholarshipTest',
        on_delete=models.SET_NULL,
        related_name='attempts',
        null=True,
        blank=True
    )
    portal_student = models.ForeignKey(
        'sds.Student',
        on_delete=models.SET_NULL,
        related_name='scholarship_test_attempts',
        null=True,
        blank=True
    )
    student_batch = models.CharField(max_length=50, blank=True, default="")
    score = models.IntegerField(default=0, help_text="Number of correct answers")
    scholarship_percentage = models.IntegerField(default=0, help_text="Scholarship percentage awarded")
    test_started_at = models.DateTimeField(auto_now_add=True)
    test_completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='started')
    total_questions = models.IntegerField(default=20)
    total_marks = models.IntegerField(default=20)
    sms_sent = models.BooleanField(default=False, help_text="Whether result SMS was sent successfully")
    sms_error = models.TextField(null=True, blank=True, help_text="Error message if SMS failed")

    class Meta:
        ordering = ['-test_started_at']

    def __str__(self):
        return f"Attempt {self.id} - {self.student.name} - Score: {self.score}/{self.total_questions}"


class ScholarshipStudentAnswer(models.Model):
    
    attempt = models.ForeignKey(
        ScholarshipTestAttempt,
        on_delete=models.CASCADE,
        related_name='answers'
    )
    question = models.ForeignKey(  
        ScholarshipQuestion,
        on_delete=models.CASCADE,
        related_name='student_answers'
    )
    selected_option = models.CharField(max_length=1)
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = ['attempt', 'question']
        ordering = ['question']

    def __str__(self):
        return f"Answer for Q{self.question.id} - {self.selected_option} - {'Correct' if self.is_correct else 'Incorrect'}"


class ScholarshipTestFolder(models.Model):
    name = models.CharField(max_length=100)
    tags = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ScholarshipTest(models.Model):
    name = models.CharField(max_length=100)
    date = models.DateField(auto_now_add=True)
    duration_hours = models.IntegerField(default=1)
    duration_minutes = models.IntegerField(default=0)
    folder = models.ForeignKey(
        ScholarshipTestFolder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tests'
    )
    tags = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=[
            ('draft', 'Draft'),
            ('published', 'Published'),
        ],
        default='draft'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def get_duration_display(self):
        hours = self.duration_hours
        minutes = self.duration_minutes
        if hours > 0 and minutes > 0:
            return f"{hours} hr {minutes} min"
        elif hours > 0:
            return f"{hours} hr"
        else:
            return f"{minutes} min"


class ScholarshipTestConfig(models.Model):
    test = models.OneToOneField(
        ScholarshipTest,
        on_delete=models.CASCADE,
        related_name='config'
    )
    instructions = models.TextField(blank=True, default="")
    default_pos_marks = models.IntegerField(default=2)
    default_neg_marks = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Config for {self.test.name}"


class ScholarshipTestSection(models.Model):
    test = models.ForeignKey(
        ScholarshipTest,
        on_delete=models.CASCADE,
        related_name='sections'
    )
    name = models.CharField(max_length=100)
    order = models.IntegerField(default=0)
    allow_switching = models.BooleanField(default=True)
    instructions = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'id']
        unique_together = ['test', 'name']

    def __str__(self):
        return f"{self.name} ({self.test.name})"


class ScholarshipTestQuestion(models.Model):
    QUESTION_TYPES = [
        ('mcq', 'Multiple Choice'),
        ('tf', 'True/False'),
        ('fitb', 'Fill In The Blanks'),
        ('int', 'Integer Type'),
        ('comp', 'Comprehension'),
    ]

    DIFFICULTY_LEVELS = [
        ('Easy', 'Easy'),
        ('Medium', 'Medium'),
        ('Hard', 'Hard'),
    ]

    section = models.ForeignKey(
        ScholarshipTestSection,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPES)
    question_text = models.TextField()
    passage = models.TextField(blank=True, default="")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_LEVELS, default='Medium')
    pos_marks = models.IntegerField(default=2)
    neg_marks = models.IntegerField(default=1)
    neg_unattempted = models.IntegerField(default=0)
    tags = models.CharField(max_length=200, blank=True, default="")
    order = models.IntegerField(default=0)
    is_multi_select = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"Q{self.id}: {self.question_text[:30]}..."


class ScholarshipTestOption(models.Model):
    question = models.ForeignKey(
        ScholarshipTestQuestion,
        on_delete=models.CASCADE,
        related_name='options'
    )
    option_text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"Option {self.id}: {self.option_text[:30]}..."


class ScholarshipTestAnswer(models.Model):

    question = models.ForeignKey(
        ScholarshipTestQuestion,
        on_delete=models.CASCADE,
        related_name='answers'   
    )
    correct_answer = models.TextField()
    is_correct = models.BooleanField(default=True)

    class Meta:
        unique_together = ['question']
        verbose_name_plural = 'Scholarship Test Answers'

    def __str__(self):
        return f"Answer for Q{self.question_id}: {self.correct_answer[:20]}..."


class ScholarshipTestImage(models.Model):
   
    test = models.ForeignKey(
        ScholarshipTest,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='scholarship_test_images/')
    original_filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Image: {self.original_filename} for {self.test.name}"

    def get_image_url(self):
       
        if self.image:
            return self.image.url
        return None
 
