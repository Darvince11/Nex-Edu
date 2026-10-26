"""Compliance: starter list, renewals roll on, reminders, evidence for head and owner."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.communication.models import Notification
from apps.compliance import services
from apps.compliance.models import Requirement
from apps.compliance.tasks import remind_all_tenants
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context
from core.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

URL = "/api/v1/compliance/items/"


@pytest.fixture
def office(campus, make_member, api):
    set_active(tenant=campus.tenant, code="compliance", active=True, request=None)
    head_user = make_member(campus.tenant, Role.PRINCIPAL)
    return {
        "head": api(head_user, campus.tenant),
        "head_user": head_user,
        "teacher": api(make_member(campus.tenant, Role.TEACHER), campus.tenant),
    }


def test_starter_checklist_is_added_once(campus, office):
    first = office["head"].post(f"{URL}starter/").json()["added"]
    assert first == len(services.STARTER)
    assert office["head"].post(f"{URL}starter/").json() == {"added": 0}
    titles = [i["title"] for i in office["head"].get(URL).json()]
    assert "Fire certificate" in titles


def test_renewals_roll_on_and_due_states_follow_the_date(campus, office):
    today = timezone.localdate()
    item = (
        office["head"]
        .post(
            URL,
            {
                "area": "safety",
                "title": "Fire certificate",
                "due_on": (today + dt.timedelta(days=10)).isoformat(),
                "renew_every_months": 12,
            },
            format="json",
        )
        .json()
    )
    assert item["state"] == "due_soon"
    done = office["head"].post(f"{URL}{item['id']}/complete/").json()
    assert done["status"] == "done" and done["state"] == "done"
    assert done["due_on"] == services.add_months(today + dt.timedelta(days=10), 12).isoformat()

    once = (
        office["head"]
        .post(URL, {"title": "Register with DPC", "area": "data"}, format="json")
        .json()
    )
    finished = office["head"].post(f"{URL}{once['id']}/complete/").json()
    assert finished["state"] == "done" and finished["due_on"] is None
    assert office["head"].post(f"{URL}{once['id']}/reopen/").json()["state"] == "open"

    late = (
        office["head"]
        .post(
            URL,
            {"title": "Licence", "due_on": (today - dt.timedelta(days=1)).isoformat()},
            format="json",
        )
        .json()
    )
    assert late["state"] == "overdue"
    assert services.add_months(dt.date(2027, 1, 31), 1) == dt.date(2027, 2, 28)


def test_reminders_go_to_leaders_weekly(campus, office):
    today = timezone.localdate()
    with tenant_context(campus.tenant):
        Requirement.objects.create(title="Fire certificate", due_on=today + dt.timedelta(days=5))
        Requirement.objects.create(title="Far off", due_on=today + dt.timedelta(days=200))
    assert remind_all_tenants() == 1
    assert remind_all_tenants() == 0  # not again within the week
    with tenant_context(campus.tenant):
        sent = Notification.objects.filter(
            recipient_user_id=office["head_user"].pk, kind="compliance.due"
        )
        assert sent.count() == 1 and "due soon" in sent.get().title


def test_evidence_is_uploaded_downloaded_and_kept_to_leaders(campus, office):
    item = office["head"].post(URL, {"title": "Fire certificate"}, format="json").json()
    upload = SimpleUploadedFile("cert.pdf", b"%PDF-1.4 certificate", content_type="application/pdf")
    added = office["head"].post(f"{URL}{item['id']}/upload/", {"file": upload}, format="multipart")
    assert added.status_code == 201, added.content
    evidence = added.json()["id"]
    got = office["head"].get(f"{URL}{item['id']}/evidence/{evidence}/")
    assert got.status_code == 200 and b"".join(got.streaming_content).startswith(b"%PDF")
    assert office["teacher"].get(f"{URL}{item['id']}/evidence/{evidence}/").status_code == 403
    assert office["teacher"].get(URL).status_code == 403

    bad = SimpleUploadedFile("run.exe", b"MZ", content_type="application/octet-stream")
    assert (
        office["head"]
        .post(f"{URL}{item['id']}/upload/", {"file": bad}, format="multipart")
        .status_code
        == 400
    )

    gone = office["head"].delete(f"{URL}{item['id']}/evidence/{evidence}/remove/")
    assert gone.status_code == 204
    assert office["head"].get(f"{URL}{item['id']}/").json()["evidence"] == []
    with tenant_context(campus.tenant):
        assert AuditEvent.objects.filter(action="compliance.evidence_removed").exists()
