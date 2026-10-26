"""Role → permission table. The single source of truth for what each role may do.

Permissions say *what kind* of action is allowed. *Which* records a user may act on
(own children, own classes, own subjects) is decided by each app's selectors.
"""

from __future__ import annotations

from collections.abc import Iterable

from control_plane.models import Role


class Perm:
    SCHOOL_MANAGE = "school.manage"
    SCHOOL_BRANDING = "school.branding"  # the school's logo: proprietor only
    SCHOOL_LEGAL = "school.legal"  # accept Nex Edu's terms for the school: proprietor only
    SCHOOL_MODULES = "school.modules"  # switch optional modules on and off: proprietor only

    STUDENTS_VIEW = "students.view"
    # Every pupil in the school, not only those in the person's own classes.
    STUDENTS_VIEW_ALL = "students.view_all"
    STUDENTS_VIEW_SENSITIVE = "students.view_sensitive"  # health records, NIN
    STUDENTS_MANAGE = "students.manage"
    # Class teachers add pupils, but only into a class they are the class teacher of.
    STUDENTS_ADD_OWN_CLASS = "students.add_to_own_class"

    STAFF_VIEW = "staff.view"
    STAFF_MANAGE = "staff.manage"  # staff records, staff attendance, approving leave
    LEAVE_REQUEST = "leave.request"  # every member of staff asks for their own leave

    ACADEMICS_VIEW = "academics.view"
    ACADEMICS_MANAGE = "academics.manage"
    # Teachers edit the timetable of classes they are assigned to, and no others.
    ACADEMICS_TIMETABLE_OWN = "academics.timetable_own"

    ADMISSIONS_VIEW = "admissions.view"
    ADMISSIONS_MANAGE = "admissions.manage"

    ATTENDANCE_VIEW = "attendance.view"
    ATTENDANCE_RECORD = "attendance.record"  # registers for classes the teacher is assigned to
    ATTENDANCE_MANAGE = "attendance.manage"  # any class

    ASSESSMENTS_VIEW = "assessments.view"
    ASSESSMENTS_RECORD = "assessments.record"  # scores for the teacher's own class + subject
    ASSESSMENTS_MANAGE = "assessments.manage"  # scores for any class
    ASSESSMENTS_CONFIGURE = "assessments.configure"  # grading setup: components, grade bands
    ASSESSMENTS_PUBLISH = "assessments.publish"  # compute and release report cards, any class
    # Class teachers compute and publish report cards for their own class.
    ASSESSMENTS_PUBLISH_OWN_CLASS = "assessments.publish_own_class"
    ASSESSMENTS_AMEND = "assessments.amend"  # change scores after publication

    FINANCE_VIEW = "finance.view"
    FINANCE_MANAGE = "finance.manage"
    FINANCE_PAY = "finance.pay"  # parents paying their children's fees

    COMMUNICATION_VIEW = "communication.view"
    COMMUNICATION_SEND = "communication.send"
    COMMUNICATION_MANAGE = "communication.manage"  # school-wide audiences, delivery logs
    # Private messages between parents and the staff who teach their children.
    MESSAGES_USE = "messages.use"
    MESSAGES_OVERSEE = "messages.oversee"  # read every conversation (safeguarding)

    CALENDAR_VIEW = "calendar.view"
    CALENDAR_MANAGE = "calendar.manage"

    MEMBERS_MANAGE = "members.manage"  # give any staff role: proprietor only
    # Head teacher: add and block teaching and support staff (HEAD_MANAGED_ROLES).
    MEMBERS_MANAGE_STAFF = "members.manage_staff"
    MEMBERS_VIEW = "members.view"  # see who has access (head teacher, administrator)
    AUDIT_VIEW = "audit.view"

    # Library module (only while the school has it switched on).
    LIBRARY_VIEW = "library.view"  # the catalogue, and one's own (or child's) loans
    LIBRARY_MANAGE = "library.manage"  # the desk: lend, return, catalogue, settings

    # Clubs module. Patrons run their own club whatever their role.
    CLUBS_VIEW = "clubs.view"
    CLUBS_MANAGE = "clubs.manage"  # set up clubs and choose patrons

    # Parent meetings module.
    MEETINGS_VIEW = "meetings.view"  # parents book; staff see their own times
    MEETINGS_MANAGE = "meetings.manage"  # set up meeting days and who takes part

    # Behaviour and discipline module.
    DISCIPLINE_VIEW = "discipline.view"  # parents: what's shared about their children
    DISCIPLINE_RECORD = "discipline.record"  # report incidents about pupils one teaches
    DISCIPLINE_MANAGE = "discipline.manage"  # every incident, actions, sharing with parents
    DISCIPLINE_COUNSEL = "discipline.counsel"  # confidential counselling notes

    # Sick bay module.
    CLINIC_VIEW = "clinic.view"  # class teachers (when and outcome), parents (own children)
    CLINIC_RECORD = "clinic.record"  # the nurse: log visits, see health details

    # Transport module.
    TRANSPORT_VIEW = "transport.view"  # parents and pupils: their own route and trips
    TRANSPORT_RECORD = "transport.record"  # drivers: their vehicle's pick-up lists
    TRANSPORT_MANAGE = "transport.manage"  # vehicles, routes, stops, riders

    # Canteen module.
    CANTEEN_VIEW = "canteen.view"  # parents and pupils: their own wallets
    CANTEEN_SELL = "canteen.sell"  # the till: sales, plan meals, cash top-ups
    CANTEEN_MANAGE = "canteen.manage"  # menu, meal plans, refunds

    # Stores and inventory module.
    INVENTORY_REQUEST = "inventory.request"  # staff ask the stores for supplies
    INVENTORY_MANAGE = "inventory.manage"  # stock, suppliers, equipment, issuing requests

    # Facilities module.
    FACILITIES_USE = "facilities.use"  # book rooms, report repairs
    FACILITIES_MANAGE = "facilities.manage"  # rooms, any booking, following repairs

    # Visitors and the gate.
    GATE_RECORD = "gate.record"  # visitors in and out; checking and recording pick-ups
    GATE_FAMILY = "gate.family"  # parents: who may collect their children, and pick-ups

    # Homework and online learning.
    LMS_TEACH = "lms.teach"  # set homework and share materials for classes one teaches
    LMS_LEARN = "lms.learn"  # pupils: see and hand in homework
    LMS_VIEW = "lms.view"  # parents: their children's homework and marks
    LMS_MANAGE = "lms.manage"  # every class

    # Boarding.
    HOSTEL_VIEW = "hostel.view"  # parents: their child's house, roll calls, exeats
    HOSTEL_RECORD = "hostel.record"  # wardens: beds, roll call, exeats for their house
    HOSTEL_MANAGE = "hostel.manage"  # houses, rooms, wardens; any house

    # Accounting.
    ACCOUNTING_VIEW = "accounting.view"  # read the accounts and reports
    ACCOUNTING_MANAGE = "accounting.manage"  # record spending and income, budgets

    # Payroll. Salaries are confidential: never in custom roles.
    PAYROLL_SELF = "payroll.self"  # every member of staff: their own payslips
    PAYROLL_MANAGE = "payroll.manage"  # the bursar: salaries, preparing pay runs
    PAYROLL_APPROVE = "payroll.approve"  # the proprietor: approving each month's pay

    # Procurement.
    PROCUREMENT_REQUEST = "procurement.request"  # any member of staff asks to buy
    PROCUREMENT_APPROVE = "procurement.approve"  # the head teacher approves requests
    PROCUREMENT_FINAL = "procurement.final"  # the proprietor: large requests, the limit
    PROCUREMENT_MANAGE = "procurement.manage"  # the bursar: orders, receiving, paying

    # Learning support (special educational needs).
    SUPPORT_VIEW = "support.view"  # teachers (own pupils) and parents: goals, adjustments
    SUPPORT_MANAGE = "support.manage"  # write plans, read confidential summaries and notes

    # Alumni and fundraising.
    ALUMNI_MANAGE = "alumni.manage"

    # The school's public website.
    WEBSITE_MANAGE = "website.manage"

    # Accreditation and compliance.
    COMPLIANCE_MANAGE = "compliance.manage"

    # Developer API keys and webhooks: the proprietor only (data leaves the school).
    INTEGRATIONS_MANAGE = "integrations.manage"

    # AI drafting help: ask for a draft (saving it needs the usual permission).
    AI_DRAFT = "assist.draft"
    REPORTS_VIEW = "reports.view"  # class lists, attendance and results for any class
    REPORTS_OWN_CLASS = "reports.own_class"  # the same, for the class teacher's own class

    @classmethod
    def all(cls) -> frozenset[str]:
        return frozenset(v for k, v in vars(cls).items() if k.isupper())


P = Perm
_STUDENTS_ALL = {
    P.STUDENTS_VIEW,
    P.STUDENTS_VIEW_ALL,
    P.STUDENTS_VIEW_SENSITIVE,
    P.STUDENTS_MANAGE,
}
_ACADEMICS_ALL = {P.ACADEMICS_VIEW, P.ACADEMICS_MANAGE}
_ADMISSIONS_ALL = {P.ADMISSIONS_VIEW, P.ADMISSIONS_MANAGE}
_ATTENDANCE_ALL = {P.ATTENDANCE_VIEW, P.ATTENDANCE_RECORD, P.ATTENDANCE_MANAGE}
_COMMS_ALL = {P.COMMUNICATION_VIEW, P.COMMUNICATION_SEND, P.COMMUNICATION_MANAGE}
_STAFF_ALL = {P.STAFF_VIEW, P.STAFF_MANAGE}
_TEACHING = {
    P.STUDENTS_VIEW,
    P.ACADEMICS_VIEW,
    P.ACADEMICS_TIMETABLE_OWN,
    P.ATTENDANCE_VIEW,
    P.ATTENDANCE_RECORD,
    P.ASSESSMENTS_VIEW,
    P.ASSESSMENTS_RECORD,
    P.COMMUNICATION_VIEW,
    P.COMMUNICATION_SEND,
    P.MESSAGES_USE,
    P.LIBRARY_VIEW,
}
_LIBRARY_ALL = {P.LIBRARY_VIEW, P.LIBRARY_MANAGE}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.OWNER: Perm.all(),
    # Head teacher: almost everything the proprietor has, except the logo, giving
    # staff their roles, and score entry (teachers enter scores; the head reviews,
    # publishes, and corrects published results with a recorded reason).
    Role.PRINCIPAL: frozenset(
        _STUDENTS_ALL
        | _ACADEMICS_ALL
        | _ADMISSIONS_ALL
        | _ATTENDANCE_ALL
        | _COMMS_ALL
        | _STAFF_ALL
        | {
            P.SCHOOL_MANAGE,
            P.ASSESSMENTS_VIEW,
            P.ASSESSMENTS_CONFIGURE,
            P.ASSESSMENTS_PUBLISH,
            P.FINANCE_VIEW,
            P.MEMBERS_VIEW,
            P.MEMBERS_MANAGE_STAFF,
            P.AUDIT_VIEW,
            P.MESSAGES_USE,
            P.MESSAGES_OVERSEE,
            P.CALENDAR_MANAGE,
            P.REPORTS_VIEW,
        }
        | _LIBRARY_ALL
    ),
    Role.ADMIN: frozenset(
        _STUDENTS_ALL
        | _ACADEMICS_ALL
        | _ADMISSIONS_ALL
        | _ATTENDANCE_ALL
        | _COMMS_ALL
        | _STAFF_ALL
        | {
            P.SCHOOL_MANAGE,
            P.ASSESSMENTS_VIEW,
            P.ASSESSMENTS_RECORD,
            P.ASSESSMENTS_MANAGE,
            P.ASSESSMENTS_CONFIGURE,
            P.ASSESSMENTS_PUBLISH,
            P.MEMBERS_VIEW,
            P.AUDIT_VIEW,
            P.MESSAGES_USE,
            P.CALENDAR_MANAGE,
            P.REPORTS_VIEW,
        }
        | _LIBRARY_ALL
    ),
    Role.BURSAR: frozenset(
        {
            P.STUDENTS_VIEW,
            P.STUDENTS_VIEW_ALL,
            P.FINANCE_VIEW,
            P.FINANCE_MANAGE,
            P.COMMUNICATION_VIEW,
            P.STAFF_VIEW,
            P.MESSAGES_USE,
        }
    ),
    Role.TEACHER: frozenset(_TEACHING),
    Role.FORM_TEACHER: frozenset(
        _TEACHING
        | {
            P.STUDENTS_VIEW_SENSITIVE,
            P.STUDENTS_ADD_OWN_CLASS,
            P.ASSESSMENTS_PUBLISH_OWN_CLASS,
            P.REPORTS_OWN_CLASS,
        }
    ),
    Role.LIBRARIAN: frozenset(
        {P.STUDENTS_VIEW, P.STUDENTS_VIEW_ALL, P.COMMUNICATION_VIEW} | _LIBRARY_ALL
    ),
    Role.WARDEN: frozenset(
        {
            P.STUDENTS_VIEW,
            P.STUDENTS_VIEW_ALL,
            P.STUDENTS_VIEW_SENSITIVE,
            P.ATTENDANCE_VIEW,
            P.COMMUNICATION_VIEW,
        }
    ),
    Role.DRIVER: frozenset({P.COMMUNICATION_VIEW}),
    Role.CANTEEN: frozenset(
        {P.STUDENTS_VIEW, P.STUDENTS_VIEW_ALL, P.COMMUNICATION_VIEW, P.CANTEEN_SELL}
    ),
    Role.STORE_KEEPER: frozenset({P.COMMUNICATION_VIEW, P.INVENTORY_MANAGE}),
    Role.GATE: frozenset({P.COMMUNICATION_VIEW, P.GATE_RECORD}),
    Role.NURSE: frozenset(
        {
            P.STUDENTS_VIEW,
            P.STUDENTS_VIEW_ALL,
            P.STUDENTS_VIEW_SENSITIVE,
            P.COMMUNICATION_VIEW,
            P.CLINIC_VIEW,
            P.CLINIC_RECORD,
        }
    ),
    Role.PARENT: frozenset(
        {
            P.STUDENTS_VIEW,
            P.STUDENTS_VIEW_SENSITIVE,
            P.ATTENDANCE_VIEW,
            P.ASSESSMENTS_VIEW,
            P.FINANCE_VIEW,
            P.FINANCE_PAY,
            P.COMMUNICATION_VIEW,
            P.MESSAGES_USE,
            P.LIBRARY_VIEW,
        }
    ),
    Role.STUDENT: frozenset(
        {
            P.STUDENTS_VIEW,
            P.ATTENDANCE_VIEW,
            P.ASSESSMENTS_VIEW,
            P.COMMUNICATION_VIEW,
            P.LIBRARY_VIEW,
        }
    ),
}

#: Roles that may see every student in the school (others are scoped by selectors).
SCHOOL_WIDE_STUDENT_ROLES = frozenset(
    {Role.OWNER, Role.PRINCIPAL, Role.ADMIN, Role.BURSAR, Role.LIBRARIAN, Role.WARDEN}
)

#: Roles whose members see draft (unpublished) results and every invoice.
STAFF_ROLES = frozenset(set(Role.values) - {Role.PARENT, Role.STUDENT})

# Every member of staff can ask for leave, and ask the stores for supplies.
for _role in STAFF_ROLES:
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {
        P.LEAVE_REQUEST,
        P.INVENTORY_REQUEST,
        P.FACILITIES_USE,
    }
for _role in (Role.PRINCIPAL, Role.ADMIN, Role.BURSAR):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.INVENTORY_MANAGE}
for _role in (Role.PRINCIPAL, Role.ADMIN):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.FACILITIES_MANAGE, P.GATE_RECORD}
ROLE_PERMISSIONS[Role.PARENT] = ROLE_PERMISSIONS[Role.PARENT] | {P.GATE_FAMILY, P.LMS_VIEW}
# Homework: teachers set it, pupils hand it in, parents follow it, leaders see all.
for _role in (Role.TEACHER, Role.FORM_TEACHER):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.LMS_TEACH}
for _role in (Role.PRINCIPAL, Role.ADMIN):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.LMS_MANAGE}
ROLE_PERMISSIONS[Role.STUDENT] = ROLE_PERMISSIONS[Role.STUDENT] | {P.LMS_LEARN}
# Boarding: leaders set it up, wardens run their house, parents follow and ask for exeats.
for _role in (Role.PRINCIPAL, Role.ADMIN):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.HOSTEL_RECORD, P.HOSTEL_MANAGE}
ROLE_PERMISSIONS[Role.WARDEN] = ROLE_PERMISSIONS[Role.WARDEN] | {P.HOSTEL_RECORD}
ROLE_PERMISSIONS[Role.PARENT] = ROLE_PERMISSIONS[Role.PARENT] | {P.HOSTEL_VIEW}
# Accounting: the bursar keeps the books; the head teacher reads them.
ROLE_PERMISSIONS[Role.BURSAR] = ROLE_PERMISSIONS[Role.BURSAR] | {
    P.ACCOUNTING_VIEW,
    P.ACCOUNTING_MANAGE,
}
ROLE_PERMISSIONS[Role.PRINCIPAL] = ROLE_PERMISSIONS[Role.PRINCIPAL] | {P.ACCOUNTING_VIEW}
# Payroll: the bursar prepares; only the proprietor (who holds everything) approves.
ROLE_PERMISSIONS[Role.BURSAR] = ROLE_PERMISSIONS[Role.BURSAR] | {P.PAYROLL_MANAGE}
for _role in STAFF_ROLES:
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.PAYROLL_SELF, P.PROCUREMENT_REQUEST}
# Procurement: the head teacher approves, the proprietor approves large requests,
# the bursar orders, receives and pays.
ROLE_PERMISSIONS[Role.PRINCIPAL] = ROLE_PERMISSIONS[Role.PRINCIPAL] | {P.PROCUREMENT_APPROVE}
ROLE_PERMISSIONS[Role.BURSAR] = ROLE_PERMISSIONS[Role.BURSAR] | {P.PROCUREMENT_MANAGE}
# Learning support: the head teacher (or a coordinator via a custom role) runs it.
ROLE_PERMISSIONS[Role.PRINCIPAL] = ROLE_PERMISSIONS[Role.PRINCIPAL] | {P.SUPPORT_MANAGE}
for _role in (Role.ADMIN, Role.TEACHER, Role.FORM_TEACHER, Role.PARENT):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.SUPPORT_VIEW}
for _role in (Role.PRINCIPAL, Role.ADMIN):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.ALUMNI_MANAGE, P.WEBSITE_MANAGE}
ROLE_PERMISSIONS[Role.PRINCIPAL] = ROLE_PERMISSIONS[Role.PRINCIPAL] | {P.COMPLIANCE_MANAGE}
for _role in (Role.PRINCIPAL, Role.ADMIN, Role.TEACHER, Role.FORM_TEACHER):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.AI_DRAFT}
# Everyone in the school sees the calendar and the clubs.
for _role in ROLE_PERMISSIONS:
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.CALENDAR_VIEW, P.CLUBS_VIEW}
for _role in (Role.PRINCIPAL, Role.ADMIN):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.CLUBS_MANAGE, P.MEETINGS_MANAGE}
# Behaviour: teachers (and wardens) report, leaders manage, the head counsels,
# parents see what is shared with them.
for _role in (Role.PRINCIPAL, Role.ADMIN, Role.TEACHER, Role.FORM_TEACHER, Role.WARDEN):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.DISCIPLINE_RECORD}
for _role in (Role.PRINCIPAL, Role.ADMIN):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.DISCIPLINE_MANAGE}
ROLE_PERMISSIONS[Role.PRINCIPAL] = ROLE_PERMISSIONS[Role.PRINCIPAL] | {P.DISCIPLINE_COUNSEL}
ROLE_PERMISSIONS[Role.PARENT] = ROLE_PERMISSIONS[Role.PARENT] | {P.DISCIPLINE_VIEW}
# Sick bay: the nurse and leaders record; class teachers and parents see their own.
for _role in (Role.PRINCIPAL, Role.ADMIN):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.CLINIC_VIEW, P.CLINIC_RECORD}
for _role in (Role.FORM_TEACHER, Role.PARENT):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.CLINIC_VIEW}
# Transport: leaders set it up, drivers keep their lists, families see their own.
for _role in (Role.PRINCIPAL, Role.ADMIN):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.TRANSPORT_MANAGE}
ROLE_PERMISSIONS[Role.DRIVER] = ROLE_PERMISSIONS[Role.DRIVER] | {P.TRANSPORT_RECORD}
for _role in (Role.PARENT, Role.STUDENT):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.TRANSPORT_VIEW, P.CANTEEN_VIEW}
# Canteen: the bursar and leaders run it (with the canteen manager at the till).
for _role in (Role.PRINCIPAL, Role.ADMIN, Role.BURSAR):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.CANTEEN_SELL, P.CANTEEN_MANAGE}
# Parents book meetings; teaching staff and leaders see their own times.
for _role in (Role.PRINCIPAL, Role.ADMIN, Role.TEACHER, Role.FORM_TEACHER, Role.PARENT):
    ROLE_PERMISSIONS[_role] = ROLE_PERMISSIONS[_role] | {P.MEETINGS_VIEW}


#: What a school's own (custom) roles may contain, grouped and described for the
#: proprietor. Left out on purpose: the proprietor's own powers (logo, terms,
#: modules), giving or blocking access, amending published scores, and permissions
#: everyone already has or that only make sense for one class or for parents.
CUSTOM_ROLE_PERMISSIONS: dict[str, tuple[str, str]] = {
    P.STUDENTS_VIEW: ("Pupils", "See pupils' records"),
    P.STUDENTS_VIEW_ALL: ("Pupils", "See every pupil in the school, not only their own classes"),
    P.STUDENTS_VIEW_SENSITIVE: ("Pupils", "See health notes and national ID numbers"),
    P.STUDENTS_MANAGE: ("Pupils", "Add, change and move pupils, and run the end of year"),
    P.ADMISSIONS_VIEW: ("Admissions", "See applications"),
    P.ADMISSIONS_MANAGE: ("Admissions", "Review, offer and enrol applicants"),
    P.STAFF_VIEW: ("Staff", "See the staff list"),
    P.STAFF_MANAGE: ("Staff", "Keep staff records, take the staff register and approve leave"),
    P.ACADEMICS_VIEW: ("Academics", "See classes, subjects and timetables"),
    P.ACADEMICS_MANAGE: ("Academics", "Set up classes, subjects, terms and timetables"),
    P.ATTENDANCE_VIEW: ("Attendance", "See registers"),
    P.ATTENDANCE_MANAGE: ("Attendance", "Take or correct the register for any class"),
    P.ASSESSMENTS_VIEW: ("Results", "See results"),
    P.ASSESSMENTS_MANAGE: ("Results", "Enter scores for any class and subject"),
    P.ASSESSMENTS_CONFIGURE: ("Results", "Set up grading: score parts and grade bands"),
    P.ASSESSMENTS_PUBLISH: ("Results", "Work out and publish report cards for any class"),
    P.REPORTS_VIEW: ("Results", "Run class lists, attendance and results reports"),
    P.FINANCE_VIEW: ("Fees", "See fees, invoices, payments and finance reports"),
    P.FINANCE_MANAGE: ("Fees", "Set fees, record payments and give scholarships"),
    P.COMMUNICATION_SEND: ("Communication", "Send announcements to parents of their classes"),
    P.COMMUNICATION_MANAGE: ("Communication", "Send school-wide announcements, see SMS logs"),
    P.MESSAGES_USE: ("Communication", "Write to and receive messages from parents"),
    P.MESSAGES_OVERSEE: (
        "Communication",
        "Read every conversation between parents and staff (safeguarding)",
    ),
    P.CALENDAR_MANAGE: ("Communication", "Add and change calendar events"),
    P.SCHOOL_MANAGE: ("School", "Change school settings"),
    P.MEMBERS_VIEW: ("School", "See who has access to the school"),
    P.AUDIT_VIEW: ("School", "Read the school's audit log"),
    P.LIBRARY_VIEW: ("Library", "Search the library catalogue"),
    P.LIBRARY_MANAGE: ("Library", "Run the library desk: lend, return, add books"),
    P.CLUBS_MANAGE: ("Clubs", "Set up clubs and teams and choose their patrons"),
    P.MEETINGS_MANAGE: ("Parent meetings", "Set up parent meeting days and who takes part"),
    P.DISCIPLINE_RECORD: ("Behaviour", "Report incidents about pupils they teach"),
    P.DISCIPLINE_MANAGE: ("Behaviour", "See all incidents, record actions, tell parents"),
    P.DISCIPLINE_COUNSEL: ("Behaviour", "Read and write confidential counselling notes"),
    P.CLINIC_RECORD: ("Sick bay", "Log sick bay visits and see pupils' health details"),
    P.TRANSPORT_MANAGE: ("Transport", "Set up buses, routes and stops, and who rides them"),
    P.CANTEEN_SELL: ("Canteen", "Sell at the canteen till and take cash top-ups"),
    P.CANTEEN_MANAGE: ("Canteen", "Set the canteen menu, meal plans and refunds"),
    P.INVENTORY_MANAGE: ("Stores", "Keep the stores: stock, suppliers, equipment, requests"),
    P.FACILITIES_MANAGE: ("Facilities", "Keep the room list, cancel bookings, follow repairs"),
    P.GATE_RECORD: ("Gate", "Sign visitors in and out and record who collects pupils"),
    P.LMS_MANAGE: ("Homework", "See and manage homework for every class"),
    P.HOSTEL_MANAGE: ("Boarding", "Set up boarding houses and rooms, run any house"),
    P.ACCOUNTING_VIEW: ("Accounting", "Read the school's accounts and reports"),
    P.ACCOUNTING_MANAGE: ("Accounting", "Record spending and other income, set budgets"),
    P.SUPPORT_MANAGE: ("Learning support", "Write learning support plans and read their notes"),
    P.ALUMNI_MANAGE: ("Alumni", "Keep the alumni list and record gifts"),
    P.WEBSITE_MANAGE: ("Website", "Edit and publish the school's public website"),
    P.COMPLIANCE_MANAGE: ("Compliance", "Keep the compliance checklist and its evidence"),
    P.AI_DRAFT: ("AI drafting help", "Ask for drafts of report comments and announcements"),
}


def permissions_for_roles(roles: Iterable[str]) -> frozenset[str]:
    granted: set[str] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)


def can_grant(granter_roles: Iterable[str], role: str) -> bool:
    """May someone with ``granter_roles`` give (or block) a person with ``role``?

    - Parent and student roles only ever reach the person's own children or
      themselves, so whoever manages pupils, admissions or members may grant them.
    - The proprietor (``members.manage``) grants any staff role that adds no
      permission they lack.
    - The head teacher (``members.manage_staff``) adds and blocks teaching and
      support staff (``HEAD_MANAGED_ROLES``) but not leadership or finance roles.
      Teachers enter scores, which the head teacher doesn't: appointing them is
      the head teacher's job, and nobody may give a role to themselves
      (``control_plane.members``), so this can't become the head's own score entry.
    """
    granted = permissions_for_roles(granter_roles)
    if role in SELF_SCOPED_ROLES:
        return bool(granted & {Perm.MEMBERS_MANAGE, Perm.STUDENTS_MANAGE, Perm.ADMISSIONS_MANAGE})
    if Perm.MEMBERS_MANAGE in granted:
        return ROLE_PERMISSIONS.get(role, frozenset()) <= granted
    return Perm.MEMBERS_MANAGE_STAFF in granted and role in HEAD_MANAGED_ROLES


def grantable_roles(granter_roles: Iterable[str]) -> list[str]:
    """The roles this person may give or block, in the order roles are listed."""
    roles = frozenset(granter_roles)
    return [role for role in Role.values if can_grant(roles, role)]


SELF_SCOPED_ROLES = frozenset({Role.PARENT, Role.STUDENT})

#: Staff the head teacher adds and blocks. Leadership and finance roles
#: (proprietor, head teacher, administrator, bursar) stay with the proprietor.
HEAD_MANAGED_ROLES = frozenset(
    {
        Role.TEACHER,
        Role.FORM_TEACHER,
        Role.LIBRARIAN,
        Role.WARDEN,
        Role.DRIVER,
        Role.NURSE,
        Role.STORE_KEEPER,
        Role.GATE,
    }
)
