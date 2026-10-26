"""Class lists, attendance and results reports, with CSV and PDF exports."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.assessments.models import ReportCard
from apps.attendance.models import AttendanceRecord
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.tenancy import tenant_context
from core.audit.models import AuditEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def school(campus, make_student):
    """Three JHS 1 pupils and one JHS 2 pupil, with registers and results."""
    a = make_student(campus.tenant, arm=campus.jhs1, first_name="Abena", gender="female")
    b = make_student(campus.tenant, arm=campus.jhs1, first_name="Kwame", gender="male")
    c = make_student(campus.tenant, arm=campus.jhs1, first_name="Yaa", gender="female")
    d = make_student(campus.tenant, arm=campus.jhs2, first_name="Kofi", gender="male")
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(
            student=a, full_name="Ama Owusu", phone="0244123456", is_primary=True
        )
        days = [campus.term.starts_on + dt.timedelta(days=i) for i in range(10)]
        for day in days:
            for pupil, status in ((a, "present"), (b, "present"), (d, "present")):
                AttendanceRecord.objects.create(
                    student=pupil,
                    arm=pupil.arm,
                    term=campus.term,
                    date=day,
                    status=status,
                    recorded_by=uuid.uuid4(),
                    recorded_at=timezone.now(),
                )
            # Yaa misses half the days.
            AttendanceRecord.objects.create(
                student=c,
                arm=c.arm,
                term=campus.term,
                date=day,
                status="present" if day.day % 2 else "absent",
                recorded_by=uuid.uuid4(),
                recorded_at=timezone.now(),
            )
        for pupil, avg, pos in ((a, "81.50", 1), (b, "64.00", 2)):
            ReportCard.objects.create(
                student=pupil,
                term=campus.term,
                arm=pupil.arm,
                lines=[
                    {"subject": "Mathematics", "total": avg},
                    {"subject": "English Language", "total": avg},
                ],
                average=Decimal(avg),
                position=pos,
                aggregate=12 if pos == 1 else 24,
                computed_at=timezone.now(),
            )
    return {"a": a, "b": b, "c": c, "d": d}


def test_leaders_report_on_every_class_and_one_class(campus, school, make_member, api):
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    everyone = head.get("/api/v1/reports/class-list/").json()
    assert everyone["summary"][0] == {"label": "Pupils", "value": 4}
    one = head.get("/api/v1/reports/class-list/", {"arm": str(campus.jhs1.pk)}).json()
    assert one["title"] == "Class list: JHS 1 A"
    rows = one["tables"][0]["rows"]
    assert [r["name"].split(", ")[1] for r in rows] == ["Abena", "Kwame", "Yaa"]
    assert rows[0]["guardian"] == "Ama Owusu" and rows[0]["phone"] == "0244123456"

    attendance = head.get("/api/v1/reports/attendance/", {"arm": str(campus.jhs1.pk)}).json()
    by_name = {r["name"].split(", ")[1]: r for r in attendance["tables"][0]["rows"]}
    assert by_name["Abena"]["rate"] == 100.0 and by_name["Yaa"]["rate"] == 50.0
    assert {"label": "Pupils under 80%", "value": 1} in attendance["summary"]
    whole = head.get("/api/v1/reports/attendance/").json()
    assert [t["title"] for t in whole["tables"]] == ["By class", "Pupils under 80%"]
    assert [r["name"] for r in whole["tables"][1]["rows"]] == [by_name["Yaa"]["name"]]

    results = head.get("/api/v1/reports/results/", {"arm": str(campus.jhs1.pk)}).json()
    pupils, subjects = results["tables"]
    assert [r["position"] for r in pupils["rows"]] == [1, 2]
    assert any(c["key"] == "aggregate" for c in pupils["columns"])  # JHS shows aggregates
    assert {r["subject"]: r["average"] for r in subjects["rows"]} == {
        "English Language": "72.75",
        "Mathematics": "72.75",
    }


def test_exports_are_files_and_are_audited(campus, school, make_member, api):
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    csv = head.get("/api/v1/reports/class-list/", {"arm": str(campus.jhs1.pk), "export": "csv"})
    assert csv["Content-Type"].startswith("text/csv")
    assert 'filename="class-list-jhs-1-a.csv"' in csv["Content-Disposition"]
    assert b"Ama Owusu" in csv.content
    pdf = head.get("/api/v1/reports/results/", {"export": "pdf"})
    assert pdf["Content-Type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    with tenant_context(campus.tenant):
        assert AuditEvent.objects.filter(action="report.exported").count() == 2


def test_class_teachers_see_only_their_class(campus, school, make_member, api, assign):
    form = make_member(campus.tenant, Role.FORM_TEACHER)
    assign(form, campus.jhs1, form=True)
    teacher = api(form, campus.tenant)
    mine = teacher.get("/api/v1/reports/class-list/").json()
    assert mine["title"] == "Class list: JHS 1 A"
    assert (
        teacher.get("/api/v1/reports/class-list/", {"arm": str(campus.jhs2.pk)}).status_code == 404
    )
    subject = make_member(campus.tenant, Role.TEACHER)
    assign(subject, campus.jhs1, campus.subjects["MTH"])
    assert api(subject, campus.tenant).get("/api/v1/reports/class-list/").status_code == 403
    parent = api(make_member(campus.tenant, Role.PARENT, mfa=False), campus.tenant)
    assert parent.get("/api/v1/reports/results/").status_code == 403
