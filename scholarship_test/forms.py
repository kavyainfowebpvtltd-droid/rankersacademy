

import re
from django import forms
from django.core.validators import RegexValidator
from scholarship_test.models import (
    ScholarshipStudent,
    ScholarshipSubject,
    ScholarshipQuestion,
    ScholarshipTestAttempt
)


class ScholarshipRegistrationStepOneForm(forms.Form):
   
    GRADE_CHOICES = [
        ('', 'Select Grade/Class'),
        ('8th', '8th'),
        ('9th', '9th'),
        ('10th', '10th'),
        ('11th', '11th'),
        ('12th', '12th'),
    ]
    
    BOARD_CHOICES = [
        ('', 'Select Board'),
        ('CBSE', 'CBSE'),
        ('State', 'State Board'),
        ('ICSE', 'ICSE'),
    ]
    
    grade = forms.ChoiceField(
        choices=GRADE_CHOICES,
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_grade'
        }),
        error_messages={
            'required': 'Please select your grade/class',
            'invalid_choice': 'Please select a valid grade'
        }
    )
    
    board = forms.ChoiceField(
        choices=BOARD_CHOICES,
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_board'
        }),
        error_messages={
            'required': 'Please select your board',
            'invalid_choice': 'Please select a valid board'
        }
    )
    
    def clean_grade(self):
        grade = self.cleaned_data.get('grade')
        if not grade or grade == '':
            raise forms.ValidationError("Please select your grade/class")
        return grade
    
    def clean_board(self):
        board = self.cleaned_data.get('board')
        if not board or board == '':
            raise forms.ValidationError("Please select your board")
        return board


class ScholarshipRegistrationStepTwoForm(forms.Form):
   
    name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your full name',
            'id': 'id_name'
        }),
        error_messages={
            'required': 'Please enter your name',
            'max_length': 'Name is too long'
        }
    )
    
    phone_number = forms.CharField(
        max_length=15,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter 10-digit mobile number',
            'id': 'id_phone',
            'maxlength': '10'
        }),
        validators=[
            RegexValidator(
                regex=r'^\d{10}$',
                message='Please enter a valid 10-digit mobile number'
            )
        ],
        error_messages={
            'required': 'Please enter your phone number'
        }
    )
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            name = name.strip()
            if len(name) < 2:
                raise forms.ValidationError("Name is too short")
            if not re.fullmatch(r'[A-Za-z ]+', name):
                raise forms.ValidationError("Name should contain only letters and spaces")
        return name
    
    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone:
            # Keep only digits
            phone = re.sub(r'\D', '', phone)
            if len(phone) != 10:
                raise forms.ValidationError("Please enter a valid 10-digit mobile number")
        return phone


class OTPVerificationForm(forms.Form):
  
    phone_number = forms.CharField(
        max_length=15,
        required=True,
        widget=forms.HiddenInput(),
        validators=[
            RegexValidator(
                regex=r'^\d{10}$',
                message='Invalid phone number'
            )
        ]
    )
    
    otp_code = forms.CharField(
        max_length=4,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter 4-digit OTP',
            'id': 'id_otp',
            'maxlength': '4',
            'autocomplete': 'off'
        }),
        validators=[
            RegexValidator(
                regex=r'^\d{4}$',
                message='Please enter a valid 4-digit OTP'
            )
        ],
        error_messages={
            'required': 'Please enter the OTP'
        }
    )
    
    def clean_otp_code(self):
        otp = self.cleaned_data.get('otp_code')
        if otp:
            if len(otp) != 4 or not otp.isdigit():
                raise forms.ValidationError("Please enter a valid 4-digit OTP")
        return otp



