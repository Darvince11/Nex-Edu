from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from apps.academics.selectors import teaches_arm
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.pagination import DefaultCursorPagination
from core.rbac import Perm
from core.views import TenantViewSet

from .. import services
from ..models import Announcement, Channel, Delivery, Notification


class AnnouncementSerializer(serializers.ModelSerializer[Announcement]):
    channels = serializers.ListField(
        child=serializers.ChoiceField(choices=[Channel.EMAIL, Channel.SMS, Channel.WHATSAPP]),
        required=False,
        default=list,
    )

    class Meta:
        model = Announcement
        fields: ClassVar = [
            "id",
            "title",
            "body",
            "audience",
            "level",
            "arm",
            "channels",
            "status",
            "created_by",
            "created_at",
            "published_at",
            "recipient_count",
        ]
        read_only_fields: ClassVar = [
            "status",
            "created_by",
            "created_at",
            "published_at",
            "recipient_count",
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        A = Announcement.Audience
        if attrs.get("audience") == A.ARM_PARENTS and not attrs.get("arm"):
            raise serializers.ValidationError({"arm": "Choose the class."})
        if attrs.get("audience") == A.LEVEL_PARENTS and not attrs.get("level"):
            raise serializers.ValidationError({"level": "Choose the level."})
        return attrs


class AnnouncementViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, TenantViewSet
):
    serializer_class = AnnouncementSerializer
    pagination_class = DefaultCursorPagination
    required_permissions: ClassVar = {
        "list": Perm.COMMUNICATION_VIEW,
        "retrieve": Perm.COMMUNICATION_VIEW,
        "create": Perm.COMMUNICATION_SEND,
        "publish": Perm.COMMUNICATION_SEND,
    }

    def get_queryset(self) -> QuerySet[Announcement]:
        user, roles, perms = self.actor()
        visible = services.visible_announcements(user, roles)
        if Perm.COMMUNICATION_SEND in perms:
            visible = visible | Announcement.objects.filter(created_by=user.pk)
        return visible.distinct()

    def _check_audience(self, audience: str, arm_id: Any) -> None:
        user, _, perms = self.actor()
        if Perm.COMMUNICATION_MANAGE in perms:
            return
        # Teachers may message only the parents of a class they teach.
        if audience != Announcement.Audience.ARM_PARENTS or not teaches_arm(user, arm_id):
            raise PermissionDenied(
                "You can only send announcements to parents of classes you teach."
            )

    def perform_create(self, serializer: AnnouncementSerializer) -> None:  # type: ignore[override]
        v = serializer.validated_data
        self._check_audience(v["audience"], getattr(v.get("arm"), "pk", None))
        with tenant_atomic():
            announcement = serializer.save(created_by=self.request.user.pk)
            record_event(action="announcement.created", request=self.request, target=announcement)

    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        announcement = self.get_object()
        self._check_audience(announcement.audience, announcement.arm_id)
        services.publish_announcement(request=request, announcement=announcement)
        announcement.refresh_from_db()
        return Response(AnnouncementSerializer(announcement).data)


class NotificationSerializer(serializers.ModelSerializer[Notification]):
    class Meta:
        model = Notification
        fields: ClassVar = ["id", "kind", "title", "body", "data", "read_at", "created_at"]


class NotificationViewSet(mixins.ListModelMixin, TenantViewSet):
    """The signed-in user's inbox in the current school."""

    serializer_class = NotificationSerializer
    pagination_class = DefaultCursorPagination
    required_permissions: ClassVar = {
        "list": Perm.COMMUNICATION_VIEW,
        "read": Perm.COMMUNICATION_VIEW,
        "read_all": Perm.COMMUNICATION_VIEW,
        "unread_count": Perm.COMMUNICATION_VIEW,
    }

    def get_queryset(self) -> QuerySet[Notification]:
        qs = Notification.objects.filter(recipient_user_id=self.request.user.pk)
        if self.request.query_params.get("unread") == "1":
            qs = qs.filter(read_at__isnull=True)
        return qs

    @action(detail=True, methods=["post"])
    def read(self, request: Request, pk: str | None = None) -> Response:
        self.get_queryset().filter(pk=pk, read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"])
    def read_all(self, request: Request) -> Response:
        self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def unread_count(self, request: Request) -> Response:
        return Response({"unread": self.get_queryset().filter(read_at__isnull=True).count()})


class DeliverySerializer(serializers.ModelSerializer[Delivery]):
    class Meta:
        model = Delivery
        fields: ClassVar = [
            "id",
            "channel",
            "to",
            "kind",
            "status",
            "provider",
            "error",
            "attempts",
            "created_at",
            "sent_at",
        ]


class DeliveryViewSet(mixins.ListModelMixin, TenantViewSet):
    serializer_class = DeliverySerializer
    pagination_class = DefaultCursorPagination
    required_permissions: ClassVar = {
        "list": Perm.COMMUNICATION_MANAGE,
        "usage": Perm.COMMUNICATION_MANAGE,
    }

    def get_queryset(self) -> QuerySet[Delivery]:
        qs = Delivery.objects.all()
        for param in ("channel", "status", "kind"):
            if value := self.request.query_params.get(param):
                qs = qs.filter(**{param: value})
        return qs

    @action(detail=False, methods=["get"])
    def usage(self, request: Request) -> Response:
        settings_row = services.messaging_settings()
        return Response(
            {
                "sms_sent_this_month": services.sms_sent_this_month(),
                "sms_monthly_limit": settings_row.sms_monthly_limit,
            }
        )
