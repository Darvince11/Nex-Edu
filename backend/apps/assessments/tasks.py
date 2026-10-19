from __future__ import annotations

from celery import shared_task

from core.files import save_tenant_file
from core.tasks import TenantTask

from .models import ReportCard
from .pdf import render_report_card


@shared_task(base=TenantTask, name="reports.generate_report_cards")
def generate_report_card_pdfs(arm_id: str, term_id: int) -> int:
    """Pre-render published report cards so results day is just file downloads."""
    cards = ReportCard.objects.filter(
        arm_id=arm_id, term_id=term_id, status=ReportCard.Status.PUBLISHED, needs_regeneration=True
    ).select_related("student", "term__session", "arm__level")
    done = 0
    for card in cards:
        key = save_tenant_file(
            f"report-cards/{term_id}/{card.student_id}.pdf", render_report_card(card)
        )
        ReportCard.objects.filter(pk=card.pk).update(pdf_path=key, needs_regeneration=False)
        done += 1
    return done
