from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import Q, QuerySet
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from apps.academics.selectors import teaches_arm
from apps.students.selectors import visible_students
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.pagination import DefaultCursorPagination
from core.rbac import Perm
from core.views import TenantViewSet

from .. import messaging, services
from ..models import Announcement, Channel, Conversation, Delivery, Message, Notification


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
        from control_plane.subscriptions import sms_allowance
        from control_plane.tenancy import require_tenant

        allowance = sms_allowance(require_tenant())
        return Response(
            {
                "sms_sent_this_month": services.sms_sent_this_month(),
                "sms_monthly_limit": allowance["monthly"],
                "sms_bought": allowance["bought"],
            }
        )


class ConversationSerializer(serializers.ModelSerializer[Conversation]):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    student_class = serializers.SerializerMethodField()
    staff = serializers.SerializerMethodField()
    parent = serializers.SerializerMethodField()
    unread = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields: ClassVar = [
            "id",
            "student",
            "student_name",
            "student_class",
            "subject",
            "staff",
            "parent",
            "created_at",
            "last_message_at",
            "unread",
            "mine",
        ]

    def _person(self, user_id: Any) -> dict[str, str]:
        return {"id": str(user_id), "name": self.context["names"].get(user_id, "")}

    def get_student_class(self, obj: Conversation) -> str:
        return str(obj.student.arm) if obj.student.arm_id else ""

    def get_staff(self, obj: Conversation) -> dict[str, str]:
        return self._person(obj.staff_user_id)

    def get_parent(self, obj: Conversation) -> dict[str, str]:
        return self._person(obj.parent_user_id)

    def get_unread(self, obj: Conversation) -> bool:
        return obj.unread_for(self.context["user"].pk)

    def get_mine(self, obj: Conversation) -> bool:
        return self.context["user"].pk in (obj.staff_user_id, obj.parent_user_id)


class MessageSerializer(serializers.ModelSerializer[Message]):
    sender_name = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields: ClassVar = ["id", "sender_user_id", "sender_name", "body", "created_at", "mine"]

    def get_sender_name(self, obj: Message) -> str:
        return str(self.context["names"].get(obj.sender_user_id, ""))

    def get_mine(self, obj: Message) -> bool:
        return bool(obj.sender_user_id == self.context["user"].pk)


class StartConversationSerializer(serializers.Serializer[dict[str, Any]]):
    student = serializers.UUIDField()
    to = serializers.UUIDField()
    subject = serializers.CharField(max_length=140)
    body = serializers.CharField(max_length=2000)


class ReplySerializer(serializers.Serializer[dict[str, Any]]):
    body = serializers.CharField(max_length=2000)


LIST_LIMIT = 300


class ConversationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantViewSet):
    """Messages between parents and staff. Each person sees their own conversations; the
    proprietor and head teacher can also read everyone's (``?all=1``)."""

    serializer_class = ConversationSerializer
    _read = (Perm.MESSAGES_USE, Perm.MESSAGES_OVERSEE)
    required_permissions: ClassVar = {
        "list": _read,
        "retrieve": _read,
        "create": Perm.MESSAGES_USE,
        "reply": Perm.MESSAGES_USE,
        "contacts": Perm.MESSAGES_USE,
        "unread_count": _read,
    }

    def get_queryset(self) -> QuerySet[Conversation]:
        user, _, perms = self.actor()
        qs = messaging.visible(user, perms)
        params = self.request.query_params
        if params.get("all") != "1":
            qs = qs.filter(Q(staff_user_id=user.pk) | Q(parent_user_id=user.pk))
        if student := params.get("student"):
            qs = qs.filter(student_id=student)
        return qs

    def _context(self, conversations: list[Conversation], extra: list[Any] = ()) -> dict[str, Any]:
        ids = {c.staff_user_id for c in conversations} | {c.parent_user_id for c in conversations}
        return {"user": self.request.user, "names": messaging.names(ids | set(extra))}

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        rows = list(self.get_queryset()[:LIST_LIMIT])
        return Response(ConversationSerializer(rows, many=True, context=self._context(rows)).data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user, _, perms = self.actor()
        conversation = messaging.visible(user, perms).filter(pk=kwargs["pk"]).first()
        if conversation is None:
            raise NotFound()
        messaging.mark_read(conversation, user)
        messages = list(conversation.messages.all())
        context = self._context([conversation], [m.sender_user_id for m in messages])
        return Response(
            {
                **ConversationSerializer(conversation, context=context).data,
                "messages": MessageSerializer(messages, many=True, context=context).data,
            }
        )

    @extend_schema(request=StartConversationSerializer, responses=ConversationSerializer)
    def create(self, request: Request) -> Response:
        data = StartConversationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        user, roles, perms = self.actor()
        student = visible_students(user, roles, perms).filter(pk=v["student"]).first()
        if student is None:
            raise NotFound("Pupil not found.")
        conversation = messaging.start(
            request=request,
            roles=roles,
            student=student,
            to=v["to"],
            subject=v["subject"],
            body=v["body"],
        )
        return Response(
            ConversationSerializer(conversation, context=self._context([conversation])).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=ReplySerializer, responses=MessageSerializer)
    @action(detail=True, methods=["post"])
    def reply(self, request: Request, pk: str | None = None) -> Response:
        user, _, perms = self.actor()
        conversation = messaging.visible(user, perms).filter(pk=pk).first()
        if conversation is None:
            raise NotFound()
        data = ReplySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        message = messaging.reply(
            request=request, conversation=conversation, body=data.validated_data["body"]
        )
        context = {"user": user, "names": messaging.names([user.pk])}
        return Response(
            MessageSerializer(message, context=context).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        parameters=[OpenApiParameter("student", OpenApiTypes.UUID, required=True)],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=["get"])
    def contacts(self, request: Request) -> Response:
        """Who the caller may write to about ?student=."""
        user, roles, perms = self.actor()
        student = (
            visible_students(user, roles, perms)
            .filter(pk=request.query_params.get("student"))
            .first()
            if request.query_params.get("student")
            else None
        )
        if student is None:
            raise NotFound("Pupil not found.")
        return Response(messaging.contacts(user, roles, student))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def unread_count(self, request: Request) -> Response:
        return Response({"unread": messaging.unread_count(request.user)})
