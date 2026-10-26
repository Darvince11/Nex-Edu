"""Platform (Super Admin) access, platform staff provisioning and the platform audit chain."""

from __future__ import annotations

import pytest
from django.core.management import CommandError, call_command
from django.db import connection
from django.urls import get_resolver

from control_plane.audit import verify_platform_chain
from control_plane.models import PlatformAuditEvent, PlatformRole, PlatformStaff, Role, User
from tests.test_authorization import _iter_views

URL = "/api/v1/platform/tenants/"


def _staff(role: str, *, mfa: bool = True, make_member, tenant) -> User:
    user = make_member(tenant, mfa=mfa)  # no school roles
    PlatformStaff.objects.create(user=user, role=role)
    return user


@pytest.mark.django_db
def test_only_platform_staff_with_the_right_role_see_all_schools(
    tenant, other_tenant, make_member, api
):
    support = _staff(PlatformRole.SUPPORT, make_member=make_member, tenant=tenant)
    response = api(support, None).get(URL)
    assert response.status_code == 200, response.content
    assert {t["slug"] for t in response.data["results"]} == {"greenfield", "royal-heights"}

    billing = _staff(PlatformRole.BILLING, make_member=make_member, tenant=tenant)
    owner = make_member(tenant, Role.OWNER)
    root = User.objects.create_superuser("root@example.test", "x" * 16)
    for user in (billing, owner, root, None):
        assert api(user, None).get(URL).status_code in (401, 403)


@pytest.mark.django_db
def test_platform_staff_get_in_without_an_app_unless_it_is_required(
    tenant, make_member, api, settings
):
    staff = _staff(PlatformRole.SUPER_ADMIN, mfa=False, make_member=make_member, tenant=tenant)
    assert api(staff, None).get(URL).status_code == 200  # optional by default
    settings.PLATFORM_MFA_REQUIRED = True
    response = api(staff, None).get(URL)
    assert response.status_code == 403
    assert response.data["code"] == "mfa_enrollment_required"


@pytest.mark.django_db
def test_deactivated_platform_staff_lose_access(tenant, make_member, api):
    staff = _staff(PlatformRole.SUPER_ADMIN, make_member=make_member, tenant=tenant)
    PlatformStaff.objects.filter(user=staff).update(is_active=False)
    assert api(staff, None).get(URL).status_code == 403


@pytest.mark.django_db
def test_me_reports_platform_roles(tenant, make_member, api):
    staff = _staff(PlatformRole.SUPPORT, make_member=make_member, tenant=tenant)
    assert api(staff, None).get("/api/v1/me/").data["platform_roles"] == ["support"]
    teacher = make_member(tenant, Role.TEACHER)
    assert api(teacher, None).get("/api/v1/me/").data["platform_roles"] == []


@pytest.mark.django_db
def test_add_platform_staff_grants_revokes_and_audits():
    call_command(
        "add_platform_staff", "--email", "Ops@NexEdu.test", "--role", "support", "--reason", "hire"
    )
    staff = PlatformStaff.objects.get(user__email="ops@nexedu.test")
    assert (staff.role, staff.is_active) == ("support", True)
    assert not staff.user.has_usable_password()  # sets one with "Forgot password"

    call_command("add_platform_staff", "--email", "ops@nexedu.test", "--revoke", "--reason", "left")
    staff.refresh_from_db()
    assert staff.is_active is False
    actions = list(PlatformAuditEvent.objects.order_by("seq").values_list("action", "reason"))
    assert actions == [("platform_staff.granted", "hire"), ("platform_staff.revoked", "left")]
    assert verify_platform_chain().valid

    with pytest.raises(CommandError):
        call_command(
            "add_platform_staff", "--email", "nobody@nexedu.test", "--revoke", "--reason", "x"
        )


@pytest.mark.django_db
def test_platform_audit_chain_detects_tampering():
    for n in range(3):
        call_command(
            "add_platform_staff",
            "--email",
            f"s{n}@nexedu.test",
            "--role",
            "billing",
            "--reason",
            "r",
        )
    assert verify_platform_chain().valid
    with pytest.raises(RuntimeError):
        PlatformAuditEvent.objects.filter(seq=2).update(reason="edited")
    # Bypass the ORM guard, as an attacker with database access would.
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE control_plane_platformauditevent SET reason = 'edited' WHERE seq = 2"
        )
    report = verify_platform_chain()
    assert (report.valid, report.first_bad_seq) == (False, 2)


def test_tenant_less_endpoints_are_exactly_the_expected_ones():
    """A view that skips school membership checks must be public (pinned in
    test_authorization) or listed here. Nothing becomes tenant-less by accident."""
    tenant_less = sorted(
        route
        for route, callback in _iter_views(get_resolver())
        if route.startswith("api/v1/")
        and (view := getattr(callback, "view_class", None) or getattr(callback, "cls", None))
        and getattr(view, "tenant_scoped", True) is False
        and not getattr(view, "public_endpoint", False)
    )
    assert tenant_less == [
        # The proprietor's own billing, export and support access: each checks that the
        # signed-in person is the school's owner (they must work while it is suspended).
        "api/v1/account/schools/<slug:slug>/billing/",
        "api/v1/account/schools/<slug:slug>/billing/charges/<str:reference>/",
        "api/v1/account/schools/<slug:slug>/billing/pay/",
        "api/v1/account/schools/<slug:slug>/export/",
        "api/v1/account/schools/<slug:slug>/support/",
        "api/v1/account/schools/<slug:slug>/support/<uuid:pk>/revoke/",
        # Developer API: an API key (one school, read-only scopes) picks the school.
        "api/v1/developer/attendance/",
        "api/v1/developer/classes/",
        "api/v1/developer/invoices/",
        "api/v1/developer/payments/",
        "api/v1/developer/students/",
        "api/v1/me/",
        # A proprietor's own Nex Edu announcements (filtered to the signed-in user).
        "api/v1/nexedu-announcements/",
        "api/v1/nexedu-announcements/<uuid:pk>/read/",
        # Super Admin console: each requires IsPlatformStaff (checked below).
        "api/v1/platform/announcements/",
        "api/v1/platform/announcements/<uuid:pk>/",
        "api/v1/platform/announcements/<uuid:pk>/publish/",
        "api/v1/platform/audit/",
        "api/v1/platform/audit/groups/",
        "api/v1/platform/audit/mine/",
        "api/v1/platform/audit/verify/",
        "api/v1/platform/billing/bands/<slug:code>/",
        "api/v1/platform/billing/invoices/",
        "api/v1/platform/billing/invoices/<uuid:pk>/",
        "api/v1/platform/billing/modules/",
        "api/v1/platform/billing/modules/<slug:code>/",
        "api/v1/platform/billing/payments/",
        "api/v1/platform/billing/pricing/",
        "api/v1/platform/billing/rules/",
        "api/v1/platform/billing/sms-bundles/",
        "api/v1/platform/billing/sms-bundles/<slug:code>/",
        "api/v1/platform/overview/",
        "api/v1/platform/registrations/",
        "api/v1/platform/registrations/<uuid:pk>/",
        "api/v1/platform/registrations/<uuid:pk>/approve/",
        "api/v1/platform/registrations/<uuid:pk>/reject/",
        "api/v1/platform/registrations/<uuid:pk>/retry/",
        "api/v1/platform/system/",
        "api/v1/platform/system/operations/",
        "api/v1/platform/system/problems/",
        "api/v1/platform/system/problems/<int:pk>/",
        "api/v1/platform/system/scan/",
        "api/v1/platform/system/security/",
        "api/v1/platform/tenants/",
        "api/v1/platform/tenants/<slug:slug>/",
        "api/v1/platform/tenants/<slug:slug>/lifecycle/",
        "api/v1/platform/tenants/<slug:slug>/modules/",
        "api/v1/platform/tenants/<slug:slug>/sms/",
        "api/v1/platform/tenants/<slug:slug>/support/",
        # Signed-in people's browsers report screen errors (scrubbed, rate-limited).
        "api/v1/problems/browser/",
        # The signed-in person's own browsers for push notifications.
        "api/v1/push/",
        "api/v1/registrations/",
        "api/v1/registrations/slug-check/",
    ]


def test_every_platform_route_requires_platform_staff():
    from core.permissions import IsPlatformStaff

    platform = [
        (route, getattr(callback, "view_class", None) or getattr(callback, "cls", None))
        for route, callback in _iter_views(get_resolver())
        if route.startswith("api/v1/platform/")
    ]
    assert platform
    for route, view in platform:
        assert IsPlatformStaff in view.permission_classes, route
        assert getattr(view, "platform_roles", ()), route


@pytest.mark.django_db
def test_tenant_cache_keys_use_the_permanent_school_id(tenant):
    from control_plane.tenancy import tenant_context
    from core.misc import tenant_cache_key

    with tenant_context(tenant):
        assert tenant_cache_key("timetable", 3) == f"t:{tenant.pk}:timetable:3"
