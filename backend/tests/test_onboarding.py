"""Getting a new school ready: the set-up checklist, failed set-ups cleaned up
and retried, stuck set-ups swept, and new schools copied from a template."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from apps.academics.models import TeachingAssignment
from apps.finance.models import FeeItem, FeeSchedule
from apps.school.models import SchoolProfile
from control_plane.models import (
    PlatformAuditEvent,
    PlatformRole,
    PlatformStaff,
    Role,
    SchoolRegistration,
    Tenant,
)
from control_plane.provisioning.service import provision_tenant
from control_plane.registrations import start_approval, sweep_stuck_setups
from control_plane.secrets import SecretNotFound, get_secrets_backend
from control_plane.tenancy import tenant_context
from control_plane.usage import collect
from tests.test_platform_registrations import pending

URL = "/api/v1/school/setup/"
pytestmark = pytest.mark.django_db


def steps(response):
    return {s["key"]: s for s in response.data["steps"]}


def test_checklist_starts_mostly_open_and_ticks_itself_off(campus, make_member, make_student, api):
    owner_user = make_member(campus.tenant, Role.OWNER)
    owner = api(owner_user, campus.tenant)
    first = owner.get(URL)
    assert first.status_code == 200
    assert [s["label"] for s in first.data["steps"]] == [
        "Complete the school profile",
        "Add the school logo",
        "Accept the terms for the school",
        "Choose your modules",
        "Set the academic year and current term",
        "Set this term's fees",
        "Add staff",
        "Assign class teachers",
        "Add pupils",
        "Invite parents",
    ]
    assert steps(first)["year"]["done"] is True  # the campus fixture has a current term
    assert steps(first)["staff"]["done"] is False

    teacher = make_member(campus.tenant, Role.FORM_TEACHER)
    make_member(campus.tenant, Role.PARENT, mfa=False)
    make_student(campus.tenant, arm=campus.jhs1)
    with tenant_context(campus.tenant):
        TeachingAssignment.objects.create(
            teacher_user_id=teacher.pk, arm=campus.jhs1, is_form_teacher=True
        )
        FeeSchedule.objects.create(
            term=campus.term, item=FeeItem.objects.create(name="Tuition"), amount_pesewas=100_000
        )
        profile = SchoolProfile.load()
        profile.address, profile.phone, profile.principal_name = "Kumasi", "0244123456", "Mrs Ofori"
        profile.save()
    later = steps(owner.get(URL))
    for key in ("profile", "fees", "staff", "class_teachers", "pupils", "parents"):
        assert later[key]["done"] is True, key
    assert later["logo"]["done"] is False and later["terms"]["done"] is False


def test_only_the_proprietor_accepts_the_terms_for_the_school(campus, make_member, api):
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    data = head.get(URL).data
    assert steps_from(data)["terms"]["can_do"] is False
    assert steps_from(data)["terms"]["who"] == "Proprietor"
    assert head.post(URL, {"action": "accept_terms"}, format="json").status_code == 403

    owner_user = make_member(campus.tenant, Role.OWNER, email="esther@greenfield.test")
    accepted = api(owner_user, campus.tenant).post(URL, {"action": "accept_terms"}, format="json")
    assert accepted.status_code == 200
    assert steps_from(accepted.data)["terms"]["done"] is True
    assert accepted.data["terms_accepted_by"] == "esther@greenfield.test"
    assert accepted.data["terms_version"] == settings.TERMS_VERSION
    # The profile form can't set it.
    api(owner_user, campus.tenant).patch(
        "/api/v1/school/profile/", {"terms_accepted_by": "someone@else.test"}, format="json"
    )
    with tenant_context(campus.tenant):
        assert SchoolProfile.load().terms_accepted_by == "esther@greenfield.test"


def steps_from(data):
    return {s["key"]: s for s in data["steps"]}


def test_leaders_can_hide_and_show_the_checklist_and_others_cannot_see_it(campus, make_member, api):
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    assert admin.post(URL, {"action": "hide"}, format="json").data["hidden"] is True
    assert admin.post(URL, {"action": "show"}, format="json").data["hidden"] is False
    teacher = api(make_member(campus.tenant, Role.TEACHER), campus.tenant)
    assert teacher.get(URL).status_code == 403


def test_platform_figures_show_set_up_progress_and_flag_slow_schools(campus, make_member):
    Tenant.objects.filter(pk=campus.tenant.pk).update(
        created_at=timezone.now() - dt.timedelta(days=10)
    )
    campus.tenant.refresh_from_db()
    usage = collect(campus.tenant)
    assert usage.setup_total == 10
    assert 0 < usage.setup_done < 10
    assert "Add staff" in usage.setup_left
    from control_plane.usage import attention

    assert any(
        r.startswith("Set-up not finished") for r in attention(campus.tenant, usage, timezone.now())
    )


# --- Failed and stuck set-ups --------------------------------------------------------------


@pytest.mark.usefixtures("_allow_tenant_databases")
def test_a_failed_set_up_leaves_nothing_behind(monkeypatch):
    def broken_seed(name):
        raise RuntimeError("seed failed")

    # A scoped patch: undoing the whole monkeypatch would also undo the fixture
    # that lets tests open school databases.
    with monkeypatch.context() as patch:
        patch.setattr("apps.school.seed.seed_new_school", broken_seed)
        with pytest.raises(RuntimeError, match="seed failed"):
            provision_tenant(slug="brokenschool", name="Broken School")
    assert not Tenant.objects.filter(slug="brokenschool").exists()
    assert not (Path(settings.TENANT_SQLITE_DIR) / "school_brokenschool.sqlite3").exists()
    with pytest.raises(SecretNotFound):
        get_secrets_backend().get(f"{settings.TENANT_SECRETS_PREFIX}brokenschool/db")
    # The same web address can be set up again straight away.
    assert provision_tenant(slug="brokenschool", name="Broken School").status == "active"


@pytest.mark.usefixtures("_allow_tenant_databases")
def test_a_failed_registration_can_be_tried_again(
    tenant, make_member, api, monkeypatch, django_capture_on_commit_callbacks
):
    from control_plane.tasks import provision_registration

    registration = pending(api, school_name="Hillside", slug="hillside")
    admin = make_member(tenant)
    PlatformStaff.objects.create(user=admin, role=PlatformRole.SUPER_ADMIN)
    client = api(admin, None)

    def broken(*args, **kwargs):
        raise RuntimeError("database server unreachable")

    # The background job runs here, in the test's thread.
    with monkeypatch.context() as patch:
        patch.setattr("control_plane.registrations.provision_tenant", broken)
        with django_capture_on_commit_callbacks(execute=False):
            client.post(
                f"/api/v1/platform/registrations/{registration.pk}/approve/", {}, format="json"
            )
        provision_registration(str(registration.pk))
    registration.refresh_from_db()
    assert registration.status == SchoolRegistration.Status.FAILED

    with django_capture_on_commit_callbacks(execute=False):
        retried = client.post(f"/api/v1/platform/registrations/{registration.pk}/retry/")
    assert retried.status_code == 202, retried.content
    provision_registration(str(registration.pk))
    registration.refresh_from_db()
    assert registration.status == SchoolRegistration.Status.APPROVED
    assert registration.tenant.slug == "hillside"
    assert PlatformAuditEvent.objects.filter(action="registration.setup_retried").exists()
    assert (
        client.post(f"/api/v1/platform/registrations/{registration.pk}/retry/").status_code == 400
    )


def test_stuck_set_ups_are_stopped_and_cleaned_up(tenant, api, monkeypatch):
    registration = pending(api, school_name="Stuck School", slug="stuckschool")
    start_approval(registration)
    leftover = Tenant.objects.create(
        slug="stuckschool",
        name="Stuck School",
        db_name="school_stuckschool",
        secret_ref="local/stuckschool/db",
        status=Tenant.Status.PROVISIONING,
    )
    long_ago = timezone.now() - dt.timedelta(hours=1)
    SchoolRegistration.objects.filter(pk=registration.pk).update(reviewed_at=long_ago)
    Tenant.objects.filter(pk=leftover.pk).update(created_at=long_ago)

    assert sweep_stuck_setups() == 2
    registration.refresh_from_db()
    assert registration.status == SchoolRegistration.Status.FAILED
    assert not Tenant.objects.filter(slug="stuckschool").exists()
    assert Tenant.objects.filter(pk=tenant.pk, status="active").exists()  # live schools untouched


def test_live_schools_are_never_discarded(tenant):
    from control_plane.provisioning.service import discard_tenant

    with pytest.raises(ValueError, match="Refusing to discard"):
        discard_tenant(tenant)
    assert Tenant.objects.filter(pk=tenant.pk).exists()


@pytest.mark.usefixtures("_allow_tenant_databases")
def test_new_schools_are_copied_from_a_migrated_template():
    provision_tenant(slug="firstschool", name="First")
    templates = list(Path(settings.TENANT_SQLITE_DIR).glob("_template_*.sqlite3"))
    assert len(templates) == 1
    second = provision_tenant(slug="secondschool", name="Second")
    with tenant_context(second):
        assert SchoolProfile.load().name == "Second"  # its own seed, not the template's
