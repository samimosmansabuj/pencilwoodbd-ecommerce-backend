from pathlib import Path
from dotenv import load_dotenv
import os
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False').strip().lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS").split(",")
CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
TRUST_X_FORWARDED_FOR = os.getenv("TRUST_X_FORWARDED_FOR", "False").strip().lower() in ("true", "1", "yes")

# Application definition
INSTALLED_APPS = [
    # 'material.admin',
    # 'jet',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    #install apps
    'rest_framework', 'rest_framework_simplejwt', 'rest_framework_simplejwt.token_blacklist',
    'corsheaders', 'django_extensions', 'django_filters', 'django_htmx',
    'channels','rest_framework.authtoken',
    
    #Custom Apps
    'authentication', 'order', 'product','live_chat', 'site_app', 'dashbaord', 'marketing',"django_json_widget",
]



# ================================================================================
# ==================== Rest Frame Work Configurations Start====================
ENABLE_BROWSABLE_API = os.getenv('ENABLE_BROWSABLE_API', 'False') == 'True'
if ENABLE_BROWSABLE_API:
    DEFAULT_RENDERER_CLASSES_ = [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ]
else:
    DEFAULT_RENDERER_CLASSES_ = [
        'rest_framework.renderers.JSONRenderer'
    ]

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': DEFAULT_RENDERER_CLASSES_,
    
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ],
    
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 12,
    
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
    ),
}

from datetime import timedelta
SIMPLE_JWT = {
    'AUTH_HEADER_TYPES': ('Bearer',),
    'BLACKLIST_AFTER_ROTATION': True,
    'ROTATE_REFRESH_TOKENS': True,
    # 'ROTATE_REFRESH_TOKENS': False,
    
    'ACCESS_TOKEN_LIFETIME': timedelta(days=60),
    # 'ACCESS_TOKEN_LIFETIME': timedelta(minutes=5),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=60),
    
    "UPDATE_LAST_LOGIN": True,
}


CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_CREDENTIALS = True
# ==================== Rest Frame Work Configurations End====================
# ================================================================================






MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.common.CommonMiddleware',
    "django_htmx.middleware.HtmxMiddleware",
    # "product.middleware.MirgateCartMiddleware",
]

ROOT_URLCONF = 'pencilwoodbd.urls'

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

WSGI_APPLICATION = 'pencilwoodbd.wsgi.application'

ASGI_APPLICATION = 'pencilwoodbd.asgi.application'

# Redis settings (for channel layers) – make sure Redis is installed and running
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],  # Change as per your Redis configuration
        },
    },
}


#===========================================Session========================================
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 2592000
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True

# CSRF settings
# CSRF_COOKIE_HTTPONLY = False
# CSRF_COOKIE_SECURE = False
# # CSRF_COOKIE_SAMESITE = "Lax"
# CSRF_COOKIE_SAMESITE = "None"



# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    },
    
    "logs": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("SUPABASE_DB_NAME"),
        "USER": os.getenv("SUPABASE_DB_USER"),
        "PASSWORD": os.getenv("SUPABASE_DB_PASSWORD"),
        "HOST": os.getenv("SUPABASE_DB_HOST"),
        "PORT": os.getenv("SUPABASE_DB_PORT", default="5432"),
    },
}

# DATABASE_ROUTERS = [
#     "pencilwoodbd.database_routers.LogsDatabaseRouter",
# ]


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = "Asia/Dhaka"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

# # Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
# # STATICFILES_DIRS = [BASE_DIR / 'static', ]
# # STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static'),]
# # STATIC_ROOT = BASE_DIR / 'collectstatic'
# STATIC_ROOT = os.path.join(BASE_DIR, 'static')

if DEBUG:
    STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
    STATIC_ROOT = None  # don't use collectstatic in dev
else:
    STATIC_ROOT = os.path.join(BASE_DIR, 'static')  # Gunicorn + Nginx serve this
    STATICFILES_DIRS = []

MEDIA_URL = '/media/'
MEDIA_ROOT = os.getenv('MEDIA_ROOT', default=os.path.join(BASE_DIR, 'media'))

HERO_SLIDER_SIZE = (1400, 500)
HERO_SLIDER_MAX_ACTIVE = 5


# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'authentication.CustomUser'
LOGIN_REDIRECT_URL = 'dashboard'
LOGIN_URL = 'login'
