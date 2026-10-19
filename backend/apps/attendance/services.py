from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import HttpRequest
from django.utils import timezone

from apps.academics.models import ClassArm, Term
from apps.academics.selectors import teaches_arm
from apps.students.models import Student
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm

from .models import AttendanceRecord, SyncedBatch

S = AttendanceRecord.Status
PRESENT_LIKE = (S.PRESENT, S.LATE)


def term_for(day: date) -> Term:
    term = Term.objects.filter(starts_on__lte=day, ends_on__gte=day).first()
    if term is None:
        raise ValidationError("No term covers this date. Set up the term dates first.")
    return term


def can_take_register(user: Any, permissions: frozenset[str], arm: ClassArm) -> bool:
    if Perm.ATTENDANCE_MANAGE in permissions:
        return True
    return Perm.ATTENDANCE_RECORD in permissions and teaches_arm(user, arm.pk)


def record_register(
    *,
    request: HttpRequest | None,
    user: Any,
    permissions: frozenset[str],
    arm: ClassArm,
    day: date,
    entries: list[dict[str, Any]],
    batch_id: UUID | None = None,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    if not can_take_register(user, permissions, arm):
        raise PermissionDenied("You can only take the register for classes you teach.")
    if day > timezone.localdate():
        raise ValidationError("You can't take a register for a future date.")
    if batch_id and (done := SyncedBatch.objects.filter(pk=batch_id).first()):
        return {**done.result, "replayed": True}

    term = term_for(day)
    recorded_at = recorded_at or timezone.now()
    if recorded_at > timezone.now() + timedelta(minutes=5):
        recorded_at = timezone.now()  # don't let a fast device clock win every conflict

    by_id = {str(e["student"]): e for e in entries}
    students = {
        str(s.pk): s
        for s in Student.objects.filter(pk__in=list(by_id), arm=arm, status=Student.Status.ACTIVE)
    }
    if unknown := set(by_id) - set(students):
        raise ValidationError(f"{len(unknown)} student(s) are not in {arm}.")

    existing = {
        str(r.student_id): r
        for r in AttendanceRecord.objects.filter(student_id__in=list(by_id), date=day)
    }
    created = updated = unchanged = 0
    conflicts: list[dict[str, Any]] = []
    newly_absent: list[Student] = []

    with tenant_atomic():
        for sid, entry in by_id.items():
            status, note = entry["status"], entry.get("note", "")
            record = existing.get(sid)
            if record is None:
                record = AttendanceRecord.objects.create(
                    student_id=sid,
                    arm=arm,
                    term=term,
                    date=day,
                    status=status,
                    note=note,
                    recorded_by=user.pk,
                    recorded_at=recorded_at,
                    batch_id=batch_id,
                )
                created += 1
            elif record.recorded_at > recorded_at:
                if record.status != status:
                    conflicts.append({"student": sid, "kept": record.status, "submitted": status})
                unchanged += 1
                continue
            elif record.status == status and record.note == note:
                unchanged += 1
                continue
            else:
                record.status, record.note = status, note
                record.recorded_by, record.recorded_at, record.batch_id = (
                    user.pk,
                    recorded_at,
                    batch_id,
                )
                if status != S.ABSENT:
                    record.parent_notified = False
                record.save()
                updated += 1
            if status == S.ABSENT and not record.parent_notified:
                newly_absent.append(students[sid])

        result = {
            "arm": str(arm.pk),
            "date": day.isoformat(),
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "conflicts": conflicts,
            "replayed": False,
        }
        if batch_id:
            SyncedBatch.objects.create(pk=batch_id, result=result)
        record_event(
            action="attendance.register_taken",
            request=request,
            target=arm,
            after={k: v for k, v in result.items() if k != "conflicts"}
            | {"conflicts": len(conflicts)},
        )

    if newly_absent and day >= timezone.localdate() - timedelta(days=1):
        _notify_absences(newly_absent, day)
    return result


def _notify_absences(students: list[Student], day: date) -> None:
    from apps.communication.models import Channel, MessagingSettings
    from apps.communication.services import notify_guardians

    channels = {Channel.SMS} if MessagingSettings.load().notify_absence_by_sms else set()
    for student in students:
        notify_guardians(
            [student],
            kind="absence",
            title="Absence",
            body=f"{student.first_name} {student.last_name} was marked absent on {day:%a %d %b}.",
            data={"student_id": str(student.pk), "date": day.isoformat()},
            channels=channels,
        )
    AttendanceRecord.objects.filter(student__in=students, date=day).update(parent_notified=True)


def register_sheet(arm: ClassArm, day: date) -> list[dict[str, Any]]:
    records = {r.student_id: r for r in AttendanceRecord.objects.filter(arm=arm, date=day)}
    rows = []
    for s in Student.objects.filter(arm=arm, status=Student.Status.ACTIVE).order_by(
        "last_name", "first_name"
    ):
        r = records.get(s.pk)
        rows.append(
            {
                "student": str(s.pk),
                "admission_number": s.admission_number,
                "name": s.full_name,
                "status": r.status if r else None,
                "note": r.note if r else "",
            }
        )
    return rows


def days_open(arm_id: Any, term: Term) -> int:
    return (
        AttendanceRecord.objects.filter(arm_id=arm_id, term=term).values("date").distinct().count()
    )


def student_summary(student: Student, term: Term) -> dict[str, int]:
    counts = dict(
        AttendanceRecord.objects.filter(student=student, term=term)
        .values_list("status")
        .annotate(n=Count("id"))
    )
    present = sum(counts.get(s, 0) for s in PRESENT_LIKE)
    return {
        "present": present,
        "absent": counts.get(S.ABSENT, 0),
        "late": counts.get(S.LATE, 0),
        "excused": counts.get(S.EXCUSED, 0),
        "days_open": days_open(student.arm_id, term) if student.arm_id else 0,
    }


def arm_summary(arm: ClassArm, term: Term) -> list[dict[str, Any]]:
    rows = (
        AttendanceRecord.objects.filter(arm=arm, term=term)
        .values("student_id")
        .annotate(
            present=Count("id", filter=Q(status__in=PRESENT_LIKE)),
            absent=Count("id", filter=Q(status=S.ABSENT)),
            late=Count("id", filter=Q(status=S.LATE)),
        )
    )
    return [{**r, "student_id": str(r["student_id"])} for r in rows]
