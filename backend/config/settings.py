"""Django settings for AMAPP (Adaptive Multi-Agent Path Planning) project.

Generated for Phase 02: Project scaffold and development environment.
"""

import os
import sys
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Ensure backend directory is in sys.path so 'apps' and 'config' can be resolved
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# Debug setting from environment (default: True for local development)
DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "yes")

# Secret key resolution and production validation
_raw_secret = os.environ.get("DJANGO_SECRET_KEY")
INSECURE_DEV_KEYS = {
    "django-insecure-dev-fallback-key-for-local-testing-only-amapp",
    "insecure-dev-key-change-in-production-only-placeholder-32-chars",
}
if not _raw_secret:
    if DEBUG:
        SECRET_KEY = "django-insecure-dev-fallback-key-for-local-testing-only-amapp"
    else:
        raise ValueError(
            "DJANGO_SECRET_KEY environment variable is strictly required when DEBUG is False."
        )
else:
    if not DEBUG and (_raw_secret in INSECURE_DEV_KEYS or len(_raw_secret) < 32):
        raise ValueError(
            "DJANGO_SECRET_KEY must be a secure, non-placeholder key "
            "of at least 32 characters when DEBUG is False."
        )
    SECRET_KEY = _raw_secret

# Allowed hosts configuration
_raw_hosts = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1],testserver")
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]
if not DEBUG and (not ALLOWED_HOSTS or ALLOWED_HOSTS == ["*"]):
    raise ValueError("ALLOWED_HOSTS must not be empty or wildcard '*' when DEBUG is False.")


# Application definition
INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party apps
    "channels",
    "rest_framework",
    # Project apps
    "apps.core.apps.CoreConfig",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
# Default: lightweight SQLite for development and testing
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Password validation
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

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Security Headers & Cookie Policies
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Request and upload size bounds (DoS mitigation)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB

# CSRF Trusted Origins (rejecting wildcards)
_raw_csrf = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in _raw_csrf.split(",")
    if o.strip() and not o.strip().startswith(("http://*", "https://*"))
]

# Django REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("AMAPP_THROTTLE_ANON", "120/minute"),
        "user": os.environ.get("AMAPP_THROTTLE_USER", "600/minute"),
        "burst": os.environ.get("AMAPP_THROTTLE_BURST", "60/minute"),
        "sustained": os.environ.get("AMAPP_THROTTLE_SUSTAINED", "1000/hour"),
        "simulation_step": os.environ.get("AMAPP_THROTTLE_STEP", "120/minute"),
        "simulation_create": os.environ.get("AMAPP_THROTTLE_CREATE", "60/minute"),
    },
    "EXCEPTION_HANDLER": "apps.core.api.exceptions.api_exception_handler",
    "UNAUTHENTICATED_USER": None,
}

# Django Channels in-memory channel layer (Phase 22)
# Suitable for single-process development and deterministic automated test execution.
# For production multi-worker deployment, an external Redis channel layer is recommended.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Real-time WebSocket streaming configuration (Phase 22 & Phase 36)
AMAPP_WS_MAX_QUEUE_SIZE = 128
AMAPP_WS_MAX_MESSAGE_BYTES = 65536
AMAPP_WS_MAX_REPLAY_RECORDS = 500
AMAPP_WS_HEARTBEAT_INTERVAL_S = 30.0
AMAPP_API_REQUIRE_AUTHENTICATION = False
AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS = os.environ.get(
    "AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS", "False"
).lower() in ("true", "1", "yes")

# Allowed WebSocket origins (rejecting wildcards)
_raw_ws_origins = os.environ.get("AMAPP_WS_ALLOWED_ORIGINS", "")
AMAPP_WS_ALLOWED_ORIGINS = [
    o.strip()
    for o in _raw_ws_origins.split(",")
    if o.strip() and not o.strip().startswith(("http://*", "https://*"))
]
