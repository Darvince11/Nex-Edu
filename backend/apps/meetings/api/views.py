from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from django.db.models import Count, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.academics.api.views import AuditedCrudViewSet
from apps.students.models import Student
from control_plane.models import Role
from core.rbac import STAFF_ROLES, Perm

from .. import services
from ..models import MeetingDay, Slot

VIEW, MANAGE = Perm.MEETINGS_VIEW, Perm.MEETINGS_MANAGE
SLOT_ID = OpenApiParameter("slot_id", OpenApiTypes.UUID, OpenApiParameter.PATH)


class MeetingDaySerializer(serializers.ModelSerializer[MeetingDay]):
    teacher_count = serializers.IntegerField(read_only=True, default=0)
    booked_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = MeetingDay
        fields: ClassVar = [
            "id",
            "title",
            "date",
            "starts_at",
            "ends_at",
            "slot_minutes",
            "location",
            "notes",
            "video_url",
            "is_open",
            "teacher_count",
            "booked_count",
        ]
        read_only_fields: ClassVar = ["is_open"]
        extra_kwargs: ClassVar = {"slot_minutes": {"min_value": 5, "max_value": 60}}

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        starts = attrs.get("starts_at", getattr(instance, "starts_at", None))
        ends = attrs.get("ends_at", getattr(instance, "ends_at", None))
        if starts and ends and ends <= starts:
            raise serializers.ValidationError({"ends_at": "It must end after it starts."})
        if (
            instance
            and instance.slots.exists()
            and {"starts_at", "ends_at", "slot_minutes", "date"}
            & {k for k, v in attrs.items() if getattr(instance, k) != v}
        ):
            raise serializers.ValidationError(
                {"detail": "Times can't change once teachers are added. Remove them first."}
            )
        if instance is None and attrs.get("date") and attrs["date"] < timezone.localdate():
            raise serializers.ValidationError({"date": "Choose a day that hasn't passed."})
        return attrs

    def create(self, validated_data: dict[str, Any]) -> MeetingDay:
        validated_data["created_by"] = self.context["request"].user.pk
        return super().create(validated_data)


class TeacherSerializer(serializers.Serializer):  # type: ignore[type-arg]
    user = serializers.UUIDField()
    room = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class BookingSerializer(serializers.Serializer):  # type: ignore[type-arg]
    student = serializers.UUIDField()
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class MeetingDayViewSet(AuditedCrudViewSet):
    """Parent meeting days. Leaders set them up; teachers see their own schedule;
    parents book times with their children's teachers."""

    serializer_class = MeetingDaySerializer
    audit_name = "meeting_day"
    required_permissions: ClassVar = {
        "list": VIEW,
        "retrieve": VIEW,
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
        "add_teacher": MANAGE,
        "remove_teacher": MANAGE,
        "open": MANAGE,
        "close": MANAGE,
        "book": VIEW,
        "cancel": VIEW,
    }

    def get_queryset(self) -> QuerySet[MeetingDay]:
        _, roles, perms = self.actor()
        qs = MeetingDay.objects.annotate(
            teacher_count=Count("teachers", distinct=True),
            booked_count=Count("slots", filter=Q(slots__student__isnull=False), distinct=True),
        )
        if MANAGE not in perms:
            qs = qs.filter(date__gte=timezone.localdate() - dt.timedelta(days=14))
            if not set(roles) & STAFF_ROLES:
                qs = qs.filter(is_open=True)
        return qs

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        day = self.get_object()
        user, roles, perms = self.actor()
        data = dict(MeetingDaySerializer(day).data)
        if MANAGE in perms:
            data["schedule"] = services.staff_view(day)
        elif set(roles) & STAFF_ROLES:
            data["schedule"] = services.staff_view(day, only=user.pk)
        if Role.PARENT in set(roles):
            data["children"] = services.parent_view(user, day)
        return Response(data)

    def perform_destroy(self, instance: MeetingDay) -> None:
        if (
            instance.slots.filter(student__isnull=False).exists()
            and instance.date >= timezone.localdate()
        ):
            raise ValidationError({"detail": "Parents have booked. Cancel their bookings first."})
        super().perform_destroy(instance)

    @extend_schema(request=TeacherSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def add_teacher(self, request: Request, pk: str | None = None) -> Response:
        day = self.get_object()
        data = TeacherSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.add_teacher(
            day=day, user_id=data.validated_data["user"], room=data.validated_data["room"]
        )
        return Response(services.staff_view(day), status=status.HTTP_201_CREATED)

    @extend_schema(request=TeacherSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def remove_teacher(self, request: Request, pk: str | None = None) -> Response:
        day = self.get_object()
        services.remove_teacher(request=request, day=day, user_id=request.data.get("user"))
        return Response(services.staff_view(day))

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def open(self, request: Request, pk: str | None = None) -> Response:
        return Response({"parents": services.open_bookings(request=request, day=self.get_object())})

    @extend_schema(request=None, responses=MeetingDaySerializer)
    @action(detail=True, methods=["post"])
    def close(self, request: Request, pk: str | None = None) -> Response:
        day = self.get_object()
        day.is_open = False
        day.save(update_fields=["is_open"])
        return Response(MeetingDaySerializer(day).data)

    def _slot(self, pk: str | None, slot_id: Any) -> Slot:
        day = self.get_object()
        return get_object_or_404(Slot.objects.select_related("day", "student"), pk=slot_id, day=day)

    @extend_schema(
        request=BookingSerializer,
        responses=OpenApiTypes.OBJECT,
        parameters=[SLOT_ID],
    )
    @action(detail=True, methods=["post"], url_path=r"slots/(?P<slot_id>[^/.]+)/book")
    def book(self, request: Request, pk: str | None = None, slot_id: str | None = None) -> Response:
        slot = self._slot(pk, slot_id)
        data = BookingSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        student = get_object_or_404(Student, pk=data.validated_data["student"])
        services.book(request=request, slot=slot, student=student, note=data.validated_data["note"])
        return Response(
            services.parent_view(request.user, slot.day), status=status.HTTP_201_CREATED
        )

    @extend_schema(request=None, responses={204: None}, parameters=[SLOT_ID])
    @action(detail=True, methods=["post"], url_path=r"slots/(?P<slot_id>[^/.]+)/cancel")
    def cancel(
        self, request: Request, pk: str | None = None, slot_id: str | None = None
    ) -> Response:
        slot = self._slot(pk, slot_id)
        _, _, perms = self.actor()
        services.cancel(request=request, slot=slot, manage=MANAGE in perms)
        return Response(status=status.HTTP_204_NO_CONTENT)
