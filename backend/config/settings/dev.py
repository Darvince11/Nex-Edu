"""Local development: SQLite control plane, SQLite school databases, no TLS."""

from .base import *  # noqa: F403
from .base import BASE_DIR

DEBUG = True
(BASE_DIR / "var" / "tenants").mkdir(parents=True, exist_ok=True)

# A throwaway RSA key is generated per process so JWT login works out of the box.
if not HEADLESS_JWT_PRIVATE_KEY:  # noqa: F405
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    _key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    HEADLESS_JWT_PRIVATE_KEY = _key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

# The web app proxies the API from its own origin. Browsers send that origin on
# every POST, so Django must trust it or CSRF checks reject sign-in.
_LOCAL_WEB = [
    "http://localhost:3000",
    "http://localhost:3100",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3100",
]
CSRF_TRUSTED_ORIGINS = sorted({*CSRF_TRUSTED_ORIGINS, *_LOCAL_WEB})  # noqa: F405
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:3100")  # noqa: F405
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/account/verify-email/{{key}}",
    "account_reset_password_from_key": f"{FRONTEND_URL}/account/password/reset/{{key}}",
    "account_signup": f"{FRONTEND_URL}/signup",
    "account_reset_password": f"{FRONTEND_URL}/forgot-password",
}

MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}
BREACHED_PASSWORD_CHECK_ENABLED = False
CELERY_TASK_ALWAYS_EAGER = True
# No worker locally: long tasks (school set-up) run on a thread, not inside the request.
TASKS_IN_THREADS = True
