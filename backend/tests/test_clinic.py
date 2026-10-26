"""The sick bay: the nurse records, teachers and parents see what they should."""

from __future__ import annotations

import pytest
from django.db import connections

from apps.communication.models import Notification
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context
from core.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

URL = "/api/v1/clinic/visits/"


@pytest.fixture
def school(campus, make_member, make_student, api, assign):
    set_active(tenant=campus.tenant, code="clinic", active=True, request=None)
    nurse_user = make_member(campus.tenant, Role.NURSE)
    form_user = make_member(campus.tenant, Role.FORM_TEACHER)
    assign(form_user, campus.jhs1, form=True)
    child = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo", medical_notes="Asthma")
    other = make_student(campus.tenant, arm=campus.jhs2)
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(student=child, guardian_user_id=parent_user.pk)
    return {
        "nurse": api(nurse_user, campus.tenant),
        "form": api(form_user, campus.tenant),
        "parent": api(parent_user, campus.tenant),
        "parent_user": parent_user,
        "subject": api(make_member(campus.tenant, Role.TEACHER), campus.tenant),
        "child": child,
        "other": other,
    }


def _visit(nurse, student, **extra):
    made = nurse.post(
        URL,
        {
            "student": str(student.pk),
            "complaint": "Headache and fever",
            "temperature": "38.4",
            **extra,
        },
        format="json",
    )
    assert made.status_code == 201, made.content
    return made.json()


def test_the_nurse_logs_a_visit_and_parents_are_told_when_sent_home(campus, school):
    visit = _visit(school["nurse"], school["child"])
    assert visit["outcome"] == "" and visit["parents_told_at"] is None
    assert school["nurse"].get(URL, {"now": "1"}).json()[0]["id"] == visit["id"]
    detail = school["nurse"].get(f"{URL}{visit['id']}/").json()
    assert detail["medical_notes"] == "Asthma"
    sent = (
        school["nurse"]
        .patch(
            f"{URL}{visit['id']}/",
            {"outcome": "sent_home", "treatment": "Paracetamol 250mg", "medication": "Paracetamol"},
            format="json",
        )
        .json()
    )
    assert sent["left_at"] and sent["parents_told_at"]
    with tenant_context(campus.tenant):
        alert = Notification.objects.get(recipient_user_id=school["parent_user"].pk, kind="clinic")
        assert "sent home" in alert.body and "fever" not in alert.body
        # Health details are encrypted in the database.
        with connections[campus.tenant.db_alias].cursor() as cursor:
            cursor.execute("SELECT complaint FROM clinic_visit")
            (stored,) = cursor.fetchone()
        assert "fever" not in stored
        assert AuditEvent.objects.filter(action="clinic.viewed").exists()


def test_teachers_see_when_but_not_what(campus, school):
    _visit(school["nurse"], school["child"], outcome="returned")
    _visit(school["nurse"], school["other"], outcome="returned")
    seen = school["form"].get(URL).json()
    assert (
        len(seen) == 1
        and "complaint" not in seen[0]
        and seen[0]["outcome_label"] == "Back to class"
    )
    assert school["subject"].get(URL).status_code == 403
    assert (
        school["form"].post(URL, {"student": str(school["child"].pk), "complaint": "x"}).status_code
        == 403
    )


def test_parents_see_their_own_childs_visits_in_full(campus, school):
    _visit(school["nurse"], school["child"], outcome="rested", treatment="Rest and water")
    _visit(school["nurse"], school["other"], outcome="returned")
    seen = school["parent"].get(URL).json()
    assert len(seen) == 1 and seen[0]["treatment"] == "Rest and water"
    # Back in class after a rest: parents aren't messaged unless the nurse asks.
    with tenant_context(campus.tenant):
        assert not Notification.objects.filter(recipient_user_id=school["parent_user"].pk).exists()


def test_summary_and_pupil_lookup(campus, school):
    for _ in range(4):
        _visit(school["nurse"], school["child"], outcome="returned")
    summary = school["nurse"].get("/api/v1/clinic/summary/").json()
    assert summary["today"] == 4 and summary["in_now"] == 0
    assert summary["frequent"][0]["count"] == 4
    pupil = school["nurse"].get(f"/api/v1/clinic/pupils/{school['child'].pk}/").json()
    assert pupil["medical_notes"] == "Asthma" and len(pupil["visits"]) == 4
    assert school["form"].get("/api/v1/clinic/summary/").status_code == 403
    bad = school["nurse"].post(
        URL,
        {"student": str(school["child"].pk), "complaint": "x", "temperature": "98.6"},
        format="json",
    )
    assert bad.status_code == 400  # Fahrenheit by mistake


def test_head_teacher_adds_a_nurse(campus, make_member, api):
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    invited = head.post(
        "/api/v1/members/", {"email": "nurse@example.test", "role": "nurse"}, format="json"
    )
    assert invited.status_code == 201, invited.content
