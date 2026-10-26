"""Background jobs for the control plane (not tied to one school's database)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from .developer import deliver  # noqa: F401  (registers the task for workers)
from .push import send_push  # noqa: F401
from .registrations import complete_approval

logger = logging.getLogger(__name__)


@shared_task(name="control_plane.provision_registration", acks_late=True)
def provision_registration(registration_id: Any) -> str | None:
    """Create an approved school's database and make the applicant its owner.

    Not retried automatically: a half-created school needs a person to look at it.
    Failures are already recorded on the registration and in the platform log.
    """
    try:
        tenant = complete_approval(registration_id)
    except Exception:
        logger.exception("Setting up registration %s failed", registration_id)
        return None
    return tenant.slug if tenant else None


@shared_task(name="control_plane.collect_usage", acks_late=True)
def collect_usage(slugs: list[str] | None = None) -> int:
    """Copy each school's totals (pupils, registers, messages, payments) into the
    control plane for the Super Admin console. Hourly, and on demand."""
    from .usage import collect_many

    return collect_many(slugs)


@shared_task(name="control_plane.email_announcement", acks_late=True)
def email_announcement(announcement_id: str) -> int:
    from .announcements import send_emails

    return send_emails(announcement_id)


@shared_task(name="control_plane.health_checks")
def health_checks() -> int:
    """Every few minutes: stuck school set-ups are stopped and cleaned up; school
    databases answer and are up to date; figures are fresh."""
    from .problems import run_health_checks
    from .registrations import sweep_stuck_setups

    sweep_stuck_setups()
    return sum(1 for r in run_health_checks() if not r["ok"])


@shared_task(name="control_plane.vulnerability_scan")
def vulnerability_scan() -> int:
    """Daily: published advisories for the Python packages this server runs."""
    from .security import scan_vulnerabilities

    return len(scan_vulnerabilities().findings)


@shared_task(name="control_plane.billing_daily")
def billing_daily() -> dict[str, int]:
    """Daily: this month's invoices, payments that came in without a webhook,
    reminders at 7 and 14 days overdue and suspension at 30."""
    from .subscriptions import chase_overdue, issue_month, reconcile_charges

    return {"issued": issue_month(), "verified": reconcile_charges(), **chase_overdue()}


@shared_task(name="control_plane.purge_closed_schools")
def purge_closed_schools() -> int:
    """Daily: destroy closed schools whose 90 days are up (key, database, files)."""
    from .lifecycle import purge_due

    return purge_due()


@shared_task(name="control_plane.analytics_export")
def analytics_export() -> str:
    """Nightly: yesterday's anonymised figures for every school, for the warehouse."""
    from .analytics import export_day

    return export_day()
