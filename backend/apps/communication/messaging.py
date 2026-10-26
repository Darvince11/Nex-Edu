"""Messages between parents and staff.

Each conversation is between one member of staff and one parent, about one pupil:

- parents write to the teachers of their child's class, the head teacher and the bursar;
- teachers write to the guardians (with a login) of pupils in classes they teach;
- school leaders and the bursar write to the guardians of any pupil.

The proprietor and head teacher can read every conversation (``messages.oversee``),
but only the two people in a conversation can write in it. Email alerts say who wrote
and about whom, never what they wrote.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.academics.models import TeachingAssignment
from apps.students.models import Student, StudentGuardian
from control_plane.models import Membership, Role, User
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm

from .models import Channel, Conversation, Message
from .services import notify_users

#: Staff who may write to the guardians of any pupil.
SCHOOL_WIDE = frozenset({Role.OWNER, Role.PRINCIPAL, Role.ADMIN, Role.BURSAR})
#: Staff every parent may write to, besides their child's teachers.
OFFICE_ROLES = {Role.PRINCIPAL: "Head teacher", Role.BURSAR: "Bursar"}


def names(user_ids: Iterable[Any]) -> dict[Any, str]:
    found = {}
    for user in User.objects.filter(pk__in=set(user_ids)).only("first_name", "last_name", "email"):
        found[user.pk] = user.get_full_name() or user.email.split("@")[0]
    return found


def _active_members(user_ids: Iterable[Any]) -> set[UUID]:
    return set(
        Membership.objects.filter(
            tenant=require_tenant(), user_id__in=list(user_ids), is_active=True
        ).values_list("user_id", flat=True)
    )


def is_guardian(user: Any, student: Student) -> bool:
    return StudentGuardian.objects.filter(student=student, guardian_user_id=user.pk).exists()


def staff_contacts(student: Student) -> list[dict[str, Any]]:
    """Who a parent of ``student`` may write to."""
    roles: dict[Any, list[str]] = {}
    if student.arm_id:
        for a in TeachingAssignment.objects.filter(arm_id=student.arm_id).select_related("subject"):
            label = "Class teacher" if a.is_form_teacher or not a.subject else a.subject.name
            roles.setdefault(a.teacher_user_id, [])
            if label not in roles[a.teacher_user_id]:
                roles[a.teacher_user_id].append(label)
    for m in Membership.objects.filter(
        tenant=require_tenant(), role__in=list(OFFICE_ROLES), is_active=True
    ):
        roles.setdefault(m.user_id, []).append(OFFICE_ROLES[m.role])
    active = _active_members(roles)
    who = names(active)
    rows = [
        {"user": str(uid), "name": who.get(uid, ""), "role": _describe(labels)}
        for uid, labels in roles.items()
        if uid in active
    ]
    # Class teacher first, then the office, then subject teachers.
    rows.sort(
        key=lambda r: (
            "Class teacher" not in r["role"],
            not any(v in r["role"] for v in OFFICE_ROLES.values()),
            r["name"],
        )
    )
    return rows


def _describe(labels: list[str]) -> str:
    """How a staff contact is shown: class teacher, office role, or subjects taught."""
    office = [label for label in labels if label in OFFICE_ROLES.values()]
    if "Class teacher" in labels:
        return ", ".join(["Class teacher", *office])
    subjects = sorted(label for label in labels if label not in office)
    if len(subjects) > 3:
        subjects = [*subjects[:2], f"{len(subjects) - 2} more subjects"]
    return ", ".join(subjects + office)


def may_write_to_guardians(user: Any, roles: Iterable[str], student: Student) -> bool:
    if set(roles) & SCHOOL_WIDE:
        return True
    return bool(
        student.arm_id
        and TeachingAssignment.objects.filter(
            teacher_user_id=user.pk, arm_id=student.arm_id
        ).exists()
    )


def guardian_contacts(student: Student) -> list[dict[str, Any]]:
    """The guardians of ``student`` who have a login (others are reached by SMS)."""
    guardians = list(StudentGuardian.objects.filter(student=student).exclude(guardian_user_id=None))
    active = _active_members(g.guardian_user_id for g in guardians)
    who = names(active)
    return [
        {
            "user": str(g.guardian_user_id),
            "name": who.get(g.guardian_user_id) or g.full_name,
            "role": g.relationship.title(),
        }
        for g in sorted(guardians, key=lambda g: not g.is_primary)
        if g.guardian_user_id in active
    ]


def contacts(user: Any, roles: Iterable[str], student: Student) -> list[dict[str, Any]]:
    """The people ``user`` may start a conversation with about ``student``."""
    roles = set(roles)
    if Role.PARENT in roles and is_guardian(user, student):
        return [c for c in staff_contacts(student) if c["user"] != str(user.pk)]
    if roles - {Role.PARENT, Role.STUDENT} and may_write_to_guardians(user, roles, student):
        return [c for c in guardian_contacts(student) if c["user"] != str(user.pk)]
    return []


def visible(user: Any, permissions: Iterable[str]) -> QuerySet[Conversation]:
    qs = Conversation.objects.select_related("student__arm__level")
    if Perm.MESSAGES_OVERSEE in set(permissions):
        return qs
    return qs.filter(Q(staff_user_id=user.pk) | Q(parent_user_id=user.pk))


def _alert(request: HttpRequest | None, conversation: Conversation, sender: Any) -> None:
    to = (
        conversation.parent_user_id
        if sender.pk == conversation.staff_user_id
        else conversation.staff_user_id
    )
    sender_name = names([sender.pk]).get(sender.pk, "Someone")
    notify_users(
        [to],
        kind="message",
        title=f"New message from {sender_name}",
        body=(
            f"{sender_name} wrote about {conversation.student.first_name}: "
            f"“{conversation.subject}”. Sign in to Nex Edu to read and reply."
        ),
        data={"conversation": str(conversation.pk)},
        channels=[Channel.EMAIL],
    )


def start(
    *,
    request: HttpRequest,
    roles: Iterable[str],
    student: Student,
    to: UUID,
    subject: str,
    body: str,
) -> Conversation:
    user = request.user
    allowed = {c["user"] for c in contacts(user, roles, student)}
    if str(to) not in allowed:
        raise PermissionDenied("You can't write to this person about this pupil.")
    parent_writes = Role.PARENT in set(roles) and is_guardian(user, student)
    now = timezone.now()
    with tenant_atomic():
        conversation = Conversation.objects.create(
            student=student,
            staff_user_id=to if parent_writes else user.pk,
            parent_user_id=user.pk if parent_writes else to,
            subject=subject.strip(),
            started_by=user.pk,
            last_message_at=now,
            last_sender_user_id=user.pk,
            **({"parent_read_at": now} if parent_writes else {"staff_read_at": now}),
        )
        Message.objects.create(conversation=conversation, sender_user_id=user.pk, body=body)
        record_event(action="message.started", request=request, target=conversation)
        _alert(request, conversation, user)
    return conversation


def reply(*, request: HttpRequest, conversation: Conversation, body: str) -> Message:
    user = request.user
    if user.pk not in (conversation.staff_user_id, conversation.parent_user_id):
        raise PermissionDenied("Only the two people in a conversation can write in it.")
    if not body.strip():
        raise ValidationError({"body": "Write a message."})
    with tenant_atomic():
        message = Message.objects.create(
            conversation=conversation, sender_user_id=user.pk, body=body
        )
        conversation.last_message_at = message.created_at
        conversation.last_sender_user_id = user.pk
        mark_read(conversation, user, save=False)
        conversation.save(
            update_fields=[
                "last_message_at",
                "last_sender_user_id",
                "staff_read_at",
                "parent_read_at",
            ]
        )
        _alert(request, conversation, user)
    return message


def mark_read(conversation: Conversation, user: Any, *, save: bool = True) -> None:
    now = timezone.now()
    if user.pk == conversation.staff_user_id:
        conversation.staff_read_at = now
    elif user.pk == conversation.parent_user_id:
        conversation.parent_read_at = now
    else:
        return
    if save:
        conversation.save(update_fields=["staff_read_at", "parent_read_at"])


_UNREAD_FIELDS = (
    "staff_user_id",
    "parent_user_id",
    "last_sender_user_id",
    "last_message_at",
    "staff_read_at",
    "parent_read_at",
)


def unread_count(user: Any) -> int:
    mine = Conversation.objects.filter(
        Q(staff_user_id=user.pk) | Q(parent_user_id=user.pk)
    ).exclude(last_sender_user_id=user.pk)
    return sum(1 for c in mine.only(*_UNREAD_FIELDS) if c.unread_for(user.pk))
