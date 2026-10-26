"""The gate: visitors in and out, who may collect each pupil, and pick-up notes."""

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

URL = "/api/v1/gate/"


@pytest.fixture
def gate(campus, make_member, make_student, api):
    set_active(tenant=campus.tenant, code="visitors", active=True, request=None)
    child = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    other = make_student(campus.tenant, arm=campus.jhs1)
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(student=child, guardian_user_id=parent_user.pk)
    return {
        "guard": api(make_member(campus.tenant, Role.GATE), campus.tenant),
        "parent": api(parent_user, campus.tenant),
        "parent_user": parent_user,
        "teacher": api(make_member(campus.tenant, Role.TEACHER), campus.tenant),
        "child": child,
        "other": other,
    }


def test_visitors_sign_in_and_out_with_their_id_encrypted(campus, gate):
    made = gate["guard"].post(
        f"{URL}visits/",
        {"name": "Mr Boateng", "purpose": "Delivering books", "id_number": "GHA-123456789-0"},
        format="json",
    )
    assert made.status_code == 201, made.content
    assert [v["name"] for v in gate["guard"].get(f"{URL}visits/", {"now": "1"}).json()] == [
        "Mr Boateng"
    ]
    gate["guard"].post(f"{URL}visits/{made.json()['id']}/sign_out/")
    assert gate["guard"].get(f"{URL}visits/", {"now": "1"}).json() == []
    with tenant_context(campus.tenant), connections[campus.tenant.db_alias].cursor() as cursor:
        cursor.execute("SELECT id_number FROM visitors_visit")
        (stored,) = cursor.fetchone()
    assert "123456789" not in stored
    assert gate["teacher"].get(f"{URL}visits/").status_code == 403


def test_families_keep_their_own_childs_collector_list(campus, gate):
    added = gate["parent"].post(
        f"{URL}collectors/",
        {"student": str(gate["child"].pk), "name": "Auntie Ama", "relationship": "Aunt"},
        format="json",
    )
    assert added.status_code == 201, added.content
    other = gate["parent"].post(
        f"{URL}collectors/",
        {"student": str(gate["other"].pk), "name": "X", "relationship": "Uncle"},
        format="json",
    )
    assert other.status_code == 403
    assert [c["name"] for c in gate["parent"].get(f"{URL}collectors/").json()] == ["Auntie Ama"]


def test_pickups_are_checked_against_the_list_and_parents_told(campus, gate):
    aunt = (
        gate["parent"]
        .post(
            f"{URL}collectors/",
            {"student": str(gate["child"].pk), "name": "Auntie Ama", "relationship": "Aunt"},
            format="json",
        )
        .json()
    )
    found = gate["guard"].get(f"{URL}check/", {"q": "Kojo"}).json()
    assert (
        found[0]["collectors"][0]["name"] == "Auntie Ama" and found[0]["collected_today"] is False
    )
    ok = gate["guard"].post(
        f"{URL}pickups/", {"student": str(gate["child"].pk), "collector": aunt["id"]}, format="json"
    )
    assert ok.status_code == 201 and ok.json()["authorised"] is True
    # Someone not on the list needs a reason, and it's flagged.
    unlisted = {"student": str(gate["child"].pk), "collected_by_name": "Kwesi"}
    assert gate["guard"].post(f"{URL}pickups/", unlisted, format="json").status_code == 400
    flagged = gate["guard"].post(
        f"{URL}pickups/", {**unlisted, "reason": "Father phoned the office"}, format="json"
    )
    assert flagged.status_code == 201 and flagged.json()["authorised"] is False
    with tenant_context(campus.tenant):
        notes = list(
            Notification.objects.filter(recipient_user_id=gate["parent_user"].pk, kind="pickup")
            .order_by("created_at")
            .values_list("body", flat=True)
        )
        assert AuditEvent.objects.filter(action="gate.pickup_unlisted").exists()
    assert "Auntie Ama (Aunt)" in notes[0]
    assert "not on your list" in notes[1] and "Father phoned" in notes[1]
    assert len(gate["parent"].get(f"{URL}pickups/").json()) == 2
    assert gate["parent"].post(f"{URL}pickups/", unlisted, format="json").status_code == 403
