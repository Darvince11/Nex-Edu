"""Scholarships on invoices, outstanding balances and collections reports."""

from __future__ import annotations

import pytest

from apps.finance import services
from apps.finance.models import FeeItem, FeeSchedule, Invoice
from control_plane.models import Role
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def fees(campus):
    """Tuition GH₵100 and PTA levy GH₵20 for everyone this term."""
    with tenant_context(campus.tenant):
        tuition = FeeItem.objects.create(name="Tuition")
        pta = FeeItem.objects.create(name="PTA levy")
        FeeSchedule.objects.create(term=campus.term, item=tuition, amount_pesewas=10_000)
        FeeSchedule.objects.create(term=campus.term, item=pta, amount_pesewas=2_000)
    return {"tuition": tuition, "pta": pta}


def _generate(campus):
    with tenant_context(campus.tenant):
        services.generate_invoices(request=None, term=campus.term)
        return {i.student_id: i for i in Invoice.objects.prefetch_related("lines")}


def test_scholarships_come_off_new_invoices_and_the_books_balance(
    campus, fees, make_student, make_member, api
):
    half_tuition = make_student(campus.tenant, arm=campus.jhs1, first_name="Half")
    fixed = make_student(campus.tenant, arm=campus.jhs1, first_name="Fixed")
    full = make_student(campus.tenant, arm=campus.jhs1, first_name="Full")
    bursar = api(make_member(campus.tenant, Role.BURSAR), campus.tenant)
    url = "/api/v1/finance/scholarships/"
    made = bursar.post(
        url,
        {
            "student": str(half_tuition.pk),
            "name": "Staff child",
            "percent": "50",
            "item": fees["tuition"].pk,
        },
        format="json",
    )
    assert made.status_code == 201, made.content
    bursar.post(
        url, {"student": str(fixed.pk), "name": "Sibling", "amount_pesewas": 3_000}, format="json"
    )
    # A bigger fixed amount than the bill is capped at the bill.
    bursar.post(
        url, {"student": str(full.pk), "name": "Bursary", "amount_pesewas": 99_000}, format="json"
    )

    invoices = _generate(campus)
    assert invoices[half_tuition.pk].total_pesewas == 7_000  # 12,000 - 50% of tuition
    assert invoices[fixed.pk].total_pesewas == 9_000
    assert invoices[full.pk].total_pesewas == 0
    assert any(line.amount_pesewas == -5_000 for line in invoices[half_tuition.pk].lines.all())
    with tenant_context(campus.tenant):
        books = services.account_balances()
    receivable, income, discounts = (
        books.get(code, 0)
        for code in (services.RECEIVABLE, services.FEE_INCOME, services.DISCOUNTS)
    )
    assert receivable == 16_000 and income == -36_000 and discounts == 20_000


def test_a_scholarship_must_be_a_percentage_or_an_amount(
    campus, fees, make_student, make_member, api
):
    pupil = make_student(campus.tenant, arm=campus.jhs1)
    bursar = api(make_member(campus.tenant, Role.BURSAR), campus.tenant)
    url = "/api/v1/finance/scholarships/"
    assert (
        bursar.post(url, {"student": str(pupil.pk), "name": "x"}, format="json").status_code == 400
    )
    both = {"student": str(pupil.pk), "name": "x", "percent": "10", "amount_pesewas": 100}
    assert bursar.post(url, both, format="json").status_code == 400
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    assert (
        head.post(
            url, {"student": str(pupil.pk), "name": "x", "percent": "10"}, format="json"
        ).status_code
        == 403
    )


def test_apply_now_reduces_this_terms_open_invoice(campus, fees, make_student, make_member, api):
    pupil = make_student(campus.tenant, arm=campus.jhs1)
    invoice = _generate(campus)[pupil.pk]
    bursar = api(make_member(campus.tenant, Role.BURSAR), campus.tenant)
    bursar.post(
        "/api/v1/finance/scholarships/",
        {"student": str(pupil.pk), "name": "Hardship", "percent": "25", "apply_now": True},
        format="json",
    )
    with tenant_context(campus.tenant):
        invoice.refresh_from_db()
    assert invoice.total_pesewas == 9_000


def test_balances_report_lists_who_owes_and_exports(campus, fees, make_student, make_member, api):
    paid = make_student(campus.tenant, arm=campus.jhs1, first_name="Paid")
    owing = make_student(campus.tenant, arm=campus.jhs1, first_name="Owing")
    invoices = _generate(campus)
    with tenant_context(campus.tenant):
        services.record_manual_payment(
            request=None,
            invoice=invoices[paid.pk],
            amount_pesewas=12_000,
            method="cash",
            reference="R1",
        )
        services.record_manual_payment(
            request=None,
            invoice=invoices[owing.pk],
            amount_pesewas=2_000,
            method="pos",
            reference="R2",
        )
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    report = head.get("/api/v1/finance/reports/balances/").data
    assert report["pupils"] == 1 and report["outstanding_pesewas"] == 10_000
    assert report["rows"][0]["student"] == str(owing.pk)
    csv = head.get("/api/v1/finance/reports/balances/", {"export": "csv"})
    assert csv["Content-Type"].startswith("text/csv")
    assert b"Owes (GHS)" in csv.content and b"100.00" in csv.content

    collected = head.get("/api/v1/finance/reports/collections/").data
    assert collected["total_pesewas"] == 14_000 and collected["payments"] == 2
    assert {m["method"]: m["total_pesewas"] for m in collected["by_method"]} == {
        "cash": 12_000,
        "pos": 2_000,
    }
    assert collected["by_class"][0]["class"] == "JHS 1 A"


def test_finance_reports_are_for_staff_only(campus, make_member, api):
    parent = api(make_member(campus.tenant, Role.PARENT, mfa=False), campus.tenant)
    assert parent.get("/api/v1/finance/reports/balances/").status_code == 403
    assert parent.get("/api/v1/finance/scholarships/").status_code == 403
    teacher = api(make_member(campus.tenant, Role.TEACHER), campus.tenant)
    assert teacher.get("/api/v1/finance/reports/collections/").status_code == 403
