"""Clubs and sports: leaders set up clubs, patrons run them, families see their own."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/clubs/"


@pytest.fixture
def school(campus, make_member, make_student, api):
    set_active(tenant=campus.tenant, code="clubs", active=True, request=None)
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    patron_user = make_member(campus.tenant, Role.TEACHER)
    other_user = make_member(campus.tenant, Role.TEACHER)
    club = head.post(
        URL, {"name": "Football", "kind": "sport", "capacity": 2}, format="json"
    ).json()
    assert (
        head.post(f"{URL}{club['id']}/add_patron/", {"user": str(patron_user.pk)}).status_code
        == 201
    )
    child = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    other = make_student(campus.tenant, arm=campus.jhs1, first_name="Yaw")
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(student=child, guardian_user_id=parent_user.pk)
    return {
        "club": club,
        "head": head,
        "patron": api(patron_user, campus.tenant),
        "other": api(other_user, campus.tenant),
        "parent": api(parent_user, campus.tenant),
        "child": child,
        "other_child": other,
    }


def test_a_patron_runs_their_club_and_others_cannot(campus, school, make_student):
    club = school["club"]
    add = f"{URL}{club['id']}/add_member/"
    assert (
        school["patron"]
        .post(add, {"student": str(school["child"].pk), "title": "Captain"})
        .status_code
        == 201
    )
    assert school["other"].post(add, {"student": str(school["other_child"].pk)}).status_code == 403
    assert (
        school["patron"].post(add, {"student": str(school["child"].pk)}).status_code == 400
    )  # already in
    assert school["patron"].post(add, {"student": str(school["other_child"].pk)}).status_code == 201
    third = make_student(campus.tenant, arm=campus.jhs2)
    full = school["patron"].post(add, {"student": str(third.pk)})
    assert full.status_code == 400 and "full" in str(full.json())

    match = school["patron"].post(
        f"{URL}{club['id']}/add_activity/",
        {
            "title": "Inter-schools match",
            "kind": "match",
            "date": (timezone.localdate() + dt.timedelta(days=3)).isoformat(),
            "opponent": "Royal Heights",
        },
        format="json",
    )
    assert match.status_code == 201, match.content
    activity = match.json()["id"]
    assert (
        school["other"]
        .patch(f"{URL}activities/{activity}/", {"result": "Lost"}, format="json")
        .status_code
        == 403
    )
    assert (
        school["patron"]
        .patch(f"{URL}activities/{activity}/", {"result": "Won 2-1"}, format="json")
        .json()["result"]
        == "Won 2-1"
    )
    detail = school["patron"].get(f"{URL}{club['id']}/").json()
    assert {m["title"] for m in detail["members"]} == {"Captain", ""}
    assert detail["can_run"] is True and len(detail["upcoming"]) == 1
    # Only leaders set up clubs and choose patrons.
    assert school["patron"].post(URL, {"name": "Chess"}, format="json").status_code == 403


def test_families_see_their_own_children_only(campus, school):
    club = school["club"]
    for pupil in ("child", "other_child"):
        school["patron"].post(f"{URL}{club['id']}/add_member/", {"student": str(school[pupil].pk)})
    school["patron"].post(
        f"{URL}{club['id']}/add_activity/",
        {"title": "Practice", "kind": "practice", "date": timezone.localdate().isoformat()},
        format="json",
    )
    parent = school["parent"]
    listed = parent.get(URL).json()
    assert listed[0]["my_children"] == ["Kojo"] and listed[0]["member_count"] == 2
    detail = parent.get(f"{URL}{club['id']}/").json()
    assert "members" not in detail  # no other pupils' names
    mine = parent.get(f"{URL}activities/", {"mine": "1", "upcoming": "1"}).json()
    assert [a["title"] for a in mine] == ["Practice"]
    assert (
        parent.post(
            f"{URL}{club['id']}/add_member/", {"student": str(school["child"].pk)}
        ).status_code
        == 403
    )


def test_leaving_keeps_history_and_patrons_must_be_staff(campus, school, make_member):
    club = school["club"]
    school["patron"].post(f"{URL}{club['id']}/add_member/", {"student": str(school["child"].pk)})
    assert (
        school["patron"]
        .post(f"{URL}{club['id']}/remove_member/", {"student": str(school["child"].pk)})
        .status_code
        == 204
    )
    # They can join again later.
    assert (
        school["patron"]
        .post(f"{URL}{club['id']}/add_member/", {"student": str(school["child"].pk)})
        .status_code
        == 201
    )
    parent = make_member(campus.tenant, Role.PARENT, mfa=False)
    assert (
        school["head"].post(f"{URL}{club['id']}/add_patron/", {"user": str(parent.pk)}).status_code
        == 400
    )


def test_clubs_are_off_until_switched_on(campus, make_member, api):
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    assert head.get(URL).json()["code"] == "module_disabled"
