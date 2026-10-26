"""The school calendar: the school's own events, plus term dates and Ghana's public
holidays, which are worked out rather than typed in.

Public holidays follow the Public Holidays and Commemorative Days (Amendment) Act,
2025 (Act 1142). Eid-ul-Fitr, Shaqq Day and Eid-ul-Adha depend on the moon and are
announced each year, so schools add those themselves.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db.models import Q

from .models import CalendarEvent, Term

MAX_DAYS = 400

FIXED_HOLIDAYS = (
    (1, 1, "New Year's Day"),
    (1, 7, "Constitution Day"),
    (3, 6, "Independence Day"),
    (5, 1, "May Day"),
    (7, 1, "Republic Day"),
    (9, 21, "Founder's Day"),
    (12, 25, "Christmas Day"),
    (12, 26, "Boxing Day"),
)


def easter_sunday(year: int) -> dt.date:
    """Western (Gregorian) Easter, by the anonymous Gregorian algorithm."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    lv = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lv) // 451
    month = (h + lv - 7 * m + 114) // 31
    day = (h + lv - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


def ghana_public_holidays(year: int) -> list[tuple[dt.date, str]]:
    days = [(dt.date(year, month, day), name) for month, day, name in FIXED_HOLIDAYS]
    easter = easter_sunday(year)
    days += [
        (easter - dt.timedelta(days=2), "Good Friday"),
        (easter + dt.timedelta(days=1), "Easter Monday"),
    ]
    first_of_december = dt.date(year, 12, 1)
    # Farmers' Day: the first Friday in December.
    days.append(
        (
            first_of_december + dt.timedelta(days=(4 - first_of_december.weekday()) % 7),
            "Farmers' Day",
        )
    )
    return sorted(days)


def _entry(**fields: Any) -> dict[str, Any]:
    return {
        "id": None,
        "kind": "other",
        "starts_at": None,
        "ends_at": None,
        "location": "",
        "description": "",
        "audience": CalendarEvent.Audience.EVERYONE,
        "editable": False,
        **fields,
        "ends_on": fields.get("ends_on") or fields["starts_on"],
    }


def entries(start: dt.date, end: dt.date, *, staff: bool) -> list[dict[str, Any]]:
    """Everything on the calendar between ``start`` and ``end`` (inclusive), by date."""
    events = CalendarEvent.objects.filter(starts_on__lte=end, ends_on__gte=start)
    if not staff:
        events = events.filter(audience=CalendarEvent.Audience.EVERYONE)
    rows = [
        _entry(
            id=str(e.pk),
            source="school",
            title=e.title,
            kind=e.kind,
            starts_on=e.starts_on,
            ends_on=e.ends_on,
            starts_at=e.starts_at,
            ends_at=e.ends_at,
            location=e.location,
            description=e.description,
            audience=e.audience,
            editable=True,
        )
        for e in events
    ]
    terms = Term.objects.filter(
        Q(starts_on__range=(start, end)) | Q(ends_on__range=(start, end))
    ).select_related("session")
    for term in terms:
        label = term.get_number_display()
        if start <= term.starts_on <= end:
            rows.append(
                _entry(
                    source="term", kind="term", title=f"{label} begins", starts_on=term.starts_on
                )
            )
        if start <= term.ends_on <= end:
            rows.append(
                _entry(source="term", kind="term", title=f"{label} ends", starts_on=term.ends_on)
            )
    for year in range(start.year, end.year + 1):
        for day, name in ghana_public_holidays(year):
            if start <= day <= end:
                rows.append(
                    _entry(
                        source="public_holiday", kind="public_holiday", title=name, starts_on=day
                    )
                )
    rows.sort(key=lambda r: (r["starts_on"], r["starts_at"] or dt.time.min, r["title"]))
    return rows
