"""Super Admin console: dashboard totals, the schools list and one school's page.

Platform staff see numbers about each school, never its records.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from django.utils import timezone

from apps.attendance.models import AttendanceRecord
from apps.finance.models import Invoice, Payment
from control_plane.models import (
    PlatformAuditEvent,
    PlatformRole,
    PlatformStaff,
    Role,
    SchoolRegistration,
    TenantUsage,
)
from control_plane.pricing import band_for
from control_plane.tenancy import tenant_context
from control_plane.usage import collect

pytestmark = pytest.mark.django_db


def _staff(make_member, tenant, role=PlatformRole.SUPER_ADMIN):
    user = make_member(tenant)
    PlatformStaff.objects.create(user=user, role=role)
    return user


@pytest.mark.parametrize(
    ("pupils", "band", "price"),
    [
        (0, "band_1", 25_000),
        (1000, "band_1", 25_000),
        (1001, "band_2", 35_000),
        (2000, "band_2", 35_000),
        (2001, "band_3", 45_000),
        (9000, "band_3", 45_000),
    ],
)
def test_price_bands_follow_pupil_numbers(pupils, band, price):
    assert (band_for(pupils).code, band_for(pupils).price_pesewas) == (band, price)


@pytest.fixture
def busy_school(campus, make_student, make_member):
    """Greenfield with three pupils (one left), a register, an invoice and a payment."""
    pupils = [
        make_student(campus.tenant, arm=campus.jhs1, first_name=f"Pupil{i}") for i in range(3)
    ]
    make_member(campus.tenant, Role.OWNER, email="esther@greenfield.test")
    make_member(campus.tenant, Role.TEACHER)
    make_member(campus.tenant, Role.PARENT, mfa=False)
    now = timezone.now()
    with tenant_context(campus.tenant):
        pupils[2].status = "withdrawn"
        pupils[2].save(update_fields=["status"])
        AttendanceRecord.objects.create(
            student=pupils[0],
            arm=campus.jhs1,
            term=campus.term,
            date=campus.today,
            status="present",
            recorded_by=pupils[0].pk,
            recorded_at=now,
        )
        invoice = Invoice.objects.create(
            number="INV-1",
            student=pupils[0],
            term=campus.term,
            total_pesewas=150_000,
            paid_pesewas=50_000,
            issued_at=now,
        )
        Payment.objects.create(
            invoice=invoice,
            method="cash",
            status="success",
            amount_pesewas=50_000,
            amount_received_pesewas=50_000,
            reference="R-1",
            paid_at=now,
        )
    return pupils


def test_collecting_copies_totals_but_nothing_personal(campus, busy_school):
    usage = collect(campus.tenant)
    assert usage.pupils == 2  # the withdrawn pupil isn't counted
    assert usage.registers_7d == 1
    assert usage.payments_30d_pesewas == 50_000
    assert usage.outstanding_pesewas == 100_000
    assert (usage.staff, usage.parents) == (2, 1)
    # Run twice in a day: still one row for today.
    collect(campus.tenant)
    assert TenantUsage.objects.filter(tenant=campus.tenant).count() == 1


def test_dashboard_adds_up_every_school(campus, other_tenant, busy_school, make_member, api):
    admin = api(_staff(make_member, campus.tenant), None)
    data = admin.get("/api/v1/platform/overview/").data
    assert data["schools"]["active"] == 2
    assert data["people"]["pupils"] == 2
    assert data["money"]["fees_processed_30d_pesewas"] == 50_000
    # Both schools are in the first band: GH₵250 each.
    assert data["money"]["expected_subscriptions_pesewas"] == 50_000
    assert [b["schools"] for b in data["bands"]] == [2, 0, 0]
    assert data["top_schools"][0]["slug"] == "greenfield"
    assert len(data["schools_by_month"]) >= 12
    assert data["history"][-1]["pupils"] == 2


def test_schools_list_shows_size_band_and_search(
    campus, other_tenant, busy_school, make_member, api
):
    admin = api(_staff(make_member, campus.tenant, PlatformRole.SUPPORT), None)
    rows = {r["slug"]: r for r in admin.get("/api/v1/platform/tenants/").data["results"]}
    assert rows["greenfield"]["pupils"] == 2
    assert rows["greenfield"]["band"]["label"] == "Up to 1,000 pupils"
    found = admin.get("/api/v1/platform/tenants/", {"q": "royal"}).data["results"]
    assert [r["slug"] for r in found] == ["royal-heights"]


def test_school_page_shows_owner_people_and_usage_without_pupil_names(
    campus, busy_school, make_member, api
):
    SchoolRegistration.objects.create(
        owner=make_member(campus.tenant, email="applicant@greenfield.test"),
        school_name="Greenfield",
        slug="greenfield",
        school_type="basic",
        region="ashanti",
        town="Kumasi",
        phone="+233244123456",
        expected_pupils=300,
        status="approved",
        tenant=campus.tenant,
    )
    admin = api(_staff(make_member, campus.tenant), None)
    response = admin.get("/api/v1/platform/tenants/greenfield/")
    assert response.status_code == 200, response.content
    data = response.data
    assert data["owner"]["email"] == "esther@greenfield.test"
    assert data["registration"]["region"] == "Ashanti"
    assert {r["role"]: r["count"] for r in data["people"]["by_role"]} == {
        "owner": 1,
        "teacher": 1,
        "parent": 1,
    }
    assert data["usage"]["pupils"] == 2
    assert data["band"]["price_pesewas"] == 25_000
    body = json.dumps(response.data, default=str)
    assert "Pupil0" not in body and "Mensah" not in body  # no pupil is named

    refreshed = admin.post("/api/v1/platform/tenants/greenfield/")
    assert refreshed.status_code == 200
    assert PlatformAuditEvent.objects.filter(action="tenant.usage_refreshed").exists()


def test_schools_needing_attention_are_flagged(campus, make_member, api):
    from control_plane.models import Tenant

    Tenant.objects.filter(pk=campus.tenant.pk).update(
        created_at=timezone.now() - dt.timedelta(days=60)
    )
    admin = api(_staff(make_member, campus.tenant), None)
    data = admin.get("/api/v1/platform/overview/").data
    [school] = [s for s in data["attention"] if s["slug"] == "greenfield"]
    assert "No activity for 14 days" in school["reasons"]


def test_only_platform_staff_see_the_console(campus, make_member, api):
    owner = make_member(campus.tenant, Role.OWNER)
    billing = _staff(make_member, campus.tenant, PlatformRole.BILLING)
    for user in (owner, billing, None):
        client = api(user, None)
        assert client.get("/api/v1/platform/tenants/greenfield/").status_code in (401, 403)
    for user in (owner, None):
        assert api(user, None).get("/api/v1/platform/overview/").status_code in (401, 403)
    # Billing staff see the dashboard (money and size), not a school's details.
    assert api(billing, None).get("/api/v1/platform/overview/").status_code == 200
