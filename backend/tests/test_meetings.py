"""Parent meetings: days, slots, booking rules and notices."""

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

URL = "/api/v1/meetings/"


@pytest.fixture
def day(campus, make_member, make_student, api, assign):
    """A meeting day 9:00-10:00 in 15-minute slots with the JHS 1 maths teacher,
    and a parent with a child in JHS 1."""
    set_active(tenant=campus.tenant, code="meetings", active=True, request=None)
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    maths_user = make_member(campus.tenant, Role.TEACHER)
    assign(maths_user, campus.jhs1, campus.subjects["MTH"])
    other_user = make_member(campus.tenant, Role.TEACHER)
    assign(other_user, campus.jhs2, campus.subjects["MTH"])
    child = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(student=child, guardian_user_id=parent_user.pk)
    made = head.post(
        URL,
        {
            "title": "End of term meetings",
            "date": (timezone.localdate() + dt.timedelta(days=7)).isoformat(),
            "starts_at": "09:00",
            "ends_at": "10:00",
            "slot_minutes": 15,
        },
        format="json",
    )
    assert made.status_code == 201, made.content
    meeting = made.json()
    for teacher in (maths_user, other_user):
        added = head.post(
            f"{URL}{meeting['id']}/add_teacher/", {"user": str(teacher.pk), "room": "JHS 1"}
        )
        assert added.status_code == 201, added.content
    return {
        "id": meeting["id"],
        "head": head,
        "maths": api(maths_user, campus.tenant),
        "maths_user": maths_user,
        "parent": api(parent_user, campus.tenant),
        "parent_user": parent_user,
        "child": child,
    }


def _first_free(day):
    view = day["parent"].get(f"{URL}{day['id']}/").json()
    (child,) = view["children"]
    (teacher,) = child["teachers"]  # only the teacher who teaches Kojo's class
    return teacher, [s for s in teacher["slots"] if s["free"]]


def test_parents_book_only_once_bookings_open(campus, day):
    assert day["parent"].get(URL).json() == []  # not open yet
    assert day["head"].post(f"{URL}{day['id']}/open/").json() == {"parents": 1}
    with tenant_context(campus.tenant):
        assert Notification.objects.filter(
            recipient_user_id=day["parent_user"].pk, kind="meeting"
        ).exists()
    teacher, free = _first_free(day)
    assert teacher["teaches"] == "Mathematics" and len(free) == 4
    booked = day["parent"].post(
        f"{URL}{day['id']}/slots/{free[0]['id']}/book/",
        {"student": str(day["child"].pk), "note": "Homework"},
        format="json",
    )
    assert booked.status_code == 201, booked.content
    # One time per child with each teacher.
    twice = day["parent"].post(
        f"{URL}{day['id']}/slots/{free[1]['id']}/book/",
        {"student": str(day["child"].pk)},
        format="json",
    )
    assert twice.status_code == 400
    teacher, free_now = _first_free(day)
    assert teacher["booking"]["note"] == "Homework" and len(free_now) == 3

    schedule = day["maths"].get(f"{URL}{day['id']}/").json()["schedule"]
    (mine,) = schedule
    assert mine["booked"] == 1 and "Kojo" in mine["slots"][0]["student_name"]
    with tenant_context(campus.tenant):
        assert Notification.objects.filter(
            recipient_user_id=day["maths_user"].pk, title="Parent meeting booked"
        ).exists()


def test_parents_cannot_book_for_other_children_or_other_teachers(
    campus, day, make_student, make_member, api
):
    day["head"].post(f"{URL}{day['id']}/open/")
    other_child = make_student(campus.tenant, arm=campus.jhs1)
    _, free = _first_free(day)
    refused = day["parent"].post(
        f"{URL}{day['id']}/slots/{free[0]['id']}/book/",
        {"student": str(other_child.pk)},
        format="json",
    )
    assert refused.status_code == 403
    staff = day["head"].get(f"{URL}{day['id']}/").json()["schedule"]
    jhs2_teacher = next(
        t for t in staff if t["booked"] == 0 and t["slots"][0]["id"] != free[0]["id"]
    )
    wrong = day["parent"].post(
        f"{URL}{day['id']}/slots/{jhs2_teacher['slots'][0]['id']}/book/",
        {"student": str(day["child"].pk)},
        format="json",
    )
    assert wrong.status_code == 403


def test_cancelling_tells_the_other_side(campus, day):
    day["head"].post(f"{URL}{day['id']}/open/")
    _, free = _first_free(day)
    slot = free[0]["id"]
    day["parent"].post(
        f"{URL}{day['id']}/slots/{slot}/book/", {"student": str(day["child"].pk)}, format="json"
    )
    assert day["maths"].post(f"{URL}{day['id']}/slots/{slot}/cancel/").status_code == 204
    with tenant_context(campus.tenant):
        assert Notification.objects.filter(
            recipient_user_id=day["parent_user"].pk, title="Parent meeting cancelled"
        ).exists()
    _, free = _first_free(day)
    assert len(free) == 4
    # A day with bookings can't be deleted; times can't change once teachers are added.
    day["parent"].post(
        f"{URL}{day['id']}/slots/{slot}/book/", {"student": str(day["child"].pk)}, format="json"
    )
    assert day["head"].delete(f"{URL}{day['id']}/").status_code == 400
    assert (
        day["head"].patch(f"{URL}{day['id']}/", {"slot_minutes": 10}, format="json").status_code
        == 400
    )


def test_only_leaders_set_up_days(campus, day):
    assert day["maths"].post(URL, {"title": "x"}, format="json").status_code == 403
    assert (
        day["maths"]
        .post(f"{URL}{day['id']}/add_teacher/", {"user": str(day["maths_user"].pk)})
        .status_code
        == 403
    )
