"""Browser (Playwright) tests: the dev stack on throwaway data under var/e2e.

The web app under test runs on port 3200 and the API on 8100, so a normal dev
session on 3100/8000 keeps running alongside. Emails are written to files so
tests can read verification codes (web/e2e/mail.ts).
"""

from .dev import *  # noqa: F403
from .dev import BASE_DIR, CSRF_TRUSTED_ORIGINS, DATABASES

E2E_DIR = BASE_DIR / "var" / "e2e"
(E2E_DIR / "tenants").mkdir(parents=True, exist_ok=True)

DATABASES = {"default": {**DATABASES["default"], "NAME": E2E_DIR / "control_plane.sqlite3"}}
TENANT_SQLITE_DIR = E2E_DIR / "tenants"
TENANT_SECRETS_FILE = E2E_DIR / "secrets.json"
MEDIA_ROOT = E2E_DIR / "media"

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.filebased.EmailBackend",
        "OPTIONS": {"file_path": str(E2E_DIR / "mail")},
    }
}

FRONTEND_URL = "http://localhost:3200"
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/account/verify-email/{{key}}",
    "account_reset_password_from_key": f"{FRONTEND_URL}/account/password/reset/{{key}}",
    "account_signup": f"{FRONTEND_URL}/signup",
    "account_reset_password": f"{FRONTEND_URL}/forgot-password",
}
CSRF_TRUSTED_ORIGINS = sorted(
    {*CSRF_TRUSTED_ORIGINS, "http://localhost:3200", "http://127.0.0.1:3200"}
)
