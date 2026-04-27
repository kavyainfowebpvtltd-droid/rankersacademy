

from django.urls import path
from scholarship_test import views

app_name = 'scholarship_test'

urlpatterns = [
    # Student URLs
    path('', views.scholarship_home, name='scholarship_home'),
    path('launch/<int:test_id>/', views.scholarship_launch_test, name='scholarship_launch_test'),

    path('scholarship-landing-page/', views.scholarship_landing, name="scholarship_landing"),
    
    # Admin Management
    path('scholarshiptest-management/', views.scholarshiptest_management, name="scholarshiptest_management"),
    path('create-test/', views.scholarship_create_test, name="scholarship_create_test"),
    
    # Test Management APIs
    path('api/tests/', views.api_get_tests, name="api_get_tests"),
    path('api/tests/create/', views.api_create_test, name="api_create_test"),
    path('api/tests/<int:test_id>/save-question/', views.api_save_question, name="api_save_question"),
    path('api/tests/<int:test_id>/', views.api_get_test_details, name="api_get_test_details"),
    path('api/tests/<int:test_id>/update/', views.api_update_test, name="api_update_test"),
    path('api/tests/<int:test_id>/delete/', views.api_delete_test, name="api_delete_test"),
    path('api/tests/<int:test_id>/move/', views.api_move_test, name="api_move_test"),
    path('api/tests/<int:test_id>/copy/', views.api_copy_test, name="api_copy_test"),
    path('api/tests/<int:test_id>/save-details/', views.api_save_test_details, name="api_save_test_details"),
    path('api/tests/<int:test_id>/save-section/', views.api_save_section, name="api_save_section"),
    path('api/tests/<int:test_id>/sections/<int:section_id>/delete/', views.api_delete_section, name="api_delete_section"),
    path('api/tests/<int:test_id>/questions/<int:question_id>/delete/', views.api_delete_question, name="api_delete_question"),

    # Image Management APIs
    path('api/tests/<int:test_id>/upload-image/', views.api_upload_image, name="api_upload_image"),
    path('api/tests/<int:test_id>/images/', views.api_get_test_images, name="api_get_test_images"),
    path('api/tests/<int:test_id>/images/<int:image_id>/delete/', views.api_delete_image, name="api_delete_image"),
    path('api/tests/import-word/', views.api_import_word_questions, name="api_import_word_questions"),

    # Folder Management APIs
    path('api/folders/', views.api_get_folders, name="api_get_folders"),
    path('api/folders/create/', views.api_create_folder, name="api_create_folder"),
    path('api/folders/<int:folder_id>/update/', views.api_update_folder, name="api_update_folder"),
    path('api/folders/<int:folder_id>/delete/', views.api_delete_folder, name="api_delete_folder"),
    
    # Registration
    path('register/', views.scholarship_register, name='scholarship_register'),
    path('register/step-1/', views.scholarship_register, name='scholarship_register_step1'),
    path('register/step-2/', views.scholarship_register_step2, name='scholarship_register_step2'),
    
    # OTP APIs
    path('api/send-otp/', views.scholarship_send_otp, name='scholarship_send_otp'),
    path('api/verify-otp/', views.scholarship_verify_otp, name='scholarship_verify_otp'),
    path('api/resend-otp/', views.scholarship_resend_otp, name='scholarship_resend_otp'),
    
    # Dashboard and Test
    path('dashboard/', views.scholarship_dashboard, name='scholarship_dashboard'),
    path('test/start/', views.scholarship_start_test, name='scholarship_start_test'),
    path('test/<int:attempt_id>/', views.scholarship_test, name='scholarship_test'),
    path('test/<int:attempt_id>/submit/', views.scholarship_submit_test, name='scholarship_submit_test'),
    
    # Result
    path('success/<int:attempt_id>/', views.scholarship_success, name='scholarship_success'),
    
    # Logout
    path('logout/', views.scholarship_logout, name='scholarship_logout'),
]
