"""Super Admin review of school registrations through the API."""

from __future__ import annotations

from typing import Any

import pytest
from allauth.account.models import EmailAddress

from control_plane.models import (
    Membership,
    PlatformAuditEvent,
    PlatformRole,
    PlatformStaff,
    Role,
    SchoolRegistration,
    Tenant,
    User,
)

LIST = "/api/v1/platform/registrations/"
FORM = {
    "school_name": "Sunrise Academy",
    "slug": "sunrise",
    "school_type": "basic",
    "region": "volta",
    "town": "Ho",
    "phone": "0244123456",
    "expected_pupils": 210,
}


def staff(role: str, *, mfa: bool = True, make_member: Any, tenant: Tenant) -> User:
    user = make_member(tenant, mfa=mfa)  # no school roles
    PlatformStaff.objects.create(user=user, role=role)
    return user


def pending(api: Any, email: str = "owner@example.test", **overrides: Any) -> SchoolRegistration:
    owner = User.objects.create_user(email, "a-long-owner-password-1", first_name="Esi")
    EmailAddress.objects.create(user=owner, email=email, verified=True, primary=True)
    response = api(owner, None).post("/api/v1/registrations/", {**FORM, **overrides}, format="json")
    assert response.status_code == 201, response.content
    return SchoolRegistration.objects.get(pk=response.data["id"])


@pytest.mark.django_db
def test_support_and_super_admins_see_the_queue_with_reviewer_details(tenant, make_member, api):
    registration = pending(api, school_name="Greenfield", slug="greenfield-two")
    for role in (PlatformRole.SUPPORT, PlatformRole.SUPER_ADMIN):
        reviewer = staff(role, make_member=make_member, tenant=tenant)
        response = api(reviewer, None).get(LIST, {"status": "pending"})
        assert response.status_code == 200, response.content
        row = response.data["results"][0]
        assert row["id"] == str(registration.pk)
        assert row["possible_duplicate"] is True
        assert row["owner_email"] == "owner@example.test"
        assert row["region_label"] == "Volta"
        detail = api(reviewer, None).get(f"{LIST}{registration.pk}/")
        assert detail.data["owner_name"] == "Esi"


@pytest.mark.django_db
def test_others_cannot_see_the_queue(tenant, make_member, api, settings):
    pending(api)
    billing = staff(PlatformRole.BILLING, make_member=make_member, tenant=tenant)
    owner = make_member(tenant, Role.OWNER)
    root = User.objects.create_superuser("root@example.test", "x" * 16)
    for user in (billing, owner, root, None):
        assert api(user, None).get(LIST).status_code in (401, 403)
    # A super admin without an authenticator app gets in unless the deployment requires one.
    no_mfa = staff(PlatformRole.SUPER_ADMIN, mfa=False, make_member=make_member, tenant=tenant)
    assert api(no_mfa, None).get(LIST).status_code == 200
    settings.PLATFORM_MFA_REQUIRED = True
    assert api(no_mfa, None).get(LIST).status_code == 403


@pytest.mark.django_db
@pytest.mark.usefixtures("_allow_tenant_databases")
def test_a_super_admin_approves_and_set_up_runs_in_the_background(
    tenant, make_member, api, django_capture_on_commit_callbacks
):
    registration = pending(api)
    admin = staff(PlatformRole.SUPER_ADMIN, make_member=make_member, tenant=tenant)
    with django_capture_on_commit_callbacks(execute=False) as queued:
        response = api(admin, None).post(
            f"{LIST}{registration.pk}/approve/", {"note": "Called the school"}, format="json"
        )
    # The request returns at once; nothing is created until the job runs.
    assert response.status_code == 202, response.content
    assert response.data["status"] == "provisioning"
    assert response.data["reviewed_by_email"] == admin.email
    assert not Tenant.objects.filter(slug="sunrise").exists()
    assert len(queued) == 1

    again = api(admin, None).post(f"{LIST}{registration.pk}/approve/", {}, format="json")
    assert again.status_code == 400  # already being set up

    queued[0]()  # the background job
    detail = api(admin, None).get(f"{LIST}{registration.pk}/").data
    assert detail["status"] == "approved"
    assert detail["school_slug"] == "sunrise"
    new_school = Tenant.objects.get(slug="sunrise")
    assert Membership.objects.filter(
        user=registration.owner, tenant=new_school, role=Role.OWNER
    ).exists()
    event = PlatformAuditEvent.objects.get(action="registration.approved")
    assert event.actor_id == admin.pk


@pytest.mark.django_db
@pytest.mark.usefixtures("_allow_tenant_databases")
def test_running_the_set_up_job_twice_does_nothing_more(tenant, make_member, api):
    from control_plane.registrations import complete_approval, start_approval

    registration = pending(api)
    admin = staff(PlatformRole.SUPER_ADMIN, make_member=make_member, tenant=tenant)
    start_approval(registration, reviewer=admin)
    assert complete_approval(registration.pk) is not None
    assert complete_approval(registration.pk) is None
    assert Tenant.objects.filter(slug="sunrise").count() == 1
    assert Membership.objects.filter(user=registration.owner).count() == 1


@pytest.mark.django_db
def test_support_staff_can_look_but_not_decide(tenant, make_member, api):
    registration = pending(api)
    support = staff(PlatformRole.SUPPORT, make_member=make_member, tenant=tenant)
    for action in ("approve", "reject"):
        response = api(support, None).post(
            f"{LIST}{registration.pk}/{action}/", {"note": "x"}, format="json"
        )
        assert response.status_code == 403
    registration.refresh_from_db()
    assert registration.status == "pending"


@pytest.mark.django_db
def test_rejection_needs_a_reason(tenant, make_member, api):
    registration = pending(api)
    admin = staff(PlatformRole.SUPER_ADMIN, make_member=make_member, tenant=tenant)
    blank = api(admin, None).post(f"{LIST}{registration.pk}/reject/", {"note": "  "}, format="json")
    assert blank.status_code == 400
    assert "note" in blank.data
    ok = api(admin, None).post(
        f"{LIST}{registration.pk}/reject/",
        {"note": "We couldn't confirm the school's details."},
        format="json",
    )
    assert ok.status_code == 200
    assert ok.data["status"] == "rejected"
    assert not Tenant.objects.filter(slug="sunrise").exists()


@pytest.mark.django_db
def test_nobody_reviews_their_own_registration(tenant, make_member, api):
    admin = staff(PlatformRole.SUPER_ADMIN, make_member=make_member, tenant=tenant)
    EmailAddress.objects.create(user=admin, email=admin.email, verified=True, primary=True)
    submitted = api(admin, None).post("/api/v1/registrations/", FORM, format="json")
    assert submitted.status_code == 201
    response = api(admin, None).post(f"{LIST}{submitted.data['id']}/approve/", {}, format="json")
    assert response.status_code == 400
    assert not Tenant.objects.filter(slug="sunrise").exists()


@pytest.mark.django_db
def test_setup_failure_is_reported_and_grants_nothing(
    tenant, make_member, api, monkeypatch, django_capture_on_commit_callbacks
):
    import control_plane.registrations as registrations

    def broken(**kwargs: Any) -> Tenant:
        raise RuntimeError("database server unavailable")

    monkeypatch.setattr(registrations, "provision_tenant", broken)
    registration = pending(api)
    admin = staff(PlatformRole.SUPER_ADMIN, make_member=make_member, tenant=tenant)
    with django_capture_on_commit_callbacks(execute=True):
        response = api(admin, None).post(f"{LIST}{registration.pk}/approve/", {}, format="json")
    assert response.status_code == 202
    detail = api(admin, None).get(f"{LIST}{registration.pk}/").data
    assert detail["status"] == "failed"
    assert "database server" not in str(detail)  # internals stay in the logs
    assert not Membership.objects.filter(user=registration.owner).exists()
    assert PlatformAuditEvent.objects.filter(action="registration.failed").exists()
