"""Boarding: houses and beds, roll call, exeats from request to return."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.communication.models import Notification
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/hostel/"


@pytest.fixture
def house(campus, make_member, make_student, api):
    set_active(tenant=campus.tenant, code="hostel", active=True, request=None)
    head_user = make_member(campus.tenant, Role.PRINCIPAL)
    head = api(head_user, campus.tenant)
    warden_user = make_member(campus.tenant, Role.WARDEN)
    made = head.post(
        f"{URL}houses/",
        {"name": "Aggrey House", "gender": "boys", "warden_user_id": str(warden_user.pk)},
        format="json",
    )
    assert made.status_code == 201, made.content
    room = head.post(
        f"{URL}rooms/", {"house": made.json()["id"], "name": "Room 1", "beds": 1}, format="json"
    ).json()
    child = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    other = make_student(campus.tenant, arm=campus.jhs1)
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(student=child, guardian_user_id=parent_user.pk)
    return {
        "head": head,
        "head_user": head_user,
        "warden": api(warden_user, campus.tenant),
        "other_warden": api(make_member(campus.tenant, Role.WARDEN), campus.tenant),
        "parent": api(parent_user, campus.tenant),
        "parent_user": parent_user,
        "house": made.json()["id"],
        "room": room["id"],
        "child": child,
        "other": other,
    }


def test_beds_and_roll_call(campus, house):
    give = f"{URL}boarders/"
    assert (
        house["warden"]
        .post(give, {"student": str(house["child"].pk), "room": house["room"]})
        .status_code
        == 201
    )
    full = house["warden"].post(give, {"student": str(house["other"].pk), "room": house["room"]})
    assert full.status_code == 400 and "full" in str(full.json())
    assert (
        house["other_warden"]
        .post(give, {"student": str(house["other"].pk), "room": house["room"]})
        .status_code
        == 403
    )

    sheet = (
        house["warden"]
        .get(f"{URL}roll-call/", {"house": house["house"], "session": "evening"})
        .json()
    )
    assert [r["name"] for r in sheet["rows"]] == [house["child"].full_name]
    saved = house["warden"].post(
        f"{URL}roll-call/",
        {
            "house": house["house"],
            "date": timezone.localdate().isoformat(),
            "session": "evening",
            "marks": [{"student": str(house["child"].pk), "status": "absent"}],
        },
        format="json",
    )
    assert saved.json() == {"saved": 1, "absent": 1}
    with tenant_context(campus.tenant):
        assert Notification.objects.filter(
            recipient_user_id=house["head_user"].pk, kind="hostel"
        ).exists()
    mine = house["parent"].get(f"{URL}mine/").json()
    assert mine[0]["house"] == "Aggrey House" and mine[0]["roll_calls"][0]["status"] == "Absent"


def test_exeat_from_request_to_return(campus, house):
    house["warden"].post(
        f"{URL}boarders/", {"student": str(house["child"].pk), "room": house["room"]}
    )
    leaves = timezone.localdate() + dt.timedelta(days=1)
    asked = house["parent"].post(
        f"{URL}exeats/",
        {
            "student": str(house["child"].pk),
            "leaves_on": leaves.isoformat(),
            "returns_on": (leaves + dt.timedelta(days=2)).isoformat(),
            "reason": "Family wedding",
            "collected_by": "Father",
        },
        format="json",
    )
    assert asked.status_code == 201, asked.content
    exeat = asked.json()["id"]
    # Not for a pupil who doesn't board.
    not_boarding = house["parent"].post(
        f"{URL}exeats/",
        {
            "student": str(house["other"].pk),
            "leaves_on": leaves.isoformat(),
            "returns_on": leaves.isoformat(),
            "reason": "x",
        },
        format="json",
    )
    assert not_boarding.status_code == 400
    assert house["parent"].post(f"{URL}exeats/{exeat}/approve/").status_code == 403
    assert (
        house["warden"]
        .post(f"{URL}exeats/{exeat}/approve/", {"note": "Back by 6pm"}, format="json")
        .status_code
        == 200
    )

    # The roll call knows they're away.
    sheet = (
        house["warden"]
        .get(
            f"{URL}roll-call/",
            {"house": house["house"], "date": leaves.isoformat(), "session": "evening"},
        )
        .json()
    )
    assert sheet["rows"][0]["status"] == "exeat" and sheet["rows"][0]["on_exeat"] is True

    assert house["warden"].post(f"{URL}exeats/{exeat}/depart/").json()["status"] == "out"
    assert house["warden"].post(f"{URL}exeats/{exeat}/back/").json()["status"] == "returned"
    with tenant_context(campus.tenant):
        titles = list(
            Notification.objects.filter(recipient_user_id=house["parent_user"].pk, kind="exeat")
            .order_by("created_at")
            .values_list("title", flat=True)
        )
    assert titles == ["Exeat approved: Kojo", "Kojo is back at school"]


def test_only_leaders_set_up_houses(campus, house):
    assert (
        house["warden"].post(f"{URL}houses/", {"name": "Other"}, format="json").status_code == 403
    )
    assert house["other_warden"].get(f"{URL}houses/").json() == []
    assert [h["name"] for h in house["warden"].get(f"{URL}houses/").json()] == ["Aggrey House"]
