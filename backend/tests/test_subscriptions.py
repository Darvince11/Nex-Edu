"""Phase 7: monthly invoices, paying online, suspension for not paying, SMS bundles,
closing a school (export, 90 days, crypto-shred), support access and operations."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import io
import json
import zipfile

import httpx
import pytest
from django.core.files.storage import default_storage
from django.test import Client
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from control_plane import lifecycle, subscriptions
from control_plane.models import (
    BillingSettings,
    JobRun,
    ModuleOffer,
    PlatformRole,
    PlatformStaff,
    Role,
    SmsBundle,
    SmsCredit,
    SubscriptionInvoice,
    SupportView,
    Tenant,
    TenantModule,
)
from control_plane.tasks import billing_daily
from core.files import save_tenant_file

pytestmark = pytest.mark.django_db

SECRET = "sk_test_nexedu"
CONSOLE = "/api/v1/platform/"


@pytest.fixture
def school(campus, make_member, api, settings):
    settings.PAYSTACK_SECRET_KEY = SECRET
    owner = make_member(campus.tenant, Role.OWNER, email="owner@greenfield.test")

    def staff(role=PlatformRole.SUPER_ADMIN):
        user = make_member(campus.tenant)
        PlatformStaff.objects.create(user=user, role=role)
        return api(user, None)

    return {
        "tenant": campus.tenant,
        "owner": api(owner, None),
        "owner_in_school": api(owner, campus.tenant),
        "super": staff(),
        "billing": staff(PlatformRole.BILLING),
        "support": staff(PlatformRole.SUPPORT),
        "head": api(make_member(campus.tenant, Role.PRINCIPAL), None),
    }


def _paystack(*, amount):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/transaction/initialize":
            body = json.loads(request.content)
            assert "subaccount" not in body  # Nex Edu's own account
            return httpx.Response(
                200,
                json={
                    "status": True,
                    "data": {
                        "authorization_url": f"https://checkout.paystack.com/{body['reference']}",
                        "reference": body["reference"],
                    },
                },
            )
        ref = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "status": "success",
                    "reference": ref,
                    "amount": amount,
                    "currency": "GHS",
                    "id": 7,
                    "paid_at": "2026-11-20T10:00:00Z",
                },
            },
        )

    return handler


def _webhook(reference):
    body = json.dumps({"event": "charge.success", "data": {"reference": reference}}).encode()
    signature = hmac.new(SECRET.encode(), body, hashlib.sha512).hexdigest()
    return Client().generic(
        "POST",
        "/api/v1/webhooks/paystack/",
        body,
        content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE=signature,
    )


def _billing(client, tenant):
    return client.get(f"/api/v1/account/schools/{tenant.slug}/billing/")


def test_monthly_invoice_has_the_band_and_paid_add_ons_once(school):
    tenant = school["tenant"]
    ModuleOffer.objects.update_or_create(code="payroll", defaults={"price_pesewas": 5_000})
    TenantModule.objects.create(tenant=tenant, code="payroll", granted=True)
    today = dt.date(2026, 11, 1)
    invoice = subscriptions.issue_invoice(tenant, today, today=today)
    assert invoice is not None
    assert [line["amount_pesewas"] for line in invoice.lines] == [25_000, 5_000]
    assert invoice.total_pesewas == 30_000
    assert invoice.due_on == today + dt.timedelta(days=BillingSettings.load().due_days)
    assert subscriptions.issue_invoice(tenant, today, today=today) is None  # once a month
    assert BillingSettings.load().period == "monthly"


def test_unpaid_invoice_reminds_then_suspends_and_paying_reactivates(school, mock_http):
    tenant = school["tenant"]
    invoice = subscriptions.issue_invoice(tenant, timezone.localdate(), today=timezone.localdate())
    due = invoice.due_on
    assert subscriptions.chase_overdue(due + dt.timedelta(days=7)) == {
        "reminded": 1,
        "suspended": 0,
    }
    assert subscriptions.chase_overdue(due + dt.timedelta(days=8)) == {
        "reminded": 0,
        "suspended": 0,
    }
    assert subscriptions.chase_overdue(due + dt.timedelta(days=14))["reminded"] == 1
    assert subscriptions.chase_overdue(due + dt.timedelta(days=30))["suspended"] == 1
    tenant.refresh_from_db()
    assert tenant.status == Tenant.Status.SUSPENDED and tenant.status_reason == "nonpayment"

    # The school is closed to everyone, but its proprietor can still pay.
    assert school["owner_in_school"].get("/api/v1/students/").status_code == 403
    assert _billing(school["head"], tenant).status_code == 403  # proprietor only
    account = _billing(school["owner"], tenant).json()
    assert account["status"] == "suspended" and account["outstanding_pesewas"] == 25_000

    # Pretend the 30 days are real so reactivation checks the same cut-off.
    SubscriptionInvoice.objects.filter(pk=invoice.pk).update(
        due_on=timezone.localdate() - dt.timedelta(days=31)
    )
    mock_http(_paystack(amount=25_000))
    started = school["owner"].post(
        f"/api/v1/account/schools/{tenant.slug}/billing/pay/",
        {"invoice": str(invoice.pk)},
        format="json",
    )
    assert started.status_code == 201, started.content
    reference = started.json()["reference"]
    assert reference.startswith("NXS-")
    assert _webhook(reference).status_code == 200
    invoice.refresh_from_db()
    tenant.refresh_from_db()
    assert invoice.status == "paid" and invoice.payments.get().method == "paystack"
    assert tenant.status == Tenant.Status.ACTIVE
    assert _webhook(reference).status_code == 200  # a repeated webhook changes nothing
    assert invoice.payments.count() == 1


def test_billing_staff_record_bank_payments_and_cancel_invoices(school):
    tenant = school["tenant"]
    first = subscriptions.issue_invoice(tenant, dt.date(2026, 10, 1), today=dt.date(2026, 10, 1))
    second = subscriptions.issue_invoice(tenant, dt.date(2026, 11, 1), today=dt.date(2026, 11, 1))
    url = f"{CONSOLE}billing/invoices/"
    assert school["support"].post(f"{url}{first.pk}/", {"action": "void"}).status_code == 403
    paid = school["billing"].post(
        f"{url}{first.pk}/",
        {"action": "mark_paid", "method": "bank", "reference": "GCB-1"},
        format="json",
    )
    assert paid.status_code == 200 and paid.json()["status"] == "paid"
    no_reason = school["billing"].post(f"{url}{second.pk}/", {"action": "void"}, format="json")
    assert no_reason.status_code == 400
    school["billing"].post(
        f"{url}{second.pk}/", {"action": "void", "reason": "Free month"}, format="json"
    )
    listed = school["billing"].get(url).json()
    assert {i["status"] for i in listed["invoices"]} == {"paid", "void"}
    assert listed["open_pesewas"] == 0


def test_sms_bundles_are_bought_online_and_checked_against_paystack(school, mock_http):
    tenant = school["tenant"]
    made = school["super"].post(
        f"{CONSOLE}billing/sms-bundles/",
        {"code": "sms-1000", "label": "1,000 SMS", "sms": 1000, "price_pesewas": 3_000},
        format="json",
    )
    assert made.status_code == 201
    assert school["billing"].post(f"{CONSOLE}billing/sms-bundles/", {}).status_code == 403
    assert _billing(school["owner"], tenant).json()["bundles"][0]["sms"] == 1000

    mock_http(_paystack(amount=2_000))  # paid less than the price
    short = (
        school["owner"]
        .post(f"/api/v1/account/schools/{tenant.slug}/billing/pay/", {"bundle": "sms-1000"})
        .json()
    )
    _webhook(short["reference"])
    assert not SmsCredit.objects.filter(tenant=tenant, balance__gt=0).exists()

    mock_http(_paystack(amount=3_000))
    good = (
        school["owner"]
        .post(f"/api/v1/account/schools/{tenant.slug}/billing/pay/", {"bundle": "sms-1000"})
        .json()
    )
    checked = school["owner"].get(
        f"/api/v1/account/schools/{tenant.slug}/billing/charges/{good['reference']}/"
    )
    assert checked.json()["status"] == "paid"
    assert SmsCredit.objects.get(tenant=tenant).balance == 1000
    gift = school["super"].post(
        f"{CONSOLE}tenants/{tenant.slug}/sms/", {"sms": 50, "reason": "Outage"}, format="json"
    )
    assert gift.json()["bought"] == 1050
    SmsBundle.objects.filter(code="sms-1000").update(is_active=False)
    off = school["owner"].post(
        f"/api/v1/account/schools/{tenant.slug}/billing/pay/", {"bundle": "sms-1000"}
    )
    assert off.status_code == 400


def test_suspend_needs_a_reason_and_only_super_admins(school):
    tenant = school["tenant"]
    url = f"{CONSOLE}tenants/{tenant.slug}/lifecycle/"
    assert school["support"].post(url, {"action": "suspend", "reason": "x"}).status_code == 403
    assert school["super"].post(url, {"action": "suspend"}, format="json").status_code == 400
    done = (
        school["super"]
        .post(url, {"action": "suspend", "reason": "Fraud check"}, format="json")
        .json()
    )
    assert done["status"] == "suspended" and done["status_reason"] == "platform"
    again = school["super"].post(url, {"action": "reactivate", "reason": "Cleared"}, format="json")
    assert again.json()["status"] == "active"


def test_closing_exports_locks_and_destroys_after_90_days(school, campus, make_student):
    tenant = school["tenant"]
    make_student(tenant, arm=campus.jhs1, first_name="Abena")
    from control_plane.tenancy import tenant_context

    with tenant_context(tenant):
        save_tenant_file("reports/card.pdf", b"%PDF card")
    url = f"{CONSOLE}tenants/{tenant.slug}/lifecycle/"
    unconfirmed = school["super"].post(
        url, {"action": "offboard", "reason": "Moving away"}, format="json"
    )
    assert unconfirmed.status_code == 400
    closed = (
        school["super"]
        .post(
            url,
            {"action": "offboard", "reason": "Moving away", "confirm": tenant.slug},
            format="json",
        )
        .json()
    )
    assert closed["status"] == "offboarded"
    assert closed["purge_after"] == (timezone.localdate() + dt.timedelta(days=90)).isoformat()

    # Only the proprietor downloads the export; it holds every record and file.
    export_url = f"/api/v1/account/schools/{tenant.slug}/export/"
    assert school["support"].get(export_url).status_code == 403
    got = school["owner"].get(export_url)
    assert got.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(b"".join(got.streaming_content)))
    names = archive.namelist()
    assert "files/reports/card.pdf" in names and "manifest.json" in names
    assert b"Abena" in archive.read("data/students.Student.json")

    tenant.refresh_from_db()
    assert lifecycle.purge_due() == 0  # not yet
    Tenant.objects.filter(pk=tenant.pk).update(purge_after=timezone.localdate())
    assert lifecycle.purge_due() == 1
    tenant.refresh_from_db()
    assert tenant.purged_at and tenant.wrapped_data_key is None and not tenant.export_key
    assert not default_storage.exists(f"tenants/{tenant.slug}/reports/card.pdf")
    assert school["owner"].get(export_url).status_code == 403
    with pytest.raises(ValidationError):
        lifecycle.reactivate(tenant, note="Too late")


def test_support_sees_the_set_up_only_while_the_proprietor_allows(school, campus, make_student):
    tenant = school["tenant"]
    make_student(tenant, arm=campus.jhs1, first_name="Kwabena", last_name="Sarpong")
    url = f"{CONSOLE}tenants/{tenant.slug}/support/?look=1"
    assert school["support"].get(url).status_code == 403
    assert (
        school["head"]
        .post(f"/api/v1/account/schools/{tenant.slug}/support/", {"hours": 2, "reason": "x"})
        .status_code
        == 403
    )
    granted = school["owner"].post(
        f"/api/v1/account/schools/{tenant.slug}/support/",
        {"hours": 2, "reason": "Report cards won't print"},
        format="json",
    )
    assert granted.status_code == 201
    me = school["owner"].get("/api/v1/me/").json()
    assert me["schools"][0]["support_access_until"] is not None  # the in-school banner
    seen = school["support"].get(url)
    assert seen.status_code == 200
    body = json.dumps(seen.json())
    assert "JHS 1" in body and "Kwabena" not in body and "Sarpong" not in body
    assert SupportView.objects.count() == 1
    history = school["owner"].get(f"/api/v1/account/schools/{tenant.slug}/support/").json()
    grant = history["grants"][0]
    assert grant["open"] and len(grant["views"]) == 1

    school["owner"].post(f"/api/v1/account/schools/{tenant.slug}/support/{grant['id']}/revoke/")
    assert school["support"].get(url).status_code == 403
    too_long = school["owner"].post(
        f"/api/v1/account/schools/{tenant.slug}/support/",
        {"hours": 24 * 8, "reason": "x"},
        format="json",
    )
    assert too_long.status_code == 400


def test_operations_view_lists_scheduled_jobs_and_records_runs(school):
    billing_daily.apply()
    run = JobRun.objects.get(name="control_plane.billing_daily")
    assert run.succeeded is True and "issued" in run.result
    ops = school["support"].get(f"{CONSOLE}system/operations/").json()
    jobs = {j["name"]: j for j in ops["jobs"]}
    assert jobs["control_plane.billing_daily"]["last_succeeded"] is True
    assert "compliance.remind_all" in jobs
    assert {"cells", "migrations", "lifecycle"} <= set(ops)
