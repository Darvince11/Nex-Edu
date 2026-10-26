"""Nex Edu's announcements to school proprietors (new features, maintenance, ...).

Publishing fixes the recipient list (proprietors of active schools in the chosen
audience), shows the announcement on their dashboards until they dismiss it,
and optionally emails them in the background.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.mail import send_mass_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from control_plane.audit import record_platform_event
from control_plane.models import (
    Membership,
    PlatformAnnouncement,
    PlatformAnnouncementRecipient,
    Role,
    SchoolRegistration,
    Tenant,
    User,
)
from control_plane.pricing import band_for
from control_plane.usage import latest_usage


def audience_schools(announcement: PlatformAnnouncement) -> list[Tenant]:
    schools = list(Tenant.objects.filter(status=Tenant.Status.ACTIVE))
    if announcement.audience == PlatformAnnouncement.Audience.REGION:
        in_region = set(
            SchoolRegistration.objects.filter(region=announcement.region).values_list(
                "tenant_id", flat=True
            )
        )
        schools = [t for t in schools if t.pk in in_region]
    elif announcement.audience == PlatformAnnouncement.Audience.BAND:
        usage = latest_usage(schools)
        schools = [
            t
            for t in schools
            if t.pk in usage and band_for(usage[t.pk].pupils).code == announcement.band_code
        ]
    return schools


def audience_users(announcement: PlatformAnnouncement) -> list[User]:
    schools = audience_schools(announcement)
    ids = (
        Membership.objects.filter(tenant__in=schools, role=Role.OWNER, is_active=True)
        .values_list("user_id", flat=True)
        .distinct()
    )
    return list(User.objects.filter(pk__in=ids, is_active=True))


def validate(data: dict[str, Any]) -> None:
    audience = data.get("audience")
    if audience == PlatformAnnouncement.Audience.REGION and not data.get("region"):
        raise ValidationError({"region": "Choose a region."})
    if audience == PlatformAnnouncement.Audience.BAND and not data.get("band_code"):
        raise ValidationError({"band_code": "Choose a price band."})


def publish(*, request: Any, announcement: PlatformAnnouncement) -> PlatformAnnouncement:
    from control_plane.tasks import email_announcement
    from core.tasks import enqueue_after_commit

    if announcement.status == PlatformAnnouncement.Status.PUBLISHED:
        raise ValidationError("This announcement has already been sent.")
    with transaction.atomic():
        users = audience_users(announcement)
        if not users:
            raise ValidationError("No proprietor is in this audience yet.")
        PlatformAnnouncementRecipient.objects.bulk_create(
            [PlatformAnnouncementRecipient(announcement=announcement, user=u) for u in users]
        )
        announcement.status = PlatformAnnouncement.Status.PUBLISHED
        announcement.published_at = timezone.now()
        announcement.recipient_count = len(users)
        announcement.save(update_fields=["status", "published_at", "recipient_count"])
        record_platform_event(
            action="announcement.published",
            request=request,
            target=announcement,
            data={
                "title": announcement.title,
                "audience": announcement.audience,
                "recipients": len(users),
            },
        )
        if announcement.email:
            enqueue_after_commit(email_announcement, str(announcement.pk))
    return announcement


def send_emails(announcement_id: str) -> int:
    announcement = PlatformAnnouncement.objects.get(pk=announcement_id)
    recipients = announcement.recipients.select_related("user")
    body = f"{announcement.body}\n\n— The Nex Edu team\n{settings.FRONTEND_URL}"
    messages = [
        (f"Nex Edu: {announcement.title}", body, None, [r.user.email])
        for r in recipients
        if r.user.email
    ]
    return send_mass_mail(messages, fail_silently=True)


def for_user(user: Any) -> list[PlatformAnnouncementRecipient]:
    """Unread announcements for a proprietor, newest first."""
    return list(
        PlatformAnnouncementRecipient.objects.filter(user=user, read_at__isnull=True)
        .select_related("announcement")
        .order_by("-announcement__published_at")[:5]
    )
