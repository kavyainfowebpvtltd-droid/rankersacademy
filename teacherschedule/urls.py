from django.urls import path
from . import views

app_name = "teacherschedule"

urlpatterns = [

path('', views.index, name='index'),
    path('admin/', views.admin_schedule_management, name='admin_management'),
    path('teacher/', views.teacher_schedule_viewer, name='teacher_viewer'),
    path('add/', views.add_schedule_entry, name='add_entry'),
    path('update/<int:entry_id>/', views.update_schedule_entry, name='update_entry'),
    path('delete/<int:entry_id>/', views.delete_schedule_entry, name='delete_entry'),
    path('mark-completed/<int:entry_id>/', views.mark_completed, name='mark_completed'),
    path('calendar/', views.get_calendar_data, name='calendar_data'),
    path('bulk-assign/', views.bulk_assign_teacher, name='bulk_assign'),
    path('export/', views.export_schedule, name='export_schedule'),
    path('import/', views.import_schedule, name='import_schedule'),
    path('import/delete/<int:upload_id>/', views.delete_uploaded_schedule, name='delete_uploaded_schedule'),
    path('import/bulk-delete/', views.bulk_delete_uploaded_schedules, name='bulk_delete_uploaded_schedules'),

]
