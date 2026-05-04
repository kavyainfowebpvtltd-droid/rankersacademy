from django.urls import path
from . import views

urlpatterns = [
    path('', views.attendance, name='attendance'),
    path('staff/', views.staff_attendance, name='staff_attendance'),
    path('staff/scan/', views.staff_attendance_scan_api, name='staff_attendance_scan_api'),
    path('export-email/', views.export_attendance_email, name='export_attendance_email'),
    path('mark/', views.mark_attendance, name='mark_attendance'),
    path('student/<int:student_id>/', views.view_student_attendance, name='view_student_attendance'),
    path('my-attendance/', views.my_attendance, name='my_attendance'),
    path('kiosk/', views.qr_kiosk, name='qr_kiosk'),
    path('kiosk/scan/', views.kiosk_scan_api, name='kiosk_scan_api'),
]
