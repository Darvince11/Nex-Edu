"""Staff records, the daily staff register, and leave.

Every login with a staff role has a staff record (``ensure_profiles``), so the
staff list and register are complete without anyone typing staff in twice.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from control_plane.models import Membership, Role, User
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.rbac import STAFF_ROLES

from .models import LeaveRequest, StaffAttendance, StaffProfile

APPROVER_ROLES = (Role.OWNER, Role.PRINCIPAL, Role.ADMIN)


def next_staff_number() -> str:
    from apps.school.services import next_number

    year, number = next_number("staff")
    return f"STF/{year}/{number:04d}"


def ensure_profiles() -> int:
    """Create a staff record for each staff login that doesn't have one yet."""
    tenant = require_tenant()
    have = set(StaffProfile.objects.exclude(user_id=None).values_list("user_id", flat=True))
    user_ids = (
        Membership.objects.filter(tenant=tenant, is_active=True, role__in=STAFF_ROLES)
        .exclude(user_id__in=have)
        .values_list("user_id", flat=True)
        .distinct()
    )
    created = 0
    for user in User.objects.filter(pk__in=list(user_ids)):
        StaffProfile.objects.create(
            user_id=user.pk,
            staff_number=next_staff_number(),
            first_name=user.first_name or user.email.split("@")[0],
            last_name=user.last_name,
            email=user.email,
            phone=user.phone,
        )
        created += 1
    return created


def profile_of(user: Any) -> StaffProfile | None:
    return StaffProfile.objects.filter(user_id=user.pk, is_active=True).first()


def working_days(start: dt.date, end: dt.date) -> int:
    """Monday to Friday between two dates, inclusive."""
    days, day = 0, start
    while day <= end:
        if day.weekday() < 5:
            days += 1
        day += dt.timedelta(days=1)
    return days


# --- Staff register -----------------------------------------------------------------------


def _on_leave(date: dt.date) -> set[Any]:
    return set(
        LeaveRequest.objects.filter(
            status=LeaveRequest.Status.APPROVED, start__lte=date, end__gte=date
        ).values_list("staff_id", flat=True)
    )


def register(date: dt.date) -> list[dict[str, Any]]:
    """Every active member of staff for a day, with any mark already saved."""
    ensure_profiles()
    marks = {m.staff_id: m for m in StaffAttendance.objects.filter(date=date)}
    leave = _on_leave(date)
    rows = []
    for staff in StaffProfile.objects.filter(is_active=True).select_related("department"):
        mark = marks.get(staff.pk)
        rows.append(
            {
                "staff": str(staff.pk),
                "name": f"{staff.first_name} {staff.last_name}".strip(),
                "staff_number": staff.staff_number,
                "job_title": staff.job_title,
                "department": staff.department.name if staff.department else "",
                "status": mark.status if mark else ("on_leave" if staff.pk in leave else None),
                "time_in": mark.time_in.strftime("%H:%M") if mark and mark.time_in else "",
                "note": mark.note if mark else "",
                "on_leave": staff.pk in leave,
            }
        )
    return rows


def save_register(*, request: Any, date: dt.date, entries: list[dict[str, Any]]) -> int:
    if date > timezone.localdate():
        raise ValidationError({"date": "You can't take a register for a future day."})
    known = set(StaffProfile.objects.values_list("pk", flat=True))
    with tenant_atomic():
        for entry in entries:
            if entry["staff"] not in known:
                raise ValidationError({"entries": "Unknown member of staff."})
            StaffAttendance.objects.update_or_create(
                staff_id=entry["staff"],
                date=date,
                defaults={
                    "status": entry["status"],
                    "time_in": entry.get("time_in"),
                    "note": entry.get("note", ""),
                    "recorded_by": request.user.pk,
                },
            )
        record_event(
            action="staff.register_saved",
            request=request,
            after={"date": date.isoformat(), "marked": len(entries)},
        )
    return len(entries)


def attendance_summary(start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    """Per member of staff: days in each status between two dates."""
    counts: dict[Any, Counter[str]] = {}
    for staff_id, status in StaffAttendance.objects.filter(date__range=(start, end)).values_list(
        "staff_id", "status"
    ):
        counts.setdefault(staff_id, Counter())[status] += 1
    return [
        {
            "staff": str(s.pk),
            "name": f"{s.first_name} {s.last_name}".strip(),
            "present": counts.get(s.pk, Counter())["present"],
            "late": counts.get(s.pk, Counter())["late"],
            "absent": counts.get(s.pk, Counter())["absent"],
            "on_leave": counts.get(s.pk, Counter())["on_leave"],
            "excused": counts.get(s.pk, Counter())["excused"],
        }
        for s in StaffProfile.objects.filter(is_active=True)
    ]


# --- Leave -----------------------------------------------------------------------------------


def _approver_ids() -> list[Any]:
    return list(
        Membership.objects.filter(tenant=require_tenant(), is_active=True, role__in=APPROVER_ROLES)
        .values_list("user_id", flat=True)
        .distinct()
    )


def _notify(user_ids: list[Any], title: str, body: str) -> None:
    from apps.communication.services import notify_users

    if user_ids:
        notify_users(user_ids, kind="leave", title=title, body=body)


def request_leave(*, request: Any, staff: StaffProfile, data: dict[str, Any]) -> LeaveRequest:
    start, end = data["start"], data["end"]
    if end < start:
        raise ValidationError({"end": "The last day can't be before the first."})
    days = working_days(start, end)
    if days == 0:
        raise ValidationError({"end": "Choose at least one working day (Monday to Friday)."})
    overlapping = LeaveRequest.objects.filter(
        staff=staff,
        status__in=[LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED],
    ).filter(Q(start__lte=end) & Q(end__gte=start))
    if overlapping.exists():
        raise ValidationError(
            {"start": "You already have leave asked for or approved on these days."}
        )
    with tenant_atomic():
        leave = LeaveRequest.objects.create(staff=staff, days=days, **data)
        record_event(
            action="staff.leave_requested",
            request=request,
            target=leave,
            after={"kind": leave.kind, "start": start.isoformat(), "end": end.isoformat()},
        )
    name = f"{staff.first_name} {staff.last_name}".strip()
    _notify(
        [uid for uid in _approver_ids() if uid != request.user.pk],
        "Leave request",
        f"{name} asked for {leave.get_kind_display().lower()}: {days} working day(s) from "
        f"{start:%d %b}. Approve or reject it under Leave.",
    )
    return leave


def decide_leave(*, request: Any, leave: LeaveRequest, approve: bool, note: str) -> LeaveRequest:
    if leave.status != LeaveRequest.Status.PENDING:
        raise ValidationError("This request has already been decided.")
    if leave.staff.user_id == request.user.pk:
        raise PermissionDenied("You can't approve or reject your own leave.")
    if not approve and not note.strip():
        raise ValidationError({"note": "Say why the request is rejected."})
    with tenant_atomic():
        leave.status = LeaveRequest.Status.APPROVED if approve else LeaveRequest.Status.REJECTED
        leave.decided_by = request.user.pk
        leave.decided_at = timezone.now()
        leave.decision_note = note.strip()[:300]
        leave.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
        record_event(
            action="staff.leave_approved" if approve else "staff.leave_rejected",
            request=request,
            target=leave,
            reason=note,
        )
    if leave.staff.user_id:
        _notify(
            [leave.staff.user_id],
            f"Leave {'approved' if approve else 'not approved'}",
            f"Your {leave.get_kind_display().lower()} from {leave.start:%d %b} was "
            f"{'approved' if approve else 'not approved'}."
            + (f" Note: {leave.decision_note}" if leave.decision_note else ""),
        )
    return leave


def cancel_leave(*, request: Any, leave: LeaveRequest) -> LeaveRequest:
    if leave.staff.user_id != request.user.pk:
        raise PermissionDenied("Only the person who asked can cancel this request.")
    if leave.status not in (LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED):
        raise ValidationError("This request can't be cancelled.")
    if leave.status == LeaveRequest.Status.APPROVED and leave.start <= timezone.localdate():
        raise ValidationError(
            "Leave that has started can't be cancelled here; ask the head teacher."
        )
    with tenant_atomic():
        leave.status = LeaveRequest.Status.CANCELLED
        leave.save(update_fields=["status"])
        record_event(action="staff.leave_cancelled", request=request, target=leave)
    return leave
