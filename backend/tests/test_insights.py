"""Dashboard charts show each person only what their pages already show them."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.assessments.models import ReportCard
from apps.attendance.models import AttendanceRecord
from apps.finance.models import Invoice
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db
URL = "/api/v1/school/insights/"


@pytest.fixture
def school(campus, make_student):
    """Two JHS 1 pupils, one JHS 2 pupil, a register, invoices and report cards."""
    a = make_student(campus.tenant, arm=campus.jhs1, gender="female")
    b = make_student(campus.tenant, arm=campus.jhs1, gender="male")
    c = make_student(campus.tenant, arm=campus.jhs2, gender="female")
    now = timezone.now()
    with tenant_context(campus.tenant):
        for student, status in ((a, "present"), (b, "absent"), (c, "late")):
            AttendanceRecord.objects.create(
                student=student,
                arm=student.arm,
                term=campus.term,
                date=campus.today,
                status=status,
                recorded_by=student.pk,
                recorded_at=now,
            )
        for i, (student, paid) in enumerate(((a, 50_000), (b, 0), (c, 100_000))):
            Invoice.objects.create(
                number=f"INV-{i}",
                student=student,
                term=campus.term,
                total_pesewas=100_000,
                paid_pesewas=paid,
                issued_at=now,
            )
        for student, status, total in ((a, "published", "80"), (c, "draft", "60")):
            ReportCard.objects.create(
                student=student,
                term=campus.term,
                arm=student.arm,
                lines=[
                    {"subject": "English", "code": "ENG", "total": total, "grade": "1", "points": 1}
                ],
                status=status,
                computed_at=now,
            )
    return {"a": a, "b": b, "c": c}


def test_leaders_see_the_whole_school(campus, school, make_member, api):
    data = api(make_member(campus.tenant, Role.OWNER), campus.tenant).get(URL).data
    by_class = {row["label"]: row for row in data["enrolment"]}
    assert by_class["JHS 1 A"]["pupils"] == 2
    assert (by_class["JHS 1 A"]["girls"], by_class["JHS 1 A"]["boys"]) == (1, 1)
    assert by_class["JHS 2 A"]["pupils"] == 1
    [day] = data["attendance"]
    assert (day["present"], day["late"], day["absent"], day["marked"]) == (1, 1, 1, 3)
    assert day["rate"] == pytest.approx(66.7)
    assert data["fees"]["billed_pesewas"] == 300_000
    assert data["fees"]["outstanding_pesewas"] == 150_000
    assert data["fees"]["collection_rate"] == 50.0
    assert data["results"]["subjects"] == [
        {"code": "ENG", "subject": "English", "average": 70.0, "pupils": 2}
    ]


def test_teachers_see_their_classes_and_no_money(campus, school, make_member, assign, api):
    teacher = make_member(campus.tenant, Role.TEACHER)
    assign(teacher, campus.jhs1, campus.subjects["ENG"])
    data = api(teacher, campus.tenant).get(URL).data
    assert [row["label"] for row in data["enrolment"]] == ["JHS 1 A"]
    assert data["attendance"][0]["marked"] == 2
    assert "fees" not in data
    assert data["results"]["report_cards"] == 1  # JHS 2's card isn't theirs


def test_parents_see_only_their_child_and_published_results(campus, school, make_member, api):
    parent = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        for child in (school["a"], school["c"]):
            StudentGuardian.objects.create(
                student=child, guardian_user_id=parent.pk, phone="+233244123456"
            )
    data = api(parent, campus.tenant).get(URL).data
    assert "enrolment" not in data
    assert "fees" not in data  # school totals are never shown to parents
    assert data["attendance"][0]["marked"] == 2
    assert data["results"]["report_cards"] == 1  # the draft stays hidden
    assert data["results"]["subjects"][0]["average"] == 80.0


def test_outsiders_get_nothing(campus, other_tenant, make_member, api):
    outsider = make_member(other_tenant, Role.OWNER)
    assert api(outsider, campus.tenant).get(URL).status_code == 403


def test_attendance_trend_keeps_the_latest_school_days(campus, make_student, make_member, api):
    pupil = make_student(campus.tenant, arm=campus.jhs1)
    with tenant_context(campus.tenant):
        for days_ago in range(30):
            AttendanceRecord.objects.create(
                student=pupil,
                arm=campus.jhs1,
                term=campus.term,
                date=campus.today - dt.timedelta(days=days_ago),
                status="present",
                recorded_by=pupil.pk,
                recorded_at=timezone.now(),
            )
    trend = (
        api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant).get(URL).data["attendance"]
    )
    assert len(trend) == 20
    assert trend[-1]["date"] == campus.today.isoformat()
    assert trend == sorted(trend, key=lambda d: d["date"])
