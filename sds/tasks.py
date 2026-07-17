import threading
from django.core.mail import EmailMessage
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def _send_pdf_email_async(student_email, pdf_bytes, filename, student_name, subject_name, subject_percent, overall_percent):
   
    try:
        from sds.views import send_report_pdf_on_email
        
        # Call the existing email function
        result = send_report_pdf_on_email(
            student_email=student_email,
            pdf_bytes=pdf_bytes,
            filename=filename,
            student_name=student_name,
            subject_name=subject_name,
            subject_percent=subject_percent,
            overall_percent=overall_percent,
            student_obj=None
        )
        
        logger.info(f"PDF report email sent to {student_email}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to send PDF email to {student_email}: {str(e)}")
        return False


class PDFGenerationTask:
    
    @staticmethod
    def generate_and_email(student_id, subject_id=None, send_email=True, email_override=None):
   
        try:
            from sds.models import Student, User, SubjectCoverage, OverallCoverage, UserTest
            from sds.views import _generate_pdf_bytes_for_student
            
            student = Student.objects.get(id=student_id)
            target_user = student.user
            
            # Generate PDF
            pdf_bytes, filename = _generate_pdf_bytes_for_student(student, target_user)
            
            # Calculate percentages for email
            overall_cov = OverallCoverage.objects.filter(user=target_user).first()
            overall_percent = float(overall_cov.overall_percent) if overall_cov else 0
            
            subject_name = "All Subjects"
            subject_percent = f"{overall_percent:.1f}"
            
            if subject_id:
                sc = SubjectCoverage.objects.filter(user=target_user, subject_id=subject_id).first()
                if sc:
                    subject_name = sc.subject.name
                    subject_percent = f"{float(sc.subject_percent):.1f}"
            
            # Send email if requested
            if send_email:
                recipient_email = email_override if email_override else student.email
                
                if recipient_email and '@' in recipient_email:
                    _send_pdf_email_async(
                        student_email=recipient_email,
                        pdf_bytes=pdf_bytes,
                        filename=filename,
                        student_name=student.student_name,
                        subject_name=subject_name,
                        subject_percent=subject_percent,
                        overall_percent=f"{overall_percent:.1f}"
                    )
                else:
                    logger.warning(f"Skipping email - invalid email for student {student_id}: {recipient_email}")
            
            logger.info(f"PDF generated successfully for student {student_id}")
            return True
            
        except Student.DoesNotExist:
            logger.error(f"Student not found: {student_id}")
            return False
        except Exception as e:
            logger.error(f"Error generating PDF for student {student_id}: {str(e)}")
            return False


def generate_pdf_async(student_id, subject_id=None, send_email=True, email_override=None):
   
    def run_task():
        PDFGenerationTask.generate_and_email(
            student_id=student_id,
            subject_id=subject_id,
            send_email=send_email,
            email_override=email_override
        )
    
    thread = threading.Thread(target=run_task, daemon=True)
    thread.start()
    
    logger.info(f"Async PDF task scheduled for student {student_id}")
    return True


def generate_pdf_sync(student_id, subject_id=None, send_email=True, email_override=None):
   
    try:
        from sds.models import Student, SubjectCoverage, OverallCoverage
        from sds.views import _generate_pdf_bytes_for_student
        
        student = Student.objects.get(id=student_id)
        target_user = student.user
        
        pdf_bytes, filename = _generate_pdf_bytes_for_student(student, target_user)
        
        if send_email:
            overall_cov = OverallCoverage.objects.filter(user=target_user).first()
            overall_percent = float(overall_cov.overall_percent) if overall_cov else 0
            
            subject_name = "All Subjects"
            subject_percent = overall_percent
            
            if subject_id:
                sc = SubjectCoverage.objects.filter(user=target_user, subject_id=subject_id).first()
                if sc:
                    subject_name = sc.subject.name
                    subject_percent = float(sc.subject_percent)
            
            recipient_email = email_override if email_override else student.email
            
            if recipient_email and '@' in recipient_email:
                _send_pdf_email_async(
                    student_email=recipient_email,
                    pdf_bytes=pdf_bytes,
                    filename=filename,
                    student_name=student.student_name,
                    subject_name=subject_name,
                    subject_percent=f"{subject_percent:.1f}",
                    overall_percent=f"{overall_percent:.1f}"
                )
        
        return pdf_bytes, filename
        
    except Exception as e:
        logger.error(f"Sync PDF generation failed for student {student_id}: {str(e)}")
        return None, None
