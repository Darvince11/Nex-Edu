"""Staff records, departments, the staff register and leave."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.communication.models import Notification
from apps.staff.models import LeaveRequest, StaffProfile
from apps.staff.services import working_days
from control_plane.models import Role
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db


def next_weekday(start: dt.date, weekday: int) -> dt.date:
    return start + dt.timedelta(days=(weekday - start.weekday()) % 7 or 7)


def test_working_days_skip_weekends():
    monday = dt.date(2026, 11, 2)
    assert working_days(monday, monday + dt.timedelta(days=6)) == 5  # Mon-Sun
    assert working_days(monday + dt.timedelta(days=5), monday + dt.timedelta(days=6)) == 0


def test_every_staff_login_has_a_staff_record(tenant, make_member, api):
    teacher = make_member(tenant, Role.TEACHER, email="kofi@greenfield.test")
    make_member(tenant, Role.PARENT, mfa=False, email="parent@greenfield.test")
    head = api(make_member(tenant, Role.PRINCIPAL), tenant)
    rows = head.get("/api/v1/staff/").data
    emails = {r["email"] for r in rows}
    assert "kofi@greenfield.test" in emails and "parent@greenfield.test" not in emails
    kofi = next(r for r in rows if r["email"] == "kofi@greenfield.test")
    assert kofi["staff_number"].startswith("STF/") and kofi["user_id"] == str(teacher.pk)
    # Listing twice doesn't duplicate anyone.
    assert len(head.get("/api/v1/staff/").data) == len(rows)


def test_leaders_add_staff_without_a_login_and_pay_details_stay_private(tenant, make_member, api):
    head = api(make_member(tenant, Role.PRINCIPAL), tenant)
    department = head.post("/api/v1/staff/departments/", {"name": "Kitchen"}, format="json").data
    cook = head.post(
        "/api/v1/staff/",
        {
            "first_name": "Ama",
            "last_name": "Owusu",
            "job_title": "Cook",
            "department": department["id"],
            "bank_account_number": "0123456789",
        },
        format="json",
    )
    assert cook.status_code == 201, cook.content
    assert cook.data["staff_number"].startswith("STF/")
    assert head.get("/api/v1/staff/departments/").data[0]["staff_count"] == 1

    bursar = api(make_member(tenant, Role.BURSAR), tenant)
    seen = next(r for r in bursar.get("/api/v1/staff/").data if r["first_name"] == "Ama")
    assert "bank_account_number" not in seen  # staff.view only
    teacher = api(make_member(tenant, Role.TEACHER), tenant)
    assert teacher.get("/api/v1/staff/").status_code == 403


def test_staff_register_marks_the_day_and_fills_in_approved_leave(tenant, make_member, api):
    head_user = make_member(tenant, Role.PRINCIPAL)
    head = api(head_user, tenant)
    teacher_user = make_member(tenant, Role.TEACHER)
    on_leave_user = make_member(tenant, Role.TEACHER)
    today = timezone.localdate()
    rows = head.get("/api/v1/staff-register/", {"date": today.isoformat()}).data["rows"]
    with tenant_context(tenant):
        on_leave = StaffProfile.objects.get(user_id=on_leave_user.pk)
        LeaveRequest.objects.create(
            staff=on_leave, kind="sick", start=today, end=today, days=1, status="approved"
        )
    rows = {r["staff"]: r for r in head.get("/api/v1/staff-register/").data["rows"]}
    assert rows[str(on_leave.pk)]["status"] == "on_leave"

    with tenant_context(tenant):
        teacher = StaffProfile.objects.get(user_id=teacher_user.pk)
    saved = head.post(
        "/api/v1/staff-register/",
        {
            "date": today.isoformat(),
            "entries": [
                {"staff": str(teacher.pk), "status": "late", "time_in": "08:20", "note": "Traffic"}
            ],
        },
        format="json",
    )
    assert saved.status_code == 200, saved.content
    marked = {r["staff"]: r for r in saved.data["rows"]}
    assert (
        marked[str(teacher.pk)]["status"] == "late"
        and marked[str(teacher.pk)]["time_in"] == "08:20"
    )
    summary = {r["staff"]: r for r in head.get("/api/v1/staff-register/summary/").data["rows"]}
    assert summary[str(teacher.pk)]["late"] == 1

    future = {"date": (today + dt.timedelta(days=2)).isoformat(), "entries": []}
    assert head.post("/api/v1/staff-register/", future, format="json").status_code == 400
    assert api(teacher_user, tenant).get("/api/v1/staff-register/").status_code == 403


def test_staff_ask_for_leave_and_a_leader_decides(tenant, make_member, api):
    head_user = make_member(tenant, Role.PRINCIPAL)
    teacher_user = make_member(tenant, Role.TEACHER)
    teacher = api(teacher_user, tenant)
    head = api(head_user, tenant)
    monday = next_weekday(timezone.localdate(), 0)
    asked = teacher.post(
        "/api/v1/staff/leave/",
        {
            "kind": "annual",
            "start": monday.isoformat(),
            "end": (monday + dt.timedelta(days=6)).isoformat(),
            "reason": "Family",
        },
        format="json",
    )
    assert asked.status_code == 201, asked.content
    assert asked.data["days"] == 5 and asked.data["status"] == "pending"
    overlap = {"kind": "sick", "start": monday.isoformat(), "end": monday.isoformat()}
    assert teacher.post("/api/v1/staff/leave/", overlap, format="json").status_code == 400
    with tenant_context(tenant):
        assert Notification.objects.filter(recipient_user_id=head_user.pk, kind="leave").exists()

    url = f"/api/v1/staff/leave/{asked.data['id']}/decide/"
    assert teacher.post(url, {"approve": True}, format="json").status_code == 403
    assert head.post(url, {"approve": False}, format="json").status_code == 400  # needs a reason
    approved = head.post(url, {"approve": True, "note": "Enjoy"}, format="json")
    assert approved.data["status"] == "approved"
    with tenant_context(tenant):
        assert Notification.objects.filter(recipient_user_id=teacher_user.pk, kind="leave").exists()
    assert head.post(url, {"approve": False, "note": "x"}, format="json").status_code == 400

    # Staff see their own requests; leaders see everyone's.
    other = make_member(tenant, Role.TEACHER)
    assert api(other, tenant).get("/api/v1/staff/leave/").data == []
    assert len(head.get("/api/v1/staff/leave/").data) == 1
    cancelled = teacher.post(f"/api/v1/staff/leave/{asked.data['id']}/cancel/")
    assert cancelled.data["status"] == "cancelled"


def test_nobody_approves_their_own_leave(tenant, make_member, api):
    head_user = make_member(tenant, Role.PRINCIPAL)
    head = api(head_user, tenant)
    monday = next_weekday(timezone.localdate(), 0)
    mine = head.post(
        "/api/v1/staff/leave/",
        {"kind": "sick", "start": monday.isoformat(), "end": monday.isoformat()},
        format="json",
    ).data
    assert (
        head.post(
            f"/api/v1/staff/leave/{mine['id']}/decide/", {"approve": True}, format="json"
        ).status_code
        == 403
    )
    owner = api(make_member(tenant, Role.OWNER), tenant)
    assert (
        owner.post(
            f"/api/v1/staff/leave/{mine['id']}/decide/", {"approve": True}, format="json"
        ).status_code
        == 200
    )
