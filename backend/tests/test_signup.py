"""Self-service sign-up: consent, password rules, bots, enumeration, email codes, audit.

Uses the same headless browser endpoints, CSRF token and Origin check as the web app.
"""

from __future__ import annotations

import re
from typing import Any
from unittest import mock

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.test import Client

from control_plane.audit import verify_platform_chain
from control_plane.models import PlatformAuditEvent, User

ORIGIN = "http://localhost:3100"
PASSWORD = "Kente-cloth-river-42"
CODE = re.compile(r"^[A-Z]{4}-[A-Z]{4}$", re.MULTILINE)


class Browser:
    """A browser talking to allauth's headless API with CSRF and Origin, like the web app."""

    def __init__(self) -> None:
        self.client = Client(enforce_csrf_checks=True, HTTP_HOST="127.0.0.1:8000")
        self.client.get("/_allauth/browser/v1/auth/session")

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self.client.post(
            f"/_allauth/browser/v1{path}",
            body,
            content_type="application/json",
            HTTP_ORIGIN=ORIGIN,
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )

    def signup(self, **overrides: Any) -> Any:
        body = {
            "email": "akua@example.test",
            "password": PASSWORD,
            "first_name": "Akua",
            "last_name": "Boateng",
            "accept_terms": True,
            **overrides,
        }
        return self.post("/auth/signup", {k: v for k, v in body.items() if v is not None})


def pending_flow(response: Any) -> str | None:
    flows = response.json().get("data", {}).get("flows", [])
    return next((f["id"] for f in flows if f.get("is_pending")), None)


def last_code() -> str:
    match = CODE.search(mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match.group(0)


@pytest.mark.django_db
def test_signup_records_consent_and_waits_for_the_email_code(settings):
    browser = Browser()
    response = browser.signup()
    assert response.status_code == 401, response.content
    assert pending_flow(response) == "verify_email"

    user = User.objects.get(email="akua@example.test")
    assert (user.first_name, user.last_name) == ("Akua", "Boateng")
    assert user.terms_version == settings.TERMS_VERSION
    assert user.terms_accepted_at is not None
    assert mail.outbox[-1].subject == "Your Nex Edu verification code"
    assert "never ask you for this code" in mail.outbox[-1].body

    verified = browser.post("/auth/email/verify", {"key": last_code()})
    assert verified.status_code == 200, verified.content
    assert verified.json()["meta"]["is_authenticated"] is True
    assert EmailAddress.objects.get(user=user).verified


@pytest.mark.django_db
def test_a_new_account_opens_no_school(tenant):
    browser = Browser()
    browser.signup()
    browser.post("/auth/email/verify", {"key": last_code()})

    me = browser.client.get("/api/v1/me/")
    assert me.status_code == 200
    assert me.json()["schools"] == []
    students = browser.client.get("/api/v1/students/", HTTP_X_TENANT=tenant.slug)
    assert students.status_code == 403


@pytest.mark.django_db
def test_code_can_be_typed_without_the_dash_or_in_lower_case():
    browser = Browser()
    browser.signup()
    typed = last_code().replace("-", "").lower()
    assert browser.post("/auth/email/verify", {"key": typed}).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        {"accept_terms": None},
        {"accept_terms": False},
        {"first_name": "Visit www.cheap-pills.example"},
        {"last_name": "<script>"},
        {"first_name": "   "},
        {"password": "short"},
        {"password": "123456789012345"},
        {"password": "password12345"},
        {"email": "not-an-email"},
    ],
    ids=[
        "no consent",
        "consent refused",
        "link in name",
        "markup in name",
        "blank name",
        "too short",
        "all digits",
        "common password",
        "bad email",
    ],
)
def test_invalid_signups_create_nothing(overrides):
    response = Browser().signup(**overrides)
    assert response.status_code == 400, response.content
    assert not User.objects.exists()
    assert not mail.outbox


@pytest.mark.django_db
def test_breached_passwords_are_refused(settings):
    settings.BREACHED_PASSWORD_CHECK_ENABLED = True
    with mock.patch("core.passwords.breach_count", return_value=31_337):
        response = Browser().signup()
    assert response.status_code == 400
    assert not User.objects.exists()


@pytest.mark.django_db
def test_bots_filling_the_honeypot_create_nothing_and_send_nothing():
    response = Browser().signup(website="http://spam.example")
    assert response.status_code == 400
    assert not User.objects.exists()
    assert not mail.outbox  # never an email to a bot-chosen address


@pytest.mark.django_db
def test_signing_up_with_a_taken_email_reveals_nothing():
    existing = User.objects.create_user("akua@example.test", "an-old-password-1")
    EmailAddress.objects.create(user=existing, email=existing.email, verified=True, primary=True)

    response = Browser().signup()
    fresh = Browser().signup(email="someone-new@example.test")
    assert response.status_code == fresh.status_code == 401
    assert pending_flow(response) == pending_flow(fresh) == "verify_email"
    assert User.objects.filter(email="akua@example.test").count() == 1
    assert existing.first_name == ""  # untouched
    owner_mail = [m for m in mail.outbox if m.to == ["akua@example.test"]]
    assert owner_mail[-1].subject.startswith("Someone tried to create a Nex Edu account")


@pytest.mark.django_db
def test_three_wrong_codes_end_the_verification():
    browser = Browser()
    browser.signup()
    code = last_code()
    for _ in range(3):
        assert browser.post("/auth/email/verify", {"key": "BBBB-BBBB"}).status_code == 400
    late = browser.post("/auth/email/verify", {"key": code})
    assert late.status_code != 200
    assert not EmailAddress.objects.filter(verified=True).exists()


@pytest.mark.django_db
def test_signups_are_rate_limited_per_ip():
    statuses = [Browser().signup(email=f"user{n}@example.test").status_code for n in range(6)]
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429


@pytest.mark.django_db
def test_sign_in_needs_the_verified_email_first():
    from django.core.cache import cache

    browser = Browser()
    browser.signup()
    cache.clear()  # a minute later: the one-code-per-minute resend limit has passed
    other = Browser()
    response = other.post("/auth/login", {"email": "akua@example.test", "password": PASSWORD})
    assert response.status_code == 401
    assert pending_flow(response) == "verify_email"


@pytest.mark.django_db
def test_wrong_passwords_get_the_same_answer_for_known_and_unknown_emails():
    User.objects.create_user("known@example.test", PASSWORD)
    known = Browser().post(
        "/auth/login", {"email": "known@example.test", "password": "wrong-pass-1"}
    )
    unknown = Browser().post(
        "/auth/login", {"email": "nobody@example.test", "password": "wrong-pass-1"}
    )
    assert known.status_code == unknown.status_code == 400
    assert known.json()["errors"][0]["message"] == unknown.json()["errors"][0]["message"]


@pytest.mark.django_db
def test_security_events_are_audited_without_secrets():
    browser = Browser()
    browser.signup()
    browser.post("/auth/email/verify", {"key": last_code()})
    Browser().post("/auth/login", {"email": "akua@example.test", "password": "a-wrong-password"})

    actions = list(PlatformAuditEvent.objects.order_by("seq").values_list("action", flat=True))
    assert "auth.signed_up" in actions
    assert "auth.email_verified" in actions
    assert "auth.signed_in" in actions
    failed = PlatformAuditEvent.objects.get(action="auth.sign_in_failed")
    assert failed.data == {"email": "akua@example.test"}
    assert failed.ip
    for event in PlatformAuditEvent.objects.all():
        assert PASSWORD not in str(event.data) and "a-wrong-password" not in str(event.data)
    assert verify_platform_chain().valid
