from __future__ import annotations

from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from control_plane.models import Role
from core.passwords import BreachedPasswordValidator


def test_health_check_bypasses_host_validation(client: Client):
    response = client.get("/healthz", HTTP_HOST="10.0.0.12")
    assert response.status_code == 200


@pytest.mark.django_db
def test_security_headers(client: Client):
    response = client.get("/api/v1/me/")
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
    assert "camera=()" in response["Permissions-Policy"]
    assert response["X-Request-ID"]


@pytest.mark.django_db
def test_me_lists_only_active_memberships(tenant, other_tenant, make_member, api):
    from control_plane.models import Membership

    user = make_member(tenant, Role.TEACHER, Role.FORM_TEACHER)
    Membership.objects.create(user=user, tenant=other_tenant, role=Role.PARENT, is_active=False)
    data = api(user, None).get("/api/v1/me/").data
    assert data["mfa_enrolled"] is True
    assert data["schools"] == [
        {"slug": "greenfield", "name": "Greenfield", "roles": ["form_teacher", "teacher"]}
    ]


def test_breached_passwords_are_rejected(settings):
    settings.BREACHED_PASSWORD_CHECK_ENABLED = True
    with mock.patch("core.passwords.breach_count", return_value=12):
        with pytest.raises(ValidationError):
            BreachedPasswordValidator().validate("password123456")
    with mock.patch("core.passwords.breach_count", return_value=None):
        BreachedPasswordValidator().validate("unreachable-service-fails-open")


@pytest.mark.django_db
def test_public_signup_is_closed(client: Client):
    response = client.post(
        "/_allauth/browser/v1/auth/signup",
        {"email": "new@example.test", "password": "a-long-unique-password-77"},
        content_type="application/json",
    )
    assert response.status_code == 403


def test_tenant_task_requires_explicit_school(tenant):
    from celery import shared_task

    from control_plane.tenancy import get_current_tenant
    from core.tasks import TenantTask

    @shared_task(base=TenantTask, name="tests.which_school")
    def which_school():
        return get_current_tenant().slug

    assert which_school.apply(kwargs={"tenant_slug": "greenfield"}).get() == "greenfield"
    with pytest.raises(ValueError, match="requires tenant_slug"):
        which_school.apply().get()
