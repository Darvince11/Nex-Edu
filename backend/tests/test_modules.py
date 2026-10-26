"""Modules: what a school has switched on, what it's entitled to, and that
switched-off features are refused everywhere (pages, public form, SMS)."""

from __future__ import annotations

import pytest
from django.urls import get_resolver
from django.utils import timezone

from apps.communication.models import Channel, Delivery
from apps.finance.models import Invoice
from control_plane.models import PlatformAuditEvent, PlatformRole, PlatformStaff, Role
from control_plane.tenancy import tenant_context
from core.modules import BY_CODE, CORE, module_for_view
from tests.test_authorization import _iter_views

pytestmark = pytest.mark.django_db
URL = "/api/v1/school/modules/"


def by_code(response):
    return {m["code"]: m for m in response.data["modules"]}


@pytest.fixture
def owner(tenant, make_member, api):
    return api(make_member(tenant, Role.OWNER), tenant)


def switch(client, code, active, **extra):
    return client.post(URL, {"code": code, "active": active, **extra}, format="json")


def test_every_school_view_belongs_to_a_module():
    """New features must be filed under a module (or the core) before they ship."""
    missing = []
    for route, callback in _iter_views(get_resolver()):
        view = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
        if not route.startswith("api/v1/") or view is None:
            continue
        if getattr(view, "public_endpoint", False) or getattr(view, "tenant_scoped", True) is False:
            continue
        if module_for_view(view) not in BY_CODE:
            missing.append(route)
    assert missing == []


def test_everything_starts_switched_on_and_planned_modules_cannot_be(owner, monkeypatch):
    import control_plane.modules as service
    import core.modules as catalogue

    # Every Phase 6 module has shipped; a made-up one stands in for the next planned one.
    planned = catalogue.Module(
        "robotics", "Robotics", "Not built yet.", available=False, default_on=False
    )
    modules = (*catalogue.MODULES, planned)
    for target in (catalogue, service):
        monkeypatch.setattr(target, "MODULES", modules)
        monkeypatch.setattr(target, "BY_CODE", {m.code: m for m in modules})

    modules = by_code(owner.get(URL))
    assert all(modules[code]["active"] for code in CORE)
    assert all(modules[code]["active"] for code in ("admissions", "fees", "sms"))
    # Modules added since start off until the proprietor chooses them.
    assert modules["library"]["available"] is True and modules["library"]["active"] is False
    assert modules["robotics"]["available"] is False and modules["robotics"]["active"] is False
    assert switch(owner, "robotics", True).status_code == 400
    assert switch(owner, "people", False).status_code == 400  # core stays on


def test_switched_off_module_is_refused_everywhere_and_comes_back(tenant, owner, make_member, api):
    bursar = api(make_member(tenant, Role.BURSAR), tenant)
    assert bursar.get("/api/v1/finance/invoices/").status_code == 200

    off = switch(owner, "fees", False)
    assert off.status_code == 200, off.content
    refused = bursar.get("/api/v1/finance/invoices/")
    assert refused.status_code == 403
    assert refused.data["code"] == "module_disabled"
    me = api(make_member(tenant, Role.OWNER), None).get("/api/v1/me/").data
    assert "fees" not in me["schools"][0]["modules"]
    setup = owner.get("/api/v1/school/setup/").data
    assert "fees" not in {s["key"] for s in setup["steps"]}

    assert switch(owner, "fees", True).status_code == 200
    assert bursar.get("/api/v1/finance/invoices/").status_code == 200
    history = owner.get(URL).data["history"]
    assert [h["action"] for h in history[:2]] == ["activated", "deactivated"]


def test_active_module_still_needs_the_permission(tenant, make_member, api):
    teacher = api(make_member(tenant, Role.TEACHER), tenant)
    response = teacher.get("/api/v1/finance/invoices/")
    assert response.status_code == 403
    assert response.data.get("code") != "module_disabled"


def test_only_the_proprietor_switches_modules(tenant, make_member, api):
    head = api(make_member(tenant, Role.PRINCIPAL), tenant)
    assert head.get(URL).status_code == 200
    assert switch(head, "sms", False).status_code == 403


def test_switching_off_with_open_records_needs_confirmation_and_keeps_them(
    campus, make_member, make_student, api
):
    owner = api(make_member(campus.tenant, Role.OWNER), campus.tenant)
    pupil = make_student(campus.tenant, arm=campus.jhs1)
    with tenant_context(campus.tenant):
        Invoice.objects.create(
            number="INV-9",
            student=pupil,
            term=campus.term,
            total_pesewas=50_000,
            issued_at=timezone.now(),
        )
    conflict = switch(owner, "fees", False)
    assert conflict.status_code == 409
    assert conflict.data["open_records"] == ["1 unpaid invoice"]
    assert switch(owner, "fees", False, confirm=True).status_code == 200
    with tenant_context(campus.tenant):
        assert Invoice.objects.count() == 1  # nothing is deleted


def test_paid_add_ons_need_nex_edu_to_grant_them(tenant, owner, make_member, api):
    admin_user = make_member(tenant)
    PlatformStaff.objects.create(user=admin_user, role=PlatformRole.SUPER_ADMIN)
    admin = api(admin_user, None)
    price = {"price_pesewas": 5_000, "reason": "SMS costs money to send"}
    assert (
        admin.post("/api/v1/platform/billing/modules/sms/", price, format="json").status_code == 200
    )
    assert PlatformAuditEvent.objects.filter(action="billing.module_price_changed").exists()

    modules = by_code(owner.get(URL))
    assert modules["sms"]["entitled"] is False and modules["sms"]["active"] is False
    refused = switch(owner, "sms", True)
    assert refused.status_code == 403
    assert "paid add-on" in str(refused.data["detail"])

    url = f"/api/v1/platform/tenants/{tenant.slug}/modules/"
    assert (
        admin.post(url, {"code": "sms", "action": "grant"}, format="json").status_code == 400
    )  # no reason
    granted = admin.post(
        url, {"code": "sms", "action": "grant", "reason": "Paid MTN-123"}, format="json"
    )
    assert granted.status_code == 200
    assert by_code(owner.get(URL))["sms"]["active"] is True
    admin.post(url, {"code": "sms", "action": "revoke", "reason": "Stopped paying"}, format="json")
    assert by_code(owner.get(URL))["sms"]["active"] is False
    history = owner.get(URL).data["history"]
    assert history[0]["action"] == "revoked" and history[0]["by_platform"] is True


def test_dependencies_must_be_on_first_and_can_not_be_pulled_out(owner):
    """Canteen depends on Fees."""
    assert switch(owner, "fees", False).status_code == 200
    blocked = switch(owner, "canteen", True)
    assert blocked.status_code == 400
    assert "Switch on Fees and payments first" in str(blocked.data)
    assert switch(owner, "fees", True).status_code == 200
    assert switch(owner, "canteen", True).status_code == 200
    pulled = switch(owner, "fees", False)
    assert pulled.status_code == 400
    assert "Switch off Canteen first" in str(pulled.data)


def test_public_admission_form_closes_with_the_module(tenant, owner):
    from django.test import Client

    form = Client().get("/api/v1/public/admissions/", HTTP_X_TENANT=tenant.slug)
    assert form.status_code == 200
    switch(owner, "admissions", False)
    closed = Client().get("/api/v1/public/admissions/", HTTP_X_TENANT=tenant.slug)
    assert closed.status_code == 404
    assert closed.json()["code"] == "module_disabled"


def test_no_text_messages_go_out_while_sms_is_off(tenant, owner):
    from apps.communication.tasks import send_deliveries

    switch(owner, "sms", False)
    with tenant_context(tenant):
        sms = Delivery.objects.create(
            channel=Channel.SMS, to="+233244123456", body="Hello", kind="test"
        )
        email = Delivery.objects.create(
            channel=Channel.EMAIL, to="p@example.test", body="Hello", kind="test"
        )
        send_deliveries.run([str(sms.pk), str(email.pk)])
        sms.refresh_from_db()
        email.refresh_from_db()
    assert sms.status == Delivery.Status.SKIPPED and "switched off" in sms.error
    assert email.status == Delivery.Status.SENT


def test_proprietor_confirms_choices_for_the_checklist(owner):
    steps = {s["key"]: s for s in owner.get("/api/v1/school/setup/").data["steps"]}
    assert steps["modules"]["done"] is False
    assert owner.post(URL, {"action": "confirm_choices"}, format="json").data["confirmed"] is True
    steps = {s["key"]: s for s in owner.get("/api/v1/school/setup/").data["steps"]}
    assert steps["modules"]["done"] is True


def test_nex_edu_staff_switch_modules_with_a_reason_and_support_only_reads(
    tenant, make_member, api
):
    support_user = make_member(tenant)
    PlatformStaff.objects.create(user=support_user, role=PlatformRole.SUPPORT)
    support = api(support_user, None)
    url = f"/api/v1/platform/tenants/{tenant.slug}/modules/"
    assert support.get(url).status_code == 200
    assert (
        support.post(
            url, {"code": "fees", "action": "deactivate", "reason": "x"}, format="json"
        ).status_code
        == 403
    )

    admin_user = make_member(tenant)
    PlatformStaff.objects.create(user=admin_user, role=PlatformRole.SUPER_ADMIN)
    admin = api(admin_user, None)
    assert (
        admin.post(url, {"code": "fees", "action": "deactivate"}, format="json").status_code == 400
    )
    done = admin.post(
        url, {"code": "admissions", "action": "deactivate", "reason": "School asked"}, format="json"
    )
    assert done.status_code == 200
    assert next(m for m in done.data["modules"] if m["code"] == "admissions")["active"] is False
    assert PlatformAuditEvent.objects.filter(
        action="module.deactivated", tenant_id=tenant.pk
    ).exists()
