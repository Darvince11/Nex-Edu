"""Everyday school reports: class lists, attendance and results.

Each report is a title, a few headline figures and one or more tables, so the same
data feeds the screen, a CSV spreadsheet and a printable PDF. School leaders see
every class (``reports.view``); class teachers see their own class
(``reports.own_class``).
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from xml.sax.saxutils import escape

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.academics.models import ClassArm, Section, TeachingAssignment, Term
from apps.assessments.models import ReportCard
from apps.attendance.models import AttendanceRecord
from apps.students.models import Student, StudentGuardian
from core.rbac import Perm

#: Attendance below this share of days open is flagged.
LOW_ATTENDANCE = 80

Report = dict[str, Any]


def report_arms(user: Any, permissions: Iterable[str]) -> QuerySet[ClassArm]:
    """The classes this person may run reports for."""
    permissions = set(permissions)
    arms = ClassArm.objects.select_related("level").filter(level__is_active=True)
    if Perm.REPORTS_VIEW in permissions:
        return arms
    if Perm.REPORTS_OWN_CLASS in permissions:
        own = TeachingAssignment.objects.filter(teacher_user_id=user.pk, is_form_teacher=True)
        return arms.filter(pk__in=own.values("arm_id"))
    return arms.none()


def _col(key: str, label: str, *, numeric: bool = False, wide: bool = False) -> dict[str, Any]:
    return {"key": key, "label": label, "numeric": numeric, "wide": wide}


def _scope(arms: list[ClassArm]) -> str:
    return str(arms[0]) if len(arms) == 1 else "All classes"


def _age(born: Any, today: Any) -> int:
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def class_list(arms: list[ClassArm]) -> Report:
    today = timezone.localdate()
    pupils = list(
        Student.objects.filter(arm__in=arms, status=Student.Status.ACTIVE)
        .select_related("arm__level")
        .order_by("arm__level__order", "arm__name", "last_name", "first_name")
    )
    guardians: dict[Any, StudentGuardian] = {}
    for g in StudentGuardian.objects.filter(student__in=pupils).order_by("-is_primary"):
        guardians.setdefault(g.student_id, g)
    many = len(arms) > 1
    rows = []
    for n, s in enumerate(pupils, 1):
        g = guardians.get(s.pk)
        rows.append(
            {
                "n": n,
                "class": str(s.arm) if s.arm_id else "",
                "admission_number": s.admission_number,
                "name": f"{s.last_name}, {s.first_name} {s.middle_name}".strip(),
                "gender": s.get_gender_display(),
                "age": _age(s.date_of_birth, today),
                "guardian": g.full_name if g else "",
                "phone": g.phone if g else "",
            }
        )
    columns = [
        _col("n", "No.", numeric=True),
        *([_col("class", "Class")] if many else []),
        _col("admission_number", "Admission no."),
        _col("name", "Name", wide=True),
        _col("gender", "Gender"),
        _col("age", "Age", numeric=True),
        _col("guardian", "Guardian", wide=True),
        _col("phone", "Phone"),
    ]
    genders = defaultdict(int)
    for s in pupils:
        genders[s.gender] += 1
    return {
        "title": f"Class list: {_scope(arms)}",
        "subtitle": f"Pupils on roll on {today:%d %b %Y}",
        "summary": [
            {"label": "Pupils", "value": len(pupils)},
            {"label": "Girls", "value": genders.get(Student.Gender.FEMALE, 0)},
            {"label": "Boys", "value": genders.get(Student.Gender.MALE, 0)},
        ],
        "tables": [{"title": "", "columns": columns, "rows": rows}],
    }


def attendance(term: Term, arms: list[ClassArm]) -> Report:
    records = AttendanceRecord.objects.filter(term=term, arm__in=arms)
    opened = dict(
        records.values("arm_id").annotate(n=Count("date", distinct=True)).values_list("arm_id", "n")
    )
    per_pupil = {
        r["student_id"]: r
        for r in records.values("student_id").annotate(
            present=Count("id", filter=Q(status=AttendanceRecord.Status.PRESENT)),
            late=Count("id", filter=Q(status=AttendanceRecord.Status.LATE)),
            absent=Count("id", filter=Q(status=AttendanceRecord.Status.ABSENT)),
            excused=Count("id", filter=Q(status=AttendanceRecord.Status.EXCUSED)),
        )
    }
    pupils = list(
        Student.objects.filter(arm__in=arms, status=Student.Status.ACTIVE)
        .select_related("arm__level")
        .order_by("arm__level__order", "arm__name", "last_name", "first_name")
    )
    rows = []
    for s in pupils:
        r = per_pupil.get(s.pk, {})
        days = opened.get(s.arm_id, 0)
        attended = r.get("present", 0) + r.get("late", 0)
        rows.append(
            {
                "student": str(s.pk),
                "class": str(s.arm),
                "arm": str(s.arm_id),
                "name": f"{s.last_name}, {s.first_name}",
                "admission_number": s.admission_number,
                "present": r.get("present", 0),
                "late": r.get("late", 0),
                "absent": r.get("absent", 0),
                "excused": r.get("excused", 0),
                "days_open": days,
                "rate": _pct(attended, days),
            }
        )
    low = [r for r in rows if r["rate"] is not None and r["rate"] < LOW_ATTENDANCE]
    low_ids = {r["student"] for r in low}
    rates = [r["rate"] for r in rows if r["rate"] is not None]
    summary = [
        {
            "label": "Average attendance",
            "value": f"{sum(rates) / len(rates):.1f}%" if rates else "—",
        },
        {"label": f"Pupils under {LOW_ATTENDANCE}%", "value": len(low)},
    ]
    subtitle = f"{term}, registers taken so far"
    if len(arms) == 1:
        summary.insert(0, {"label": "Days open", "value": opened.get(arms[0].pk, 0)})
        columns = [
            _col("name", "Name", wide=True),
            _col("admission_number", "Admission no."),
            _col("present", "Present", numeric=True),
            _col("late", "Late", numeric=True),
            _col("absent", "Absent", numeric=True),
            _col("excused", "Excused", numeric=True),
            _col("rate", "Attendance %", numeric=True),
        ]
        return {
            "title": f"Attendance: {_scope(arms)}",
            "subtitle": subtitle,
            "summary": summary,
            "tables": [{"title": "", "columns": columns, "rows": rows}],
        }
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_class[r["arm"]].append(r)
    class_rows = []
    for arm in arms:
        members = by_class.get(str(arm.pk), [])
        arm_rates = [r["rate"] for r in members if r["rate"] is not None]
        class_rows.append(
            {
                "arm": str(arm.pk),
                "class": str(arm),
                "pupils": len(members),
                "days_open": opened.get(arm.pk, 0),
                "rate": round(sum(arm_rates) / len(arm_rates), 1) if arm_rates else None,
                "low": sum(1 for r in members if r["student"] in low_ids),
            }
        )
    low_columns = [
        _col("class", "Class"),
        _col("name", "Name", wide=True),
        _col("absent", "Absent", numeric=True),
        _col("rate", "Attendance %", numeric=True),
    ]
    return {
        "title": "Attendance: all classes",
        "subtitle": subtitle,
        "summary": summary,
        "tables": [
            {
                "title": "By class",
                "columns": [
                    _col("class", "Class", wide=True),
                    _col("pupils", "Pupils", numeric=True),
                    _col("days_open", "Days open", numeric=True),
                    _col("rate", "Attendance %", numeric=True),
                    _col("low", f"Under {LOW_ATTENDANCE}%", numeric=True),
                ],
                "rows": class_rows,
            },
            {
                "title": f"Pupils under {LOW_ATTENDANCE}%",
                "columns": low_columns,
                "rows": sorted(low, key=lambda r: r["rate"]),
            },
        ],
    }


def _two(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), ROUND_HALF_UP))


def results(term: Term, arms: list[ClassArm]) -> Report:
    cards = list(
        ReportCard.objects.filter(term=term, arm__in=arms)
        .select_related("student", "arm__level")
        .order_by("arm__level__order", "arm__name", "position", "student__last_name")
    )
    subjects: dict[str, list[Decimal]] = defaultdict(list)
    for card in cards:
        for line in card.lines:
            subjects[line["subject"]].append(Decimal(line["total"]))
    subject_rows = [
        {
            "subject": name,
            "entries": len(totals),
            "average": _two(sum(totals, Decimal(0)) / len(totals)),
            "highest": _two(max(totals)),
            "lowest": _two(min(totals)),
        }
        for name, totals in sorted(subjects.items())
    ]
    subject_table = {
        "title": "Subjects",
        "columns": [
            _col("subject", "Subject", wide=True),
            _col("entries", "Pupils", numeric=True),
            _col("average", "Average", numeric=True),
            _col("highest", "Highest", numeric=True),
            _col("lowest", "Lowest", numeric=True),
        ],
        "rows": subject_rows,
    }
    averages = [c.average for c in cards if c.lines]
    published = sum(1 for c in cards if c.status == ReportCard.Status.PUBLISHED)
    summary = [
        {"label": "Pupils with results", "value": len(averages)},
        {"label": "Published", "value": published},
        {
            "label": "Average score",
            "value": _two(sum(averages, Decimal(0)) / len(averages)) if averages else "—",
        },
    ]
    base = {"subtitle": f"{term}, from the results last worked out", "summary": summary}
    if len(arms) == 1:
        jhs = arms[0].level.section == Section.JHS
        rows = [
            {
                "student": str(c.student_id),
                "position": c.position,
                "name": f"{c.student.last_name}, {c.student.first_name}",
                "admission_number": c.student.admission_number,
                "subjects": len(c.lines),
                "average": _two(c.average),
                "aggregate": c.aggregate,
                "status": c.get_status_display(),
            }
            for c in cards
            if c.lines
        ]
        columns = [
            _col("position", "Position", numeric=True),
            _col("name", "Name", wide=True),
            _col("admission_number", "Admission no."),
            _col("subjects", "Subjects", numeric=True),
            _col("average", "Average", numeric=True),
            *([_col("aggregate", "Aggregate", numeric=True)] if jhs else []),
            _col("status", "Status"),
        ]
        return {
            **base,
            "title": f"Results: {_scope(arms)}",
            "tables": [{"title": "Pupils", "columns": columns, "rows": rows}, subject_table],
        }
    by_arm: dict[Any, list[ReportCard]] = defaultdict(list)
    for c in cards:
        if c.lines:
            by_arm[c.arm_id].append(c)
    class_rows = []
    for arm in arms:
        members = by_arm.get(arm.pk, [])
        values = [c.average for c in members]
        class_rows.append(
            {
                "arm": str(arm.pk),
                "class": str(arm),
                "pupils": len(members),
                "published": sum(1 for c in members if c.status == ReportCard.Status.PUBLISHED),
                "average": _two(sum(values, Decimal(0)) / len(values)) if values else None,
                "highest": _two(max(values)) if values else None,
                "lowest": _two(min(values)) if values else None,
            }
        )
    return {
        **base,
        "title": "Results: all classes",
        "tables": [
            {
                "title": "By class",
                "columns": [
                    _col("class", "Class", wide=True),
                    _col("pupils", "Pupils", numeric=True),
                    _col("published", "Published", numeric=True),
                    _col("average", "Class average", numeric=True),
                    _col("highest", "Best average", numeric=True),
                    _col("lowest", "Lowest average", numeric=True),
                ],
                "rows": class_rows,
            },
            subject_table,
        ],
    }


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def to_csv(report: Report) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([report["title"]])
    writer.writerow([report["subtitle"]])
    for item in report["summary"]:
        writer.writerow([item["label"], _cell(item["value"])])
    for table in report["tables"]:
        writer.writerow([])
        if table["title"]:
            writer.writerow([table["title"]])
        writer.writerow([c["label"] for c in table["columns"]])
        for row in table["rows"]:
            writer.writerow([_cell(row.get(c["key"])) for c in table["columns"]])
    return out.getvalue()


def to_pdf(report: Report) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    from apps.school.models import SchoolProfile
    from core import pdf

    profile = SchoolProfile.load()

    def build(width: float) -> list[Any]:
        story = pdf.header(profile, escape(report["title"]))
        story.append(Paragraph(escape(report["subtitle"]), pdf.SMALL))
        story.append(Spacer(1, 3 * mm))
        story.append(
            pdf.key_values(
                [(escape(i["label"]), escape(_cell(i["value"]))) for i in report["summary"]], width
            )
        )
        for table in report["tables"]:
            if table["title"]:
                story.append(Paragraph(escape(table["title"]), pdf.H))
            else:
                story.append(Spacer(1, 4 * mm))
            columns = table["columns"]
            if not table["rows"]:
                story.append(Paragraph("Nothing to show.", pdf.BODY))
                continue
            weights = [2.4 if c["wide"] else 1.0 for c in columns]
            widths = [width * w / sum(weights) for w in weights]
            rows: list[list[Any]] = [[escape(c["label"]) for c in columns]]
            rows += [
                [Paragraph(escape(_cell(row.get(c["key"]))), pdf.BODY) for c in columns]
                for row in table["rows"]
            ]
            story.append(pdf.table(rows, widths))
        return story

    return pdf.render(build, title=report["title"], footer=report["subtitle"])


KINDS = {"class-list": "Class list", "attendance": "Attendance", "results": "Results"}
