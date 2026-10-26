"""Announcements, the in-app inbox, and outbound SMS / WhatsApp / email deliveries."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.academics.models import ClassArm, ClassLevel


class Channel(models.TextChoices):
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"


class MessagingSettings(models.Model):
    """Per-school messaging settings. How many SMS a school may send is set by Nex Edu
    (``control_plane.subscriptions.sms_allowance``): a monthly allowance plus bundles."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    sms_sender_id = models.CharField(max_length=11, blank=True, help_text="Registered sender ID")
    notify_absence_by_sms = models.BooleanField(default=True)
    notify_results_by_sms = models.BooleanField(default=True)
    whatsapp_enabled = models.BooleanField(default=False)

    @classmethod
    def load(cls) -> MessagingSettings:
        return cls.objects.get_or_create(pk=1)[0]


class Announcement(models.Model):
    class Audience(models.TextChoices):
        EVERYONE = "everyone"
        STAFF = "staff"
        PARENTS = "parents"
        STUDENTS = "students"
        LEVEL_PARENTS = "level_parents"
        ARM_PARENTS = "arm_parents"

    class Status(models.TextChoices):
        DRAFT = "draft"
        PUBLISHED = "published"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=140)
    body = models.TextField(max_length=5000)
    audience = models.CharField(max_length=20, choices=Audience.choices)
    level = models.ForeignKey(
        ClassLevel, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    arm = models.ForeignKey(
        ClassArm, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    channels = models.JSONField(default=list, help_text="Extra channels beyond in-app")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering: ClassVar = ["-created_at"]


class Notification(models.Model):
    """An in-app inbox item for one user in this school."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient_user_id = models.UUIDField(db_index=True)
    kind = models.CharField(max_length=40)  # "announcement", "absence", "results", "payment"
    title = models.CharField(max_length=140)
    body = models.TextField(max_length=5000)
    data = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["recipient_user_id", "read_at"])]


class Delivery(models.Model):
    """One outbound message on an external channel. Logged for cost and support."""

    class Status(models.TextChoices):
        QUEUED = "queued"
        SENT = "sent"
        FAILED = "failed"
        SKIPPED = "skipped"  # over quota, opted out, or no contact

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    to = models.CharField(max_length=254)
    subject = models.CharField(max_length=140, blank=True)
    body = models.TextField(max_length=5000)
    kind = models.CharField(max_length=40)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    provider = models.CharField(max_length=20, blank=True)
    provider_message_id = models.CharField(max_length=100, blank=True)
    error = models.CharField(max_length=300, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["channel", "status", "created_at"])]


class Conversation(models.Model):
    """Private messages between one member of staff and one parent, about one pupil.

    The proprietor and head teacher can read every conversation (safeguarding);
    only the two people in it can write.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        "students.Student", on_delete=models.CASCADE, related_name="conversations"
    )
    staff_user_id = models.UUIDField(db_index=True)
    parent_user_id = models.UUIDField(db_index=True)
    subject = models.CharField(max_length=140)
    started_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(db_index=True)
    last_sender_user_id = models.UUIDField()
    staff_read_at = models.DateTimeField(null=True, blank=True)
    parent_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-last_message_at"]

    def __str__(self) -> str:
        return self.subject

    def unread_for(self, user_id: object) -> bool:
        if self.last_sender_user_id == user_id:
            return False
        if user_id == self.staff_user_id:
            seen = self.staff_read_at
        elif user_id == self.parent_user_id:
            seen = self.parent_read_at
        else:
            return False
        return seen is None or seen < self.last_message_at


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender_user_id = models.UUIDField()
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["created_at"]
