"""Super Admin console: pricing and billing, audit logs, announcements, system."""

from __future__ import annotations

import datetime as dt
import json
import logging

import httpx
import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from control_plane.audit import record_platform_event
from control_plane.models import (
    PlatformAuditEvent,
    PlatformRole,
    PlatformStaff,
    PriceBandSetting,
    Problem,
    Role,
    SchoolRegistration,
)
from control_plane.problems import capture, scrub

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(make_member, tenant):
    def _make(role=PlatformRole.SUPER_ADMIN, email=None):
        user = make_member(tenant, email=email)  # no school roles
        PlatformStaff.objects.create(user=user, role=role)
        return user

    return _make


# --- Pricing and billing -----------------------------------------------------------------


def test_prices_start_at_the_owners_bands_and_only_a_super_admin_changes_them(staff, api):
    billing = api(staff(PlatformRole.BILLING), None)
    data = billing.get("/api/v1/platform/billing/pricing/").data
    assert [(b["code"], b["price_pesewas"]) for b in data["bands"]] == [
        ("band_1", 25_000),
        ("band_2", 35_000),
        ("band_3", 45_000),
    ]
    assert data["free_trial_days"] == 0
    change = {"price_pesewas": 27_500, "reason": "New term pricing"}
    url = "/api/v1/platform/billing/bands/band_1/"
    assert billing.post(url, change, format="json").status_code == 403

    admin = api(staff(), None)
    assert (
        admin.post(url, {"price_pesewas": 27_500, "reason": ""}, format="json").status_code == 400
    )
    assert admin.post(url, change, format="json").status_code == 200
    assert PriceBandSetting.objects.get(code="band_1").price_pesewas == 27_500
    event = PlatformAuditEvent.objects.get(action="billing.price_changed")
    assert event.data == {"band": "band_1", "before_pesewas": 25_000, "after_pesewas": 27_500}
    assert event.reason == "New term pricing"

    assert (
        admin.patch("/api/v1/platform/billing/pricing/", {"period": "termly"}, format="json").data[
            "period_label"
        ]
        == "Per term"
    )


def test_payments_are_recorded_and_listed_with_earlier_months_apart(tenant, staff, api):
    billing = api(staff(PlatformRole.BILLING), None)
    url = "/api/v1/platform/billing/payments/"
    today = timezone.localdate()
    last_month = today.replace(day=1) - dt.timedelta(days=3)
    payment = {
        "school": "greenfield",
        "amount_pesewas": 25_000,
        "period_label": "September 2026",
        "method": "momo",
        "reference": "MTN-123",
        "received_on": last_month.isoformat(),
    }
    assert billing.post(url, payment, format="json").status_code == 201
    assert (
        billing.post(url, {**payment, "received_on": today.isoformat()}, format="json").status_code
        == 201
    )
    future = {**payment, "received_on": (today + dt.timedelta(days=2)).isoformat()}
    assert billing.post(url, future, format="json").status_code == 400

    everything = billing.get(url).data
    assert everything["total_pesewas"] == 50_000
    assert everything["before_this_month_pesewas"] == 25_000
    assert everything["payments"][0]["recorded_by"].endswith("@example.test")
    earlier = billing.get(url, {"before_month": "1"}).data
    assert [p["period_label"] for p in earlier["payments"]] == ["September 2026"]
    assert (
        PlatformAuditEvent.objects.filter(
            action="billing.payment_recorded", tenant_id=tenant.pk
        ).count()
        == 2
    )

    support = api(staff(PlatformRole.SUPPORT), None)
    assert support.get(url).status_code == 403


# --- Audit logs --------------------------------------------------------------------------


def test_audit_log_files_events_under_the_right_school(
    tenant, other_tenant, make_member, staff, api
):
    teacher = make_member(tenant, Role.TEACHER, email="kofi@greenfield.test")
    make_member(other_tenant, Role.TEACHER, email="ama@royal.test")
    for _ in range(2):
        record_platform_event(action="auth.sign_in_failed", data={"email": teacher.email})
    record_platform_event(action="auth.sign_in_failed", data={"email": "ama@royal.test"})
    admin_user = staff()
    record_platform_event(action="platform_staff.granted", actor=admin_user, target=admin_user)

    admin = api(admin_user, None)
    greenfield = admin.get("/api/v1/platform/audit/", {"school": "greenfield"}).data["events"]
    assert [e["action"] for e in greenfield] == ["auth.sign_in_failed", "auth.sign_in_failed"]
    assert greenfield[0]["schools"] == [{"slug": "greenfield", "name": "Greenfield"}]
    royal = admin.get("/api/v1/platform/audit/", {"school": "royal-heights"}).data["events"]
    assert len(royal) == 1
    platform = admin.get("/api/v1/platform/audit/", {"school": "platform"}).data["events"]
    assert [e["action"] for e in platform] == ["platform_staff.granted"]

    groups = {g["slug"]: g["events"] for g in admin.get("/api/v1/platform/audit/groups/").data}
    assert groups["greenfield"] == 2 and groups["royal-heights"] == 1

    mine = admin.get("/api/v1/platform/audit/mine/").data["events"]
    assert [e["action"] for e in mine] == ["platform_staff.granted"]
    assert admin.get("/api/v1/platform/audit/verify/").data["valid"] is True


def test_audit_logs_need_the_right_role(staff, api):
    billing = api(staff(PlatformRole.BILLING), None)
    assert billing.get("/api/v1/platform/audit/").status_code == 403
    assert billing.get("/api/v1/platform/audit/mine/").status_code == 200  # everyone sees their own


# --- Announcements -----------------------------------------------------------------------


def test_announcements_reach_proprietors_and_can_be_dismissed(
    tenant, other_tenant, make_member, staff, api, django_capture_on_commit_callbacks
):
    owner = make_member(tenant, Role.OWNER, email="esther@greenfield.test")
    make_member(tenant, Role.TEACHER)  # not a proprietor
    other_owner = make_member(other_tenant, Role.OWNER)
    SchoolRegistration.objects.create(
        owner=owner,
        school_name="Greenfield",
        slug="greenfield",
        school_type="basic",
        region="ashanti",
        town="Kumasi",
        phone="+233244123456",
        expected_pupils=200,
        status="approved",
        tenant=tenant,
    )
    admin = api(staff(), None)
    draft = {
        "title": "Report cards now print in colour",
        "body": "Try it this term.",
        "audience": "region",
    }
    assert admin.post("/api/v1/platform/announcements/", draft, format="json").status_code == 400
    created = admin.post(
        "/api/v1/platform/announcements/", {**draft, "region": "ashanti"}, format="json"
    ).data
    with django_capture_on_commit_callbacks(execute=True):
        sent = admin.post(f"/api/v1/platform/announcements/{created['id']}/publish/").data
    assert sent["status"] == "published"
    assert sent["recipient_count"] == 1  # only Greenfield is in Ashanti
    assert [m.to for m in mail.outbox] == [["esther@greenfield.test"]]

    feed = api(owner, None).get("/api/v1/nexedu-announcements/").data
    assert [a["title"] for a in feed] == ["Report cards now print in colour"]
    assert api(other_owner, None).get("/api/v1/nexedu-announcements/").data == []
    api(owner, None).post(f"/api/v1/nexedu-announcements/{created['id']}/read/")
    assert api(owner, None).get("/api/v1/nexedu-announcements/").data == []
    assert admin.get("/api/v1/platform/announcements/").data[0]["read_count"] == 1

    again = admin.post(f"/api/v1/platform/announcements/{created['id']}/publish/")
    assert again.status_code == 400
    support = api(staff(PlatformRole.SUPPORT), None)
    assert support.post("/api/v1/platform/announcements/", draft, format="json").status_code == 403


# --- System: problems, security, updates, vulnerabilities ---------------------------------


def test_personal_details_and_secrets_are_scrubbed():
    text = scrub(
        "Failed for ama@example.com, phone 024 412 3456, card 4111111111111111, password='hunter2'"
    )
    assert "ama@example.com" not in text and "4111111111111111" not in text
    assert "412 3456" not in text and "hunter2" not in text
    assert "[email]" in text and "[phone]" in text


@pytest.fixture
def problem_handler():
    """Test settings turn logging handlers off; attach the real one for these tests."""
    from control_plane.problems import ProblemLogHandler

    handler = ProblemLogHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    yield handler
    root.removeHandler(handler)


def test_production_logging_sends_errors_to_the_problem_list():
    from config.settings import base

    assert "problems" in base.LOGGING["root"]["handlers"]
    assert "control_plane.problems.SlowRequestMiddleware" in base.MIDDLEWARE


def test_errors_are_grouped_counted_and_reopen_when_they_return(settings, problem_handler):
    settings.PROBLEM_EMAILS_INLINE = True
    log = logging.getLogger("apps.finance.api")
    for _ in range(3):
        try:
            raise ValueError("Paystack said no for kofi@example.com")
        except ValueError:
            log.exception("Payment confirmation failed")
    problem = Problem.objects.get()
    assert problem.count == 3
    assert problem.kind == "server" and problem.severity == "critical"
    assert "kofi@example.com" not in problem.title + problem.detail
    problem.status = Problem.Status.FIXED
    problem.save()
    capture(
        kind="server",
        title=problem.title,
        location=problem.location,
        fingerprint=problem.fingerprint,
    )
    problem.refresh_from_db()
    assert problem.status == Problem.Status.NEW and problem.count == 4


def test_new_critical_problems_email_super_admins(settings, staff):
    settings.PROBLEM_EMAILS_INLINE = True
    staff(email="ops@nexedu.test")
    capture(kind="job", title="School set-up failed", location="control_plane/tasks.py:20")
    assert mail.outbox[-1].to == ["ops@nexedu.test"]
    assert "School set-up failed" in mail.outbox[-1].subject


def test_browser_errors_and_problem_triage(make_member, tenant, staff, api):
    teacher = api(make_member(tenant, Role.TEACHER), None)
    report = {
        "message": "TypeError: x is undefined",
        "source": "app/(school)/scores/page.tsx",
        "page": "/students/0f4c1e2a-1234-4abc-9def-1234567890ab",
    }
    assert teacher.post("/api/v1/problems/browser/", report, format="json").status_code == 204
    problem = Problem.objects.get(kind="browser")
    assert problem.last_path == "/students/:id"

    support = api(staff(PlatformRole.SUPPORT), None)
    listed = support.get("/api/v1/platform/system/problems/").data
    assert listed["open"] == 1
    changed = support.patch(
        f"/api/v1/platform/system/problems/{problem.pk}/",
        {"status": "investigating", "note": "Looking into it", "title": "renamed"},
        format="json",
    ).data
    assert changed["status"] == "investigating" and changed["title"] == problem.title
    assert PlatformAuditEvent.objects.filter(action="problem.status_changed").exists()


def test_slow_pages_are_recorded_by_page_not_by_record(monkeypatch, make_member, tenant, api):
    from control_plane import problems

    monkeypatch.setattr(problems, "SLOW_REQUEST_SECONDS", 0.0)
    owner = api(make_member(tenant, Role.OWNER), tenant)
    owner.get("/api/v1/students/")
    owner.get("/api/v1/students/")
    slow = Problem.objects.get(kind="slow")
    assert slow.count == 2 and slow.severity == "warning"
    assert slow.schools == ["greenfield"]


def test_sign_in_failures_and_password_resets_show_on_the_security_page(
    make_member, tenant, staff, api
):
    member = make_member(tenant, Role.TEACHER, email="kofi@greenfield.test")
    for _ in range(5):
        record_platform_event(action="auth.sign_in_failed", data={"email": member.email})
    record_platform_event(action="auth.sign_in_failed", data={"email": "nobody@example.test"})

    browser = Client()
    browser.get("/_allauth/browser/v1/auth/session")
    browser.post(
        "/_allauth/browser/v1/auth/password/request",
        data=json.dumps({"email": member.email}),
        content_type="application/json",
    )
    assert PlatformAuditEvent.objects.filter(action="auth.password_reset_requested").exists()

    data = api(staff(PlatformRole.SUPPORT), None).get("/api/v1/platform/system/security/").data
    kofi = next(a for a in data["accounts"] if a["email"] == member.email)
    assert kofi["attempts"] == 5 and kofi["suspicious"] is True
    assert kofi["schools"] == [{"slug": "greenfield", "name": "Greenfield"}]
    unknown = next(a for a in data["accounts"] if a["email"] == "nobody@example.test")
    assert unknown["known_account"] is False
    reset = data["password_resets"][0]
    assert reset["action"] == "auth.password_reset_requested"
    assert reset["schools"] == [{"slug": "greenfield", "name": "Greenfield"}]


def test_system_page_shows_versions_health_and_vulnerabilities(staff, api, mock_http, settings):
    def osv(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("querybatch"):
            queries = json.loads(request.content)["queries"]
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"vulns": [{"id": "GHSA-test"}]} if q["package"]["name"] == "django" else {}
                        for q in queries
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "summary": "Example advisory",
                "aliases": ["CVE-2026-0001"],
                "affected": [{"ranges": [{"events": [{"introduced": "0"}, {"fixed": "99.0"}]}]}],
            },
        )

    mock_http(osv)
    from control_plane.security import scan_vulnerabilities

    scan = scan_vulnerabilities()
    assert [f["package"] for f in scan.findings] == ["django"]
    assert scan.findings[0]["fixed_in"] == ["99.0"]

    admin = api(staff(), None)
    status = admin.get("/api/v1/platform/system/").data
    assert status["django"] and status["schema_version"]
    assert status["scan"]["findings"][0]["id"] == "GHSA-test"
    checked = admin.post("/api/v1/platform/system/").data
    assert any(h["check"] == "usage-fresh" for h in checked["health"])
    assert api(staff(PlatformRole.BILLING), None).get("/api/v1/platform/system/").status_code == 403
