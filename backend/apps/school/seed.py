"""Everything a brand-new school database needs before its first login."""

from __future__ import annotations


def seed_new_school(name: str) -> None:
    from apps.academics.services import seed_default_structure
    from apps.assessments.services import seed_grading_defaults
    from apps.communication.models import MessagingSettings
    from apps.finance.models import PaymentSettings
    from apps.finance.services import seed_ledger_accounts

    from .services import ensure_profile

    ensure_profile(name)
    seed_default_structure()
    seed_grading_defaults()
    seed_ledger_accounts()
    PaymentSettings.load()
    MessagingSettings.load()
