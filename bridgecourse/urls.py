from django.urls import path
from . import views

app_name = 'bridgecourse'

urlpatterns = [
   path("admin/management/", views.bridgecourse_management, name='bridgecourse-management'),
   path("bridge-course-login/", views.bridge_course_login, name='bridge_course_login'),
   path("bridge-course-login-only/", views.bridge_course_login_only, name='bridge_course_login_only'),
   path("bridge-course-register/", views.bridge_course_register, name='bridge_course_register'),
   path("bridge-course/", views.bridge_course, name='bridge_course'),
   path("bridge-course-logout/", views.bridge_course_logout, name='bridge_course_logout'),
  
   path("api/bridge-course/send-otp/", views.bridge_course_send_otp, name='bridge_course_send_otp'),
   path("api/bridge-course/verify-otp/", views.bridge_course_verify_otp, name='bridge_course_verify_otp'),
 
   path("api/bridge-course/check-user/", views.bridge_course_check_user, name='bridge_course_check_user'),
   path("api/bridge-course/login-send-otp/", views.bridge_course_login_send_otp, name='bridge_course_login_send_otp'),
   path("api/bridge-course/login-verify-otp/", views.bridge_course_login_verify_otp, name='bridge_course_login_verify_otp'),
   
   path("api/subjects/", views.get_subjects, name='get_subjects'),
   path("api/subjects/add/", views.add_subject, name='add_subject'),
   path("api/subjects/delete/<int:subject_id>/", views.delete_subject, name='delete_subject'),
   path("api/lectures/", views.get_lectures, name='get_lectures'),
   path("api/lectures/add/", views.add_lecture, name='add_lecture'),
   path("api/lectures/update/", views.update_lecture, name='update_lecture'),
   path("api/lectures/delete/<int:lecture_id>/", views.delete_lecture, name='delete_lecture'),
   path("api/lectures/<int:lecture_id>/notes/", views.get_lecture_notes, name='get_lecture_notes'),
  
   path("api/lectures/track-progress/", views.track_video_progress, name='track_video_progress'),
]