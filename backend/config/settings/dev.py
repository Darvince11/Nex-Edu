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

MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = True
BREACHED_PASSWORD_CHECK_ENABLED = False
CELERY_TASK_ALWAYS_EAGER = True
