"""School transport. School leaders set up vehicles, routes, stops and riders; a
vehicle's driver keeps the pick-up list for its routes; parents see their child's
route and today's trips, and get a note in their inbox when their child gets on
in the morning, isn't at the stop, or is dropped off in the afternoon."""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from django.db import transaction
from django.db.models import Count, Prefetch, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.api.views import AuditedCrudViewSet
from apps.students.models import Student
from apps.students.selectors import visible_students
from control_plane.models import Membership, Role, User
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm
from core.views import TenantViewSet

from ..models import Rider, Route, Stop, TripMark, Vehicle

VIEW, RECORD, MANAGE = Perm.TRANSPORT_VIEW, Perm.TRANSPORT_RECORD, Perm.TRANSPORT_MANAGE


def _names(ids: set[Any]) -> dict[Any, str]:
    return {u.pk: u.get_full_name() or u.email for u in User.objects.filter(pk__in=ids)}


class VehicleSerializer(serializers.ModelSerializer[Vehicle]):
    driver_name = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields: ClassVar = [
            "id",
            "name",
            "registration",
            "seats",
            "driver_user_id",
            "driver_name",
            "attendant",
            "attendant_phone",
            "is_active",
        ]
        extra_kwargs: ClassVar = {"seats": {"min_value": 1, "max_value": 120}}

    def get_driver_name(self, obj: Vehicle) -> str:
        if not obj.driver_user_id:
            return ""
        return str(self.context.get("names", {}).get(obj.driver_user_id, ""))

    def validate_driver_user_id(self, value: Any) -> Any:
        if (
            value
            and not Membership.objects.filter(
                tenant=require_tenant(), user_id=value, role=Role.DRIVER, is_active=True
            ).exists()
        ):
            raise serializers.ValidationError("Choose someone with the Driver role.")
        return value


class VehicleViewSet(AuditedCrudViewSet):
    serializer_class = VehicleSerializer
    audit_name = "vehicle"
    queryset = Vehicle.objects.all()
    required_permissions: ClassVar = {
        "list": MANAGE,
        "retrieve": MANAGE,
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
    }

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        ids = set(
            Vehicle.objects.exclude(driver_user_id=None).values_list("driver_user_id", flat=True)
        )
        context["names"] = _names(ids)
        return context


class StopSerializer(serializers.ModelSerializer[Stop]):
    id = serializers.IntegerField(required=False)
    rider_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Stop
        fields: ClassVar = ["id", "name", "order", "pickup_at", "drop_at", "rider_count"]


class RouteSerializer(serializers.ModelSerializer[Route]):
    stops = StopSerializer(many=True, required=False)
    vehicle_name = serializers.CharField(source="vehicle.name", read_only=True, default="")
    seats = serializers.IntegerField(source="vehicle.seats", read_only=True, default=None)
    rider_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Route
        fields: ClassVar = [
            "id",
            "name",
            "vehicle",
            "vehicle_name",
            "seats",
            "is_active",
            "rider_count",
            "stops",
        ]

    def _save_stops(self, route: Route, stops: list[dict[str, Any]] | None) -> None:
        """Replace the route's stops with the given list, keeping those that pupils use."""
        if stops is None:
            return
        keep = {s["id"] for s in stops if s.get("id")}
        in_use = set(
            Rider.objects.filter(route=route, ended_on__isnull=True).values_list(
                "stop_id", flat=True
            )
        )
        dropped = set(route.stops.values_list("pk", flat=True)) - keep
        if dropped & in_use:
            raise serializers.ValidationError(
                {"stops": "Move the pupils at a stop to another stop before removing it."}
            )
        route.stops.filter(pk__in=dropped).delete()
        for order, s in enumerate(stops):
            fields = {
                "name": s["name"],
                "order": order,
                "pickup_at": s.get("pickup_at"),
                "drop_at": s.get("drop_at"),
            }
            if s.get("id"):
                route.stops.filter(pk=s["id"]).update(**fields)
            else:
                Stop.objects.create(route=route, **fields)

    def create(self, validated_data: dict[str, Any]) -> Route:
        stops = validated_data.pop("stops", None)
        route = super().create(validated_data)
        self._save_stops(route, stops)
        return route

    def update(self, instance: Route, validated_data: dict[str, Any]) -> Route:
        stops = validated_data.pop("stops", None)
        route = super().update(instance, validated_data)
        self._save_stops(route, stops)
        return route


def _can_mark(view: TenantViewSet, route: Route) -> bool:
    user, _, perms = view.actor()
    if MANAGE in perms:
        return True
    return RECORD in perms and bool(route.vehicle_id) and route.vehicle.driver_user_id == user.pk


class MarkSerializer(serializers.Serializer):  # type: ignore[type-arg]
    student = serializers.UUIDField()
    direction = serializers.ChoiceField(choices=TripMark.Direction.choices)
    status = serializers.ChoiceField(choices=TripMark.Status.choices)


class RiderSerializer(serializers.Serializer):  # type: ignore[type-arg]
    student = serializers.UUIDField()
    stop = serializers.IntegerField()
    direction = serializers.ChoiceField(
        choices=Rider.Direction.choices, default=Rider.Direction.BOTH
    )


def _tell_parents(mark: TripMark, stop: Stop | None) -> None:
    from apps.communication.services import notify_guardians

    pupil = mark.student
    at = timezone.localtime(mark.marked_at)
    if mark.direction == TripMark.Direction.MORNING and mark.status == TripMark.Status.BOARDED:
        body = f"{pupil.first_name} got on the school bus at {at:%H:%M}."
    elif mark.direction == TripMark.Direction.MORNING and mark.status == TripMark.Status.ABSENT:
        body = f"{pupil.first_name} wasn't at the bus stop this morning."
    elif mark.direction == TripMark.Direction.AFTERNOON and mark.status == TripMark.Status.DROPPED:
        place = f" at {stop.name}" if stop else ""
        body = f"{pupil.first_name} was dropped off{place} at {at:%H:%M}."
    else:
        return
    notify_guardians(
        [pupil],
        kind="transport",
        title="School bus",
        body=body,
        data={"student_id": str(pupil.pk), "route": str(mark.route_id)},
    )


class RouteViewSet(AuditedCrudViewSet):
    """Routes with their stops. Leaders see all; a driver sees their vehicle's routes;
    parents see only their children's (via ``/transport/mine``)."""

    serializer_class = RouteSerializer
    audit_name = "route"
    required_permissions: ClassVar = {
        "list": (RECORD, MANAGE),
        "retrieve": (RECORD, MANAGE),
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
        "roll": (RECORD, MANAGE),
        "mark": (RECORD, MANAGE),
        "add_rider": MANAGE,
        "remove_rider": MANAGE,
    }

    def get_queryset(self) -> QuerySet[Route]:
        user, _, perms = self.actor()
        stops = Stop.objects.annotate(
            rider_count=Count("riders", filter=Q(riders__ended_on__isnull=True))
        )
        qs = (
            Route.objects.select_related("vehicle")
            .prefetch_related(Prefetch("stops", queryset=stops))
            .annotate(
                rider_count=Count("riders", filter=Q(riders__ended_on__isnull=True), distinct=True)
            )
        )
        if MANAGE not in perms:
            qs = qs.filter(vehicle__driver_user_id=user.pk, is_active=True)
        return qs

    def perform_destroy(self, instance: Route) -> None:
        if instance.riders.filter(ended_on__isnull=True).exists():
            raise ValidationError({"detail": "Move the pupils on this route first."})
        super().perform_destroy(instance)

    @extend_schema(
        parameters=[
            OpenApiParameter("direction", OpenApiTypes.STR, enum=["morning", "afternoon"]),
            OpenApiParameter("date", OpenApiTypes.DATE),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=True, methods=["get"])
    def roll(self, request: Request, pk: str | None = None) -> Response:
        """The pick-up list for one trip, in stop order, with each pupil's mark."""
        route = self.get_object()
        if not _can_mark(self, route):
            raise PermissionDenied("Only this route's driver and school leaders keep its list.")
        direction = request.query_params.get("direction") or (
            "morning" if timezone.localtime().hour < 12 else "afternoon"
        )
        try:
            day = dt.date.fromisoformat(
                request.query_params.get("date") or timezone.localdate().isoformat()
            )
        except ValueError as exc:
            raise ValidationError({"date": "Use YYYY-MM-DD."}) from exc
        riders = (
            route.riders.filter(ended_on__isnull=True)
            .exclude(
                direction=Rider.Direction.AFTERNOON
                if direction == "morning"
                else Rider.Direction.MORNING
            )
            .select_related("student__arm__level", "stop")
            .order_by("stop__order", "student__last_name")
        )
        marks = dict(
            TripMark.objects.filter(route=route, date=day, direction=direction).values_list(
                "student_id", "status"
            )
        )
        return Response(
            {
                "route": route.name,
                "date": day,
                "direction": direction,
                "riders": [
                    {
                        "student": str(r.student_id),
                        "name": r.student.full_name,
                        "class": str(r.student.arm) if r.student.arm_id else "",
                        "stop": r.stop.name,
                        "time": r.stop.pickup_at if direction == "morning" else r.stop.drop_at,
                        "status": marks.get(r.student_id, ""),
                    }
                    for r in riders
                ],
            }
        )

    @extend_schema(request=MarkSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def mark(self, request: Request, pk: str | None = None) -> Response:
        route = self.get_object()
        if not _can_mark(self, route):
            raise PermissionDenied("Only this route's driver and school leaders keep its list.")
        data = MarkSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        rider = (
            route.riders.filter(student_id=v["student"], ended_on__isnull=True)
            .select_related("student", "stop")
            .first()
        )
        if rider is None:
            raise ValidationError({"student": "This pupil doesn't ride this route."})
        today = timezone.localdate()
        previous = TripMark.objects.filter(
            student=rider.student, date=today, direction=v["direction"]
        ).first()
        with tenant_atomic():
            mark, _ = TripMark.objects.update_or_create(
                student=rider.student,
                date=today,
                direction=v["direction"],
                defaults={"route": route, "status": v["status"], "marked_by": request.user.pk},
            )
        if previous is None or previous.status != mark.status:
            _tell_parents(mark, rider.stop)
        return Response({"student": str(rider.student_id), "status": mark.status})

    @extend_schema(request=RiderSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def add_rider(self, request: Request, pk: str | None = None) -> Response:
        route = self.get_object()
        data = RiderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        student = get_object_or_404(Student, pk=v["student"], status=Student.Status.ACTIVE)
        stop = get_object_or_404(Stop, pk=v["stop"], route=route)
        current = route.riders.filter(ended_on__isnull=True).count()
        if route.vehicle_id and current >= route.vehicle.seats:
            raise ValidationError(
                {"student": f"{route.vehicle.name} is full ({route.vehicle.seats} seats)."}
            )
        with transaction.atomic(using=require_tenant().db_alias):
            # Moving routes ends the old ride.
            Rider.objects.filter(student=student, ended_on__isnull=True).update(
                ended_on=timezone.localdate()
            )
            Rider.objects.create(student=student, route=route, stop=stop, direction=v["direction"])
            record_event(
                action="transport.rider_added",
                request=request,
                target=route,
                after={"student": student.full_name, "stop": stop.name},
            )
        return Response({"riders": current + 1}, status=status.HTTP_201_CREATED)

    @extend_schema(request=RiderSerializer, responses={204: None})
    @action(detail=True, methods=["post"])
    def remove_rider(self, request: Request, pk: str | None = None) -> Response:
        route = self.get_object()
        ended = route.riders.filter(
            student_id=request.data.get("student"), ended_on__isnull=True
        ).update(ended_on=timezone.localdate())
        if not ended:
            raise ValidationError({"student": "They don't ride this route."})
        with tenant_atomic():
            record_event(
                action="transport.rider_removed",
                request=request,
                target=route,
                after={"student": str(request.data.get("student"))},
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RiderListView(APIView):
    """Leaders: every pupil on the buses, by route (``?route=``)."""

    required_permissions: ClassVar = {"GET": MANAGE}

    @extend_schema(
        parameters=[OpenApiParameter("route", OpenApiTypes.UUID)], responses=OpenApiTypes.OBJECT
    )
    def get(self, request: Request) -> Response:
        riders = Rider.objects.filter(ended_on__isnull=True).select_related(
            "student__arm__level", "stop", "route"
        )
        if route := request.query_params.get("route"):
            riders = riders.filter(route_id=route)
        return Response(
            [
                {
                    "student": str(r.student_id),
                    "name": r.student.full_name,
                    "class": str(r.student.arm) if r.student.arm_id else "",
                    "route": str(r.route_id),
                    "route_name": r.route.name,
                    "stop": r.stop.name,
                    "direction": r.get_direction_display(),
                    "since": r.since,
                }
                for r in riders.order_by("route__name", "stop__order", "student__last_name")
            ]
        )


class MyTransportView(APIView):
    """Parents (and pupils): each child's route, stop, times and today's trips."""

    required_permissions: ClassVar = {"GET": VIEW}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        from core.permissions import load_membership

        roles = load_membership(request)
        perms = getattr(request, "permissions", frozenset())
        pupils = visible_students(request.user, roles, perms)
        if MANAGE in perms or RECORD in perms:
            return Response([])  # staff use the route pages
        today = timezone.localdate()
        riders = Rider.objects.filter(ended_on__isnull=True, student__in=pupils).select_related(
            "student", "route__vehicle", "stop"
        )
        marks: dict[Any, dict[str, str]] = {}
        for m in TripMark.objects.filter(date=today, student__in=pupils):
            marks.setdefault(m.student_id, {})[m.direction] = m.get_status_display()
        drivers = _names({r.route.vehicle.driver_user_id for r in riders if r.route.vehicle_id})
        return Response(
            [
                {
                    "student": str(r.student_id),
                    "name": r.student.first_name,
                    "route": r.route.name,
                    "vehicle": r.route.vehicle.name if r.route.vehicle_id else "",
                    "registration": r.route.vehicle.registration if r.route.vehicle_id else "",
                    "driver": drivers.get(r.route.vehicle.driver_user_id, "")
                    if r.route.vehicle_id
                    else "",
                    "attendant": r.route.vehicle.attendant if r.route.vehicle_id else "",
                    "attendant_phone": r.route.vehicle.attendant_phone
                    if r.route.vehicle_id
                    else "",
                    "stop": r.stop.name,
                    "pickup_at": r.stop.pickup_at,
                    "drop_at": r.stop.drop_at,
                    "direction": r.get_direction_display(),
                    "today": marks.get(r.student_id, {}),
                }
                for r in riders
            ]
        )


class DriverOptionsView(APIView):
    """Leaders: people with the Driver role, to put on a vehicle."""

    required_permissions: ClassVar = {"GET": MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        ids = set(
            Membership.objects.filter(
                tenant=require_tenant(), role=Role.DRIVER, is_active=True
            ).values_list("user_id", flat=True)
        )
        names = _names(ids)
        return Response(
            sorted(({"id": str(i), "name": n} for i, n in names.items()), key=lambda d: d["name"])
        )
