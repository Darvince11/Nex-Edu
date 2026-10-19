"""Role → permission table. The single source of truth for what each role may do.

Permissions say *what kind* of action is allowed. *Which* records a user may act on
(own children, own classes, own subjects) is decided by each app's selectors.
"""

from __future__ import annotations

from collections.abc import Iterable

from control_plane.models import Role


class Perm:
    SCHOOL_MANAGE = "school.manage"

    STUDENTS_VIEW = "students.view"
    STUDENTS_VIEW_SENSITIVE = "students.view_sensitive"  # health records, NIN
    STUDENTS_MANAGE = "students.manage"

    STAFF_VIEW = "staff.view"
    STAFF_MANAGE = "staff.manage"

    ACADEMICS_VIEW = "academics.view"
    ACADEMICS_MANAGE = "academics.manage"

    ADMISSIONS_VIEW = "admissions.view"
    ADMISSIONS_MANAGE = "admissions.manage"

    ATTENDANCE_VIEW = "attendance.view"
    ATTENDANCE_RECORD = "attendance.record"  # registers for classes the teacher is assigned to
    ATTENDANCE_MANAGE = "attendance.manage"  # any class

    ASSESSMENTS_VIEW = "assessments.view"
    ASSESSMENTS_RECORD = "assessments.record"  # scores for the teacher's own class + subject
    ASSESSMENTS_MANAGE = "assessments.manage"  # scores for any class, grading setup
    ASSESSMENTS_PUBLISH = "assessments.publish"  # compute and release report cards
    ASSESSMENTS_AMEND = "assessments.amend"  # change scores after publication

    FINANCE_VIEW = "finance.view"
    FINANCE_MANAGE = "finance.manage"
    FINANCE_PAY = "finance.pay"  # parents paying their children's fees

    COMMUNICATION_VIEW = "communication.view"
    COMMUNICATION_SEND = "communication.send"
    COMMUNICATION_MANAGE = "communication.manage"  # school-wide audiences, delivery logs

    MEMBERS_MANAGE = "members.manage"
    AUDIT_VIEW = "audit.view"

    @classmethod
    def all(cls) -> frozenset[str]:
        return frozenset(v for k, v in vars(cls).items() if k.isupper())


P = Perm
_STUDENTS_ALL = {P.STUDENTS_VIEW, P.STUDENTS_VIEW_SENSITIVE, P.STUDENTS_MANAGE}
_ACADEMICS_ALL = {P.ACADEMICS_VIEW, P.ACADEMICS_MANAGE}
_ADMISSIONS_ALL = {P.ADMISSIONS_VIEW, P.ADMISSIONS_MANAGE}
_ATTENDANCE_ALL = {P.ATTENDANCE_VIEW, P.ATTENDANCE_RECORD, P.ATTENDANCE_MANAGE}
_COMMS_ALL = {P.COMMUNICATION_VIEW, P.COMMUNICATION_SEND, P.COMMUNICATION_MANAGE}
_STAFF_ALL = {P.STAFF_VIEW, P.STAFF_MANAGE}
_TEACHING = {
    P.STUDENTS_VIEW,
    P.ACADEMICS_VIEW,
    P.ATTENDANCE_VIEW,
    P.ATTENDANCE_RECORD,
    P.ASSESSMENTS_VIEW,
    P.ASSESSMENTS_RECORD,
    P.COMMUNICATION_VIEW,
    P.COMMUNICATION_SEND,
}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.OWNER: Perm.all(),
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
            P.ASSESSMENTS_RECORD,
            P.ASSESSMENTS_MANAGE,
            P.ASSESSMENTS_PUBLISH,
            P.ASSESSMENTS_AMEND,
            P.FINANCE_VIEW,
            P.MEMBERS_MANAGE,
            P.AUDIT_VIEW,
        }
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
            P.ASSESSMENTS_PUBLISH,
            P.MEMBERS_MANAGE,
            P.AUDIT_VIEW,
        }
    ),
    Role.BURSAR: frozenset(
        {P.STUDENTS_VIEW, P.FINANCE_VIEW, P.FINANCE_MANAGE, P.COMMUNICATION_VIEW, P.STAFF_VIEW}
    ),
    Role.TEACHER: frozenset(_TEACHING),
    Role.FORM_TEACHER: frozenset(_TEACHING | {P.STUDENTS_VIEW_SENSITIVE}),
    Role.LIBRARIAN: frozenset({P.STUDENTS_VIEW, P.COMMUNICATION_VIEW}),
    Role.WARDEN: frozenset(
        {P.STUDENTS_VIEW, P.STUDENTS_VIEW_SENSITIVE, P.ATTENDANCE_VIEW, P.COMMUNICATION_VIEW}
    ),
    Role.DRIVER: frozenset({P.COMMUNICATION_VIEW}),
    Role.PARENT: frozenset(
        {
            P.STUDENTS_VIEW,
            P.STUDENTS_VIEW_SENSITIVE,
            P.ATTENDANCE_VIEW,
            P.ASSESSMENTS_VIEW,
            P.FINANCE_VIEW,
            P.FINANCE_PAY,
            P.COMMUNICATION_VIEW,
        }
    ),
    Role.STUDENT: frozenset(
        {P.STUDENTS_VIEW, P.ATTENDANCE_VIEW, P.ASSESSMENTS_VIEW, P.COMMUNICATION_VIEW}
    ),
}

#: Roles that may see every student in the school (others are scoped by selectors).
SCHOOL_WIDE_STUDENT_ROLES = frozenset(
    {Role.OWNER, Role.PRINCIPAL, Role.ADMIN, Role.BURSAR, Role.LIBRARIAN, Role.WARDEN}
)

#: Roles whose members see draft (unpublished) results and every invoice.
STAFF_ROLES = frozenset(set(Role.values) - {Role.PARENT, Role.STUDENT})


def permissions_for_roles(roles: Iterable[str]) -> frozenset[str]:
    granted: set[str] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)


def can_grant(granter_roles: Iterable[str], role: str) -> bool:
    """A user may grant a role only if it gives no permission they lack themselves.

    Stops an administrator from creating an owner, or a principal from minting
    a bursar with finance powers the principal doesn't hold.
    """
    granted = permissions_for_roles(granter_roles)
    if role in SELF_SCOPED_ROLES:
        # Parent and student permissions only ever reach the user's own children or
        # themselves, so whoever manages students or members may grant them.
        return bool(granted & {Perm.MEMBERS_MANAGE, Perm.STUDENTS_MANAGE, Perm.ADMISSIONS_MANAGE})
    return ROLE_PERMISSIONS.get(role, frozenset()) <= granted


SELF_SCOPED_ROLES = frozenset({Role.PARENT, Role.STUDENT})
