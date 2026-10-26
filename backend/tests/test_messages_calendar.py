"""Messages between parents and staff, and the school calendar."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.academics.calendar import easter_sunday, ghana_public_holidays
from apps.communication.models import Delivery, Notification
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/communication/conversations/"


@pytest.fixture
def family(campus, make_student, make_member, assign):
    """A JHS 1 pupil with a parent who has a login, their class and maths teachers,
    a teacher of another class, the head teacher and the proprietor."""
    pupil = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    parent = make_member(campus.tenant, Role.PARENT, mfa=False)
    parent.first_name, parent.last_name = "Efua", "Owusu"
    parent.save()
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(
            student=pupil, guardian_user_id=parent.pk, full_name="Efua Owusu", is_primary=True
        )
    class_teacher = make_member(campus.tenant, Role.FORM_TEACHER)
    maths = make_member(campus.tenant, Role.TEACHER)
    other = make_member(campus.tenant, Role.TEACHER)
    assign(class_teacher, campus.jhs1, form=True)
    assign(maths, campus.jhs1, campus.subjects["MTH"])
    assign(other, campus.jhs2, campus.subjects["MTH"])
    return {
        "pupil": pupil,
        "parent": parent,
        "class_teacher": class_teacher,
        "maths": maths,
        "other": other,
        "head": make_member(campus.tenant, Role.PRINCIPAL),
        "owner": make_member(campus.tenant, Role.OWNER),
    }


def test_a_parent_writes_to_their_childs_teachers_and_the_head(campus, family, api):
    parent = api(family["parent"], campus.tenant)
    contacts = parent.get(f"{URL}contacts/", {"student": str(family["pupil"].pk)}).json()
    who = {c["user"]: c["role"] for c in contacts}
    assert who[str(family["class_teacher"].pk)] == "Class teacher"
    assert who[str(family["head"].pk)] == "Head teacher"
    assert str(family["maths"].pk) in who
    assert str(family["other"].pk) not in who  # doesn't teach this pupil

    started = parent.post(
        URL,
        {
            "student": str(family["pupil"].pk),
            "to": str(family["class_teacher"].pk),
            "subject": "Homework",
            "body": "Kojo was unwell, so his homework is late.",
        },
        format="json",
    )
    assert started.status_code == 201, started.content
    conversation = started.json()["id"]
    refused = parent.post(
        URL,
        {
            "student": str(family["pupil"].pk),
            "to": str(family["other"].pk),
            "subject": "x",
            "body": "x",
        },
        format="json",
    )
    assert refused.status_code == 403

    teacher = api(family["class_teacher"], campus.tenant)
    assert teacher.get(f"{URL}unread_count/").json() == {"unread": 1}
    thread = teacher.get(f"{URL}{conversation}/").json()
    assert [m["body"] for m in thread["messages"]] == ["Kojo was unwell, so his homework is late."]
    assert thread["parent"]["name"] == "Efua Owusu"
    assert teacher.get(f"{URL}unread_count/").json() == {"unread": 0}
    reply = teacher.post(f"{URL}{conversation}/reply/", {"body": "Thanks for letting me know."})
    assert reply.status_code == 201
    assert parent.get(URL).json()[0]["unread"] is True

    with tenant_context(campus.tenant):
        alert = Notification.objects.filter(recipient_user_id=family["parent"].pk, kind="message")
        assert alert.count() == 1
        # Email alerts never carry what was written.
        emails = Delivery.objects.filter(kind="message")
        assert emails.count() == 2
        assert not any("homework is late" in d.body for d in emails)


def test_a_teacher_writes_only_about_pupils_they_teach(campus, family, api):
    other = api(family["other"], campus.tenant)
    message = {
        "student": str(family["pupil"].pk),
        "to": str(family["parent"].pk),
        "subject": "Hello",
        "body": "Hello",
    }
    # The pupil isn't in their classes, so to them the pupil doesn't exist.
    assert other.post(URL, message, format="json").status_code == 404
    maths = api(family["maths"], campus.tenant)
    contacts = maths.get(f"{URL}contacts/", {"student": str(family["pupil"].pk)}).json()
    assert [c["user"] for c in contacts] == [str(family["parent"].pk)]
    assert maths.post(URL, message, format="json").status_code == 201


def test_the_head_can_read_but_not_write_in_others_conversations(campus, family, api):
    maths = api(family["maths"], campus.tenant)
    conversation = maths.post(
        URL,
        {
            "student": str(family["pupil"].pk),
            "to": str(family["parent"].pk),
            "subject": "Test results",
            "body": "Kojo did well.",
        },
        format="json",
    ).json()["id"]
    head = api(family["head"], campus.tenant)
    assert head.get(URL).json() == []  # their own inbox is empty
    everyone = head.get(URL, {"all": "1"}).json()
    assert [c["id"] for c in everyone] == [conversation] and everyone[0]["mine"] is False
    assert head.get(f"{URL}{conversation}/").status_code == 200
    assert head.post(f"{URL}{conversation}/reply/", {"body": "x"}).status_code == 403
    # Other teachers can neither see it nor read it.
    other = api(family["other"], campus.tenant)
    assert other.get(URL, {"all": "1"}).json() == []
    assert other.get(f"{URL}{conversation}/").status_code == 404


def test_ghana_public_holidays():
    assert easter_sunday(2026) == dt.date(2026, 4, 5)
    days = dict((name, day) for day, name in ghana_public_holidays(2026))
    assert days["Good Friday"] == dt.date(2026, 4, 3)
    assert days["Easter Monday"] == dt.date(2026, 4, 6)
    assert days["Farmers' Day"] == dt.date(2026, 12, 4)  # first Friday in December
    assert days["Republic Day"] == dt.date(2026, 7, 1)
    assert days["Founder's Day"] == dt.date(2026, 9, 21)
    assert len(days) == 11


def test_calendar_shows_events_terms_and_holidays_to_the_right_people(
    campus, family, make_member, api
):
    head = api(family["head"], campus.tenant)
    day = campus.today + dt.timedelta(days=5)
    made = head.post(
        "/api/v1/calendar/events/",
        {"title": "PTA meeting", "kind": "meeting", "starts_on": day, "notify": True},
        format="json",
    )
    assert made.status_code == 201, made.content
    assert made.json()["ends_on"] == day.isoformat()
    head.post(
        "/api/v1/calendar/events/",
        {"title": "Staff briefing", "starts_on": day, "audience": "staff"},
        format="json",
    )
    bad = head.post(
        "/api/v1/calendar/events/",
        {"title": "Backwards", "starts_on": day, "ends_on": day - dt.timedelta(days=1)},
        format="json",
    )
    assert bad.status_code == 400

    window = {"start": campus.term.starts_on, "end": campus.term.ends_on}
    staff_view = head.get("/api/v1/calendar/", window).json()
    titles = [e["title"] for e in staff_view]
    assert {"PTA meeting", "Staff briefing", "First term begins", "First term ends"} <= set(titles)
    parent = api(family["parent"], campus.tenant)
    parent_titles = [e["title"] for e in parent.get("/api/v1/calendar/", window).json()]
    assert "PTA meeting" in parent_titles and "Staff briefing" not in parent_titles
    with tenant_context(campus.tenant):
        assert Notification.objects.filter(
            kind="calendar", recipient_user_id=family["parent"].pk
        ).exists()

    # Only leaders write to the calendar.
    teacher = api(family["maths"], campus.tenant)
    assert (
        teacher.post(
            "/api/v1/calendar/events/", {"title": "x", "starts_on": day}, format="json"
        ).status_code
        == 403
    )
    holidays = head.get("/api/v1/calendar/", {"start": "2026-12-01", "end": "2026-12-31"}).json()
    assert [h["title"] for h in holidays if h["kind"] == "public_holiday"] == [
        "Farmers' Day",
        "Christmas Day",
        "Boxing Day",
    ]
