import environ
import os
import datetime
from pathlib import Path
from celery.schedules import crontab
from kombu import Queue, Exchange

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))

SECRET_KEY = env("SECRET_KEY")

DEBUG = env("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = ["*"]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    # Config whitenoise
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    # Third-party apps
    "rest_framework",
    "corsheaders",
    "drf_yasg",
    "django_filters",
    "django_celery_beat",
    "django_db_views",
    # Local apps
    "apps.wardriving",
    "apps.files",
    "apps.vendors",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # Cors configurados para admitir distintos destinos
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    # Allow Locations and language support
    "django.middleware.locale.LocaleMiddleware",
]

ROOT_URLCONF = "wardrive.urls"

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

WSGI_APPLICATION = "wardrive.wsgi.application"


DATABASES = {
    "default": {
        "ENGINE": env("DB_ENGINE", default="django.db.backends.postgresql"),
        "NAME": env("DB_NAME", default=""),
        "USER": env("DB_USER", default=""),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default=""),
        "PORT": env("DB_PORT", default=0, cast=int),
    }
}


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


LANGUAGE_CODE = "es-mx"

TIME_ZONE = "America/Mexico_City"

USE_I18N = True

USE_TZ = True

FORCE_SCRIPT_NAME = env("FORCE_SCRIPT_NAME", default="")
# Static files (CSS, JavaScript, Images)
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATIC_URL = os.path.join(FORCE_SCRIPT_NAME, "static/")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media Config
MEDIA_URL = os.path.join(FORCE_SCRIPT_NAME, "/media/")
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# REST Config
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": [],
    # https://www.django-rest-framework.org/api-guide/exceptions/#custom-exception-handling
    # "EXCEPTION_HANDLER": "rest.exception_handler.custom_exception_handler",
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "EXCEPTION_HANDLER": "api.exception_handler.custom_exception_handler",
}

# JWT headers
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": datetime.timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": datetime.timedelta(days=1),
}

# CORS
CORS_ALLOW_ALL_ORIGINS = env("CORS_ORIGIN_ALLOW_ALL", default=False, cast=bool)

# Storages
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}
# Related to documentation
SWAGGER_EMAIL = env("SWAGGER_EMAIL", default="example@mail.com")
SWAGGER_AUTHOR = env("SWAGGER_AUTHOR", default="not specified")
SWAGGER_CONTACT_URL = env(
    "SWAGGER_CONTACT_URL",
    default="https://static.wikia.nocookie.net/memeaventuras/images/5/51/Ola.jpg/revision/latest?cb=20140613225246&path-prefix=es",
)
SWAGGER_LICENSE = env("SWAGGER_LICENSE", default="Not specified yet")


# Swagger Settings
SWAGGER_SETTINGS = {
    "USE_SESSION_AUTH": env(
        "SWAGGER_USE_SESSION_AUTH", default=False, cast=bool
    ),  # Desactiva la autenticación por sesión
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
        },
    },
}

# Redis Configuration
REDIS_HOST = env("REDIS_HOST", default="localhost")
REDIS_PORT = env("REDIS_PORT", default=6379, cast=int)
REDIS_DB = env("REDIS_DB", default=0, cast=int)

REDIS_URL = ""
if REDIS_HOST and REDIS_PORT:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Celery Configuration
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "America/Mexico_City"
CELERY_ENABLE_UTC = False
# --- Sharding por (uploaded_by, device_source) ---
CELERY_SHARDS = int(os.getenv("CELERY_SHARDS", "4"))
CELERY_TASK_DEFAULT_QUEUE = "proc_0"
QUEUE_ARGS = {"x-max-priority": 10}

CELERY_TASK_QUEUES = tuple(
    Queue(
        name=f"proc_{i}",
        exchange=Exchange(f"proc_{i}"),
        routing_key=f"proc_{i}",
        **{"queue_arguments": QUEUE_ARGS},
    )
    for i in range(CELERY_SHARDS)
)


def _shard_for(uploaded_by_id, device_source, n=CELERY_SHARDS):
    key = f"{uploaded_by_id}:{device_source}"
    return f"proc_{(hash(key) % n)}"


def route_by_pair(name, args, kwargs, options, task=None, **_):
    if name.endswith("process_file"):
        ub = kwargs.get("_uploaded_by_id")
        ds = kwargs.get("_device_source")
        if ub is not None and ds is not None:
            q = _shard_for(ub, ds)
            # prioridad ejemplo: fuentes críticas más alto (más cercano a 10)
            prio = 8 if ds in {"wardriving_app"} else 5
            return {"queue": q, "routing_key": q, "priority": prio}
    return None


CELERY_TASK_ROUTES = (route_by_pair,)
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

APPEND_SLASH = False
USE_X_FORWARDED_HOST = True
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://*.ngrok.io",
    "https://*.ngrok.io",
    "http://*.ngrok-free.app",
    "https://*.ngrok-free.app",
    "http://*.tcp.ngrok.io",
    "https://*.tcp.ngrok.io",
]
