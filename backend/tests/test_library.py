"""The library module: catalogue, lending, returns, renewals, reminders, import."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.communication.models import Notification
from apps.library.models import Copy, Loan
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def library(campus, make_member, api):
    """The library switched on, with its librarian at the desk."""
    set_active(tenant=campus.tenant, code="library", active=True, request=None)
    librarian = make_member(campus.tenant, Role.LIBRARIAN)
    return api(librarian, campus.tenant)


def _book(desk, copies=2, **extra):
    made = desk.post(
        "/api/v1/library/books/",
        {"title": "Akosua and the Talking Drum", "author": "A. Mensah", "copies": copies, **extra},
        format="json",
    )
    assert made.status_code == 201, made.content
    return made.json()


def _accessions(campus, book_id):
    with tenant_context(campus.tenant):
        return list(Copy.objects.filter(book_id=book_id).values_list("accession_number", flat=True))


def test_the_library_is_off_until_the_school_switches_it_on(campus, make_member, api):
    librarian = api(make_member(campus.tenant, Role.LIBRARIAN), campus.tenant)
    refused = librarian.get("/api/v1/library/books/")
    assert refused.status_code == 403 and refused.json()["code"] == "module_disabled"


def test_lend_renew_and_return(campus, library, make_student):
    book = _book(library)
    first, second = _accessions(campus, book["id"])
    assert (first, second) == ("LIB-00001", "LIB-00002")
    pupil = make_student(campus.tenant, arm=campus.jhs1)
    lent = library.post(
        "/api/v1/library/loans/issue/",
        {"accession_number": first, "student": str(pupil.pk)},
        format="json",
    )
    assert lent.status_code == 201, lent.content
    loan = lent.json()
    assert loan["due_on"] == (timezone.localdate() + dt.timedelta(days=14)).isoformat()
    # The same copy can't go out twice.
    again = library.post(
        "/api/v1/library/loans/issue/",
        {"accession_number": first, "student": str(pupil.pk)},
        format="json",
    )
    assert again.status_code == 400
    listed = library.get("/api/v1/library/books/").json()[0]
    assert listed["copies_total"] == 2 and listed["copies_available"] == 1

    renewed = library.post(f"/api/v1/library/loans/{loan['id']}/renew/").json()
    assert renewed["renewals"] == 1
    assert renewed["due_on"] == (timezone.localdate() + dt.timedelta(days=28)).isoformat()

    back = library.post(
        "/api/v1/library/loans/return/",
        {"accession_number": first.lower(), "condition": "fair"},
        format="json",
    )
    assert back.status_code == 200 and back.json()["outcome"] == "returned"
    with tenant_context(campus.tenant):
        copy = Copy.objects.get(accession_number=first)
    assert (copy.status, copy.condition) == ("available", "fair")


def test_borrowing_limits_and_who_may_borrow(campus, library, make_student, make_member):
    book = _book(library, copies=3)
    numbers = _accessions(campus, book["id"])
    pupil = make_student(campus.tenant, arm=campus.jhs1)
    for number in numbers[:2]:
        assert (
            library.post(
                "/api/v1/library/loans/issue/",
                {"accession_number": number, "student": str(pupil.pk)},
                format="json",
            ).status_code
            == 201
        )
    third = library.post(
        "/api/v1/library/loans/issue/",
        {"accession_number": numbers[2], "student": str(pupil.pk)},
        format="json",
    )
    assert third.status_code == 400 and "most allowed" in str(third.json())
    parent = make_member(campus.tenant, Role.PARENT, mfa=False)
    not_staff = library.post(
        "/api/v1/library/loans/issue/",
        {"accession_number": numbers[2], "staff_user": str(parent.pk)},
        format="json",
    )
    assert not_staff.status_code == 400
    teacher = make_member(campus.tenant, Role.TEACHER)
    staff_loan = library.post(
        "/api/v1/library/loans/issue/",
        {"accession_number": numbers[2], "staff_user": str(teacher.pk)},
        format="json",
    )
    assert staff_loan.status_code == 201
    assert staff_loan.json()["borrower_class"] == "Staff"


def test_overdue_books_remind_guardians_once_a_day(campus, library, make_student, make_member):
    book = _book(library, copies=1)
    (number,) = _accessions(campus, book["id"])
    pupil = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    parent = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(student=pupil, guardian_user_id=parent.pk, full_name="P")
    library.post(
        "/api/v1/library/loans/issue/",
        {"accession_number": number, "student": str(pupil.pk)},
        format="json",
    )
    with tenant_context(campus.tenant):
        Loan.objects.update(due_on=timezone.localdate() - dt.timedelta(days=3))
    overdue = library.get("/api/v1/library/loans/", {"state": "overdue"}).json()
    assert [loan["overdue_days"] for loan in overdue] == [3]
    # Overdue books can't be renewed.
    assert library.post(f"/api/v1/library/loans/{overdue[0]['id']}/renew/").status_code == 400
    assert library.post("/api/v1/library/loans/remind/", {}).json() == {"pupils": 1}
    assert library.post("/api/v1/library/loans/remind/", {}).json() == {"pupils": 0}
    with tenant_context(campus.tenant):
        alert = Notification.objects.get(recipient_user_id=parent.pk, kind="library")
    assert "Akosua and the Talking Drum" in alert.body


def test_parents_see_their_childs_loans_only(campus, library, make_student, make_member, api):
    book = _book(library, copies=2)
    a, b = _accessions(campus, book["id"])
    mine = make_student(campus.tenant, arm=campus.jhs1)
    other = make_student(campus.tenant, arm=campus.jhs1)
    for number, pupil in ((a, mine), (b, other)):
        library.post(
            "/api/v1/library/loans/issue/",
            {"accession_number": number, "student": str(pupil.pk)},
            format="json",
        )
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(student=mine, guardian_user_id=parent_user.pk)
    parent = api(parent_user, campus.tenant)
    loans = parent.get("/api/v1/library/loans/").json()
    assert [loan["student"] for loan in loans] == [str(mine.pk)]
    assert parent.get("/api/v1/library/books/").status_code == 200  # may browse
    assert (
        parent.post(
            "/api/v1/library/loans/issue/", {"accession_number": a, "student": str(mine.pk)}
        ).status_code
        == 403
    )
    assert "titles" not in parent.get("/api/v1/library/").json()  # no desk figures


def test_lost_books_and_switching_off(campus, library, make_student):
    book = _book(library, copies=1)
    (number,) = _accessions(campus, book["id"])
    pupil = make_student(campus.tenant, arm=campus.jhs1)
    loan = library.post(
        "/api/v1/library/loans/issue/",
        {"accession_number": number, "student": str(pupil.pk)},
        format="json",
    ).json()
    from control_plane.modules import OpenRecords

    with pytest.raises(OpenRecords):
        set_active(tenant=campus.tenant, code="library", active=False, request=None)
    lost = library.post(f"/api/v1/library/loans/{loan['id']}/lost/").json()
    assert lost["outcome"] == "lost"
    summary = library.get("/api/v1/library/").json()
    assert summary["lost"] == 1 and summary["on_loan"] == 0
    # The book has been lent, so it can't be deleted, only its copies withdrawn.
    assert library.delete(f"/api/v1/library/books/{book['id']}/").status_code == 400
    set_active(tenant=campus.tenant, code="library", active=False, request=None)


def test_import_books_from_a_spreadsheet(campus, library):
    good = SimpleUploadedFile(
        "books.csv",
        b"Title,Author,ISBN,Category,Shelf,Copies\n"
        b"English for JHS 1,GES,9789988000001,Textbook,T1,3\n"
        b"Kweku Ananse Stories,,,Reader / storybook,R2,\n",
        content_type="text/csv",
    )
    done = library.post("/api/v1/library/import/", {"file": good}, format="multipart")
    assert done.status_code == 201, done.content
    assert done.json() == {"titles": 2, "copies": 4}
    bad = SimpleUploadedFile(
        "books.csv", b"Title,Copies\nA book,lots\n,2\n", content_type="text/csv"
    )
    refused = library.post("/api/v1/library/import/", {"file": bad}, format="multipart")
    assert refused.status_code == 400
    assert len(refused.json()["rows"]) == 2
    books = library.get("/api/v1/library/books/", {"q": "ananse"}).json()
    assert books[0]["category"] == "reader"
