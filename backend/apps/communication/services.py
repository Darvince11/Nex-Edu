"""Who gets told what, and on which channel.

Every message lands in the in-app inbox for users who have a login. SMS,
WhatsApp and email are queued as ``Delivery`` rows and sent by a background task,
so a school-wide announcement never blocks a web request.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from apps.students.models import Student, StudentGuardian
from control_plane.models import Membership, Role, User
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.tasks import enqueue_for_current_tenant
from integrations.phone import normalize_gh_phone

from .models import Announcement, Channel, Delivery, MessagingSettings, Notification

BATCH = 500
SMS_MAX_CHARS = 459  # three concatenated SMS segments


def member_ids(roles: Iterable[str]) -> set[UUID]:
    return set(
        Membership.objects.filter(
            tenant=require_tenant(), role__in=list(roles), is_active=True
        ).values_list("user_id", flat=True)
    )


def _queue(deliveries: list[Delivery]) -> int:
    if not deliveries:
        return 0
    Delivery.objects.bulk_create(deliveries, batch_size=BATCH)
    ids = [str(d.id) for d in deliveries]
    from .tasks import send_deliveries

    def enqueue() -> None:
        for start in range(0, len(ids), BATCH):
            enqueue_for_current_tenant(send_deliveries, ids[start : start + BATCH])

    # Workers must not see the ids before the rows are committed.
    transaction.on_commit(enqueue, using=require_tenant().db_alias)
    return len(deliveries)


def notify_users(
    user_ids: Iterable[UUID],
    *,
    kind: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    channels: Iterable[str] = (),
) -> int:
    """In-app notification for each user, plus any extra channels using their profile."""
    user_ids = list(dict.fromkeys(user_ids))
    Notification.objects.bulk_create(
        [
            Notification(recipient_user_id=uid, kind=kind, title=title, body=body, data=data or {})
            for uid in user_ids
        ],
        batch_size=BATCH,
    )
    channels = set(channels) - {Channel.IN_APP}
    if channels:
        deliveries: list[Delivery] = []
        for user in User.objects.filter(pk__in=user_ids).only("email", "phone"):
            if Channel.EMAIL in channels and user.email:
                deliveries.append(
                    Delivery(
                        channel=Channel.EMAIL, to=user.email, subject=title, body=body, kind=kind
                    )
                )
            phone = normalize_gh_phone(user.phone)
            for channel in channels & {Channel.SMS, Channel.WHATSAPP}:
                if phone:
                    deliveries.append(
                        Delivery(channel=channel, to=phone, body=_sms_text(title, body), kind=kind)
                    )
        _queue(deliveries)
    return len(user_ids)


def notify_guardians(
    students: Iterable[Student],
    *,
    kind: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    channels: Iterable[str] = (),
) -> int:
    """Tell each student's guardians, by login if they have one and by phone/email if asked."""
    channels = set(channels)
    student_ids = [s.pk for s in students]
    guardians = StudentGuardian.objects.filter(student_id__in=student_ids)
    user_ids = {g.guardian_user_id for g in guardians if g.guardian_user_id}
    if user_ids:
        notify_users(user_ids, kind=kind, title=title, body=body, data=data)

    deliveries: list[Delivery] = []
    seen: set[tuple[str, str]] = set()
    for g in guardians:
        targets: list[tuple[str, str]] = []
        phone = normalize_gh_phone(g.phone)
        if phone and g.receives_sms:
            targets += [(c, phone) for c in channels & {Channel.SMS, Channel.WHATSAPP}]
        if g.email and Channel.EMAIL in channels:
            targets.append((Channel.EMAIL, g.email))
        for channel, to in targets:
            if (channel, to) in seen:
                continue
            seen.add((channel, to))
            text = body if channel == Channel.EMAIL else _sms_text(title, body)
            deliveries.append(Delivery(channel=channel, to=to, subject=title, body=text, kind=kind))
    _queue(deliveries)
    return len(guardians)


def _sms_text(title: str, body: str) -> str:
    school = require_tenant().name
    text = f"{school}: {title}. {body}" if title else f"{school}: {body}"
    return text if len(text) <= SMS_MAX_CHARS else text[: SMS_MAX_CHARS - 1] + "…"


def sms_sent_this_month() -> int:
    start = timezone.localdate().replace(day=1)
    return Delivery.objects.filter(
        channel=Channel.SMS, status=Delivery.Status.SENT, sent_at__date__gte=start
    ).count()


# --- Announcements ------------------------------------------------------------


def announcement_recipients(announcement: Announcement) -> tuple[set[UUID], list[Student]]:
    """Users to put in the inbox, and students whose guardians to contact by phone."""
    audience = announcement.audience
    A = Announcement.Audience
    staff_roles = set(Role.values) - {Role.PARENT, Role.STUDENT}
    users: set[UUID] = set()
    students: list[Student] = []
    if audience in {A.EVERYONE, A.STAFF}:
        users |= member_ids(staff_roles)
    if audience in {A.EVERYONE, A.STUDENTS}:
        users |= member_ids([Role.STUDENT])
    if audience in {A.EVERYONE, A.PARENTS, A.LEVEL_PARENTS, A.ARM_PARENTS}:
        active = Student.objects.filter(status=Student.Status.ACTIVE)
        if audience == A.LEVEL_PARENTS:
            active = active.filter(arm__level=announcement.level_id)
        elif audience == A.ARM_PARENTS:
            active = active.filter(arm=announcement.arm_id)
        students = list(active)
    return users, students


def publish_announcement(*, request: HttpRequest | None, announcement: Announcement) -> int:
    if announcement.status == Announcement.Status.PUBLISHED:
        return announcement.recipient_count
    users, students = announcement_recipients(announcement)
    channels = set(announcement.channels)
    data = {"announcement_id": str(announcement.pk)}
    with tenant_atomic():
        notify_users(
            users,
            kind="announcement",
            title=announcement.title,
            body=announcement.body,
            data=data,
            channels=channels,
        )
        guardian_count = notify_guardians(
            students,
            kind="announcement",
            title=announcement.title,
            body=announcement.body,
            data=data,
            channels=channels,
        )
        announcement.status = Announcement.Status.PUBLISHED
        announcement.published_at = timezone.now()
        announcement.recipient_count = len(users) + guardian_count
        announcement.save(update_fields=["status", "published_at", "recipient_count"])
        record_event(
            action="announcement.published",
            request=request,
            target=announcement,
            after={
                "audience": announcement.audience,
                "channels": sorted(channels),
                "recipients": announcement.recipient_count,
            },
        )
    return announcement.recipient_count


def visible_announcements(user: Any, roles: Iterable[str]) -> Any:
    """Published announcements addressed to this user, by role and children's classes."""
    roles = set(roles)
    A = Announcement.Audience
    q = Q(audience=A.EVERYONE)
    if roles - {Role.PARENT, Role.STUDENT}:
        q |= Q(audience=A.STAFF)
    if Role.STUDENT in roles:
        q |= Q(audience=A.STUDENTS)
    if Role.PARENT in roles:
        children = Student.objects.filter(guardians__guardian_user_id=user.pk)
        q |= Q(audience=A.PARENTS)
        q |= Q(audience=A.ARM_PARENTS, arm__in=children.values("arm"))
        q |= Q(audience=A.LEVEL_PARENTS, level__in=children.values("arm__level"))
    staff_roles = set(Role.values) - {Role.PARENT, Role.STUDENT}
    published = Announcement.objects.filter(status=Announcement.Status.PUBLISHED)
    if roles & staff_roles:
        return published  # staff see every published announcement in their school
    return published.filter(q)


def messaging_settings() -> MessagingSettings:
    return MessagingSettings.load()
