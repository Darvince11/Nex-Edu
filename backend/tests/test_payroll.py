"""Payroll: PAYE and SSNIT sums, pay runs through to the books, and who sees what."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.finance import services as finance
from apps.payroll import services as payroll
from apps.payroll.models import DEFAULT_PAYE_BANDS
from apps.staff.models import StaffProfile
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/payroll/"


def test_paye_follows_the_bands():
    # GH₵3,000 chargeable a month under the September 2026 bands:
    # 588 at 0% + 80 at 5% (4.00) + 100 at 10% (10.00) + 2,232 at 17.5% (390.60) = 404.60
    assert payroll.paye(300_000, DEFAULT_PAYE_BANDS) == 40_460
    assert payroll.paye(58_800, DEFAULT_PAYE_BANDS) == 0
    assert payroll.paye(0, DEFAULT_PAYE_BANDS) == 0
    # Everything above GH¢50,000 is at 35%.
    assert (
        payroll.paye(5_100_000, DEFAULT_PAYE_BANDS) - payroll.paye(5_000_000, DEFAULT_PAYE_BANDS)
        == 35_000
    )


@pytest.fixture
def school(campus, make_member, api):
    set_active(tenant=campus.tenant, code="accounting", active=True, request=None)
    set_active(tenant=campus.tenant, code="payroll", active=True, request=None)
    teacher_user = make_member(campus.tenant, Role.TEACHER)
    other_user = make_member(campus.tenant, Role.TEACHER)
    with tenant_context(campus.tenant):
        teacher = StaffProfile.objects.create(
            user_id=teacher_user.pk, staff_number="STF/1", first_name="Ama", last_name="Owusu"
        )
        StaffProfile.objects.create(
            user_id=other_user.pk, staff_number="STF/2", first_name="Kofi", last_name="Asare"
        )
    return {
        "bursar": api(make_member(campus.tenant, Role.BURSAR), campus.tenant),
        "owner": api(make_member(campus.tenant, Role.OWNER), campus.tenant),
        "head": api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant),
        "teacher": api(teacher_user, campus.tenant),
        "other": api(other_user, campus.tenant),
        "staff": teacher,
    }


def test_a_month_from_salary_to_payslip(campus, school):
    bursar = school["bursar"]
    set_pay = bursar.put(
        f"{URL}salaries/?staff={school['staff'].pk}",
        {
            "basic_pesewas": 300_000,
            "allowances": [{"name": "Transport", "amount_pesewas": 20_000, "taxable": True}],
            "deductions": [{"name": "Staff welfare", "amount_pesewas": 2_000}],
            "ssnit_number": "C123",
            "tin": "GHA-000000000-1",
        },
        format="json",
    )
    assert set_pay.status_code == 200, set_pay.content
    numbers = set_pay.json()["figures"]
    assert (
        numbers["ssnit_employee_pesewas"] == 16_500 and numbers["ssnit_employer_pesewas"] == 39_000
    )
    # Taxable: 3,200 - 165 SSNIT = 3,035 -> 4 + 10 + 2,267 x 17.5% (396.725) = 410.73
    assert numbers["paye_pesewas"] == 41_073
    assert numbers["net_pesewas"] == 320_000 - 16_500 - 41_073 - 2_000

    month = timezone.localdate().replace(day=1).isoformat()
    unconfirmed = bursar.post(f"{URL}runs/prepare/", {"month": month}, format="json")
    assert unconfirmed.status_code == 400 and "Confirm" in str(unconfirmed.json())
    bursar.post(f"{URL}rules/")
    run = bursar.post(f"{URL}runs/prepare/", {"month": month}, format="json")
    assert run.status_code == 201, run.content
    run_id = run.json()["id"]

    # Draft payslips aren't shown to staff; only the proprietor approves.
    assert school["teacher"].get(f"{URL}mine/").json() == []
    assert bursar.post(f"{URL}runs/{run_id}/approve/").status_code == 403
    assert school["owner"].post(f"{URL}runs/{run_id}/approve/").json()["status"] == "approved"
    assert bursar.post(f"{URL}runs/{run_id}/prepare/", {"month": month}).status_code in (404, 405)
    assert bursar.post(f"{URL}runs/prepare/", {"month": month}, format="json").status_code == 400
    assert bursar.post(f"{URL}runs/{run_id}/paid/").json()["status"] == "paid"
    with tenant_context(campus.tenant):
        books = finance.account_balances()
    assert books[payroll.NET_PAYABLE] == 0  # paid out
    assert books[payroll.PAYE_PAYABLE] == -41_073  # owed to GRA
    assert books[payroll.SSNIT_PAYABLE] == -(16_500 + 39_000)

    mine = school["teacher"].get(f"{URL}mine/").json()
    assert len(mine) == 1 and mine[0]["net_pesewas"] == numbers["net_pesewas"]
    pdf = school["teacher"].get(f"{URL}payslips/{mine[0]['id']}/pdf/")
    assert pdf["Content-Type"] == "application/pdf"
    assert school["other"].get(f"{URL}payslips/{mine[0]['id']}/pdf/").status_code == 403
    paye_csv = bursar.get(f"{URL}runs/{run_id}/schedule/", {"kind": "paye"})
    assert b"GHA-000000000-1" in paye_csv.content and b"410.73" in paye_csv.content


def test_salaries_are_confidential_and_rules_need_reconfirming(campus, school):
    assert school["head"].get(f"{URL}salaries/").status_code == 403
    assert school["teacher"].get(f"{URL}salaries/").status_code == 403
    school["bursar"].post(f"{URL}rules/")
    changed = school["bursar"].patch(
        f"{URL}rules/", {"paye_bands": [[58_800, "0"], [None, "10"]]}, format="json"
    )
    assert changed.status_code == 200 and changed.json()["rates_confirmed_at"] is None
    bad = school["bursar"].patch(
        f"{URL}rules/", {"paye_bands": [[None, "10"], [100, "5"]]}, format="json"
    )
    assert bad.status_code == 400
