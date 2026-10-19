from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest

from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event, snapshot

from .models import AcademicSession, ClassArm, ClassLevel, Period, Section, Subject, Term

DEFAULT_LEVELS: list[tuple[str, str]] = [
    ("KG 1", Section.KINDERGARTEN),
    ("KG 2", Section.KINDERGARTEN),
    *[(f"Basic {n}", Section.LOWER_PRIMARY) for n in range(1, 4)],
    *[(f"Basic {n}", Section.UPPER_PRIMARY) for n in range(4, 7)],
    *[(f"JHS {n}", Section.JHS) for n in range(1, 4)],
]

_KG, _LP, _UP, _JHS = (
    Section.KINDERGARTEN,
    Section.LOWER_PRIMARY,
    Section.UPPER_PRIMARY,
    Section.JHS,
)
_PRI = [_LP, _UP]
# GES / NaCCA standards-based curriculum (KG, primary) and Common Core Programme (JHS).
DEFAULT_SUBJECTS: list[tuple[str, str, list[str]]] = [
    ("Language and Literacy", "LL", [_KG]),
    ("Numeracy", "NUM", [_KG]),
    ("Our World and Our People", "OWOP", [_KG, *_PRI]),
    ("Creative Arts", "CA", [_KG, *_PRI]),
    ("English Language", "ENG", [*_PRI, _JHS]),
    ("Mathematics", "MTH", [*_PRI, _JHS]),
    ("Science", "SCI", [*_PRI, _JHS]),
    ("Ghanaian Language", "GHL", [*_PRI, _JHS]),
    ("Religious and Moral Education", "RME", [*_PRI, _JHS]),
    ("History", "HIS", _PRI),
    ("Computing", "ICT", [*_PRI, _JHS]),
    ("Physical Education", "PE", _PRI),
    ("French", "FRE", [*_PRI, _JHS]),
    ("Social Studies", "SOC", [_JHS]),
    ("Career Technology", "CT", [_JHS]),
    ("Creative Arts and Design", "CAD", [_JHS]),
    ("Physical and Health Education", "PHE", [_JHS]),
    ("Arabic", "ARB", [_JHS]),
]

#: BECE core subjects. A JHS aggregate is these four plus the best two others.
BECE_CORE_CODES = ("ENG", "MTH", "SCI", "SOC")


def seed_default_structure() -> None:
    """Standard Ghanaian basic-school levels (arm "A" each) and GES subjects. Idempotent."""
    with tenant_atomic():
        for order, (name, section) in enumerate(DEFAULT_LEVELS, start=1):
            level, _ = ClassLevel.objects.get_or_create(
                name=name, defaults={"section": section, "order": order}
            )
            ClassArm.objects.get_or_create(level=level, name="A")
        for name, code, sections in DEFAULT_SUBJECTS:
            Subject.objects.get_or_create(code=code, defaults={"name": name, "sections": sections})


def current_term() -> Term | None:
    return Term.objects.select_related("session").filter(is_current=True).first()


def set_current_session(*, request: HttpRequest | None, session: AcademicSession) -> None:
    with tenant_atomic():
        AcademicSession.objects.filter(is_current=True).exclude(pk=session.pk).update(
            is_current=False
        )
        AcademicSession.objects.filter(pk=session.pk).update(is_current=True)
        record_event(action="academics.session_current", request=request, target=session)


def set_current_term(*, request: HttpRequest | None, term: Term) -> None:
    with tenant_atomic():
        Term.objects.filter(is_current=True).exclude(pk=term.pk).update(is_current=False)
        Term.objects.filter(pk=term.pk).update(is_current=True)
        if not term.session.is_current:
            AcademicSession.objects.filter(is_current=True).update(is_current=False)
            AcademicSession.objects.filter(pk=term.session_id).update(is_current=True)
        record_event(action="academics.term_current", request=request, target=term)


def find_clashes(period: Period) -> list[str]:
    """Overlapping periods for the same class arm or the same teacher."""
    overlap = Q(
        term=period.term_id,
        weekday=period.weekday,
        starts_at__lt=period.ends_at,
        ends_at__gt=period.starts_at,
    )
    others = Period.objects.filter(overlap).exclude(pk=period.pk).select_related("arm", "subject")
    problems: list[str] = []
    for other in others.filter(arm=period.arm_id):
        problems.append(
            f"{other.arm} already has {other.subject} "
            f"{other.starts_at:%H:%M}-{other.ends_at:%H:%M}."
        )
    if period.teacher_user_id:
        for other in others.filter(teacher_user_id=period.teacher_user_id).exclude(
            arm=period.arm_id
        ):
            problems.append(
                f"The teacher is already teaching {other.arm} "
                f"{other.starts_at:%H:%M}-{other.ends_at:%H:%M}."
            )
    return problems


def save_period(*, request: HttpRequest | None, period: Period, data: dict[str, Any]) -> Period:
    creating = period.pk is None
    before = None if creating else snapshot(period)
    for field, value in data.items():
        setattr(period, field, value)
    period.full_clean()
    if problems := find_clashes(period):
        raise ValidationError(problems)
    with tenant_atomic():
        period.save()
        record_event(
            action="timetable.period_created" if creating else "timetable.period_updated",
            request=request,
            target=period,
            before=before,
            after=snapshot(period),
        )
    return period
