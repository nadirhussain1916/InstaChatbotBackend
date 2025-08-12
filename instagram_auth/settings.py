from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import os
load_dotenv()

# Only install MySQL adapter if using MySQL database
import os
if os.getenv('DATABASE_URL') and 'mysql' in os.getenv('DATABASE_URL', ''):
    import pymysql
    pymysql.install_as_MySQLdb()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
BASE_DIR = Path(__file__).resolve().parent.parent
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', "django-insecure-^baredo@4py=(i6l=w0o6*7%u$*u%p#mbf2+(o@$()b#lh%qrl")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
CORS_ALLOW_ALL_ORIGINS = DEBUG  # Only allow all origins in development
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    'instachatbotbackend-production.up.railway.app',
] + os.getenv('ALLOWED_HOSTS', '').split(',') if os.getenv('ALLOWED_HOSTS') else [
    'localhost',
    '127.0.0.1', 
    '0.0.0.0',
    'instachatbotbackend-production.up.railway.app',
]

# CORS settings
CORS_ALLOW_ALL_ORIGINS = DEBUG  # Only allow all origins in development

# Specific allowed origins for production
CORS_ALLOWED_ORIGINS = [
    'https://insta-chatbot-frontend.vercel.app',
    'https://instachatbotbackend-production.up.railway.app',
] + (os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if os.getenv('CORS_ALLOWED_ORIGINS') else [])

# CSRF trusted origins for cross-domain requests
CSRF_TRUSTED_ORIGINS = [
    'https://insta-chatbot-frontend.vercel.app',
    'https://instachatbotbackend-production.up.railway.app',
    'http://127.0.0.1:8000',  # for local development
    'http://localhost:8000',  # for local development
] + (os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if os.getenv('CSRF_TRUSTED_ORIGINS') else [])


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    'instaapp',
    "corsheaders",
]

MIDDLEWARE = [
    'whitenoise.middleware.WhiteNoiseMiddleware',
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
]

ROOT_URLCONF = "instagram_auth.urls"
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "instagram_auth.wsgi.application"

# settings.py

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}


# Database configuration
import dj_database_url

# Check if DATABASE_URL is provided (common on Railway/Heroku)
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    # Use DATABASE_URL for production (Railway/Heroku style)
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require=True)
    }
else:
    # Use individual environment variables (Neon style)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'instagram'),
            'USER': os.environ.get('DB_USER', 'neondb_owner'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', ''),
            'PORT': os.environ.get('DB_PORT', '5432'),
            'OPTIONS': {
                'sslmode': os.environ.get('DB_SSLMODE', 'require'),
                'channel_binding': os.environ.get('DB_CHANNEL_BINDING', 'require'),
            },
        }
    }






# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Cloudinary configuration
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
}
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
FINE_TUNED_MODEL_ID = os.getenv('FINE_TUNED_MODEL_ID', 'ft:gpt-3.5-turbo-0125:kar-brulhart-inc::BlEigy85')

# secret key for encrypt or decrypt pasword
SECRET_ENCRYPTION_KEY = os.environ.get('FERNET_KEY')

# Production Security Settings
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Instagram OAuth2 settings
SOCIAL_AUTH_INSTAGRAM_KEY = os.getenv('INSTAGRAM_CLIENT_ID', "1717476175794446")        # Client ID
SOCIAL_AUTH_INSTAGRAM_SECRET = os.getenv('INSTAGRAM_CLIENT_SECRET', "98750104cc7f71f0f75256d05e40fd2c")  # Client Secret
SOCIAL_AUTH_INSTAGRAM_REDIRECT_URI = os.getenv('INSTAGRAM_REDIRECT_URI', 'http://127.0.0.1:8000/complete/instagram/')
SOCIAL_AUTH_INSTAGRAM_SCOPE = ['user_profile', 'user_media']

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=6), # set to desired value
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}