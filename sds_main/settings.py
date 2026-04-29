from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-)-#wj42wfm88kx+@@_pc2++83-7f9yls%kw2l+n8kfq6fas6u*'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
"147.93.29.224",
"rankersonlinetest.com",
"www.rankersonlinetest.com"
]
CSRF_TRUSTED_ORIGINS = [
"https://rankersonlinetest.com",
"https://www.rankersonlinetest.com"
]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'sds',
    'scholarship_test',
    'bridgecourse',
    'attendance',
    'teacherschedule',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'sds.middleware.ForcePasswordChangeMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'sds_main.urls'

TEMPLATES = [    
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'sds_main.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
   'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'rankers_db',
        'USER': 'root',
        'PASSWORD': 'Vishal@2026',
        'HOST': 'db',
        'PORT': '3306',
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR/'static'
STATICFILES_DIRS = [
  'sds_main/static',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR /'media'

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

X_FRAME_OPTIONS = 'SAMEORIGIN'

LOGIN_URL = '/'
LOGIN_REDIRECT_URL = '/'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_ENGINE = 'django.contrib.sessions.backends.db'




CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# ===========================
# OTP CONFIG (MSG91)
# ===========================
MSG91_AUTH_KEY = "493211AgvoFrlV3h698f0555P1"

# Template IDs
MSG91_TEMPLATE_LOGIN = "698b1b5a68286b4de314fbc2"
MSG91_TEMPLATE_GENERAL = "698ecc30737f4574275a3f78"

# Scholarship result SMS template
# User-provided template ID: 69cb62066737ad5136011e13
# DLT template ID: 1207177329008677759
# Sender ID: RNKARS
MSG91_TEMPLATE_SCHOLARSHIP_RESULT = "69cb62066737ad5136011e13"

# Success SMS template (user provided)
# Template ID: 69cb62066737ad5136011e13
MSG91_TEMPLATE_SUCCESS = "69cb62066737ad5136011e13"

MSG91_SENDER_ID = "RNKARS"

# Academy contact number for scholarship SMS (CTA number)
SCHOLARSHIP_ACADEMY_CONTACT = "918329100890"

# Study download specific template (uses login template for now)
MSG91_STUDY_OTP_TEMPLATE_ID = "698b1b5a68286b4de314fbc2"

# Attendance flow template IDs
MSG91_ATTENDANCE_CHECKIN_TEMPLATE = "69e9ebdab7357117ee02be94"
MSG91_ATTENDANCE_CHECKOUT_TEMPLATE = "69e9f17cf301542d5f04c6b2"
MSG91_ATTENDANCE_LATE_TEMPLATE = "69e9f21e60f3a90e250bd294"
MSG91_ATTENDANCE_ABSENT_TEMPLATE = "69e9f2fd177c9eba030ce112"

OTP_LENGTH = 6

# MSG91 OTP validity (minutes) - MUST match your template text / DLT content
MSG91_OTP_EXPIRY_MINUTES = 10

# Country code used by MSG91 in mobile param
MSG91_COUNTRY_CODE = "91"

# Network settings
MSG91_TIMEOUT_SECONDS = 60
MSG91_REALTIME_RESPONSE = 1

# Sender ID (for reference, may not be needed for OTP API)
MSG91_OTP_SENDER = "RANKER"

# ===========================
# Server-side safety controls
# ===========================
OTP_MAX_ATTEMPTS = 5

# cache TTL for OTP sessions; keep in sync with MSG91 expiry
OTP_EXPIRY_SECONDS = MSG91_OTP_EXPIRY_MINUTES * 60

# ============================
# Email Configuration (SMTP)
# ============================

EMAIL_ENABLED = True
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'therankersacademyngp@gmail.com'
EMAIL_HOST_PASSWORD = 'bniu pgxo vith gzma'  # App password
DEFAULT_FROM_EMAIL = "Ranker's Academy <therankersacademyngp@gmail.com>"

     

# Logging configuration for debugging OTP issues
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'sds': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
