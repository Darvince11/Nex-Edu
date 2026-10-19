"""Shared settings for every environment.

Environment-specific modules (dev, test, prod) import from here and override.
Secrets never live in this file: prod reads them from the environment, which ECS
populates from AWS Secrets Manager.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable {name}")
    return value or ""


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-dev-only-key-change-me")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,.localhost")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
# Control-plane apps live in the shared "default" database.
CONTROL_PLANE_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "allauth.headless",
    "allauth.usersessions",
    "control_plane",
]

# Tenant apps live in each school's own database. The DB router uses this list
# to decide where a model's queries and migrations go.
TENANT_APPS = [
    "core.audit",
    "apps.school",
    "apps.academics",
    "apps.students",
    "apps.staff",
    "apps.admissions",
    "apps.attendance",
    "apps.assessments",
    "apps.finance",
    "apps.communication",
]

INSTALLED_APPS = [*CONTROL_PLANE_APPS, "core", *TENANT_APPS]

# App labels (not dotted paths) of tenant apps, used by the router.
TENANT_APP_LABELS = frozenset(
    {
        "audit",
        "school",
        "academics",
        "students",
        "staff",
        "admissions",
        "attendance",
        "assessments",
        "finance",
        "communication",
    }
)

MIDDLEWARE = [
    "core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "core.middleware.PermissionsPolicyMiddleware",
    "core.middleware.RequestIdMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "control_plane.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csp",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Databases and multi-tenancy
# ---------------------------------------------------------------------------
# "default" is the control-plane database. School databases are registered at
# runtime under aliases "tenant_<slug>" by control_plane.db.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "var" / "control_plane.sqlite3",
    }
}
DATABASE_ROUTERS = ["control_plane.routers.TenantRouter"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Tenant resolution: <slug>.<TENANT_BASE_DOMAIN> or the X-Tenant header.
TENANT_BASE_DOMAIN = env("TENANT_BASE_DOMAIN", "localhost")
TENANT_HEADER = "X-Tenant"
TENANT_DB_ALIAS_PREFIX = "tenant_"
TENANT_PROVISIONER = env(
    "TENANT_PROVISIONER", "control_plane.provisioning.sqlite.SqliteProvisioner"
)
TENANT_SQLITE_DIR = Path(env("TENANT_SQLITE_DIR", str(BASE_DIR / "var" / "tenants")))
TENANT_SECRETS_BACKEND = env(
    "TENANT_SECRETS_BACKEND", "control_plane.secrets.LocalFileSecretsBackend"
)
TENANT_SECRETS_FILE = Path(env("TENANT_SECRETS_FILE", str(BASE_DIR / "var" / "secrets.json")))
TENANT_SECRETS_PREFIX = env("TENANT_SECRETS_PREFIX", "nexedu/dev/tenants/")
TENANT_MIGRATION_PARALLELISM = int(env("TENANT_MIGRATION_PARALLELISM", "8"))

# ---------------------------------------------------------------------------
# Field-level encryption (envelope encryption, one data key per school)
# ---------------------------------------------------------------------------
FIELD_ENCRYPTION_KEY_PROVIDER = env("FIELD_ENCRYPTION_KEY_PROVIDER", "core.crypto.LocalKeyProvider")
# Base64 32-byte key. Dev/test only; prod uses AWS KMS via KmsKeyProvider.
FIELD_ENCRYPTION_LOCAL_MASTER_KEY = env(
    "FIELD_ENCRYPTION_LOCAL_MASTER_KEY", "ZGV2LW9ubHktbWFzdGVyLWtleS0zMi1ieXRlcyEhISE="
)
FIELD_ENCRYPTION_KMS_KEY_ID = env("FIELD_ENCRYPTION_KMS_KEY_ID", "")

# ---------------------------------------------------------------------------
# Authentication (django-allauth headless: passkeys, TOTP, recovery codes)
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "control_plane.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "core.passwords.BreachedPasswordValidator"},
]
BREACHED_PASSWORD_CHECK_ENABLED = env_bool("BREACHED_PASSWORD_CHECK_ENABLED", True)

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_REAUTHENTICATION_TIMEOUT = 300
ACCOUNT_LOGIN_BY_CODE_ENABLED = False
# Schools invite users. Public self-signup is closed.
ACCOUNT_ADAPTER = "control_plane.adapters.InviteOnlyAccountAdapter"
ACCOUNT_RATE_LIMITS = {
    "login": "20/m/ip",
    "login_failed": "10/m/ip,5/5m/key",
    "confirm_email": "1/3m/key",
    "reset_password": "20/m/ip,5/m/key",
    "reauthenticate": "10/m/user",
}

MFA_SUPPORTED_TYPES = ["webauthn", "totp", "recovery_codes"]
MFA_PASSKEY_LOGIN_ENABLED = True
MFA_TOTP_ISSUER = "Nex Edu"
MFA_TRUST_ENABLED = False

HEADLESS_ONLY = True
HEADLESS_CLIENTS = ("browser", "app")
# Mobile apps get short-lived JWT access tokens and rotating refresh tokens.
HEADLESS_TOKEN_STRATEGY = "allauth.headless.tokens.strategies.jwt.JWTTokenStrategy"
HEADLESS_JWT_ALGORITHM = "RS256"
HEADLESS_JWT_PRIVATE_KEY = env("HEADLESS_JWT_PRIVATE_KEY", "")
HEADLESS_JWT_ACCESS_TOKEN_EXPIRES_IN = 600
HEADLESS_JWT_REFRESH_TOKEN_EXPIRES_IN = 60 * 60 * 24 * 30
HEADLESS_JWT_ROTATE_REFRESH_TOKEN = True
HEADLESS_JWT_STATEFUL_VALIDATION_ENABLED = True
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:3000")
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/account/verify-email/{{key}}",
    "account_reset_password_from_key": f"{FRONTEND_URL}/account/password/reset/{{key}}",
    "account_signup": f"{FRONTEND_URL}/account/signup",
}

# Roles that must have MFA enrolled before they can use any tenant endpoint.
MFA_REQUIRED_ROLES = frozenset(
    {"owner", "principal", "admin", "bursar", "teacher", "form_teacher", "librarian", "warden"}
)

# ---------------------------------------------------------------------------
# Sessions, cookies, CSRF
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_COOKIE_NAME = "nexedu_session"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:3000")

# ---------------------------------------------------------------------------
# HTTP security headers
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:"],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.NONE],
    "frame-ancestors": [CSP.NONE],
    "form-action": [CSP.SELF],
}
# Number of proxies in front of the app that append to X-Forwarded-For.
TRUSTED_PROXY_COUNT = int(env("TRUSTED_PROXY_COUNT", "0"))
ADMIN_ENABLED = env_bool("DJANGO_ADMIN_ENABLED", True)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
CORS_ALLOWED_ORIGIN_REGEXES = env_list("CORS_ALLOWED_ORIGIN_REGEXES", "")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "x-csrftoken",
    "x-requested-with",
    "x-session-token",
    "x-tenant",
    "idempotency-key",
]

# ---------------------------------------------------------------------------
# REST framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "allauth.headless.contrib.rest_framework.authentication.JWTTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Fail closed: every endpoint needs an authenticated member of the resolved
    # school with MFA (for staff) unless the view explicitly opts out.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "core.permissions.IsTenantMember",
        "core.permissions.MFAEnrolledForStaff",
        "core.permissions.HasRequiredPermission",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "core.throttling.TenantRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "600/min",
        "tenant": "6000/min",
        "public": "10/min",
    },
    "DEFAULT_PAGINATION_CLASS": "core.pagination.DefaultCursorPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "core.exceptions.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Nex Edu API",
    "VERSION": "1.0.0",
    "OAS_VERSION": "3.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# Cache and Celery
# ---------------------------------------------------------------------------
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_DEFAULT_QUEUE = "default"
# Separate queues so a report-card PDF storm can't delay payment processing.
CELERY_TASK_ROUTES = {
    "integrations.payments.*": {"queue": "critical-payments"},
    "communication.*": {"queue": "notifications"},
    "reports.*": {"queue": "reports"},
}
CELERY_BEAT_SCHEDULE = {
    "export-audit-events": {
        "task": "core.audit.tasks.export_audit_events_all_tenants",
        "schedule": timedelta(minutes=15),
    },
    "reconcile-payments": {
        "task": "integrations.payments.reconcile_all",
        "schedule": timedelta(minutes=15),
    },
}
AUDIT_EXPORT_BUCKET = env("AUDIT_EXPORT_BUCKET", "")

# ---------------------------------------------------------------------------
# Ghana: payments (GHS, mobile money) and messaging providers
# ---------------------------------------------------------------------------
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", "")
FLUTTERWAVE_SECRET_KEY = env("FLUTTERWAVE_SECRET_KEY", "")
FLUTTERWAVE_WEBHOOK_HASH = env("FLUTTERWAVE_WEBHOOK_HASH", "")
SMS_PROVIDER = env("SMS_PROVIDER", "console")  # "arkesel" in production
ARKESEL_API_KEY = env("ARKESEL_API_KEY", "")
ARKESEL_BASE_URL = env("ARKESEL_BASE_URL", "https://sms.arkesel.com")
SMS_DEFAULT_SENDER_ID = env("SMS_DEFAULT_SENDER_ID", "NexEdu")
WHATSAPP_PROVIDER = env("WHATSAPP_PROVIDER", "console")  # "cloud" in production
WHATSAPP_TOKEN = env("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_API_VERSION = env("WHATSAPP_API_VERSION", "v23.0")
WHATSAPP_TEMPLATE_NAME = env("WHATSAPP_TEMPLATE_NAME", "nexedu_notice")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Nex Edu <no-reply@nexedu.com.gh>")

# ---------------------------------------------------------------------------
# Files: local disk in development, S3 (SSE-KMS, presigned URLs) in production
# ---------------------------------------------------------------------------
MEDIA_ROOT = BASE_DIR / "var" / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES

# ---------------------------------------------------------------------------
# I18N, static files, logging
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Accra"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "var" / "static"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_context": {"()": "core.logging.RequestContextFilter"}},
    "formatters": {"json": {"()": "core.logging.JsonFormatter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_context"],
        }
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
