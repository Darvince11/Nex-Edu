"""Alumni: graduates imported, contact only with consent, gifts into the books."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.accounting.models import Transaction
from apps.alumni.models import Alumnus
from apps.students.models import Student
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/alumni/"


@pytest.fixture
def office(campus, make_member, api):
    set_active(tenant=campus.tenant, code="alumni", active=True, request=None)
    return {
        "head": api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant),
        "teacher": api(make_member(campus.tenant, Role.TEACHER), campus.tenant),
    }


def test_graduates_are_imported_once_and_consent_is_recorded(campus, office, make_student):
    pupil = make_student(campus.tenant, arm=campus.jhs1, first_name="Esi")
    with tenant_context(campus.tenant):
        Student.objects.filter(pk=pupil.pk).update(status=Student.Status.GRADUATED)
    assert office["head"].post(f"{URL}people/import_graduates/").json() == {"added": 1}
    assert office["head"].post(f"{URL}people/import_graduates/").json() == {"added": 0}
    person = office["head"].get(f"{URL}people/").json()[0]
    assert person["first_name"] == "Esi" and person["consent_recorded_at"] is None

    agreed = (
        office["head"]
        .patch(
            f"{URL}people/{person['id']}/",
            {"may_contact": True, "phone": "0244000111"},
            format="json",
        )
        .json()
    )
    assert agreed["consent_recorded_at"] is not None
    office["head"].post(
        f"{URL}people/",
        {"first_name": "Kofi", "last_name": "Boateng", "class_of": 2010, "phone": "0200000000"},
        format="json",
    )
    mailing = office["head"].get(f"{URL}people/mailing_list/").content.decode()
    assert "0244000111" in mailing and "0200000000" not in mailing  # Kofi didn't agree

    assert office["teacher"].get(f"{URL}people/").status_code == 403


def test_gifts_go_into_the_books_when_accounting_is_on(campus, office):
    today = timezone.localdate().isoformat()
    first = office["head"].post(
        f"{URL}gifts/",
        {"donor": "Class of 2010", "amount_pesewas": 500_000, "date": today, "purpose": "Roof"},
        format="json",
    )
    assert first.status_code == 201 and first.json()["in_books"] is False

    set_active(tenant=campus.tenant, code="fees", active=True, request=None)
    set_active(tenant=campus.tenant, code="accounting", active=True, request=None)
    pledge = (
        office["head"]
        .post(
            f"{URL}gifts/",
            {"donor": "Old pupils", "amount_pesewas": 200_000, "date": today, "kind": "pledge"},
            format="json",
        )
        .json()
    )
    assert pledge["in_books"] is False
    paid = office["head"].post(f"{URL}gifts/{pledge['id']}/received/").json()
    assert paid["kind"] == "received" and paid["in_books"] is True
    with tenant_context(campus.tenant):
        txn = Transaction.objects.get()
        assert txn.amount_pesewas == 200_000 and txn.account.code == "4200"

    summary = office["head"].get(f"{URL}gifts/summary/").json()
    assert summary["received_pesewas"] == 700_000 and summary["pledged_pesewas"] == 0

    future = (timezone.localdate() + dt.timedelta(days=3)).isoformat()
    bad = office["head"].post(
        f"{URL}gifts/", {"donor": "X", "amount_pesewas": 100, "date": future}, format="json"
    )
    assert bad.status_code == 400


def test_a_gift_from_an_alumnus_takes_their_name(campus, office):
    with tenant_context(campus.tenant):
        person = Alumnus.objects.create(first_name="Ama", last_name="Owusu", class_of=2015)
    gift = (
        office["head"]
        .post(
            f"{URL}gifts/",
            {
                "alumnus": str(person.pk),
                "amount_pesewas": 10_000,
                "date": timezone.localdate().isoformat(),
            },
            format="json",
        )
        .json()
    )
    assert gift["donor"] == "Ama Owusu"
    listed = office["head"].get(f"{URL}people/").json()[0]
    assert listed["given_pesewas"] == 10_000
