"""Facilities: rooms, bookings without clashes, repairs and their notes."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.communication.models import Notification
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/facilities/"


@pytest.fixture
def school(campus, make_member, api):
    set_active(tenant=campus.tenant, code="facilities", active=True, request=None)
    admin_user = make_member(campus.tenant, Role.ADMIN)
    admin = api(admin_user, campus.tenant)
    hall = admin.post(
        f"{URL}rooms/", {"name": "Assembly hall", "kind": "hall"}, format="json"
    ).json()
    teacher_user = make_member(campus.tenant, Role.TEACHER)
    return {
        "admin": admin,
        "admin_user": admin_user,
        "teacher": api(teacher_user, campus.tenant),
        "teacher_user": teacher_user,
        "other": api(make_member(campus.tenant, Role.TEACHER), campus.tenant),
        "hall": hall["id"],
        "day": (timezone.localdate() + dt.timedelta(days=2)).isoformat(),
    }


def _book(client, school, start, end, purpose="Rehearsal"):
    return client.post(
        f"{URL}bookings/",
        {
            "room": school["hall"],
            "date": school["day"],
            "starts_at": start,
            "ends_at": end,
            "purpose": purpose,
        },
        format="json",
    )


def test_bookings_never_clash(campus, school):
    assert _book(school["teacher"], school, "10:00", "11:00").status_code == 201
    clash = _book(school["other"], school, "10:30", "11:30", "PTA")
    assert clash.status_code == 400 and "Rehearsal" in str(clash.json())
    assert (
        _book(school["other"], school, "11:00", "12:00", "PTA").status_code == 201
    )  # back to back is fine
    past = school["teacher"].post(
        f"{URL}bookings/",
        {
            "room": school["hall"],
            "date": "2020-01-01",
            "starts_at": "09:00",
            "ends_at": "10:00",
            "purpose": "x",
        },
        format="json",
    )
    assert past.status_code == 400
    day = school["teacher"].get(f"{URL}bookings/", {"date": school["day"]}).json()
    assert [b["purpose"] for b in day] == ["Rehearsal", "PTA"]
    assert [b["mine"] for b in day] == [True, False]


def test_only_the_booker_or_a_leader_cancels(campus, school):
    booking = _book(school["teacher"], school, "10:00", "11:00").json()["id"]
    assert school["other"].delete(f"{URL}bookings/{booking}/").status_code == 403
    assert school["admin"].delete(f"{URL}bookings/{booking}/").status_code == 204
    # Only managers keep the room list.
    assert school["teacher"].post(f"{URL}rooms/", {"name": "Lab"}, format="json").status_code == 403


def test_repairs_are_reported_followed_and_closed(campus, school):
    reported = school["teacher"].post(
        f"{URL}repairs/",
        {"room": school["hall"], "title": "Broken window", "priority": "urgent"},
        format="json",
    )
    assert reported.status_code == 201, reported.content
    repair = reported.json()["id"]
    with tenant_context(campus.tenant):
        assert Notification.objects.filter(
            recipient_user_id=school["admin_user"].pk, title="Urgent repair: Broken window"
        ).exists()
    # The reporter sees their own, can't move it along.
    assert len(school["teacher"].get(f"{URL}repairs/").json()) == 1
    assert school["other"].get(f"{URL}repairs/").json() == []
    assert (
        school["teacher"]
        .patch(f"{URL}repairs/{repair}/", {"status": "done"}, format="json")
        .status_code
        == 403
    )
    done = school["admin"].patch(
        f"{URL}repairs/{repair}/",
        {
            "status": "done",
            "assigned_to": "Kofi the carpenter",
            "cost_pesewas": 25000,
            "outcome": "Glass replaced.",
        },
        format="json",
    )
    assert done.status_code == 200 and done.json()["closed_at"]
    with tenant_context(campus.tenant):
        note = Notification.objects.get(
            recipient_user_id=school["teacher_user"].pk, kind="facilities"
        )
    assert note.body == "Glass replaced."
    assert school["admin"].get(f"{URL}repairs/", {"status": "open"}).json() == []
    nowhere = school["teacher"].post(f"{URL}repairs/", {"title": "Leak"}, format="json")
    assert nowhere.status_code == 400
