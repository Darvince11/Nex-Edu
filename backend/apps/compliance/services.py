"""Compliance: the starter checklist, completing items (and rolling renewals on) and reminders."""

from __future__ import annotations

import calendar
import datetime as dt

from django.utils import timezone

from apps.communication.services import member_ids, notify_users

from .models import Requirement

A = Requirement.Area

#: A starting point for a Ghanaian private basic school. No dates: the school
#: fills them in from its own certificates, since terms differ by office.
STARTER: list[tuple[str, str, str]] = [
    (A.LICENCE, "School licence", "National Schools Inspectorate Authority (NaSIA)"),
    (A.SAFETY, "Fire certificate", "Ghana National Fire Service (GNFS)"),
    (A.STAFF, "Teachers' professional licences", "National Teaching Council (NTC)"),
    (A.DATA, "Data controller registration", "Data Protection Commission (Act 843)"),
    (
        A.HEALTH,
        "Health certificates for food vendors",
        "Metropolitan, Municipal or District Assembly",
    ),
    (A.SAFEGUARDING, "Child protection policy reviewed", "Ghana Education Service"),
]


def add_starter() -> int:
    """Add the starter items the school doesn't have yet (by title)."""
    have = set(Requirement.objects.values_list("title", flat=True))
    new = [
        Requirement(area=area, title=title, authority=authority)
        for area, title, authority in STARTER
        if title not in have
    ]
    Requirement.objects.bulk_create(new)
    return len(new)


def add_months(day: dt.date, months: int) -> dt.date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def complete(item: Requirement, *, on: dt.date) -> None:
    """Mark done; a renewable item's next due date moves on from the current one."""
    item.status, item.completed_on, item.last_reminded_on = Requirement.Status.DONE, on, None
    if item.renew_every_months:
        item.due_on = add_months(item.due_on or on, item.renew_every_months)
        while item.due_on <= on:  # long overdue: skip to the next one ahead
            item.due_on = add_months(item.due_on, item.renew_every_months)
    item.save(update_fields=["status", "completed_on", "due_on", "last_reminded_on"])


def send_reminders() -> int:
    """Remind the proprietor and head teacher of items due soon or overdue, weekly per item."""
    today = timezone.localdate()
    week_ago = today - dt.timedelta(days=7)
    due = [
        item
        for item in Requirement.objects.filter(due_on__isnull=False)
        if item.state(today) in ("due_soon", "overdue")
        and (item.last_reminded_on is None or item.last_reminded_on <= week_ago)
    ]
    if not due:
        return 0
    people = member_ids(["owner", "principal"])
    for item in due:
        late = item.state(today) == "overdue"
        notify_users(
            people,
            kind="compliance.due",
            title=f"{item.title}: {'overdue' if late else 'due soon'}",
            body=f"Due on {item.due_on:%d %b %Y}. {item.authority}".strip(),
            data={"requirement": str(item.pk)},
        )
        item.last_reminded_on = today
        item.save(update_fields=["last_reminded_on"])
    return len(due)
