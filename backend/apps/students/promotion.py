"""End of year: move every class up a level and graduate the top class.

Each class moves to the arm with the same name in the next active level
(JHS 1 A → JHS 2 A), created if the school doesn't have it yet. Pupils in the
top level graduate. Leaders can keep a pupil in the same class ("repeat") or
mark them as leaving. Nothing is deleted: graduates and leavers keep their
records with a new status.
"""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from apps.academics.models import AcademicSession, ClassArm, ClassLevel
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event

from .models import PromotionRun, Student

ACTIONS = ("promote", "repeat", "graduate", "leave")


class AlreadyPromoted(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "already_promoted"


def _next_levels() -> dict[int, ClassLevel | None]:
    """For each active level, the next active level up (None for the top one)."""
    levels = list(ClassLevel.objects.filter(is_active=True).order_by("order"))
    return {
        level.pk: (levels[i + 1] if i + 1 < len(levels) else None) for i, level in enumerate(levels)
    }


def plan() -> dict[str, Any]:
    nexts = _next_levels()
    session = AcademicSession.objects.filter(is_current=True).first()
    last = PromotionRun.objects.filter(session=session).first() if session else None
    classes = []
    for arm in (
        ClassArm.objects.filter(level__is_active=True)
        .select_related("level")
        .order_by("-level__order", "name")
    ):
        pupils = list(
            Student.objects.filter(arm=arm, status=Student.Status.ACTIVE).order_by(
                "last_name", "first_name"
            )
        )
        if not pupils:
            continue
        nxt = nexts.get(arm.level_id)
        classes.append(
            {
                "arm": str(arm.pk),
                "label": str(arm),
                "to": f"{nxt.name} {arm.name}" if nxt else None,
                "default": "promote" if nxt else "graduate",
                "pupils": [
                    {"id": str(p.pk), "name": p.full_name, "admission_number": p.admission_number}
                    for p in pupils
                ],
            }
        )
    return {
        "session": session.name if session else None,
        "already_run_at": last.run_at if last else None,
        "classes": classes,
    }


def apply(*, request: Any, overrides: dict[str, str], confirm: bool = False) -> PromotionRun:
    """Move every active pupil per the plan, with per-pupil overrides by student id."""
    bad = {sid: a for sid, a in overrides.items() if a not in ACTIONS}
    if bad:
        raise ValidationError({"overrides": "Use promote, repeat, graduate or leave."})
    session = AcademicSession.objects.filter(is_current=True).first()
    if session and not confirm and PromotionRun.objects.filter(session=session).exists():
        raise AlreadyPromoted(
            {
                "detail": f"Pupils were already moved up for {session.name}. Doing it again "
                "would move them up twice; confirm only if that's what you mean.",
                "code": "already_promoted",
            }
        )
    nexts = _next_levels()
    counts = {"promoted": 0, "repeated": 0, "graduated": 0, "left": 0}
    moves: list[dict[str, Any]] = []
    with tenant_atomic():
        # Top classes first, so nobody is moved twice in one run.
        for arm in (
            ClassArm.objects.filter(level__is_active=True)
            .select_related("level")
            .order_by("-level__order", "name")
        ):
            nxt = nexts.get(arm.level_id)
            target = None
            for pupil in Student.objects.filter(arm=arm, status=Student.Status.ACTIVE):
                action = overrides.get(str(pupil.pk)) or ("promote" if nxt else "graduate")
                if action == "promote" and nxt is None:
                    action = "graduate"  # nowhere further to go
                move = {
                    "student": str(pupil.pk),
                    "name": pupil.full_name,
                    "action": action,
                    "from": str(arm),
                }
                if action == "promote":
                    if target is None:
                        target, _ = ClassArm.objects.get_or_create(level=nxt, name=arm.name)
                    pupil.arm = target
                    pupil.save(update_fields=["arm"])
                    move["to"] = str(target)
                    counts["promoted"] += 1
                elif action == "graduate":
                    pupil.status = Student.Status.GRADUATED
                    pupil.save(update_fields=["status"])
                    counts["graduated"] += 1
                elif action == "leave":
                    pupil.status = Student.Status.WITHDRAWN
                    pupil.save(update_fields=["status"])
                    counts["left"] += 1
                else:
                    counts["repeated"] += 1
                moves.append(move)
        run = PromotionRun.objects.create(
            session=session, run_by=request.user.pk, summary=counts, moves=moves
        )
        record_event(action="students.promoted", request=request, target=run, after=counts)
    return run
