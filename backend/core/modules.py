"""The module catalogue: every feature area of Nex Edu, core or optional.

Core modules are always on. Optional modules can be switched on and off per
school by the proprietor (``control_plane.modules``), within what the school is
entitled to: an optional module priced at GH₵0 is included in every price band;
one with a price is a paid add-on that Nex Edu grants. Modules not built yet are
listed as ``available=False, default_on=False`` and can't be switched on.

Every school API view belongs to a module through its Django app (``APP_MODULES``)
or a ``module`` attribute on the view; a test fails if one doesn't.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Module:
    code: str
    name: str
    description: str
    core: bool = False
    available: bool = True
    #: Whether a school that never touched the switch has it on. The modules that
    #: existed before switches were added start on; new ones start off, so nothing
    #: appears in a school without the proprietor choosing it.
    default_on: bool = True
    depends: tuple[str, ...] = ()
    #: Records still open in the school (counted before switching off), e.g. unpaid invoices.
    open_records: Callable[[], list[str]] | None = field(default=None, compare=False)


def _fees_open() -> list[str]:
    from apps.finance.models import Invoice

    unpaid = Invoice.objects.filter(
        status__in=[Invoice.Status.ISSUED, Invoice.Status.PART_PAID]
    ).count()
    return [f"{unpaid} unpaid invoice{'s' if unpaid != 1 else ''}"] if unpaid else []


def _admissions_open() -> list[str]:
    from apps.admissions.models import Application

    waiting = Application.objects.filter(
        status__in=[Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW]
    ).count()
    return [f"{waiting} application{'s' if waiting != 1 else ''} waiting"] if waiting else []


def _sms_open() -> list[str]:
    from apps.communication.models import Channel, Delivery

    queued = Delivery.objects.filter(channel=Channel.SMS, status=Delivery.Status.QUEUED).count()
    return [f"{queued} SMS waiting to send"] if queued else []


def _library_open() -> list[str]:
    from apps.library.models import Loan

    out = Loan.objects.filter(outcome=Loan.Outcome.OPEN).count()
    return [f"{out} book{'s' if out != 1 else ''} on loan"] if out else []


def _meetings_open() -> list[str]:
    import datetime as dt

    from apps.meetings.models import Slot

    booked = Slot.objects.filter(student__isnull=False, day__date__gte=dt.date.today()).count()
    return [f"{booked} parent meeting{'s' if booked != 1 else ''} booked"] if booked else []


def _canteen_open() -> list[str]:
    from django.db.models import Sum

    from apps.canteen.models import Wallet

    held = Wallet.objects.aggregate(s=Sum("balance_pesewas"))["s"] or 0
    return [f"GH₵{held / 100:,.2f} still in pupils' canteen wallets"] if held else []


MODULES: tuple[Module, ...] = (
    # --- Core: always on -----------------------------------------------------------------
    Module(
        "people",
        "Pupils and staff",
        "Pupil records, guardians, staff and who has access.",
        core=True,
    ),
    Module(
        "academics",
        "Classes and timetable",
        "Academic year, terms, classes, subjects, timetable.",
        core=True,
    ),
    Module(
        "attendance",
        "Registers",
        "Daily registers, also offline, with absence alerts in the app.",
        core=True,
    ),
    Module(
        "assessments",
        "Scores and report cards",
        "Score entry, grading, positions, report cards.",
        core=True,
    ),
    Module("communication", "Messages", "Announcements and the in-app inbox.", core=True),
    Module("school", "School settings", "Profile, logo, dashboard and set-up.", core=True),
    # --- Optional, built --------------------------------------------------------------------
    Module(
        "admissions",
        "Online admissions",
        "A public application form on the school's web address, and reviewing applications.",
        open_records=_admissions_open,
    ),
    Module(
        "fees",
        "Fees and payments",
        "Fee schedules, invoices, receipts, and mobile money and card payments by parents.",
        open_records=_fees_open,
    ),
    Module(
        "sms",
        "SMS to parents",
        "Absence alerts, results and announcements by text message (uses the SMS allowance).",
        open_records=_sms_open,
    ),
    Module(
        "library",
        "Library",
        "Catalogue, copies, lending to pupils and staff, overdue reminders.",
        default_on=False,
        open_records=_library_open,
    ),
    Module(
        "clubs",
        "Clubs and sports",
        "Clubs, societies and teams: patrons, members, meetings, matches and results.",
        default_on=False,
    ),
    Module(
        "meetings",
        "Parent meetings",
        "Meeting days split into slots; parents book times with their children's teachers.",
        default_on=False,
        open_records=_meetings_open,
    ),
    Module(
        "discipline",
        "Behaviour and discipline",
        "Incidents, what was done, notes shared with parents, confidential counselling notes.",
        default_on=False,
    ),
    Module(
        "clinic",
        "Sick bay",
        "Sick bay visits, treatment and medicine given, parents told when a child goes home.",
        default_on=False,
    ),
    Module(
        "transport",
        "School transport",
        "Buses, routes and stops, the driver's pick-up list, and a note to parents at each stop.",
        default_on=False,
    ),
    Module(
        "canteen",
        "Canteen",
        "Pupils' canteen wallets, cash top-ups, sales at the till, and term meal plans.",
        default_on=False,
        depends=("fees",),
        open_records=_canteen_open,
    ),
    Module(
        "inventory",
        "Stores and inventory",
        "Stock in and out, staff requests to the stores, suppliers and the equipment register.",
        default_on=False,
    ),
    Module(
        "facilities",
        "Facilities and repairs",
        "Rooms and spaces, booking them without clashes, and reporting and following repairs.",
        default_on=False,
    ),
    Module(
        "visitors",
        "Visitors and the gate",
        "Visitors signed in and out, who may collect each pupil, and a note to parents at pick-up.",
        default_on=False,
    ),
    Module(
        "lms",
        "Homework and online learning",
        "Homework set online, work handed in and marked with feedback, and learning materials.",
        default_on=False,
    ),
    Module(
        "hostel",
        "Boarding",
        "Houses, rooms and beds, morning and evening roll call, and exeats asked for by parents.",
        default_on=False,
    ),
    Module(
        "accounting",
        "Accounting",
        "Spending and other income in the school's books, budgets, trial balance and cash book.",
        default_on=False,
        depends=("fees",),
    ),
    Module(
        "payroll",
        "Payroll",
        "Salaries, PAYE and SSNIT worked out each month, payslips, and GRA and SSNIT schedules.",
        default_on=False,
        depends=("accounting",),
    ),
    Module(
        "procurement",
        "Procurement",
        "Purchase requests and approvals, orders to suppliers, goods received and suppliers paid.",
        default_on=False,
        depends=("inventory", "accounting"),
    ),
    Module(
        "online_exams",
        "Online tests",
        "Timed tests sat online, marked by Nex Edu or the teacher, results shared with families.",
        default_on=False,
        depends=("lms",),
    ),
    Module(
        "special_ed",
        "Learning support",
        "Support plans for pupils with additional needs: goals, adjustments, test extra time.",
        default_on=False,
    ),
    Module(
        "alumni",
        "Alumni and fundraising",
        "Past pupils who agreed to keep in touch, gifts and pledges, a mailing list.",
        default_on=False,
    ),
    Module(
        "website",
        "School website",
        "A public website for the school: about, pages, news, events and a link to apply.",
        default_on=False,
    ),
    Module(
        "compliance",
        "Accreditation and compliance",
        "Checklists for inspections and licences, with evidence and renewal reminders.",
        default_on=False,
    ),
    Module(
        "developer_api",
        "Developer API and webhooks",
        "Keys for other systems to read pupils, classes, attendance and fees; live event updates.",
        default_on=False,
    ),
    Module(
        "ai_assist",
        "AI drafting help",
        "Drafts of report-card comments and announcements for staff to edit. No pupil names sent.",
        default_on=False,
    ),
)

BY_CODE: dict[str, Module] = {m.code: m for m in MODULES}
CORE: frozenset[str] = frozenset(m.code for m in MODULES if m.core)

#: Which module each Django app's school API belongs to.
APP_MODULES: dict[str, str] = {
    "students": "people",
    "staff": "people",
    "control_plane": "people",  # staff access (members)
    "academics": "academics",
    "attendance": "attendance",
    "assessments": "assessments",
    "communication": "communication",
    "school": "school",
    "audit": "school",
    "admissions": "admissions",
    "finance": "fees",
    "library": "library",
    "clubs": "clubs",
    "meetings": "meetings",
    "discipline": "discipline",
    "clinic": "clinic",
    "transport": "transport",
    "canteen": "canteen",
    "inventory": "inventory",
    "facilities": "facilities",
    "visitors": "visitors",
    "lms": "lms",
    "hostel": "hostel",
    "accounting": "accounting",
    "payroll": "payroll",
    "procurement": "procurement",
    "exams": "online_exams",
    "support": "special_ed",
    "alumni": "alumni",
    "website": "website",
    "compliance": "compliance",
    "assist": "ai_assist",
}


def module_for_view(view: Any) -> str | None:
    """The module a view belongs to: its ``module`` attribute, else its app's."""
    explicit = getattr(view, "module", None)
    if explicit:
        return str(explicit)
    from django.apps import apps

    view_class = view if isinstance(view, type) else type(view)
    config = apps.get_containing_app_config(view_class.__module__)
    return APP_MODULES.get(config.label) if config else None


def dependents_of(code: str) -> list[Module]:
    return [m for m in MODULES if code in m.depends]
