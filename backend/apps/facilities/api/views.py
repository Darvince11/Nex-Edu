"""Facilities. Every member of staff can book a room and report something broken;
school leaders (or whoever holds ``facilities.manage``) keep the room list, can
cancel any booking, and follow repairs through to the end."""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from django.db.models import QuerySet
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.academics.api.views import AuditedCrudViewSet
from control_plane.models import Membership, User
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm, permissions_for_roles
from core.views import TenantViewSet

from ..models import Booking, Repair, Room

USE, MANAGE = Perm.FACILITIES_USE, Perm.FACILITIES_MANAGE


def _names(ids: set[Any]) -> dict[Any, str]:
    return {u.pk: u.get_full_name() or u.email for u in User.objects.filter(pk__in=ids)}


def _managers() -> set[Any]:
    from control_plane.models import Role

    rows = Membership.objects.filter(tenant=require_tenant(), is_active=True).exclude(
        role=Role.OWNER
    )
    return {m.user_id for m in rows if MANAGE in permissions_for_roles([m.role])}


class FacilityRoomSerializer(serializers.ModelSerializer[Room]):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Room
        fields: ClassVar = ["id", "name", "kind", "kind_label", "capacity", "bookable", "notes"]


class RoomViewSet(AuditedCrudViewSet):
    serializer_class = FacilityRoomSerializer
    audit_name = "room"
    queryset = Room.objects.all()
    required_permissions: ClassVar = {
        "list": (USE, MANAGE),
        "retrieve": (USE, MANAGE),
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
    }


class RoomBookingSerializer(serializers.ModelSerializer[Booking]):
    room_name = serializers.CharField(source="room.name", read_only=True)
    booked_by_name = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields: ClassVar = [
            "id",
            "room",
            "room_name",
            "date",
            "starts_at",
            "ends_at",
            "purpose",
            "booked_by_name",
            "mine",
        ]

    def get_booked_by_name(self, obj: Booking) -> str:
        return str(self.context.get("names", {}).get(obj.booked_by, ""))

    def get_mine(self, obj: Booking) -> bool:
        return bool(obj.booked_by == self.context["request"].user.pk)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        room, date = attrs["room"], attrs["date"]
        starts, ends = attrs["starts_at"], attrs["ends_at"]
        if not room.bookable:
            raise serializers.ValidationError({"room": "This room can't be booked."})
        if ends <= starts:
            raise serializers.ValidationError({"ends_at": "It must end after it starts."})
        if date < timezone.localdate():
            raise serializers.ValidationError({"date": "Choose a day that hasn't passed."})
        if date > timezone.localdate() + dt.timedelta(days=366):
            raise serializers.ValidationError({"date": "Book up to a year ahead."})
        clash = Booking.objects.filter(
            room=room, date=date, starts_at__lt=ends, ends_at__gt=starts
        ).first()
        if clash:
            raise serializers.ValidationError(
                {
                    "starts_at": f"{room.name} is booked {clash.starts_at:%H:%M} to "
                    f"{clash.ends_at:%H:%M} for {clash.purpose}."
                }
            )
        return attrs


class BookingViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, TenantViewSet
):
    """Room bookings. ``?date=`` (default today) or ``?room=&start=&end=``."""

    serializer_class = RoomBookingSerializer
    required_permissions: ClassVar = {
        "list": (USE, MANAGE),
        "create": (USE, MANAGE),
        "destroy": (USE, MANAGE),
    }

    def get_queryset(self) -> QuerySet[Booking]:
        qs = Booking.objects.select_related("room")
        params = self.request.query_params
        try:
            if params.get("start") or params.get("end"):
                start = dt.date.fromisoformat(
                    params.get("start") or timezone.localdate().isoformat()
                )
                end = dt.date.fromisoformat(
                    params.get("end") or (start + dt.timedelta(days=6)).isoformat()
                )
                qs = qs.filter(date__range=(start, end))
            elif self.action == "list":
                qs = qs.filter(
                    date=dt.date.fromisoformat(
                        params.get("date") or timezone.localdate().isoformat()
                    )
                )
        except ValueError as exc:
            raise ValidationError({"date": "Use YYYY-MM-DD."}) from exc
        if room := params.get("room"):
            qs = qs.filter(room_id=room)
        if params.get("mine") == "1":
            qs = qs.filter(booked_by=self.request.user.pk, date__gte=timezone.localdate())
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("date", OpenApiTypes.DATE),
            OpenApiParameter("start", OpenApiTypes.DATE),
            OpenApiParameter("end", OpenApiTypes.DATE),
            OpenApiParameter("room", OpenApiTypes.INT),
            OpenApiParameter("mine", OpenApiTypes.STR),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        rows = list(self.get_queryset()[:500])
        context = {"request": request, "names": _names({b.booked_by for b in rows})}
        return Response(RoomBookingSerializer(rows, many=True, context=context).data)

    def perform_create(self, serializer: Any) -> None:
        serializer.save(booked_by=self.request.user.pk)

    def perform_destroy(self, instance: Booking) -> None:
        _, _, perms = self.actor()
        if instance.booked_by != self.request.user.pk and MANAGE not in perms:
            raise PermissionDenied("Only the person who booked, or a school leader, can cancel.")
        with tenant_atomic():
            record_event(
                action="facilities.booking_cancelled",
                request=self.request,
                before={
                    "room": instance.room.name,
                    "date": str(instance.date),
                    "purpose": instance.purpose,
                },
            )
            instance.delete()


class FacilityRepairSerializer(serializers.ModelSerializer[Repair]):
    room_name = serializers.CharField(source="room.name", read_only=True, default="")
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    reported_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Repair
        fields: ClassVar = [
            "id",
            "room",
            "room_name",
            "where",
            "title",
            "details",
            "priority",
            "priority_label",
            "status",
            "status_label",
            "reported_by_name",
            "assigned_to",
            "cost_pesewas",
            "outcome",
            "created_at",
            "closed_at",
        ]
        read_only_fields: ClassVar = ["closed_at"]

    def get_reported_by_name(self, obj: Repair) -> str:
        return str(self.context.get("names", {}).get(obj.reported_by, ""))

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.instance is None and not attrs.get("room") and not attrs.get("where", "").strip():
            raise serializers.ValidationError({"where": "Say where it is."})
        return attrs


MANAGER_FIELDS = {"status", "assigned_to", "cost_pesewas", "outcome", "priority"}


class RepairViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, TenantViewSet
):
    """Repairs. Anyone on the staff reports; managers move them along. Reporters see
    their own reports; managers see all (``?status=``)."""

    serializer_class = FacilityRepairSerializer
    required_permissions: ClassVar = {
        "list": (USE, MANAGE),
        "create": (USE, MANAGE),
        "update": MANAGE,
        "partial_update": MANAGE,
    }

    def get_queryset(self) -> QuerySet[Repair]:
        user, _, perms = self.actor()
        qs = Repair.objects.select_related("room")
        if MANAGE not in perms:
            qs = qs.filter(reported_by=user.pk)
        state = self.request.query_params.get("status")
        if state == "open":
            qs = qs.filter(status__in=[Repair.Status.REPORTED, Repair.Status.IN_PROGRESS])
        elif state in Repair.Status.values:
            qs = qs.filter(status=state)
        return qs

    @extend_schema(parameters=[OpenApiParameter("status", OpenApiTypes.STR)])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        rows = list(self.get_queryset()[:300])
        context = {"names": _names({r.reported_by for r in rows})}
        return Response(FacilityRepairSerializer(rows, many=True, context=context).data)

    def perform_create(self, serializer: Any) -> None:
        from apps.communication.services import notify_users

        _, _, perms = self.actor()
        extra = {
            k: v for k, v in serializer.validated_data.items() if k in MANAGER_FIELDS - {"priority"}
        }
        if extra and MANAGE not in perms:
            raise PermissionDenied("Only facilities managers set these.")
        repair = serializer.save(reported_by=self.request.user.pk, status=Repair.Status.REPORTED)
        place = repair.room.name if repair.room_id else repair.where
        notify_users(
            _managers() - {self.request.user.pk},
            kind="facilities",
            title=(
                "Urgent repair: "
                if repair.priority == Repair.Priority.URGENT
                else "Repair reported: "
            )
            + repair.title,
            body=f"{repair.title} at {place}." + (f" {repair.details}" if repair.details else ""),
            data={"repair": str(repair.pk)},
        )

    def perform_update(self, serializer: Any) -> None:
        from apps.communication.services import notify_users

        repair = serializer.instance
        before = repair.status
        updated = serializer.save()
        closed = updated.status in (Repair.Status.DONE, Repair.Status.WONT_FIX)
        if closed and not updated.closed_at:
            updated.closed_at = timezone.now()
            updated.save(update_fields=["closed_at"])
        if not closed and updated.closed_at:
            updated.closed_at = None
            updated.save(update_fields=["closed_at"])
        if updated.status != before:
            with tenant_atomic():
                record_event(
                    action="facilities.repair_status",
                    request=self.request,
                    target=updated,
                    after={"status": updated.status, "cost_pesewas": updated.cost_pesewas},
                )
            if closed:
                notify_users(
                    [updated.reported_by],
                    kind="facilities",
                    title=f"Repair {updated.get_status_display().lower()}: {updated.title}",
                    body=updated.outcome or f"{updated.title}: {updated.get_status_display()}.",
                    data={"repair": str(updated.pk)},
                )
