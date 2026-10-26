"""Private calendar links (iCalendar, RFC 5545) that Google Calendar, Outlook and
Apple Calendar subscribe to.

Each person gets one link per school. The token is random, shown once, and only
its hash is kept; replacing it kills the old link. The feed carries what the
school calendar page shows that person (staff-only events only for staff), term
dates, Ghana's public holidays and, with Parent meetings on, their booked slots.
Ghana keeps GMT all year, so times are written in UTC.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from typing import Any

from django.conf import settings
from django.utils import timezone

from control_plane.models import CalendarFeed, Membership, Tenant
from control_plane.tenancy import tenant_context
from core.rbac import STAFF_ROLES

PREFIX = "cal_"
PAST_DAYS, FUTURE_DAYS = 60, 400


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(user: Any, tenant: Tenant) -> str:
    """A new link for the person (the old one stops working). Returns the token."""
    token = PREFIX + secrets.token_urlsafe(24)
    CalendarFeed.objects.update_or_create(
        user=user, tenant=tenant, defaults={"token_hash": _hash(token), "last_used_at": None}
    )
    return token


def url_for(token: str) -> str:
    return f"{settings.FRONTEND_URL}/api/v1/public/calendar/{token}/"


def find(token: str) -> CalendarFeed | None:
    if not token.startswith(PREFIX):
        return None
    feed = (
        CalendarFeed.objects.select_related("user", "tenant")
        .filter(token_hash=_hash(token))
        .first()
    )
    if feed is None or feed.tenant.status != Tenant.Status.ACTIVE or not feed.user.is_active:
        return None
    roles = set(
        Membership.objects.filter(user=feed.user, tenant=feed.tenant, is_active=True).values_list(
            "role", flat=True
        )
    )
    return feed if roles else None


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Lines longer than 75 octets are folded (RFC 5545 3.1)."""
    out, raw = [], line.encode()
    while len(raw) > 75:
        cut = 75
        while (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode())
        raw = b" " + raw[cut:]
    out.append(raw.decode())
    return "\r\n".join(out)


def _stamp(day: dt.date, time: dt.time | None) -> str:
    return day.strftime("%Y%m%d") + (time.strftime("T%H%M%SZ") if time else "")


def _event(uid: str, title: str, start: dt.date, end: dt.date, **extra: Any) -> list[str]:
    starts_at, ends_at = extra.get("starts_at"), extra.get("ends_at")
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{timezone.now():%Y%m%dT%H%M%SZ}"]
    if starts_at:
        lines += [
            f"DTSTART:{_stamp(start, starts_at)}",
            f"DTEND:{_stamp(end, ends_at or starts_at)}",
        ]
    else:  # all-day: DTEND is the day after
        lines += [
            f"DTSTART;VALUE=DATE:{_stamp(start, None)}",
            f"DTEND;VALUE=DATE:{_stamp(end + dt.timedelta(days=1), None)}",
        ]
    lines.append(f"SUMMARY:{_escape(title)}")
    if extra.get("location"):
        lines.append(f"LOCATION:{_escape(extra['location'])}")
    if extra.get("description"):
        lines.append(f"DESCRIPTION:{_escape(extra['description'])}")
    lines.append("END:VEVENT")
    return lines


def render(feed: CalendarFeed) -> str:
    from apps.academics.calendar import entries
    from control_plane.modules import is_active

    tenant, user = feed.tenant, feed.user
    roles = set(
        Membership.objects.filter(user=user, tenant=tenant, is_active=True).values_list(
            "role", flat=True
        )
    )
    today = timezone.localdate()
    start, end = today - dt.timedelta(days=PAST_DAYS), today + dt.timedelta(days=FUTURE_DAYS)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Nex Edu//School calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(tenant.name)}",
        "X-WR-TIMEZONE:Africa/Accra",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
    ]
    with tenant_context(tenant):
        for i, row in enumerate(entries(start, end, staff=bool(roles & STAFF_ROLES))):
            key = row["id"] or f"{row['source']}-{row['starts_on']}-{i}"
            uid = f"{key}@{tenant.slug}.nexedu"
            lines += _event(
                uid,
                row["title"],
                row["starts_on"],
                row["ends_on"],
                starts_at=row["starts_at"],
                ends_at=row["ends_at"],
                location=row["location"],
                description=row["description"],
            )
        if is_active(tenant, "meetings"):
            lines += _meeting_slots(user, start, end, tenant.slug)
    lines.append("END:VCALENDAR")
    CalendarFeed.objects.filter(pk=feed.pk).update(last_used_at=timezone.now())
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _meeting_slots(user: Any, start: dt.date, end: dt.date, slug: str) -> list[str]:
    """Parent meetings the person booked (parents) or has booked with them (teachers)."""
    from django.db.models import Q

    from apps.meetings.models import Slot

    lines: list[str] = []
    slots = Slot.objects.filter(
        Q(booked_by=user.pk) | Q(teacher_user_id=user.pk, student__isnull=False),
        day__date__range=(start, end),
    ).select_related("day", "student")
    for slot in slots:
        who = f" ({slot.student.first_name})" if slot.student else ""
        lines += _event(
            f"slot-{slot.pk}@{slug}.nexedu",
            f"{slot.day.title}{who}",
            slot.day.date,
            slot.day.date,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            location=slot.day.location,
        )
    return lines
