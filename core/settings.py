from pathlib import Path
import os
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import cloudinary.api

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY
SECRET_KEY = 'h4q6%5=)m!n(hk6@g$ye4g9hd7htdwx@j13x)nwi+^25phj@x4'
DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '*']  
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8000', 'http://localhost:8000']

AUTH_USER_MODEL = 'lendogo.User'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    'cloudinary',              
    'cloudinary_storage',      

    'lendogo',
    'lendogo.chat',
    'services',
    'payments',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'lendogo.middleware.UpdateLastSeenMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'lendogo' / 'templates'],
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

WSGI_APPLICATION = 'core.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Blantyre'  
USE_I18N = True
USE_TZ = True


STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / "static",           
    BASE_DIR / "lendogo" / "static",  
]
STATIC_ROOT = BASE_DIR / "staticfiles" 
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# MEDIA FILES - CLOUDINARY
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
MEDIA_URL = '/media/'

cloudinary.config( 
  cloud_name = 'sbsdxiie',  
  api_key = '619153399851344',        
  api_secret = 'RczBGOUCUFx6z_P8W3Oyi9qCIL8'   
)

# PAYCHANGU - LIVE KEYS
PAYCHANGU_PUBLIC_KEY = 'pub-live-eDaKRML8UthiKOQsfJfBsidl.s1itBbT6'
PAYCHANGU_SECRET_KEY = 'sec-live-M4zsMpzeqkGUyHlwXhKoxJlQ5tz2c6iB'
PAYCHANGU_MODE = 'live'
PAYCHANGU_VERIFY_SSL = True
VERIFICATION_FEE = 2000

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@lendogo.com'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

DATA_UPLOAD_MAX_MEMORY_SIZE = 31457280  # 30MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 31457280  # 30MB

# SECURITY SETTINGS FOR PRODUCTION
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'