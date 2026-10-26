"""School registration: a verified owner asks, platform staff decide, access follows approval."""

from __future__ import annotations

from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.core.management import CommandError, call_command

from control_plane.audit import verify_platform_chain
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
from control_plane.tenancy import tenant_context

URL = "/api/v1/registrations/"
FORM = {
    "school_name": "Sunrise Academy",
    "slug": "sunrise",
    "school_type": "primary",
    "region": "ashanti",
    "town": "Kumasi",
    "phone": "024 412 3456",
    "expected_pupils": 320,
}


def owner(email: str = "owner@example.test", *, verified: bool = True) -> User:
    user = User.objects.create_user(email, "a-long-owner-password-1", first_name="Esi")
    EmailAddress.objects.create(user=user, email=email, verified=verified, primary=True)
    return user


def submit(api: Any, user: User, **overrides: Any) -> Any:
    return api(user, None).post(URL, {**FORM, **overrides}, format="json")


@pytest.fixture
def staff_reviewer(db: None) -> User:
    user = User.objects.create_user("reviewer@nexedu.test", "a-long-staff-password-1")
    PlatformStaff.objects.create(user=user, role=PlatformRole.SUPER_ADMIN)
    return user


@pytest.mark.django_db
def test_an_unverified_email_cannot_ask_for_a_school(api):
    response = submit(api, owner(verified=False))
    assert response.status_code == 403
    assert response.data["code"] == "email_unverified"
    assert not SchoolRegistration.objects.exists()


@pytest.mark.django_db
def test_a_verified_owner_submits_one_request_for_review(api):
    user = owner()
    response = submit(api, user)
    assert response.status_code == 201, response.content
    assert response.data["status"] == "pending"
    assert response.data["phone"] == "+233244123456"
    assert "possible_duplicate" not in response.data
    assert Membership.objects.filter(user=user).count() == 0  # nothing granted yet

    again = submit(api, user, slug="sunrise-two")
    assert again.status_code == 400
    assert SchoolRegistration.objects.filter(owner=user).count() == 1
    assert PlatformAuditEvent.objects.filter(action="registration.submitted").count() == 1


@pytest.mark.django_db
def test_owners_see_only_their_own_requests(api):
    first, second = owner("a@example.test"), owner("b@example.test")
    submit(api, first)
    assert api(second, None).get(URL).data == []
    assert [r["slug"] for r in api(first, None).get(URL).data] == ["sunrise"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "slug", ["admin", "www", "Sunrise!", "ab", "greenfield", "-bad"], ids=lambda s: s or "blank"
)
def test_unusable_web_addresses_are_refused(api, tenant, slug):
    response = submit(api, owner(), slug=slug)
    assert response.status_code == 400
    assert "slug" in response.data
    check = api(owner("checker@example.test"), None).get(
        "/api/v1/registrations/slug-check/", {"slug": slug}
    )
    assert check.data["available"] is False


@pytest.mark.django_db
def test_a_pending_request_holds_its_web_address(api):
    submit(api, owner("a@example.test"))
    assert submit(api, owner("b@example.test")).status_code == 400
    free = api(owner("c@example.test"), None).get(
        "/api/v1/registrations/slug-check/", {"slug": "moonlight"}
    )
    assert free.data == {"available": True, "reason": ""}


@pytest.mark.django_db
def test_bad_phone_numbers_and_sizes_are_refused(api):
    user = owner()
    assert submit(api, user, phone="12345").status_code == 400
    assert submit(api, user, expected_pupils=0).status_code == 400
    assert submit(api, user, region="lagos").status_code == 400
    assert not SchoolRegistration.objects.exists()


@pytest.mark.django_db
def test_lookalike_names_are_flagged_for_reviewers_only(api, tenant):
    response = submit(api, owner(), school_name="greenfield", slug="greenfield-two")
    assert response.status_code == 201
    assert SchoolRegistration.objects.get().possible_duplicate is True
    assert "possible_duplicate" not in response.data


@pytest.mark.django_db
@pytest.mark.usefixtures("_allow_tenant_databases")
def test_approval_creates_the_school_and_then_the_owner(api, staff_reviewer):
    from apps.academics.models import ClassLevel
    from apps.school.models import SchoolProfile

    user = owner()
    registration_id = submit(api, user).data["id"]
    call_command(
        "review_registration", "--approve", registration_id, "--reviewer", staff_reviewer.email
    )

    registration = SchoolRegistration.objects.get(pk=registration_id)
    tenant = Tenant.objects.get(slug="sunrise")
    assert (registration.status, registration.tenant, registration.reviewed_by) == (
        "approved",
        tenant,
        staff_reviewer,
    )
    assert tenant.status == Tenant.Status.ACTIVE
    assert Membership.objects.filter(user=user, tenant=tenant, role=Role.OWNER).exists()
    with tenant_context(tenant):
        offered = set(ClassLevel.objects.filter(is_active=True).values_list("section", flat=True))
        assert offered == {"kg", "lower_primary", "upper_primary"}  # "primary": no JHS
        assert SchoolProfile.load().phone == "+233244123456"
    assert mail.outbox[-1].to == [user.email]
    assert "ready on Nex Edu" in mail.outbox[-1].subject
    assert api(user, None).get(URL).data[0]["school_slug"] == "sunrise"

    # The new owner can open their school straight away; an authenticator app is optional.
    assert api(user, tenant).get("/api/v1/students/").status_code == 200

    with pytest.raises(CommandError):
        call_command("review_registration", "--approve", registration_id)
    assert verify_platform_chain().valid


@pytest.mark.django_db
def test_rejection_needs_a_reason_and_grants_nothing(api, staff_reviewer):
    user = owner()
    registration_id = submit(api, user).data["id"]
    with pytest.raises(CommandError):
        call_command("review_registration", "--reject", registration_id)
    call_command(
        "review_registration",
        "--reject",
        registration_id,
        "--reviewer",
        staff_reviewer.email,
        "--note",
        "We couldn't confirm the school's GES registration.",
    )
    data = api(user, None).get(URL).data[0]
    assert data["status"] == "rejected"
    assert data["decision_note"] == "We couldn't confirm the school's GES registration."
    assert not Membership.objects.filter(user=user).exists()
    assert not Tenant.objects.filter(slug="sunrise").exists()
    assert "couldn't confirm" in mail.outbox[-1].body
    # A rejected owner may apply again.
    assert submit(api, user, slug="sunrise-academy").status_code == 201


@pytest.mark.django_db
def test_only_platform_staff_can_be_named_as_reviewer(api):
    registration_id = submit(api, owner()).data["id"]
    outsider = User.objects.create_user("random@example.test", "a-long-password-123")
    with pytest.raises(CommandError, match="not active platform staff"):
        call_command(
            "review_registration", "--approve", registration_id, "--reviewer", outsider.email
        )
    assert SchoolRegistration.objects.get(pk=registration_id).status == "pending"


@pytest.mark.django_db
def test_failed_setup_leaves_no_owner_access(api, monkeypatch):
    import control_plane.registrations as registrations

    def broken(**kwargs: Any) -> Tenant:
        raise RuntimeError("database server unavailable")

    monkeypatch.setattr(registrations, "provision_tenant", broken)
    user = owner()
    registration_id = submit(api, user).data["id"]
    with pytest.raises(RuntimeError):
        call_command("review_registration", "--approve", registration_id)
    assert SchoolRegistration.objects.get(pk=registration_id).status == "failed"
    assert not Membership.objects.filter(user=user).exists()
    assert PlatformAuditEvent.objects.filter(action="registration.failed").exists()


@pytest.mark.django_db
def test_submissions_are_rate_limited(api):
    user = owner()
    statuses = [submit(api, user, slug=f"school-{n}").status_code for n in range(11)]
    assert statuses[0] == 201
    assert statuses[-1] == 429


@pytest.mark.django_db
def test_a_school_being_set_up_still_blocks_a_second_request_and_holds_its_address(api):
    user = owner()
    registration_id = submit(api, user).data["id"]
    SchoolRegistration.objects.filter(pk=registration_id).update(status="provisioning")
    assert submit(api, user, slug="sunrise-two").status_code == 400
    assert submit(api, owner("other@example.test")).status_code == 400  # "sunrise" is held
