from pathlib import Path
import os
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import cloudinary.api
import dj_database_url

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY - NOW FROM ENV
SECRET_KEY = os.environ.get('SECRET_KEY')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = ['lendogo-production.up.railway.app', '.up.railway.app', 'localhost', '127.0.0.1']  
CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000', 
    'http://localhost:8000',
    'https://lendogo-production.up.railway.app'
]

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

# DATABASE
if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=600,
            ssl_require=True
        )
    }
else:
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

# MEDIA FILES - CLOUDINARY FROM ENV
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
MEDIA_URL = '/media/'

cloudinary.config( 
  cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),  
  api_key = os.environ.get('CLOUDINARY_API_KEY'),        
  api_secret = os.environ.get('CLOUDINARY_API_SECRET')   
)

CLOUDINARY_URL = f"cloudinary://{os.environ.get('CLOUDINARY_API_KEY')}:{os.environ.get('CLOUDINARY_API_SECRET')}@{os.environ.get('CLOUDINARY_CLOUD_NAME')}"

# PAYCHANGU - FROM ENV
PAYCHANGU_PUBLIC_KEY = os.environ.get('PAYCHANGU_PUBLIC_KEY')
PAYCHANGU_SECRET_KEY = os.environ.get('PAYCHANGU_SECRET_KEY')
PAYCHANGU_MODE = os.environ.get('PAYCHANGU_MODE', 'live')
PAYCHANGU_VERIFY_SSL = True
VERIFICATION_FEE = int(os.environ.get('VERIFICATION_FEE', 2100))
BOOST_FEE = int(os.environ.get('BOOST_FEE', 550))

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@lendogo.com'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

DATA_UPLOAD_MAX_MEMORY_SIZE = 31457280
FILE_UPLOAD_MAX_MEMORY_SIZE = 31457280

# SECURITY SETTINGS FOR PRODUCTION
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SAMESITE = 'Lax'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'