"""Parent meetings: slots, bookings and who may book whom.

- School leaders set up a day and add the teachers taking part; each teacher's time
  is cut into slots of ``slot_minutes``.
- Once bookings open, a parent books one slot per child with each teacher who
  teaches that child's class (or with the head teacher, if taking part).
- Parents never see who else has booked; teachers see their own list.
- Either side can cancel before the day; the other is told.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Any

from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.academics.models import TeachingAssignment
from apps.students.models import Student, StudentGuardian
from control_plane.models import Membership, Role, User
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.rbac import STAFF_ROLES

from .models import MeetingDay, MeetingTeacher, Slot

MAX_SLOTS_PER_TEACHER = 80


def names(user_ids: Iterable[Any]) -> dict[Any, str]:
    return {u.pk: u.get_full_name() or u.email for u in User.objects.filter(pk__in=set(user_ids))}


def slot_times(day: MeetingDay) -> list[tuple[dt.time, dt.time]]:
    step = dt.timedelta(minutes=day.slot_minutes)
    start = dt.datetime.combine(day.date, day.starts_at)
    end = dt.datetime.combine(day.date, day.ends_at)
    times = []
    while start + step <= end:
        times.append((start.time(), (start + step).time()))
        start += step
    return times


def add_teacher(*, day: MeetingDay, user_id: Any, room: str = "") -> MeetingTeacher:
    if not Membership.objects.filter(
        tenant=require_tenant(), user_id=user_id, is_active=True, role__in=STAFF_ROLES
    ).exists():
        raise ValidationError({"user": "Only active members of staff can see parents."})
    times = slot_times(day)
    if not times:
        raise ValidationError({"user": "The day is too short for even one slot."})
    if len(times) > MAX_SLOTS_PER_TEACHER:
        raise ValidationError({"user": f"Keep to {MAX_SLOTS_PER_TEACHER} slots per teacher."})
    with tenant_atomic():
        teacher, created = MeetingTeacher.objects.get_or_create(
            day=day, user_id=user_id, defaults={"room": room}
        )
        if created:
            Slot.objects.bulk_create(
                [Slot(day=day, teacher_user_id=user_id, starts_at=a, ends_at=b) for a, b in times]
            )
    return teacher


def remove_teacher(*, request: HttpRequest, day: MeetingDay, user_id: Any) -> None:
    booked = list(
        Slot.objects.filter(day=day, teacher_user_id=user_id, student__isnull=False).select_related(
            "student"
        )
    )
    with tenant_atomic():
        for slot in booked:
            _tell_parent_cancelled(slot, "The teacher is no longer available that day.")
        Slot.objects.filter(day=day, teacher_user_id=user_id).delete()
        MeetingTeacher.objects.filter(day=day, user_id=user_id).delete()
        record_event(
            action="meetings.teacher_removed",
            request=request,
            target=day,
            after={"user": str(user_id), "bookings_cancelled": len(booked)},
        )


def children_of(user: Any) -> list[Student]:
    ids = StudentGuardian.objects.filter(guardian_user_id=user.pk).values("student_id")
    return list(
        Student.objects.filter(pk__in=ids, status=Student.Status.ACTIVE).select_related(
            "arm__level"
        )
    )


def teachers_for(student: Student, day: MeetingDay) -> dict[Any, list[str]]:
    """Teachers on the day a parent of ``student`` may book, with what they teach."""
    on_day = set(day.teachers.values_list("user_id", flat=True))
    found: dict[Any, list[str]] = {}
    if student.arm_id:
        for a in TeachingAssignment.objects.filter(
            arm_id=student.arm_id, teacher_user_id__in=on_day
        ).select_related("subject"):
            label = "Class teacher" if a.is_form_teacher or not a.subject else a.subject.name
            found.setdefault(a.teacher_user_id, [])
            if label not in found[a.teacher_user_id]:
                found[a.teacher_user_id].append(label)
    for head in Membership.objects.filter(
        tenant=require_tenant(), role=Role.PRINCIPAL, is_active=True, user_id__in=on_day
    ).values_list("user_id", flat=True):
        found.setdefault(head, []).append("Head teacher")
    return found


def parent_view(user: Any, day: MeetingDay) -> list[dict[str, Any]]:
    """For each of the parent's children: the teachers they may book and the free
    times (others' bookings show only as taken)."""
    who = names(day.teachers.values_list("user_id", flat=True))
    rooms = dict(day.teachers.values_list("user_id", "room"))
    out = []
    for child in children_of(user):
        teachers = teachers_for(child, day)
        slots = Slot.objects.filter(day=day, teacher_user_id__in=teachers)
        by_teacher: dict[Any, list[dict[str, Any]]] = {t: [] for t in teachers}
        booked: dict[Any, dict[str, Any]] = {}
        for s in slots:
            mine = s.student_id == child.pk
            entry = {
                "id": str(s.id),
                "starts_at": s.starts_at,
                "ends_at": s.ends_at,
                "free": s.student_id is None,
                "mine": mine,
            }
            by_teacher[s.teacher_user_id].append(entry)
            if mine:
                booked[s.teacher_user_id] = {**entry, "note": s.note}
        out.append(
            {
                "student": str(child.pk),
                "name": child.first_name,
                "class": str(child.arm) if child.arm_id else "",
                "teachers": [
                    {
                        "user": str(t),
                        "name": who.get(t, ""),
                        "teaches": ", ".join(labels),
                        "room": rooms.get(t, ""),
                        "booking": booked.get(t),
                        "slots": by_teacher[t],
                    }
                    for t, labels in sorted(teachers.items(), key=lambda kv: who.get(kv[0], ""))
                ],
            }
        )
    return out


def staff_view(day: MeetingDay, only: Any = None) -> list[dict[str, Any]]:
    """Each teacher's slots with who booked (all teachers for leaders, else one)."""
    teachers = day.teachers.all()
    if only is not None:
        teachers = teachers.filter(user_id=only)
    slots = Slot.objects.filter(day=day, teacher_user_id__in=[t.user_id for t in teachers])
    slots = slots.select_related("student__arm__level")
    parents = names(s.booked_by for s in slots if s.booked_by)
    who = names(t.user_id for t in teachers)
    rows: dict[Any, list[dict[str, Any]]] = {t.user_id: [] for t in teachers}
    for s in slots:
        rows[s.teacher_user_id].append(
            {
                "id": str(s.id),
                "starts_at": s.starts_at,
                "ends_at": s.ends_at,
                "student": str(s.student_id) if s.student_id else None,
                "student_name": s.student.full_name if s.student_id else "",
                "student_class": str(s.student.arm) if s.student_id and s.student.arm_id else "",
                "parent": parents.get(s.booked_by, "") if s.booked_by else "",
                "note": s.note,
            }
        )
    return [
        {
            "user": str(t.user_id),
            "name": who.get(t.user_id, ""),
            "room": t.room,
            "booked": sum(1 for s in rows[t.user_id] if s["student"]),
            "slots": rows[t.user_id],
        }
        for t in sorted(teachers, key=lambda t: who.get(t.user_id, ""))
    ]


def _not_past(day: MeetingDay) -> None:
    if day.date < timezone.localdate():
        raise ValidationError({"detail": "This meeting day has passed."})


def book(*, request: HttpRequest, slot: Slot, student: Student, note: str = "") -> Slot:
    day = slot.day
    _not_past(day)
    if not day.is_open:
        raise ValidationError({"detail": "Bookings for this day aren't open."})
    if not StudentGuardian.objects.filter(
        student=student, guardian_user_id=request.user.pk
    ).exists():
        raise PermissionDenied("You can only book for your own children.")
    if slot.teacher_user_id not in teachers_for(student, day):
        raise PermissionDenied("This teacher doesn't teach this child's class.")
    try:
        with transaction.atomic(using=require_tenant().db_alias):
            taken = Slot.objects.select_for_update().get(pk=slot.pk)
            if taken.student_id:
                raise ValidationError(
                    {"detail": "Someone has just booked this time. Choose another."}
                )
            taken.student, taken.booked_by = student, request.user.pk
            taken.booked_at, taken.note = timezone.now(), note.strip()
            taken.save(update_fields=["student", "booked_by", "booked_at", "note"])
    except IntegrityError as exc:
        raise ValidationError(
            {
                "detail": f"{student.first_name} already has a time with this teacher. "
                "Cancel it first."
            }
        ) from exc
    from apps.communication.services import notify_users

    notify_users(
        [slot.teacher_user_id],
        kind="meeting",
        title="Parent meeting booked",
        body=(
            f"A parent of {student.full_name} booked {taken.starts_at:%H:%M} on "
            f"{day.date:%a %d %b} ({day.title})."
        ),
        data={"day": str(day.pk)},
    )
    return taken


def _tell_parent_cancelled(slot: Slot, reason: str) -> None:
    from apps.communication.services import notify_users

    if slot.booked_by:
        notify_users(
            [slot.booked_by],
            kind="meeting",
            title="Parent meeting cancelled",
            body=(
                f"Your {slot.starts_at:%H:%M} meeting about {slot.student.first_name} on "
                f"{slot.day.date:%a %d %b} was cancelled. {reason}"
            ),
            data={"day": str(slot.day_id)},
        )


def cancel(*, request: HttpRequest, slot: Slot, manage: bool) -> Slot:
    from apps.communication.services import notify_users

    _not_past(slot.day)
    if slot.student_id is None:
        raise ValidationError({"detail": "This time isn't booked."})
    by_parent = slot.booked_by == request.user.pk
    by_teacher = slot.teacher_user_id == request.user.pk
    if not (by_parent or by_teacher or manage):
        raise PermissionDenied(
            "Only the parent who booked, the teacher or a school leader can cancel."
        )
    if by_parent:
        notify_users(
            [slot.teacher_user_id],
            kind="meeting",
            title="Parent meeting cancelled",
            body=(
                f"The {slot.starts_at:%H:%M} meeting about {slot.student.full_name} was cancelled."
            ),
            data={"day": str(slot.day_id)},
        )
    else:
        _tell_parent_cancelled(slot, "Please book another time.")
    slot.student = None
    slot.booked_by = None
    slot.booked_at = None
    slot.note = ""
    slot.save(update_fields=["student", "booked_by", "booked_at", "note"])
    return slot


def open_bookings(*, request: HttpRequest, day: MeetingDay) -> int:
    """Open the day for booking and tell the parents of pupils its teachers teach."""
    from apps.communication.services import notify_users

    _not_past(day)
    if not day.teachers.exists():
        raise ValidationError({"detail": "Add the teachers taking part first."})
    teachers = list(day.teachers.values_list("user_id", flat=True))
    arms = TeachingAssignment.objects.filter(teacher_user_id__in=teachers).values("arm_id")
    parents = set(
        StudentGuardian.objects.filter(
            student__arm_id__in=arms, student__status=Student.Status.ACTIVE
        )
        .exclude(guardian_user_id=None)
        .values_list("guardian_user_id", flat=True)
    )
    with tenant_atomic():
        day.is_open = True
        day.save(update_fields=["is_open"])
        record_event(action="meetings.opened", request=request, target=day)
    notify_users(
        parents,
        kind="meeting",
        title=f"Book a parent meeting: {day.title}",
        body=(
            f"Teachers are meeting parents on {day.date:%A %d %B}"
            f"{f' at {day.location}' if day.location else ''}. Book a time in Nex Edu."
        ),
        data={"day": str(day.pk)},
    )
    return len(parents)
