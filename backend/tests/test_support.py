"""Learning support: plans, who sees what, notes kept confidential, test extra time."""

from __future__ import annotations

import datetime as dt

import pytest
from django.db import connections
from django.utils import timezone

from apps.exams.api.views import deadline
from apps.exams.models import Attempt
from apps.exams.models import Test as OnlineTest
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context
from core.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

URL = "/api/v1/support/plans/"


@pytest.fixture
def school(campus, make_member, make_student, api, assign):
    set_active(tenant=campus.tenant, code="special_ed", active=True, request=None)
    teacher_user = make_member(campus.tenant, Role.TEACHER)
    assign(teacher_user, campus.jhs1, campus.subjects["MTH"])
    child = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(student=child, guardian_user_id=parent_user.pk)
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    plan = head.post(
        URL,
        {
            "student": str(child.pk),
            "needs": ["learning", "vision"],
            "summary": "Confidential: diagnosed dyslexia, report from Korle Bu.",
            "goals": [{"goal": "Read a short passage aloud", "measure": "Termly reading check"}],
            "adjustments": "Front seat; large print; 25% extra time in tests.",
            "extra_time_percent": 25,
        },
        format="json",
    )
    assert plan.status_code == 201, plan.content
    return {
        "head": head,
        "teacher": api(teacher_user, campus.tenant),
        "other": api(make_member(campus.tenant, Role.TEACHER), campus.tenant),
        "parent": api(parent_user, campus.tenant),
        "plan": plan.json()["id"],
        "child": child,
    }


def test_teachers_see_adjustments_not_the_confidential_summary(campus, school):
    seen = school["teacher"].get(URL).json()
    assert len(seen) == 1 and "summary" not in seen[0]
    assert seen[0]["adjustments"].startswith("Front seat")
    assert school["other"].get(URL).json() == []  # doesn't teach the pupil
    assert (
        school["teacher"]
        .post(URL, {"student": str(school["child"].pk), "needs": ["other"]}, format="json")
        .status_code
        == 403
    )
    # Parents only once shared.
    assert school["parent"].get(URL).json() == []
    school["head"].patch(f"{URL}{school['plan']}/", {"shared_with_parents": True}, format="json")
    shared = school["parent"].get(URL).json()
    assert len(shared) == 1 and "summary" not in shared[0]


def test_summary_and_notes_are_encrypted_and_reads_audited(campus, school):
    full = school["head"].get(f"{URL}{school['plan']}/").json()
    assert full["summary"].startswith("Confidential")
    school["head"].post(
        f"{URL}{school['plan']}/add_note/", {"text": "Reading age up six months."}, format="json"
    )
    notes = school["head"].get(f"{URL}{school['plan']}/notes/").json()
    assert notes[0]["text"] == "Reading age up six months."
    assert school["teacher"].get(f"{URL}{school['plan']}/notes/").status_code == 403
    with tenant_context(campus.tenant):
        with connections[campus.tenant.db_alias].cursor() as cursor:
            cursor.execute("SELECT summary FROM support_plan")
            (stored,) = cursor.fetchone()
        assert "dyslexia" not in stored
        assert AuditEvent.objects.filter(action="support.notes_read").exists()
    again = school["head"].post(
        URL, {"student": str(school["child"].pk), "needs": ["other"]}, format="json"
    )
    assert again.status_code == 400  # one active plan per pupil


def test_extra_time_applies_to_online_tests(campus, school):
    now = timezone.now()
    with tenant_context(campus.tenant):
        test = OnlineTest.objects.create(
            arm=campus.jhs1,
            subject=campus.subjects["MTH"],
            title="Quiz",
            opens_at=now,
            closes_at=now + dt.timedelta(hours=2),
            minutes=40,
            created_by=school["child"].pk,
        )
        attempt = Attempt.objects.create(test=test, student=school["child"], started_at=now)
        assert deadline(test, attempt) == now + dt.timedelta(minutes=50)
