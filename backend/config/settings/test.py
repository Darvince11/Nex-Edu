"""Test settings. Each test gets its own temporary school databases."""

from .dev import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
TASKS_IN_THREADS = False  # deterministic: tasks run in the test's own thread
CELERY_TASK_EAGER_PROPAGATES = True
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}  # noqa: F405
MEDIA_ROOT = BASE_DIR / "var" / "test-media"  # noqa: F405
LOGGING = {"version": 1, "disable_existing_loggers": False}
