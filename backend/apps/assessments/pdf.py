"""Ghanaian basic-school terminal report (GES style)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from apps.school.models import SchoolProfile
from core import pdf

from .models import AssessmentComponent, GradeBand, ReportCard
from .services import ordinal


def _num(value: Decimal) -> str:
    """30.00 → "30", 79.99 → "79.99"."""
    return f"{value.normalize():f}"


def render_report_card(card: ReportCard) -> bytes:
    profile = SchoolProfile.load()
    student = card.student
    term = card.term
    components = list(AssessmentComponent.objects.filter(is_active=True))
    section = card.arm.level.section
    bands = list(GradeBand.objects.filter(section=section)) or list(
        GradeBand.objects.filter(section="")
    )

    def build(width: float) -> list[Any]:
        story = pdf.header(profile, f"Terminal report: {term}")
        story.append(
            pdf.key_values(
                [
                    ("Name", escape(student.full_name)),
                    ("Admission no.", escape(student.admission_number)),
                    ("Class", escape(str(card.arm))),
                    ("Session", escape(term.session.name)),
                    (
                        "Position",
                        f"{ordinal(card.position)} of {card.class_size}" if card.position else "—",
                    ),
                    ("Average", f"{card.average}%"),
                    *([("Aggregate", str(card.aggregate))] if card.aggregate is not None else []),
                    ("Attendance", f"{card.days_present} of {card.days_open} days"),
                    (
                        "Next term begins",
                        f"{term.next_term_begins:%d %B %Y}" if term.next_term_begins else "—",
                    ),
                ],
                width,
            )
        )
        story.append(Spacer(1, 4 * mm))

        head = [
            "Subject",
            *[f"{c.code}\n/{_num(c.max_score)}" for c in components],
            "Total",
            "Grade",
            "Remark",
            "Pos.",
            "High",
            "Low",
            "Avg",
        ]
        rows: list[list[Any]] = [head]
        for line in card.lines:
            rows.append(
                [
                    Paragraph(escape(line["subject"]), pdf.BODY),
                    *[line["components"].get(c.code) or "—" for c in components],
                    line["total"],
                    line["grade"],
                    line["remark"],
                    line["position"],
                    line["class_highest"],
                    line["class_lowest"],
                    line["class_average"],
                ]
            )
        n = len(components)
        fixed = 11 * mm
        subject_w = width - fixed * (n + 7) - 19 * mm
        widths = [
            subject_w,
            *[fixed] * n,
            fixed + 3 * mm,
            fixed,
            16 * mm + fixed,
            fixed,
            fixed,
            fixed,
            fixed,
        ]
        story.append(pdf.table(rows, widths, align_right_from=1))
        story.append(Spacer(1, 4 * mm))
        story.append(
            pdf.key_values(
                [
                    ("Total score", str(card.total_score)),
                    ("Subjects", str(len(card.lines))),
                ],
                width,
            )
        )

        story.append(Paragraph("Comments", pdf.H))
        story.append(
            pdf.key_values(
                [
                    ("Class teacher", escape(card.form_teacher_comment)),
                    ("Head teacher", escape(card.principal_comment)),
                ],
                width,
            )
        )
        if bands:
            key = ", ".join(
                f"{b.grade} {_num(b.min_score)}-{_num(b.max_score)} {b.remark}" for b in bands
            )
            story += [Spacer(1, 3 * mm), Paragraph(f"Grading key: {escape(key)}", pdf.SMALL)]
        return story

    return pdf.render(
        build, title=f"Report card {student.admission_number}", footer=profile.report_card_footer
    )
