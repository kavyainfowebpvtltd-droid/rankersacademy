from django.urls import path
from . import views

urlpatterns = [
    path('', views.attendance, name='attendance'),
    path('staff/', views.staff_attendance, name='staff_attendance'),
    path('staff/export-email/', views.export_staff_attendance_email, name='export_staff_attendance_email'),
    path('staff/<int:staff_id>/', views.view_staff_attendance, name='view_staff_attendance'),
    path('export-email/', views.export_attendance_email, name='export_attendance_email'),
    path('mark/', views.mark_attendance, name='mark_attendance'),
    path('student/<int:student_id>/', views.view_student_attendance, name='view_student_attendance'),
    path('my-attendance/', views.my_attendance, name='my_attendance'),
    path('kiosk/', views.qr_kiosk, name='qr_kiosk'),
    path('kiosk/scan/', views.kiosk_scan_api, name='kiosk_scan_api'),
]
