from __future__ import annotations

import json

import httpx

from apps.communication.models import Delivery, Notification
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.tenancy import tenant_context
from integrations.messaging import ArkeselSms


def _guardian(tenant, student, user=None, phone="+233244123456"):
    with tenant_context(tenant):
        StudentGuardian.objects.create(
            student=student, guardian_user_id=getattr(user, "pk", None), phone=phone
        )


def test_class_announcement_reaches_parents_by_inbox_and_sms(
    campus, make_member, make_student, api
):
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    parent = make_member(campus.tenant, Role.PARENT, mfa=False)
    in_class = make_student(campus.tenant, arm=campus.jhs1)
    elsewhere = make_student(campus.tenant, arm=campus.jhs2)
    _guardian(campus.tenant, in_class, parent)
    _guardian(campus.tenant, elsewhere, phone="+233551234567")

    created = admin.post(
        "/api/v1/communication/announcements/",
        {
            "title": "PTA meeting",
            "body": "Saturday 10am in the assembly hall.",
            "audience": "arm_parents",
            "arm": str(campus.jhs1.pk),
            "channels": ["sms"],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    published = admin.post(f"/api/v1/communication/announcements/{created.data['id']}/publish/")
    assert published.data["status"] == "published"
    with tenant_context(campus.tenant):
        assert Notification.objects.filter(recipient_user_id=parent.pk).count() == 1
        sms = list(Delivery.objects.filter(channel="sms"))
        assert [d.to for d in sms] == ["+233244123456"]
        assert sms[0].status == "sent"
        assert sms[0].body.startswith("Greenfield: PTA meeting.")

    inbox = api(parent, campus.tenant).get("/api/v1/communication/notifications/").data["results"]
    assert [n["title"] for n in inbox] == ["PTA meeting"]
    feed = api(parent, campus.tenant).get("/api/v1/communication/announcements/").data["results"]
    assert len(feed) == 1


def test_teachers_message_only_their_own_classes(campus, make_member, assign, api):
    teacher = make_member(campus.tenant, Role.TEACHER)
    assign(teacher, campus.jhs1, campus.subjects["ENG"])
    client = api(teacher, campus.tenant)
    ok = client.post(
        "/api/v1/communication/announcements/",
        {
            "title": "Homework",
            "body": "Read chapter 3.",
            "audience": "arm_parents",
            "arm": str(campus.jhs1.pk),
        },
        format="json",
    )
    assert ok.status_code == 201
    for body in ({"audience": "arm_parents", "arm": str(campus.jhs2.pk)}, {"audience": "everyone"}):
        denied = client.post(
            "/api/v1/communication/announcements/",
            {"title": "x", "body": "y", **body},
            format="json",
        )
        assert denied.status_code == 403


def _announce_by_sms(admin):
    created = admin.post(
        "/api/v1/communication/announcements/",
        {
            "title": "Closing",
            "body": "School closes at noon.",
            "audience": "parents",
            "channels": ["sms"],
        },
        format="json",
    )
    admin.post(f"/api/v1/communication/announcements/{created.data['id']}/publish/")


def test_sms_stop_at_the_allowance_then_use_bought_bundles(campus, make_member, make_student, api):
    from control_plane.models import BillingSettings, SmsCredit
    from control_plane.subscriptions import add_sms

    billing = BillingSettings.load()
    billing.sms_included_monthly = 1
    billing.save()
    for phone in ("+233244123456", "+233551234567", "+233201234567"):
        _guardian(campus.tenant, make_student(campus.tenant, arm=campus.jhs1), phone=phone)
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    _announce_by_sms(admin)
    with tenant_context(campus.tenant):
        statuses = sorted(Delivery.objects.values_list("status", flat=True))
        assert statuses == ["sent", "skipped", "skipped"]
    usage = admin.get("/api/v1/communication/deliveries/usage/").data
    assert usage == {"sms_sent_this_month": 1, "sms_monthly_limit": 1, "sms_bought": 0}

    add_sms(campus.tenant, 5)  # a bundle bought through Paystack
    _announce_by_sms(admin)
    with tenant_context(campus.tenant):
        assert Delivery.objects.filter(status="sent").count() == 4
    assert SmsCredit.objects.get(tenant=campus.tenant).balance == 2


def test_inbox_is_private_and_mark_read(campus, make_member, api):
    a = make_member(campus.tenant, Role.TEACHER)
    b = make_member(campus.tenant, Role.TEACHER)
    with tenant_context(campus.tenant):
        Notification.objects.create(recipient_user_id=a.pk, kind="x", title="For A", body="")
    client_b = api(b, campus.tenant)
    assert client_b.get("/api/v1/communication/notifications/").data["results"] == []
    client_a = api(a, campus.tenant)
    assert client_a.get("/api/v1/communication/notifications/unread_count/").data == {"unread": 1}
    client_a.post("/api/v1/communication/notifications/read_all/")
    assert client_a.get("/api/v1/communication/notifications/unread_count/").data == {"unread": 0}


def test_arkesel_request_format(settings, mock_http):
    settings.ARKESEL_API_KEY = "ark-key"
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "success", "data": [{"id": "msg-1"}]})

    mock_http(handler)
    assert ArkeselSms().send(to="+233244123456", body="Hello", sender_id="GreenfieldSch") == "msg-1"
    payload = json.loads(seen[0].content)
    assert seen[0].url.path == "/api/v2/sms/send"
    assert seen[0].headers["api-key"] == "ark-key"
    assert payload == {"sender": "GreenfieldS", "message": "Hello", "recipients": ["233244123456"]}
