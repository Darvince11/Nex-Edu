"""Production on AWS: Aurora PostgreSQL, Valkey, SQS, Secrets Manager, KMS.

Every secret comes from the environment, which ECS injects from Secrets Manager.
"""

from .base import *  # noqa: F403
from .base import env, env_list

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("CONTROL_DB_NAME", "control_plane"),
        "USER": env("CONTROL_DB_USER", required=True),
        "PASSWORD": env("CONTROL_DB_PASSWORD", required=True),
        "HOST": env("CONTROL_DB_HOST", required=True),  # PgBouncer endpoint
        "PORT": env("CONTROL_DB_PORT", "6432"),
        "CONN_MAX_AGE": 0,
        # Required behind PgBouncer in transaction-pooling mode.
        "DISABLE_SERVER_SIDE_CURSORS": True,
        "OPTIONS": {
            "sslmode": "verify-full",
            # The app reaches the control plane through PgBouncer (internal CA).
            "sslrootcert": env("POOLER_SSL_ROOT_CERT", "/etc/ssl/certs/nexedu-internal-ca.pem"),
        },
    }
}

TENANT_PROVISIONER = "control_plane.provisioning.postgres.PostgresProvisioner"
TENANT_SECRETS_BACKEND = "control_plane.secrets.AwsSecretsManagerBackend"
TENANT_SECRETS_PREFIX = env("TENANT_SECRETS_PREFIX", "nexedu/prod/tenants/")
FIELD_ENCRYPTION_KEY_PROVIDER = "core.crypto.KmsKeyProvider"
FIELD_ENCRYPTION_KMS_KEY_ID = env("FIELD_ENCRYPTION_KMS_KEY_ID", required=True)
FIELD_ENCRYPTION_LOCAL_MASTER_KEY = ""
HEADLESS_JWT_PRIVATE_KEY = env("HEADLESS_JWT_PRIVATE_KEY", required=True)

VALKEY_URL = env("VALKEY_URL", required=True)  # rediss:// (TLS) URL
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": VALKEY_URL,
        "KEY_PREFIX": "nexedu",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cache"

CELERY_BROKER_URL = "sqs://"
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "region": env("AWS_REGION", "af-south-1"),
    "predefined_queues": {
        name: {"url": env(f"SQS_QUEUE_URL_{name.upper().replace('-', '_')}", required=True)}
        for name in ("default", "critical-payments", "notifications", "reports")
    },
}

# CloudFront -> ALB -> app. The client IP is the second entry from the right.
TRUSTED_PROXY_COUNT = 2
# The control-plane console lives in the web app; Django admin is off in production.
ADMIN_ENABLED = False

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 63072000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_DOMAIN = env("SESSION_COOKIE_DOMAIN", "") or None
CSRF_COOKIE_DOMAIN = SESSION_COOKIE_DOMAIN

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("FILES_BUCKET", required=True),
            "region_name": env("AWS_REGION", "af-south-1"),
            "default_acl": None,
            "querystring_auth": True,  # downloads are presigned, short-lived URLs
            "querystring_expire": 300,
            "file_overwrite": True,
            "object_parameters": {"ServerSideEncryption": "aws:kms"},
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
SMS_PROVIDER = "arkesel"
WHATSAPP_PROVIDER = env("WHATSAPP_PROVIDER", "cloud")

# Amazon SES over SMTP with STARTTLS.
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": env("EMAIL_HOST", "email-smtp.af-south-1.amazonaws.com"),
            "port": 587,
            "use_tls": True,
            "username": env("EMAIL_HOST_USER", ""),
            "password": env("EMAIL_HOST_PASSWORD", ""),
            "timeout": 10,
        },
    }
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "no-reply@nexedu.com.gh")
