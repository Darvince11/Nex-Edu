"""The gate. The gate officer (and leaders) sign visitors in and out and check who
collects each pupil against the list the family keeps. Collection by someone not on
the list needs a reason and is flagged; the family is told every time."""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.students.models import Student, StudentGuardian
from apps.students.selectors import visible_students
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.permissions import load_membership
from core.rbac import Perm
from core.views import TenantViewSet

from ..models import Collector, Pickup, Visit

GATE, FAMILY = Perm.GATE_RECORD, Perm.GATE_FAMILY


class GateVisitSerializer(serializers.ModelSerializer[Visit]):
    class Meta:
        model = Visit
        fields: ClassVar = [
            "id",
            "name",
            "phone",
            "organisation",
            "purpose",
            "to_see",
            "id_number",
            "badge",
            "arrived_at",
            "left_at",
        ]
        read_only_fields: ClassVar = ["arrived_at", "left_at"]


class VisitViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, TenantViewSet):
    """Visitors: ``?now=1`` for those still on site, ``?date=`` for a day."""

    serializer_class = GateVisitSerializer
    required_permissions: ClassVar = {"list": GATE, "create": GATE, "sign_out": GATE}

    def get_queryset(self) -> QuerySet[Visit]:
        qs = Visit.objects.all()
        params = self.request.query_params
        if params.get("now") == "1":
            return qs.filter(left_at__isnull=True)
        try:
            day = dt.date.fromisoformat(params.get("date") or timezone.localdate().isoformat())
        except ValueError as exc:
            raise ValidationError({"date": "Use YYYY-MM-DD."}) from exc
        qs = qs.filter(arrived_at__date=day)
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(name__icontains=q) | Q(organisation__icontains=q) | Q(to_see__icontains=q)
            )
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("now", OpenApiTypes.STR),
            OpenApiParameter("date", OpenApiTypes.DATE),
            OpenApiParameter("q", OpenApiTypes.STR),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(GateVisitSerializer(self.get_queryset()[:300], many=True).data)

    def perform_create(self, serializer: Any) -> None:
        serializer.save(arrived_at=timezone.now(), signed_in_by=self.request.user.pk)

    @extend_schema(request=None, responses=GateVisitSerializer)
    @action(detail=True, methods=["post"])
    def sign_out(self, request: Request, pk: str | None = None) -> Response:
        visit = get_object_or_404(Visit, pk=pk)
        if visit.left_at is None:
            visit.left_at = timezone.now()
            visit.save(update_fields=["left_at"])
        return Response(GateVisitSerializer(visit).data)


class CollectorSerializer(serializers.ModelSerializer[Collector]):
    class Meta:
        model = Collector
        fields: ClassVar = ["id", "student", "name", "relationship", "phone", "notes"]


def _is_family(request: Request, student: Student) -> bool:
    return StudentGuardian.objects.filter(
        student=student, guardian_user_id=request.user.pk
    ).exists()


def _gate(request: Request) -> bool:
    load_membership(request)
    return GATE in getattr(request, "permissions", frozenset())


class CollectorViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, TenantViewSet
):
    """Who may collect a pupil (``?student=``). Families keep their own children's
    lists; the gate and the office can see and change any."""

    serializer_class = CollectorSerializer
    required_permissions: ClassVar = {
        "list": (GATE, FAMILY),
        "create": (GATE, FAMILY),
        "destroy": (GATE, FAMILY),
    }

    def get_queryset(self) -> QuerySet[Collector]:
        user, roles, perms = self.actor()
        qs = Collector.objects.select_related("student")
        if GATE not in perms:
            qs = qs.filter(student__in=visible_students(user, roles, perms))
        if student := self.request.query_params.get("student"):
            qs = qs.filter(student_id=student)
        return qs

    @extend_schema(parameters=[OpenApiParameter("student", OpenApiTypes.UUID)])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer: Any) -> None:
        student = serializer.validated_data["student"]
        if not _gate(self.request) and not _is_family(self.request, student):
            raise PermissionDenied("You can only add people for your own children.")
        with tenant_atomic():
            collector = serializer.save(added_by=self.request.user.pk)
            record_event(
                action="gate.collector_added",
                request=self.request,
                target=student,
                after={"name": collector.name, "relationship": collector.relationship},
            )

    def perform_destroy(self, instance: Collector) -> None:
        if not _gate(self.request) and not _is_family(self.request, instance.student):
            raise PermissionDenied("You can only change your own children's list.")
        with tenant_atomic():
            record_event(
                action="gate.collector_removed",
                request=self.request,
                target=instance.student,
                before={"name": instance.name, "relationship": instance.relationship},
            )
            instance.delete()


class PickupSerializer(serializers.ModelSerializer[Pickup]):
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = Pickup
        fields: ClassVar = [
            "id",
            "student",
            "student_name",
            "collector",
            "collected_by_name",
            "authorised",
            "reason",
            "at",
        ]
        read_only_fields: ClassVar = ["authorised", "at"]
        extra_kwargs: ClassVar = {"collected_by_name": {"required": False, "allow_blank": True}}


class GateCheckView(APIView):
    """The gate looking up a pupil: their class, photo-free details and who may collect."""

    required_permissions: ClassVar = {"GET": GATE}

    @extend_schema(
        parameters=[OpenApiParameter("q", OpenApiTypes.STR)], responses=OpenApiTypes.OBJECT
    )
    def get(self, request: Request) -> Response:
        q = request.query_params.get("q", "").strip()
        if len(q) < 2:
            return Response([])
        pupils = (
            Student.objects.filter(status=Student.Status.ACTIVE)
            .filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(admission_number__icontains=q)
            )
            .select_related("arm__level")
            .prefetch_related("collectors")[:10]
        )
        today = timezone.localdate()
        gone = set(
            Pickup.objects.filter(student__in=pupils, at__date=today).values_list(
                "student_id", flat=True
            )
        )
        return Response(
            [
                {
                    "student": str(p.pk),
                    "name": p.full_name,
                    "class": str(p.arm) if p.arm_id else "",
                    "admission_number": p.admission_number,
                    "collected_today": p.pk in gone,
                    "collectors": CollectorSerializer(p.collectors.all(), many=True).data,
                }
                for p in pupils
            ]
        )


class PickupViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, TenantViewSet):
    """Who collected whom. The gate records; families see their own children's."""

    serializer_class = PickupSerializer
    required_permissions: ClassVar = {"list": (GATE, FAMILY), "create": GATE}

    def get_queryset(self) -> QuerySet[Pickup]:
        user, roles, perms = self.actor()
        qs = Pickup.objects.select_related("student")
        if GATE not in perms:
            return qs.filter(student__in=visible_students(user, roles, perms))[:100]
        try:
            day = dt.date.fromisoformat(
                self.request.query_params.get("date") or timezone.localdate().isoformat()
            )
        except ValueError as exc:
            raise ValidationError({"date": "Use YYYY-MM-DD."}) from exc
        return qs.filter(at__date=day)

    @extend_schema(parameters=[OpenApiParameter("date", OpenApiTypes.DATE)])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(PickupSerializer(self.get_queryset(), many=True).data)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from apps.communication.services import notify_guardians

        data = PickupSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        student = v["student"]
        collector = v.get("collector")
        if collector is not None and collector.student_id != student.pk:
            raise ValidationError({"collector": "This person isn't on this pupil's list."})
        authorised = collector is not None
        name = collector.name if collector else v.get("collected_by_name", "").strip()
        if not name:
            raise ValidationError({"collected_by_name": "Who is collecting?"})
        if not authorised and not v.get("reason", "").strip():
            raise ValidationError(
                {"reason": "They aren't on the list. Say why they may take the pupil."}
            )
        with tenant_atomic():
            pickup = Pickup.objects.create(
                student=student,
                collector=collector,
                collected_by_name=name,
                authorised=authorised,
                reason=v.get("reason", ""),
                recorded_by=request.user.pk,
            )
            record_event(
                action="gate.pickup" if authorised else "gate.pickup_unlisted",
                request=request,
                target=student,
                after={"by": name, "authorised": authorised, "reason": pickup.reason},
            )
        who = (
            f"{name} ({collector.relationship})"
            if collector
            else f"{name}, who is not on your list"
        )
        notify_guardians(
            [student],
            kind="pickup",
            title=f"{student.first_name} was collected from school",
            body=(
                f"{student.first_name} was collected by {who} at "
                f"{timezone.localtime(pickup.at):%H:%M}."
                + ("" if authorised else f" Reason given: {pickup.reason}")
            ),
            data={"student_id": str(student.pk)},
        )
        return Response(PickupSerializer(pickup).data, status=status.HTTP_201_CREATED)
