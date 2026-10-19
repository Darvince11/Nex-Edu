from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.platypus import Spacer

from apps.school.models import SchoolProfile
from core import pdf

from .models import Payment


def cedis(pesewas: int) -> str:
    return f"GH₵{pesewas / 100:,.2f}"


def render_receipt(payment: Payment) -> bytes:
    profile = SchoolProfile.load()
    invoice = payment.invoice
    student = invoice.student

    def build(width: float) -> list[Any]:
        story = pdf.header(profile, f"Official receipt {payment.receipt_number}")
        paid_at = timezone.localtime(payment.paid_at) if payment.paid_at else None
        story.append(
            pdf.key_values(
                [
                    ("Student", escape(student.full_name)),
                    ("Admission no.", escape(student.admission_number)),
                    ("Invoice", escape(invoice.number)),
                    ("Term", escape(str(invoice.term))),
                    ("Amount paid", cedis(payment.amount_received_pesewas)),
                    ("Method", payment.get_method_display()),
                    ("Date", f"{paid_at:%d %b %Y %H:%M}" if paid_at else "—"),
                    ("Reference", escape(payment.reference)),
                ],
                width,
            )
        )
        story.append(Spacer(1, 6))
        rows: list[list[Any]] = [["Item", "Amount"]]
        rows += [
            [escape(line.description), cedis(line.amount_pesewas)] for line in invoice.lines.all()
        ]
        rows += [
            ["Invoice total", cedis(invoice.total_pesewas)],
            ["Total paid to date", cedis(invoice.paid_pesewas)],
            ["Balance", cedis(invoice.balance_pesewas)],
        ]
        story.append(pdf.table(rows, [width * 0.7, width * 0.3], align_right_from=1))
        return story

    return pdf.render(build, title=f"Receipt {payment.receipt_number}")
