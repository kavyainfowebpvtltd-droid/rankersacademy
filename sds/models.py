from django.db import models
from django.contrib.auth.models import User



# Student Model

class Student(models.Model): 
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    student_name = models.CharField(max_length=255)
    profile_photo = models.ImageField(upload_to="student_profiles/", blank=True, null=True)
    username = models.CharField(max_length=150, blank=True, default="")
    father_name = models.CharField(max_length=255, blank=True, default="")
    contact = models.CharField(max_length=15, unique=True)
    emergency_contact_name = models.CharField(max_length=255, blank=True, default="")
    emergency_contact = models.CharField(max_length=15, blank=True, default="")
    email = models.EmailField(max_length=255, unique=True)
    school = models.CharField(max_length=255)
    stream = models.CharField(max_length=20, blank=True, default="")
    board = models.CharField(max_length=50)
    grade = models.CharField(max_length=20)
    batch = models.CharField(max_length=50, default="B1")
    blood_group = models.CharField(max_length=10, blank=True, default="")
    gender = models.CharField(max_length=10)
    is_external = models.BooleanField(default=False)
    dob = models.DateField(blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=80, blank=True, default="")
    state = models.CharField(max_length=80, blank=True, default="")
    pincode = models.CharField(max_length=10, blank=True, default="")
    interested_exams = models.JSONField(default=list, blank=True) 
    # Email tracking fields
    report_email_sent = models.BooleanField(default=False)
    report_email_sent_at = models.DateTimeField(blank=True, null=True)
    report_email_error = models.TextField(blank=True, default="")
    must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return self.student_name



# Teacher / Admin Model

class TeacherAdmin(models.Model):
    ROLE_CHOICES = (("Teacher", "Teacher"), ("Admin", "Admin"))
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    username = models.CharField(max_length=150)
    email = models.EmailField(max_length=255, unique=True)
    contact = models.CharField(max_length=15, unique=True)
    gender = models.CharField(max_length=10)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)

    grade = models.CharField(max_length=20, blank=True, null=True)
    board = models.CharField(max_length=50, blank=True, null=True)
    batch = models.CharField(max_length=50, blank=True, null=True)

    subjects = models.TextField(blank=True)
    profile_picture = models.ImageField(upload_to="teacher_profiles/", blank=True, null=True)
    must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.role})"


# Subject Model

class Subject(models.Model):
    name = models.CharField(max_length=100)
    grade = models.CharField(max_length=20, default="10")
    board = models.CharField(max_length=50, default="CBSE")
    batch = models.CharField(max_length=50, default="B1")  

    class Meta:
        unique_together = ("name", "grade", "board", "batch")  

    def __str__(self):
        return f"{self.name} | {self.grade} | {self.board} | {self.batch}"


# Chapter Model

class Chapter(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="chapters")
    name = models.CharField(max_length=150)

    def __str__(self):
        return f"{self.subject.name} - {self.name}"


# Important Questions and Solutions Pdf Model

class ChapterImpQuestions(models.Model):
    
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="imp_questions")
    imp_questions = models.FileField(upload_to="study_material/imp_questions/", blank=True, null=True)
    imp_solutions = models.FileField(upload_to="study_material/imp_solutions/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Imp Questions - {self.chapter.name}"

# Topic Model

class Topic(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="topics")
    name = models.CharField(max_length=150)

    def __str__(self):
        return f"{self.chapter.name} - {self.name}"

# MCQ Questions Models

class Question(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="mcqs")
    question = models.TextField()
    question_image = models.ImageField(upload_to="mcq_images/", blank=True, null=True)
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255, default= "N/A")
    correct_answer = models.CharField(
        max_length=1,
        choices=[("A","A"),("B","B"),("C","C"),("D","D")],
        default= "A"
    )   

    def __str__(self):
        return self.question[:50]



# User Test Model

class UserTest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    test_number = models.PositiveIntegerField(default=1)
    attempted_topics = models.JSONField(default=list)
    correct_topics = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "subject", "test_number")

    def __str__(self):
        return f"{self.user.username} - {self.subject.name} - Test {self.test_number}"


# Subject Coverage Model

class SubjectCoverage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.ForeignKey("Subject", on_delete=models.CASCADE)
    covered_topic_ids = models.JSONField(default=list)    
    chapter_coverage = models.JSONField(default=dict)    
    subject_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "subject")

    def __str__(self):
        return f"{self.user.username} - {self.subject.name} - {self.subject_percent}%"

class OverallCoverage(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    grade = models.CharField(max_length=20)
    board = models.CharField(max_length=50)
    overall_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.grade}/{self.board} - {self.overall_percent}%"
    
