"""Lending rules for the library desk.

- A copy is lent to one pupil (active, on roll) or one member of staff at a time.
- Borrowers may hold up to the school's limit; loans last the school's loan period.
- Renewing pushes the due date on by a loan period, up to ``max_renewals`` times,
  and never for an overdue book (bring it back first).
- Marking a book lost closes the loan and takes the copy off the shelf.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from typing import Any

from django.db import IntegrityError
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.students.models import Student
from control_plane.models import Membership
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.rbac import STAFF_ROLES

from .models import Book, Copy, LibrarySettings, Loan

ACCESSION_PREFIX = "LIB-"
MAX_IMPORT_ROWS = 5000
MAX_COPIES_AT_ONCE = 200


def next_accession_numbers(count: int) -> list[str]:
    """The next ``count`` free numbers in the LIB-00001 series."""
    highest = 0
    for number in Copy.objects.filter(accession_number__startswith=ACCESSION_PREFIX).values_list(
        "accession_number", flat=True
    ):
        digits = number[len(ACCESSION_PREFIX) :]
        if digits.isdigit():
            highest = max(highest, int(digits))
    return [f"{ACCESSION_PREFIX}{n:05d}" for n in range(highest + 1, highest + 1 + count)]


def add_copies(book: Book, count: int, numbers: list[str] | None = None) -> list[Copy]:
    if not 1 <= count <= MAX_COPIES_AT_ONCE:
        raise ValidationError(
            {"copies": f"Add between 1 and {MAX_COPIES_AT_ONCE} copies at a time."}
        )
    numbers = [n.strip() for n in numbers or [] if n.strip()]
    if numbers and len(numbers) != count:
        raise ValidationError({"accession_numbers": "Give one number per copy, or none."})
    numbers = numbers or next_accession_numbers(count)
    taken = set(
        Copy.objects.filter(accession_number__in=numbers).values_list("accession_number", flat=True)
    )
    if taken:
        raise ValidationError({"accession_numbers": f"Already in use: {', '.join(sorted(taken))}."})
    return Copy.objects.bulk_create([Copy(book=book, accession_number=n) for n in numbers])


def _staff_ids(user_ids: list[Any]) -> set[Any]:
    return set(
        Membership.objects.filter(
            tenant=require_tenant(), user_id__in=user_ids, is_active=True, role__in=STAFF_ROLES
        ).values_list("user_id", flat=True)
    )


def open_loans(*, student: Student | None = None, staff_user_id: Any = None) -> QuerySet[Loan]:
    qs = Loan.objects.filter(outcome=Loan.Outcome.OPEN)
    return qs.filter(student=student) if student else qs.filter(staff_user_id=staff_user_id)


def find_copy(accession: str) -> Copy:
    copy = (
        Copy.objects.select_related("book")
        .filter(accession_number__iexact=accession.strip())
        .first()
    )
    if copy is None:
        raise ValidationError({"accession_number": "No copy has this number."})
    return copy


def issue(
    *,
    request: HttpRequest,
    accession: str,
    student: Student | None = None,
    staff_user_id: Any = None,
    due_on: dt.date | None = None,
) -> Loan:
    if (student is None) == (staff_user_id is None):
        raise ValidationError({"borrower": "Choose a pupil or a member of staff."})
    settings = LibrarySettings.load()
    copy = find_copy(accession)
    if copy.status != Copy.Status.AVAILABLE:
        raise ValidationError(
            {"accession_number": f"This copy is {copy.get_status_display().lower()}."}
        )
    if student is not None:
        if student.status != Student.Status.ACTIVE:
            raise ValidationError({"borrower": "Only pupils on roll can borrow."})
        limit, days = settings.pupil_limit, settings.pupil_loan_days
    else:
        if staff_user_id not in _staff_ids([staff_user_id]):
            raise ValidationError({"borrower": "Only active staff can borrow."})
        limit, days = settings.staff_limit, settings.staff_loan_days
    holding = open_loans(student=student, staff_user_id=staff_user_id)
    if holding.count() >= limit:
        raise ValidationError(
            {"borrower": f"They already have {limit} book(s) out, the most allowed."}
        )
    today = timezone.localdate()
    due = due_on or today + dt.timedelta(days=days)
    if due < today:
        raise ValidationError({"due_on": "The due date can't be in the past."})
    try:
        with tenant_atomic():
            loan = Loan.objects.create(
                copy=copy,
                student=student,
                staff_user_id=staff_user_id,
                borrowed_on=today,
                due_on=due,
                issued_by=request.user.pk,
            )
            copy.status = Copy.Status.ON_LOAN
            copy.save(update_fields=["status"])
    except IntegrityError as exc:  # lent at the same moment from another desk
        raise ValidationError({"accession_number": "This copy has just been lent."}) from exc
    return loan


def _close(request: HttpRequest, loan: Loan, outcome: str, copy_status: str) -> Loan:
    if loan.outcome != Loan.Outcome.OPEN:
        raise ValidationError({"detail": "This loan is already closed."})
    with tenant_atomic():
        loan.outcome = outcome
        loan.returned_on = timezone.localdate()
        loan.closed_by = request.user.pk
        loan.save(update_fields=["outcome", "returned_on", "closed_by"])
        loan.copy.status = copy_status
        loan.copy.save(update_fields=["status"])
    return loan


def return_copy(*, request: HttpRequest, accession: str, condition: str = "") -> Loan:
    copy = find_copy(accession)
    loan = Loan.objects.filter(copy=copy, outcome=Loan.Outcome.OPEN).select_related("copy").first()
    if loan is None:
        raise ValidationError({"accession_number": "This copy isn't on loan."})
    if condition in Copy.Condition.values:
        copy.condition = condition
        copy.save(update_fields=["condition"])
    return _close(request, loan, Loan.Outcome.RETURNED, Copy.Status.AVAILABLE)


def mark_lost(*, request: HttpRequest, loan: Loan) -> Loan:
    loan = _close(request, loan, Loan.Outcome.LOST, Copy.Status.LOST)
    with tenant_atomic():
        record_event(
            action="library.lost",
            request=request,
            target=loan.copy,
            after={"accession_number": loan.copy.accession_number, "title": loan.copy.book.title},
        )
    return loan


def renew(*, loan: Loan) -> Loan:
    settings = LibrarySettings.load()
    if loan.outcome != Loan.Outcome.OPEN:
        raise ValidationError({"detail": "Only books on loan can be renewed."})
    if loan.due_on < timezone.localdate():
        raise ValidationError(
            {"detail": "This book is overdue. Return it first, then lend it again."}
        )
    if loan.renewals >= settings.max_renewals:
        raise ValidationError({"detail": f"Already renewed {settings.max_renewals} times."})
    days = settings.pupil_loan_days if loan.student_id else settings.staff_loan_days
    loan.due_on = loan.due_on + dt.timedelta(days=days)
    loan.renewals += 1
    loan.save(update_fields=["due_on", "renewals"])
    return loan


def overdue() -> QuerySet[Loan]:
    return Loan.objects.filter(outcome=Loan.Outcome.OPEN, due_on__lt=timezone.localdate())


def remind_overdue(*, request: HttpRequest, sms: bool = False) -> int:
    """Tell each overdue pupil's guardians (once a day at most) which books to bring back."""
    from apps.communication.models import Channel
    from apps.communication.services import notify_guardians

    today = timezone.localdate()
    loans = (
        overdue()
        .filter(student__isnull=False)
        .exclude(reminded_on=today)
        .select_related("student", "copy__book")
    )
    by_pupil: dict[Any, list[Loan]] = {}
    for loan in loans:
        by_pupil.setdefault(loan.student_id, []).append(loan)
    for pupil_loans in by_pupil.values():
        pupil = pupil_loans[0].student
        titles = ", ".join(f"“{loan.copy.book.title}”" for loan in pupil_loans)
        notify_guardians(
            [pupil],
            kind="library",
            title="Library book overdue",
            body=f"{pupil.first_name} has a library book to bring back: {titles}.",
            data={"student_id": str(pupil.pk)},
            channels={Channel.SMS} if sms else set(),
        )
    Loan.objects.filter(pk__in=[loan.pk for loans in by_pupil.values() for loan in loans]).update(
        reminded_on=today
    )
    if by_pupil:
        with tenant_atomic():
            record_event(
                action="library.reminded",
                request=request,
                after={"pupils": len(by_pupil), "sms": sms},
            )
    return len(by_pupil)


def summary() -> dict[str, Any]:
    copies = dict(Copy.objects.values_list("status").annotate(n=Count("pk")))
    since = timezone.localdate() - dt.timedelta(days=90)
    popular = (
        Loan.objects.filter(borrowed_on__gte=since)
        .values("copy__book_id", "copy__book__title")
        .annotate(n=Count("pk"))
        .order_by("-n", "copy__book__title")[:5]
    )
    return {
        "titles": Book.objects.count(),
        "copies": sum(copies.values()),
        "on_shelf": copies.get(Copy.Status.AVAILABLE, 0),
        "on_loan": copies.get(Copy.Status.ON_LOAN, 0),
        "lost": copies.get(Copy.Status.LOST, 0),
        "overdue": overdue().count(),
        "popular": [
            {"book": str(p["copy__book_id"]), "title": p["copy__book__title"], "loans": p["n"]}
            for p in popular
        ],
    }


IMPORT_COLUMNS = ("title", "author", "isbn", "publisher", "category", "shelf", "copies")


def _norm(header: str) -> str:
    return re.sub(r"[^a-z]", "", header.lower())


def import_books(*, request: HttpRequest, text: str) -> dict[str, Any]:
    """Add books from a spreadsheet (CSV). Columns: title (required), author, isbn,
    publisher, category, shelf, copies (default 1). All rows are checked first;
    nothing is added if any row is wrong."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    fields = {_norm(h): h for h in reader.fieldnames or []}
    if "title" not in fields:
        raise ValidationError({"file": "The first row must name the columns, including Title."})
    label_to_value = {c.label.lower(): c.value for c in Book.Category}
    categories = set(Book.Category.values) | set(label_to_value)
    rows, errors = [], []
    for line, raw in enumerate(reader, start=2):
        if line - 1 > MAX_IMPORT_ROWS:
            raise ValidationError({"file": f"Import at most {MAX_IMPORT_ROWS} rows at a time."})
        row = {
            name: (raw.get(fields[name]) or "").strip() for name in IMPORT_COLUMNS if name in fields
        }
        if not any(row.values()):
            continue
        if not row.get("title"):
            errors.append(f"Row {line}: the title is missing.")
            continue
        copies = row.get("copies") or "1"
        if not copies.isdigit() or not 1 <= int(copies) <= MAX_COPIES_AT_ONCE:
            errors.append(f"Row {line}: copies must be a number from 1 to {MAX_COPIES_AT_ONCE}.")
            continue
        category = row.get("category", "").lower()
        if category and category not in categories:
            errors.append(f"Row {line}: unknown category “{row['category']}”.")
            continue
        rows.append(
            {
                "title": row["title"][:200],
                "author": row.get("author", "")[:160],
                "isbn": row.get("isbn", "")[:20],
                "publisher": row.get("publisher", "")[:120],
                "category": label_to_value.get(category, category) or Book.Category.OTHER,
                "shelf": row.get("shelf", "")[:40],
                "copies": int(copies),
            }
        )
    if errors:
        raise ValidationError({"rows": errors[:50]})
    if not rows:
        raise ValidationError({"file": "There are no books in the file."})
    total = sum(r["copies"] for r in rows)
    with tenant_atomic():
        numbers = iter(next_accession_numbers(total))
        for r in rows:
            count = r.pop("copies")
            book = Book.objects.create(**r)
            Copy.objects.bulk_create(
                [Copy(book=book, accession_number=next(numbers)) for _ in range(count)]
            )
        record_event(
            action="library.imported",
            request=request,
            after={"titles": len(rows)},
        )
    return {"titles": len(rows), "copies": total}


def borrower_search(q: str) -> dict[str, list[dict[str, Any]]]:
    """Pupils and staff whose names (or admission numbers) match, with books held."""
    from control_plane.models import User

    q = q.strip()
    if len(q) < 2:
        return {"pupils": [], "staff": []}
    pupils = list(
        Student.objects.filter(status=Student.Status.ACTIVE)
        .filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(admission_number__icontains=q)
        )
        .select_related("arm__level")[:15]
    )
    held = dict(
        Loan.objects.filter(outcome=Loan.Outcome.OPEN, student__in=pupils)
        .values_list("student_id")
        .annotate(n=Count("pk"))
    )
    staff_ids = list(
        Membership.objects.filter(tenant=require_tenant(), is_active=True, role__in=STAFF_ROLES)
        .values_list("user_id", flat=True)
        .distinct()
    )
    staff = list(
        User.objects.filter(pk__in=staff_ids)
        .filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q))
        .order_by("last_name")[:10]
    )
    staff_held = dict(
        Loan.objects.filter(outcome=Loan.Outcome.OPEN, staff_user_id__in=[u.pk for u in staff])
        .values_list("staff_user_id")
        .annotate(n=Count("pk"))
    )
    return {
        "pupils": [
            {
                "id": str(p.pk),
                "name": p.full_name,
                "admission_number": p.admission_number,
                "class": str(p.arm) if p.arm_id else "",
                "holding": held.get(p.pk, 0),
            }
            for p in pupils
        ],
        "staff": [
            {
                "id": str(u.pk),
                "name": u.get_full_name() or u.email,
                "holding": staff_held.get(u.pk, 0),
            }
            for u in staff
        ],
    }
