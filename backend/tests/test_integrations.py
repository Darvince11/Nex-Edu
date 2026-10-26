"""Phase 8: calendar feeds, video links, accounting export, push, developer API and
webhooks, analytics export and AI drafting help."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from celery.exceptions import Retry
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.storage import default_storage
from django.test import Client
from django.utils import timezone

from apps.academics.models import CalendarEvent, ClassLevel
from apps.assessments.models import ReportCard
from apps.finance.models import FeeItem, FeeSchedule, Invoice
from apps.finance.services import record_manual_payment
from control_plane import analytics, developer
from control_plane.models import (
    Membership,
    PushSubscription,
    Role,
    WebhookDelivery,
    WebhookEndpoint,
)
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context
from core.links import service_name, validate_video_link

pytestmark = pytest.mark.django_db


# --- Calendar feeds ---------------------------------------------------------------------


def test_calendar_feed_is_private_replaceable_and_follows_membership(campus, make_member, api):
    parent = make_member(campus.tenant, Role.PARENT, mfa=False)
    today = timezone.localdate()
    with tenant_context(campus.tenant):
        CalendarEvent.objects.create(
            title="Sports day; all welcome", starts_on=today, ends_on=today
        )
        CalendarEvent.objects.create(
            title="Staff training", starts_on=today, ends_on=today, audience="staff"
        )
    client = api(parent, campus.tenant)
    assert client.get("/api/v1/calendar/feed/").json()["active"] is False
    url = client.post("/api/v1/calendar/feed/").json()["url"]
    token = url.rstrip("/").rsplit("/", 1)[-1]

    feed = Client().get(f"/api/v1/public/calendar/{token}/")
    body = feed.content.decode()
    assert feed.status_code == 200 and feed["Content-Type"].startswith("text/calendar")
    assert body.startswith("BEGIN:VCALENDAR") and "Sports day\\; all welcome" in body
    assert "Staff training" not in body  # staff-only
    assert "Independence Day" in body or "Republic Day" in body or "DTSTART" in body

    newer = client.post("/api/v1/calendar/feed/").json()["url"].rstrip("/").rsplit("/", 1)[-1]
    assert Client().get(f"/api/v1/public/calendar/{token}/").status_code == 404
    Membership.objects.filter(user=parent).update(is_active=False)
    assert Client().get(f"/api/v1/public/calendar/{newer}/").status_code == 404


# --- Video links ------------------------------------------------------------------------


def test_video_links_must_be_plain_https():
    validate_video_link("https://meet.google.com/abc-defg-hij")
    for bad in ("http://zoom.us/j/1", "https://user:pw@zoom.us/j/1", "javascript:alert(1)"):
        with pytest.raises(DjangoValidationError):
            validate_video_link(bad)
    assert service_name("https://us02web.zoom.us/j/123") == "Zoom"
    assert service_name("https://chat.whatsapp.com/x") == "WhatsApp"
    assert service_name("https://example.com/room") == "the link"


# --- Fees fixture shared by the export, webhook and API tests ------------------------------


@pytest.fixture
def fees(campus, make_member, make_student, api):
    with tenant_context(campus.tenant):
        item = FeeItem.objects.create(name="Tuition")
        FeeSchedule.objects.create(
            term=campus.term,
            level=ClassLevel.objects.get(name="JHS 1"),
            item=item,
            amount_pesewas=120_000,
        )
    kofi = make_student(campus.tenant, arm=campus.jhs1, first_name="Kofi", last_name="Mensah")
    bursar = make_member(campus.tenant, Role.BURSAR)
    api(bursar, campus.tenant).post(
        "/api/v1/finance/invoices/generate/", {"term": campus.term.pk}, format="json"
    )
    with tenant_context(campus.tenant):
        invoice = Invoice.objects.get(student=kofi)
    return SimpleNamespace(kofi=kofi, invoice=invoice, bursar=api(bursar, campus.tenant))


def test_accounting_export_is_a_balanced_journal(campus, fees, make_member, api):
    set_active(tenant=campus.tenant, code="accounting", active=True, request=None)
    with tenant_context(campus.tenant):
        record_manual_payment(
            request=None, invoice=fees.invoice, amount_pesewas=50_000, method="cash", reference="R1"
        )
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    today = timezone.localdate().isoformat()
    got = head.get(f"/api/v1/accounting/export/journal/?start={today}&end={today}")
    rows = list(csv.DictReader(io.StringIO(got.content.decode())))
    assert rows and {r["Currency"] for r in rows} == {"GHS"}
    debit = sum(Decimal(r["Debit"] or 0) for r in rows)
    credit = sum(Decimal(r["Credit"] or 0) for r in rows)
    assert debit == credit > 0
    assert sum(Decimal(r["Amount"]) for r in rows) == 0
    accounts = head.get("/api/v1/accounting/export/accounts/").content.decode()
    assert accounts.startswith("Account code,Account name,Account type")


# --- Push -------------------------------------------------------------------------------


def test_notifications_are_pushed_and_dead_browsers_dropped(
    campus, make_member, api, settings, monkeypatch, django_capture_on_commit_callbacks
):
    settings.WEB_PUSH_VAPID_PUBLIC_KEY = "public"
    settings.WEB_PUSH_VAPID_PRIVATE_KEY = "private"
    teacher = make_member(campus.tenant, Role.TEACHER)
    client = api(teacher, None)
    assert client.get("/api/v1/push/").json()["enabled"] is True
    for endpoint in ("https://push.example/ok", "https://push.example/gone"):
        made = client.post(
            "/api/v1/push/", {"endpoint": endpoint, "p256dh": "k", "auth": "a"}, format="json"
        )
        assert made.status_code == 201
    sent: list[dict] = []

    from pywebpush import WebPushException

    def fake_webpush(*, subscription_info, data, **kwargs):
        if subscription_info["endpoint"].endswith("gone"):
            raise WebPushException("gone", response=SimpleNamespace(status_code=410))
        sent.append(json.loads(data))

    monkeypatch.setattr("pywebpush.webpush", fake_webpush)
    from apps.communication.services import notify_users

    with tenant_context(campus.tenant), django_capture_on_commit_callbacks(execute=True):
        notify_users([teacher.pk], kind="test", title="Staff meeting", body="At 2 pm today.")
    assert sent == [{"title": "Staff meeting", "body": "At 2 pm today.", "url": "/inbox"}]
    assert list(PushSubscription.objects.values_list("endpoint", flat=True)) == [
        "https://push.example/ok"
    ]


# --- Developer API and webhooks -----------------------------------------------------------


@pytest.fixture
def dev(campus, make_member, api, monkeypatch):
    set_active(tenant=campus.tenant, code="developer_api", active=True, request=None)
    monkeypatch.setattr(developer, "_public_host", lambda host: host != "internal.example")
    owner = make_member(campus.tenant, Role.OWNER)
    return SimpleNamespace(
        owner=api(owner, campus.tenant),
        head=api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant),
    )


def _bearer(key):
    return {"HTTP_AUTHORIZATION": f"Bearer {key}"}


def test_api_keys_read_only_their_scopes_and_school(campus, other_tenant, fees, dev):
    assert (
        dev.head.post(
            "/api/v1/integrations/keys/", {"name": "x", "scopes": ["students:read"]}, format="json"
        ).status_code
        == 403
    )
    made = dev.owner.post(
        "/api/v1/integrations/keys/",
        {"name": "Ledger app", "scopes": ["students:read"]},
        format="json",
    )
    assert made.status_code == 201
    key = made.json()["key"]
    assert (
        key.startswith("nxk_")
        and "key" not in dev.owner.get("/api/v1/integrations/keys/").json()[0]
    )

    pupils = Client().get("/api/v1/developer/students/", **_bearer(key))
    assert pupils.status_code == 200
    row = pupils.json()["results"][0]
    assert row["first_name"] == "Kofi" and "date_of_birth" not in row
    assert Client().get("/api/v1/developer/payments/", **_bearer(key)).status_code == 403
    other = Client().get(
        "/api/v1/developer/students/", HTTP_X_TENANT=other_tenant.slug, **_bearer(key)
    )
    assert other.status_code == 403  # the key is Greenfield's

    set_active(tenant=campus.tenant, code="developer_api", active=False, request=None)
    assert Client().get("/api/v1/developer/students/", **_bearer(key)).status_code == 401
    set_active(tenant=campus.tenant, code="developer_api", active=True, request=None)
    dev.owner.post(f"/api/v1/integrations/keys/{made.json()['id']}/revoke/")
    assert Client().get("/api/v1/developer/students/", **_bearer(key)).status_code == 401


def test_webhooks_are_signed_retried_and_refuse_private_addresses(
    campus, fees, dev, mock_http, django_capture_on_commit_callbacks
):
    private = dev.owner.post(
        "/api/v1/integrations/webhooks/",
        {"url": "https://internal.example/hook", "events": ["payment.received"]},
        format="json",
    )
    assert private.status_code == 400
    made = dev.owner.post(
        "/api/v1/integrations/webhooks/",
        {"url": "https://hooks.example/nexedu", "events": ["payment.received"]},
        format="json",
    ).json()
    secret = made["secret"]
    received: list[httpx.Request] = []
    status = {"code": 500}

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(status["code"])

    mock_http(handler)
    with (
        tenant_context(campus.tenant),
        pytest.raises(Retry),
        django_capture_on_commit_callbacks(execute=True),
    ):
        record_manual_payment(
            request=None, invoice=fees.invoice, amount_pesewas=20_000, method="cash", reference="R2"
        )
    delivery = WebhookDelivery.objects.get()
    assert delivery.status == "pending" and delivery.attempts == 1

    status["code"] = 200
    developer.deliver.apply(args=[str(delivery.pk)])
    delivery.refresh_from_db()
    assert delivery.status == "sent"
    request = received[-1]
    stamp, mac = (
        part.split("=", 1)[1] for part in request.headers["X-NexEdu-Signature"].split(",")
    )
    expected = hmac.new(secret.encode(), f"{stamp}.".encode() + request.content, hashlib.sha256)
    assert hmac.compare_digest(mac, expected.hexdigest())
    payload = json.loads(request.content)
    assert payload["type"] == "payment.received" and payload["data"]["amount_pesewas"] == 20_000
    assert WebhookEndpoint.objects.get().secret != secret  # stored encrypted


# --- Analytics export -------------------------------------------------------------------


def test_analytics_export_has_no_names(campus, fees):
    key = analytics.export_day(timezone.localdate())
    with default_storage.open(key) as handle:
        text = handle.read().decode()
    row = json.loads(text.splitlines()[0])
    assert row["pupils"] == 1 and row["school"] == analytics.school_key(campus.tenant)
    assert row["pupils_by_level"] is None  # fewer than 10 pupils: no breakdown
    for secret in ("Kofi", "Mensah", campus.tenant.slug, campus.tenant.name):
        assert secret not in text


# --- AI drafting help -------------------------------------------------------------------


class FakeClaude:
    """Stands in for anthropic.Anthropic; records what would be sent."""

    calls: list[dict] = []
    reply = "[PUPIL] works hard in Mathematics. Keep reading every day, [PUPIL]!"
    stop = "end_turn"

    def __init__(self, **kwargs):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        FakeClaude.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason=FakeClaude.stop,
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=FakeClaude.reply),
            ],
            usage=SimpleNamespace(input_tokens=120, output_tokens=40),
        )


@pytest.fixture
def drafting(campus, make_member, make_student, api, settings, monkeypatch, assign):
    settings.ANTHROPIC_API_KEY = "sk-test"
    set_active(tenant=campus.tenant, code="ai_assist", active=True, request=None)
    monkeypatch.setattr("anthropic.Anthropic", FakeClaude)
    FakeClaude.calls, FakeClaude.stop = [], "end_turn"
    pupil = make_student(campus.tenant, arm=campus.jhs1, first_name="Abena", last_name="Owusu")
    class_teacher = make_member(campus.tenant, Role.TEACHER)
    assign(class_teacher, campus.jhs1, campus.subjects["MTH"], form=True)
    with tenant_context(campus.tenant):
        card = ReportCard.objects.create(
            student=pupil,
            term=campus.term,
            arm=campus.jhs1,
            lines=[{"subject": "Mathematics", "total": "78", "grade": "B2", "remark": "Very good"}],
            average=Decimal("78"),
            position=3,
            class_size=30,
            days_present=58,
            days_open=60,
            computed_at=timezone.now(),
        )
    return SimpleNamespace(
        card=card,
        teacher=api(class_teacher, campus.tenant),
        other=api(make_member(campus.tenant, Role.TEACHER), campus.tenant),
    )


def test_report_comment_drafts_never_send_the_name(drafting):
    url = "/api/v1/assist/report-comment/"
    draft = drafting.teacher.post(
        url, {"report_card": str(drafting.card.pk), "notes": "Abena helps others"}, format="json"
    )
    assert draft.status_code == 200, draft.content
    assert draft.json()["draft"].startswith("Abena works hard")
    sent = json.dumps(FakeClaude.calls[0], default=str)
    assert "Abena" not in sent and "Owusu" not in sent and "[NAME-1] helps others" in sent
    call = FakeClaude.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    assert "temperature" not in call
    assert (
        drafting.other.post(url, {"report_card": str(drafting.card.pk)}, format="json").status_code
        == 404  # a teacher who does not teach the pupil cannot see the card at all
    )

    FakeClaude.stop = "refusal"
    declined = drafting.teacher.post(url, {"report_card": str(drafting.card.pk)}, format="json")
    assert declined.status_code == 503 and declined.json()["code"] == "draft_unavailable"


def test_announcement_drafts_hide_names_and_need_the_module(campus, drafting, make_member, api):
    FakeClaude.reply = "Title: Science fair\n\nCome and see [NAME-1]'s project on Friday."
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    got = admin.post(
        "/api/v1/assist/announcement/",
        {"notes": "science fair friday, abena owusu won"},
        format="json",
    ).json()
    assert got["title"] == "Science fair" and "abena" in got["body"].lower()
    assert "abena" not in json.dumps(FakeClaude.calls[-1], default=str).lower()
    set_active(tenant=campus.tenant, code="ai_assist", active=False, request=None)
    assert (
        admin.post("/api/v1/assist/announcement/", {"notes": "x"}, format="json").status_code == 403
    )
