"""Behaviour and discipline: who reports, who sees, what parents are told."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.communication.models import Notification
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context
from core.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

URL = "/api/v1/discipline/incidents/"


@pytest.fixture
def school(campus, make_member, make_student, api, assign):
    set_active(tenant=campus.tenant, code="discipline", active=True, request=None)
    teacher_user = make_member(campus.tenant, Role.TEACHER)
    assign(teacher_user, campus.jhs1, campus.subjects["MTH"])
    other_user = make_member(campus.tenant, Role.TEACHER)
    assign(other_user, campus.jhs2, campus.subjects["MTH"])
    child = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(student=child, guardian_user_id=parent_user.pk)
    return {
        "teacher": api(teacher_user, campus.tenant),
        "other": api(other_user, campus.tenant),
        "head": api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant),
        "parent": api(parent_user, campus.tenant),
        "parent_user": parent_user,
        "child": child,
    }


def _report(client, student, **extra):
    return client.post(
        URL,
        {
            "student": str(student.pk),
            "date": timezone.localdate().isoformat(),
            "category": "fighting",
            "severity": "moderate",
            "description": "Pushed another pupil at break. Staff note: witnessed by Mr Asare.",
            **extra,
        },
        format="json",
    )


def test_teachers_report_about_their_own_pupils(campus, school):
    made = _report(school["teacher"], school["child"])
    assert made.status_code == 201, made.content
    assert _report(school["other"], school["child"]).status_code == 403
    assert school["other"].get(URL).json() == []
    assert len(school["teacher"].get(URL).json()) == 1
    # Only leaders record what was done.
    incident = made.json()["id"]
    assert (
        school["teacher"]
        .post(f"{URL}{incident}/add_action/", {"kind": "warning", "date": "2026-10-01"})
        .status_code
        == 403
    )


def test_parents_see_only_what_leaders_share(campus, school):
    incident = _report(school["teacher"], school["child"]).json()["id"]
    assert school["parent"].get(URL).json() == []
    head = school["head"]
    suspended = head.post(
        f"{URL}{incident}/add_action/",
        {"kind": "suspension", "date": timezone.localdate().isoformat()},
        format="json",
    )
    assert suspended.status_code == 400  # needs the number of days
    head.post(
        f"{URL}{incident}/add_action/",
        {"kind": "detention", "date": timezone.localdate().isoformat(), "notes": "Staff only"},
        format="json",
    )
    shared = head.post(
        f"{URL}{incident}/share/",
        {"summary": "Kojo was in a scuffle at break and has a detention on Friday."},
        format="json",
    )
    assert shared.status_code == 200
    seen = school["parent"].get(URL).json()
    assert len(seen) == 1
    assert seen[0]["shared_summary"].startswith("Kojo was in a scuffle")
    assert "description" not in seen[0] and "reported_by" not in seen[0]
    assert seen[0]["actions"] == [
        {"kind_label": "Detention", "date": timezone.localdate().isoformat(), "days": None}
    ]
    with tenant_context(campus.tenant):
        alert = Notification.objects.get(
            recipient_user_id=school["parent_user"].pk, kind="behaviour"
        )
    assert "Staff note" not in alert.body


def test_counselling_notes_are_confidential_and_reads_are_audited(campus, school):
    url = "/api/v1/discipline/counselling/"
    note = {
        "student": str(school["child"].pk),
        "date": timezone.localdate().isoformat(),
        "notes": "Private.",
    }
    assert school["teacher"].post(url, note, format="json").status_code == 403
    assert school["head"].post(url, note, format="json").status_code == 201
    assert school["teacher"].get(url, {"student": str(school["child"].pk)}).status_code == 403
    read = school["head"].get(url, {"student": str(school["child"].pk)}).json()
    assert [n["notes"] for n in read] == ["Private."]
    with tenant_context(campus.tenant):
        assert AuditEvent.objects.filter(action="discipline.counselling_read").count() == 1


def test_summary_counts_repeat_incidents(campus, school):
    for _ in range(3):
        _report(school["teacher"], school["child"])
    summary = school["head"].get("/api/v1/discipline/summary/").json()
    assert summary["total"] == 3 and summary["open"] == 3
    assert summary["repeat"][0]["count"] == 3
    assert summary["by_category"][0]["label"] == "Fighting"
    assert school["teacher"].get("/api/v1/discipline/summary/").status_code == 403


def test_reporter_edits_only_while_open(campus, school):
    incident = _report(school["teacher"], school["child"]).json()["id"]
    assert (
        school["teacher"]
        .patch(f"{URL}{incident}/", {"location": "Field"}, format="json")
        .status_code
        == 200
    )
    school["head"].post(f"{URL}{incident}/resolve/")
    assert (
        school["teacher"]
        .patch(f"{URL}{incident}/", {"location": "Hall"}, format="json")
        .status_code
        == 403
    )
    future = _report(school["teacher"], school["child"], date="2999-01-01")
    assert future.status_code == 400
