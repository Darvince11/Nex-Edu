"""Local stack from docker-compose.yml: real PostgreSQL school databases, Valkey, Mailpit.

Exercises the production code paths (PostgresProvisioner, per-school roles,
PgBouncer-style settings) without AWS. TLS is relaxed because it's all local.
"""

import os

from .dev import *  # noqa: F403

os.environ.setdefault("DB_SSLMODE", "disable")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "control_plane",
        "USER": "nexedu",
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "nexedu-local-only"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": "5432",
        "CONN_MAX_AGE": 0,
    }
}
TENANT_PROVISIONER = "control_plane.provisioning.postgres.PostgresProvisioner"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("VALKEY_URL", "redis://localhost:6379/0"),
    }
}
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {"host": os.environ.get("SMTP_HOST", "localhost"), "port": 1025},
    }
}
