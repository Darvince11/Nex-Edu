"""Scores in, report cards out.

- Teachers enter scores only for the arm + subject they are assigned to.
- Computing results freezes a snapshot per student (``ReportCard.lines``).
- Publishing makes cards visible to parents and locks the scores behind them.
- After publication, a score changes only through ``amend_score``: it needs the
  amend permission and a reason, is audited, and regenerates the class's cards.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.http import HttpRequest
from django.utils import timezone

from apps.academics.models import ClassArm, Section, Subject, Term
from apps.academics.selectors import subjects_for_arm, teaches_subject
from apps.attendance.models import AttendanceRecord
from apps.attendance.services import days_open
from apps.students.models import Student
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm

from .models import AssessmentComponent, GradeBand, ReportCard, Score

TWO = Decimal("0.01")

# BECE grading used for JHS (WAEC Ghana). Lower grade = better; points = grade number.
BECE_BANDS = [
    ("1", 80, 100, "Highest", 1),
    ("2", 70, 79.99, "Higher", 2),
    ("3", 60, 69.99, "High", 3),
    ("4", 55, 59.99, "High average", 4),
    ("5", 50, 54.99, "Average", 5),
    ("6", 45, 49.99, "Low average", 6),
    ("7", 40, 44.99, "Low", 7),
    ("8", 35, 39.99, "Lower", 8),
    ("9", 0, 34.99, "Lowest", 9),
]
# NaCCA standards-based proficiency levels for KG and primary.
PROFICIENCY_BANDS = [
    ("HP", 80, 100, "Highly proficient", 5),
    ("P", 68, 79.99, "Proficient", 4),
    ("AP", 54, 67.99, "Approaching proficiency", 3),
    ("D", 40, 53.99, "Developing", 2),
    ("E", 0, 39.99, "Emerging", 1),
]
# GES school-based assessment: class score 30%, end-of-term examination 70%.
DEFAULT_COMPONENTS = [("Class score", "CS", 30, 1), ("End-of-term exam", "EXAM", 70, 2)]


class ScoresLocked(ValidationError):
    pass


def seed_grading_defaults() -> None:
    with tenant_atomic():
        for section, bands in (("", PROFICIENCY_BANDS), (Section.JHS, BECE_BANDS)):
            for grade, low, high, remark, points in bands:
                GradeBand.objects.get_or_create(
                    section=section,
                    grade=grade,
                    defaults={
                        "min_score": Decimal(str(low)),
                        "max_score": Decimal(str(high)),
                        "remark": remark,
                        "points": Decimal(points),
                    },
                )
        if not AssessmentComponent.objects.exists():
            for name, code, max_score, order in DEFAULT_COMPONENTS:
                AssessmentComponent.objects.create(
                    name=name, code=code, max_score=Decimal(max_score), order=order
                )


def active_components() -> list[AssessmentComponent]:
    components = list(AssessmentComponent.objects.filter(is_active=True))
    total = sum((c.max_score for c in components), Decimal(0))
    if total != Decimal(100):
        raise ValidationError(f"Active assessment components add up to {total}, not 100.")
    return components


def grade_for(total: Decimal, section: str) -> GradeBand | None:
    bands = list(GradeBand.objects.filter(section=section)) or list(
        GradeBand.objects.filter(section="")
    )
    for band in bands:
        if band.min_score <= total <= band.max_score:
            return band
    return None


def bece_aggregate(lines: list[dict[str, Any]]) -> int | None:
    """BECE-style aggregate: the four core subjects plus the best two others.

    Lower is better (6 is the best possible). None if a core subject or enough
    electives are missing.
    """
    from apps.academics.services import BECE_CORE_CODES

    points = {line["code"]: line.get("points") for line in lines if line.get("points") is not None}
    if any(code not in points for code in BECE_CORE_CODES):
        return None
    others = sorted(v for code, v in points.items() if code not in BECE_CORE_CODES)
    if len(others) < 2:
        return None
    return sum(points[c] for c in BECE_CORE_CODES) + sum(others[:2])


def ordinal(n: int | None) -> str:
    if n is None:
        return ""
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def competition_rank(values: dict[Any, Decimal]) -> dict[Any, int]:
    """Standard competition ranking: equal values share a place (1, 1, 3)."""
    ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=True)
    ranks: dict[Any, int] = {}
    previous: Decimal | None = None
    place = 0
    for index, (key, value) in enumerate(ordered, start=1):
        if value != previous:
            place, previous = index, value
        ranks[key] = place
    return ranks


def _published_lock(term: Term, student_ids: list[Any]) -> set[str]:
    return {
        str(sid)
        for sid in ReportCard.objects.filter(
            term=term, student_id__in=student_ids, status=ReportCard.Status.PUBLISHED
        ).values_list("student_id", flat=True)
    }


def can_record(user: Any, permissions: frozenset[str], arm: ClassArm, subject: Subject) -> bool:
    if Perm.ASSESSMENTS_MANAGE in permissions:
        return True
    return Perm.ASSESSMENTS_RECORD in permissions and teaches_subject(user, arm.pk, subject.pk)


def score_sheet(arm: ClassArm, subject: Subject, term: Term) -> dict[str, Any]:
    components = list(AssessmentComponent.objects.filter(is_active=True))
    students = list(
        Student.objects.filter(arm=arm, status=Student.Status.ACTIVE).order_by(
            "last_name", "first_name"
        )
    )
    scores: dict[tuple[str, int], Decimal] = {
        (str(s.student_id), s.component_id): s.score
        for s in Score.objects.filter(term=term, subject=subject, student__in=students)
    }
    locked = _published_lock(term, [s.pk for s in students])
    return {
        "components": [
            {"id": c.pk, "name": c.name, "code": c.code, "max_score": str(c.max_score)}
            for c in components
        ],
        "rows": [
            {
                "student": str(s.pk),
                "admission_number": s.admission_number,
                "name": s.full_name,
                "locked": str(s.pk) in locked,
                "scores": {
                    str(c.pk): (
                        str(scores[(str(s.pk), c.pk)]) if (str(s.pk), c.pk) in scores else None
                    )
                    for c in components
                },
            }
            for s in students
        ],
    }


def record_scores(
    *,
    request: HttpRequest | None,
    user: Any,
    permissions: frozenset[str],
    arm: ClassArm,
    subject: Subject,
    term: Term,
    entries: list[dict[str, Any]],
) -> dict[str, int]:
    """entries: [{"student": id, "component": id, "score": "17.5" | None}] (None clears)."""
    if not can_record(user, permissions, arm, subject):
        raise PermissionDenied("You can only enter scores for subjects you teach in this class.")
    components = {c.pk: c for c in AssessmentComponent.objects.filter(is_active=True)}
    student_ids = {
        str(pk)
        for pk in Student.objects.filter(arm=arm, status=Student.Status.ACTIVE).values_list(
            "pk", flat=True
        )
    }
    locked = _published_lock(term, list(student_ids))
    errors: list[str] = []
    for e in entries:
        sid, cid = str(e["student"]), int(e["component"])
        if sid not in student_ids:
            errors.append(f"Student {sid} is not in {arm}.")
        if cid not in components:
            errors.append(f"Unknown assessment component {cid}.")
        elif e.get("score") is not None:
            value = Decimal(str(e["score"]))
            if value < 0 or value > components[cid].max_score:
                errors.append(f"Score {value} is outside 0-{components[cid].max_score}.")
        if sid in locked:
            errors.append("Results for this term are published. Ask the principal to amend.")
    if errors:
        raise ValidationError(sorted(set(errors)))

    changed = cleared = 0
    with tenant_atomic():
        for e in entries:
            key = {
                "student_id": e["student"],
                "subject": subject,
                "term": term,
                "component_id": int(e["component"]),
            }
            if e.get("score") is None:
                cleared += Score.objects.filter(**key).delete()[0]
                continue
            value = Decimal(str(e["score"])).quantize(TWO)
            score, created = Score.objects.get_or_create(
                **key, defaults={"score": value, "entered_by": user.pk}
            )
            if created or score.score != value:
                score.score, score.entered_by = value, user.pk
                score.save(update_fields=["score", "entered_by", "updated_at"])
                changed += 1
        record_event(
            action="assessments.scores_recorded",
            request=request,
            target=arm,
            after={
                "subject": subject.code,
                "term": str(term.pk),
                "changed": changed,
                "cleared": cleared,
            },
        )
    return {"changed": changed, "cleared": cleared}


def _build(arm: ClassArm, term: Term) -> dict[str, dict[str, Any]]:
    """Compute every student's results for the arm and term (no writes)."""
    components = active_components()
    section = arm.level.section
    students = list(Student.objects.filter(arm=arm, status=Student.Status.ACTIVE))
    sids = [s.pk for s in students]
    subjects = {s.pk: s for s in subjects_for_arm(arm)}
    raw: dict[tuple[str, int], dict[int, Decimal]] = defaultdict(dict)
    for score in Score.objects.filter(term=term, student_id__in=sids).select_related("subject"):
        subjects.setdefault(score.subject_id, score.subject)
        raw[(str(score.student_id), score.subject_id)][score.component_id] = score.score

    # Subject totals and per-subject class statistics.
    totals: dict[int, dict[str, Decimal]] = defaultdict(dict)
    for (sid, subject_id), parts in raw.items():
        totals[subject_id][sid] = sum(parts.values(), Decimal(0))

    stats: dict[int, dict[str, Any]] = {}
    for subject_id, by_student in totals.items():
        values = list(by_student.values())
        stats[subject_id] = {
            "highest": max(values),
            "lowest": min(values),
            "average": (sum(values, Decimal(0)) / len(values)).quantize(TWO, ROUND_HALF_UP),
            "ranks": competition_rank(by_student),
        }

    cards: dict[str, dict[str, Any]] = {}
    for student in students:
        sid = str(student.pk)
        lines = []
        for subject_id, subject in sorted(subjects.items(), key=lambda kv: kv[1].name):
            if sid not in totals.get(subject_id, {}):
                continue  # subject not taken
            total = totals[subject_id][sid]
            band = grade_for(total, section)
            parts = raw[(sid, subject_id)]
            lines.append(
                {
                    "subject": subject.name,
                    "code": subject.code,
                    "components": {
                        c.code: (str(parts[c.pk]) if c.pk in parts else None) for c in components
                    },
                    "total": str(total),
                    "grade": band.grade if band else "",
                    "points": int(band.points) if band else None,
                    "remark": band.remark if band else "",
                    "position": ordinal(stats[subject_id]["ranks"][sid]),
                    "class_highest": str(stats[subject_id]["highest"]),
                    "class_lowest": str(stats[subject_id]["lowest"]),
                    "class_average": str(stats[subject_id]["average"]),
                }
            )
        grand = sum((Decimal(line["total"]) for line in lines), Decimal(0))
        average = (grand / len(lines)).quantize(TWO, ROUND_HALF_UP) if lines else Decimal(0)
        aggregate = bece_aggregate(lines) if section == Section.JHS else None
        cards[sid] = {
            "lines": lines,
            "total_score": grand,
            "average": average,
            "aggregate": aggregate,
        }

    ranks = competition_rank({sid: c["average"] for sid, c in cards.items() if c["lines"]})
    present = {
        str(row["student_id"]): row["n"]
        for row in AttendanceRecord.objects.filter(
            term=term, student_id__in=sids, status__in=["present", "late"]
        )
        .values("student_id")
        .annotate(n=Count("id"))
    }
    opened = days_open(arm.pk, term)
    for sid, card in cards.items():
        card["position"] = ranks.get(sid)
        card["class_size"] = len(ranks)
        card["days_present"] = present.get(sid, 0)
        card["days_open"] = opened
    return cards


def compute_results(
    *, request: HttpRequest | None, arm: ClassArm, term: Term, include_published: bool = False
) -> dict[str, int]:
    cards = _build(arm, term)
    now = timezone.now()
    created = updated = skipped = 0
    with tenant_atomic():
        existing = {str(c.student_id): c for c in ReportCard.objects.filter(arm=arm, term=term)}
        for sid, data in cards.items():
            card = existing.get(sid) or ReportCard.objects.filter(student_id=sid, term=term).first()
            if card and card.status == ReportCard.Status.PUBLISHED and not include_published:
                skipped += 1
                continue
            fields = {**data, "arm": arm, "computed_at": now}
            if card is None:
                ReportCard.objects.create(student_id=sid, term=term, **fields)
                created += 1
            else:
                for k, v in fields.items():
                    setattr(card, k, v)
                if card.status == ReportCard.Status.PUBLISHED:
                    card.needs_regeneration = True
                card.save()
                updated += 1
        record_event(
            action="assessments.results_computed",
            request=request,
            target=arm,
            after={
                "term": str(term.pk),
                "created": created,
                "updated": updated,
                "skipped_published": skipped,
            },
        )
    return {"created": created, "updated": updated, "skipped_published": skipped}


def publish_results(*, request: HttpRequest | None, arm: ClassArm, term: Term) -> int:
    from apps.communication.models import Channel, MessagingSettings
    from apps.communication.services import notify_guardians

    with tenant_atomic():
        drafts = list(
            ReportCard.objects.filter(
                arm=arm, term=term, status=ReportCard.Status.DRAFT
            ).select_related("student")
        )
        if not drafts:
            raise ValidationError("There are no draft results to publish. Compute results first.")
        now = timezone.now()
        ReportCard.objects.filter(pk__in=[c.pk for c in drafts]).update(
            status=ReportCard.Status.PUBLISHED, published_at=now, needs_regeneration=True
        )
        record_event(
            action="assessments.results_published",
            request=request,
            target=arm,
            after={"term": str(term.pk), "published": len(drafts)},
        )
        from control_plane.developer import emit

        emit(
            "results.published", {"class": str(arm), "term": str(term), "report_cards": len(drafts)}
        )

    _schedule_pdfs(arm, term)
    channels = {Channel.SMS} if MessagingSettings.load().notify_results_by_sms else set()
    for card in drafts:
        notify_guardians(
            [card.student],
            kind="results",
            title="Results available",
            body=f"{card.student.first_name}'s {term} report card is ready in Nex Edu.",
            data={"report_card_id": str(card.pk)},
            channels=channels,
        )
    return len(drafts)


def amend_score(
    *,
    request: HttpRequest | None,
    user: Any,
    permissions: frozenset[str],
    student: Student,
    subject: Subject,
    term: Term,
    component: AssessmentComponent,
    score: Decimal,
    reason: str,
) -> Score:
    if Perm.ASSESSMENTS_AMEND not in permissions:
        raise PermissionDenied("Only the principal can amend published results.")
    if len(reason.strip()) < 10:
        raise ValidationError("Give a reason of at least 10 characters for the amendment.")
    if score < 0 or score > component.max_score:
        raise ValidationError(f"Score must be between 0 and {component.max_score}.")
    if student.arm is None:
        raise ValidationError("The student has no class.")
    with tenant_atomic():
        existing = Score.objects.filter(
            student=student, subject=subject, term=term, component=component
        ).first()
        before = str(existing.score) if existing else None
        obj, _ = Score.objects.update_or_create(
            student=student,
            subject=subject,
            term=term,
            component=component,
            defaults={"score": score.quantize(TWO), "entered_by": user.pk},
        )
        record_event(
            action="assessments.score_amended",
            request=request,
            target=obj,
            before={"score": before},
            after={"score": str(obj.score), "subject": subject.code, "component": component.code},
            reason=reason,
        )
        compute_results(request=request, arm=student.arm, term=term, include_published=True)
    _schedule_pdfs(student.arm, term)
    return obj


def _schedule_pdfs(arm: ClassArm, term: Term) -> None:
    from django.db import transaction

    from .tasks import generate_report_card_pdfs

    tenant = require_tenant()
    transaction.on_commit(
        lambda: generate_report_card_pdfs.apply_async(
            args=[str(arm.pk), term.pk], kwargs={"tenant_slug": tenant.slug}
        ),
        using=tenant.db_alias,
    )
