from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import os
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
BASE_DIR = Path(__file__).resolve().parent.parent
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-^baredo@4py=(i6l=w0o6*7%u$*u%p#mbf2+(o@$()b#lh%qrl"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
CORS_ALLOW_ALL_ORIGINS = True
ALLOWED_HOSTS = ['*']


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
    "django.middleware.security.SecurityMiddleware",
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


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': 'instagram',           # 👈 Your database name
#         'USER': 'root',        # 👈 Your MySQL username
#         'PASSWORD': '',# 👈 Your MySQL password
#         'HOST': 'localhost',              # 👈 Or your DB host, e.g. '127.0.0.1'
#         'PORT': '3306',                   # 👈 Default MySQL port
#     }
# }




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

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
FINE_TUNED_MODEL_ID = os.getenv('FINE_TUNED_MODEL_ID', 'ft:gpt-3.5-turbo-0125:kar-brulhart-inc::BlEigy85')

# secret key for encrypt or decrypt pasword
SECRET_ENCRYPTION_KEY = os.environ.get('FERNET_KEY')

# Instagram OAuth2 settings
SOCIAL_AUTH_INSTAGRAM_KEY = "1717476175794446"        # Client ID
SOCIAL_AUTH_INSTAGRAM_SECRET = "98750104cc7f71f0f75256d05e40fd2c"  # Client Secret
SOCIAL_AUTH_INSTAGRAM_REDIRECT_URI = 'http://127.0.0.1:8000/complete/instagram/'
SOCIAL_AUTH_INSTAGRAM_SCOPE = ['user_profile', 'user_media']

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),  # set to desired value
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}