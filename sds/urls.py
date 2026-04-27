from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [

    # Authentication

    path("", views.login_view, name="login"),
    path("accounts/login/", RedirectView.as_view(url='/', permanent=False), name="account_login"),
    path("register/", views.register_student, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("force-password-change/", views.force_password_change, name="force_password_change"),

    # OTP login

    path("auth/send-login-otp/", views.send_login_otp, name="send_login_otp"),
    path("auth/verify-login-otp/", views.verify_login_otp, name="verify_login_otp"),

    # OTP password reset 

    path("auth/send-reset-otp/", views.send_reset_otp, name="send_reset_otp"),
    path("auth/verify-reset-otp/", views.verify_reset_otp, name="verify_reset_otp"),
    path("auth/set-new-password/", views.set_new_password, name="set_new_password"),

    # OTP registration

    path("auth/send-register-phone-otp/", views.send_register_phone_otp, name="send_register_phone_otp"),
    path("auth/verify-register-phone-otp/", views.verify_register_phone_otp, name="verify_register_phone_otp"),
    
    # Check if phone/email already exists
    path("auth/check-phone-exists/", views.check_phone_exists, name="check_phone_exists"),
    path("auth/check-email-exists/", views.check_email_exists, name="check_email_exists"),

    # Study Material Download OTP

    path("auth/send-study-download-otp/", views.send_study_download_otp, name="send_study_download_otp"),
    path("auth/verify-study-download-otp/", views.verify_study_download_otp, name="verify_study_download_otp"),


    # User Management

    path("user-management/", views.user_management, name="user-management"),
    path("add-user/", views.add_user, name="add_user"),

    path("edit-student/<int:id>/", views.edit_student, name="edit_student"),
    path("delete-student/<int:id>/", views.delete_student, name="delete_student"),

    path("edit-teacher/<int:id>/", views.edit_teacher, name="edit_teacher"),
    path("delete-teacher/<int:id>/", views.delete_teacher, name="delete_teacher"),

    # Dashboards

    path("dashboard/student-dashboard/", views.student_dashboard, name="student-dashboard"),
    path("dashboard/admin-dashboard/", views.admin_dashboard, name="admin-dashboard"),

    # Student Module

    path("gap-analysis/", views.gap_analysis, name="gap_analysis"),
    path("subject-analysis/", views.subject_analysis, name="subject_analysis"),
    path("reports/", views.report, name="reports"),

    # Backend PDF

    path("dashboard/students/<int:student_id>/pdf-report/", views.pdf_report, name="pdf-report"),
    path("dashboard/students/<int:student_id>/print-report/", views.print_report, name="print-report"),
    path("api/send-report-email/", views.send_report_email_api, name="send-report-email-api"),

    # Admin Module

    path("system-management/", views.system_management, name="system-management"),
    path("syllabus-management/", views.syllabus_management, name="syllabus-management"),

    path("add-subject/", views.add_subject, name="add_subject"),
    path("add-chapter/", views.add_chapter, name="add_chapter"),
    path("add-topic/", views.add_topic, name="add_topic"),
    path("add-mcq/", views.add_mcq, name="add_mcq"),

    path("edit-subject/<int:id>/", views.edit_subject, name="edit_subject"),
    path("edit-chapter/<int:id>/", views.edit_chapter, name="edit_chapter"),
    path("edit-topic/<int:id>/", views.edit_topic, name="edit_topic"),
    path("edit-mcq/<int:id>/", views.edit_mcq, name="edit_mcq"),

    path("delete-subject/<int:id>/", views.delete_subject, name="delete_subject"),
    path("delete-chapter/<int:id>/", views.delete_chapter, name="delete_chapter"),
    path("delete-topic/<int:id>/", views.delete_topic, name="delete_topic"),
    path("delete-mcq/<int:id>/", views.delete_mcq, name="delete_mcq"),

    # Chapter Important Questions Upload

    path("upload-imp-questions/<int:chapter_id>/", views.upload_imp_questions, name="upload_imp_questions"),

    # Students needing attention page

    path("dashboard/student-needing-attention/", views.student_needing_attention,       name="student-needing-attention",
    ),



    # Test URL

    path("test/", views.test, name="test"), 
    path("test/load-subjects/", views.load_subjects, name="load_subjects"), 
    path("test/load-chapters/<int:subject_id>/", views.load_chapters, name="load_chapters"),
    path("test/load-quiz/<int:chapter_id>/", views.load_quiz, name="load_quiz"),
    path("test/submit-quiz/", views.submit_quiz, name="submit_quiz"),
    path("test/submit-self-diagnostic/", views.submit_self_diagnostic, name="submit_self_diagnostic"),
    

    path("study-material/", views.study_material_redirect, name="study_material"),
    path('ssc-state/', views.ssc_state, name='ssc_state'),
    path('ssc-cbse/', views.ssc_cbse, name='ssc_cbse'),
    path('hsc-state/', views.hsc_state, name='hsc_state'),
    path('hsc-cbse/', views.hsc_cbse, name='hsc_cbse' ),

    # API Endpoint
    path('api/student-progress/', views.api_student_progress, name='api_student_progress'),

]
