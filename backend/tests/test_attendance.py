from __future__ import annotations

import datetime as dt
import uuid

from django.utils import timezone

from apps.attendance.models import AttendanceRecord
from apps.communication.models import Delivery, Notification
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.tenancy import tenant_context


def _register(client, arm, day, entries, **extra):
    return client.post(
        "/api/v1/attendance/register/",
        {"arm": str(arm.pk), "date": str(day), "entries": entries, **extra},
        format="json",
    )


def test_teacher_takes_register_for_own_class_only(campus, make_member, make_student, assign, api):
    teacher = make_member(campus.tenant, Role.TEACHER)
    assign(teacher, campus.jhs1, form=True)
    s1 = make_student(campus.tenant, arm=campus.jhs1)
    client = api(teacher, campus.tenant)

    sheet = client.get(f"/api/v1/attendance/register/?arm={campus.jhs1.pk}&date={campus.today}")
    assert sheet.status_code == 200
    assert [r["student"] for r in sheet.data["rows"]] == [str(s1.pk)]

    ok = _register(
        client, campus.jhs1, campus.today, [{"student": str(s1.pk), "status": "present"}]
    )
    assert ok.status_code == 200, ok.data
    assert ok.data["created"] == 1

    other = _register(
        client, campus.jhs2, campus.today, [{"student": str(s1.pk), "status": "present"}]
    )
    assert other.status_code == 403


def test_students_from_other_classes_and_future_dates_are_rejected(
    campus, make_member, make_student, api
):
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    outsider = make_student(campus.tenant, arm=campus.jhs2)
    assert (
        _register(
            admin, campus.jhs1, campus.today, [{"student": str(outsider.pk), "status": "present"}]
        ).status_code
        == 400
    )
    s1 = make_student(campus.tenant, arm=campus.jhs1)
    tomorrow = campus.today + dt.timedelta(days=1)
    assert (
        _register(
            admin, campus.jhs1, tomorrow, [{"student": str(s1.pk), "status": "present"}]
        ).status_code
        == 400
    )


def test_offline_batch_replay_is_a_no_op(campus, make_member, make_student, api):
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    s1 = make_student(campus.tenant, arm=campus.jhs1)
    batch = str(uuid.uuid4())
    entries = [{"student": str(s1.pk), "status": "late"}]
    first = _register(admin, campus.jhs1, campus.today, entries, batch_id=batch)
    again = _register(admin, campus.jhs1, campus.today, entries, batch_id=batch)
    assert first.data["created"] == 1
    assert again.data["replayed"] is True
    with tenant_context(campus.tenant):
        assert AttendanceRecord.objects.count() == 1


def test_later_observation_wins_conflicts(campus, make_member, make_student, api):
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    s1 = make_student(campus.tenant, arm=campus.jhs1)
    now = timezone.now()
    _register(
        admin,
        campus.jhs1,
        campus.today,
        [{"student": str(s1.pk), "status": "present"}],
        recorded_at=now.isoformat(),
    )
    # A phone that was offline syncs an older register later: it must not overwrite.
    stale = _register(
        admin,
        campus.jhs1,
        campus.today,
        [{"student": str(s1.pk), "status": "absent"}],
        recorded_at=(now - dt.timedelta(hours=2)).isoformat(),
    )
    assert stale.data["conflicts"] == [
        {"student": str(s1.pk), "kept": "present", "submitted": "absent"}
    ]
    with tenant_context(campus.tenant):
        assert AttendanceRecord.objects.get().status == "present"


def test_absence_alerts_guardians_once(campus, make_member, make_student, api):
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    parent = make_member(campus.tenant, Role.PARENT, mfa=False)
    s1 = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(
            student=s1, guardian_user_id=parent.pk, phone="+233244123456", full_name="Esi"
        )
    entries = [{"student": str(s1.pk), "status": "absent"}]
    _register(admin, campus.jhs1, campus.today, entries)
    _register(admin, campus.jhs1, campus.today, list(entries))  # resubmitted unchanged
    with tenant_context(campus.tenant):
        assert Notification.objects.filter(recipient_user_id=parent.pk, kind="absence").count() == 1
        sms = Delivery.objects.get(channel="sms", kind="absence")
        assert sms.to == "+233244123456"
        assert sms.status == "sent"
        assert "Kojo" in sms.body


def test_parent_sees_only_own_childs_attendance(campus, make_member, make_student, api):
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    parent = make_member(campus.tenant, Role.PARENT, mfa=False)
    mine = make_student(campus.tenant, arm=campus.jhs1)
    other = make_student(campus.tenant, arm=campus.jhs1)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(
            student=mine, guardian_user_id=parent.pk, phone="+233244123456"
        )
    _register(
        admin,
        campus.jhs1,
        campus.today,
        [
            {"student": str(mine.pk), "status": "present"},
            {"student": str(other.pk), "status": "absent"},
        ],
    )
    client = api(parent, campus.tenant)
    response = client.get(f"/api/v1/students/{mine.pk}/attendance/")
    assert response.status_code == 200
    assert response.data["summary"]["present"] == 1
    assert response.data["summary"]["days_open"] == 1
    assert client.get(f"/api/v1/students/{other.pk}/attendance/").status_code == 404
    assert (
        client.get(
            f"/api/v1/attendance/register/?arm={campus.jhs1.pk}&date={campus.today}"
        ).status_code
        == 403
    )
