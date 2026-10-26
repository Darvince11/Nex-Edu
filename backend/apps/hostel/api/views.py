"""Boarding. Who does what:

- School leaders (``hostel.manage``) set up houses and rooms and choose wardens.
- A house's warden (``hostel.record``) gives beds, takes roll call, and approves
  exeats for their own house; leaders can do this for any house.
- Parents (``hostel.view``) see their child's house and room, roll calls and
  exeats, and ask for an exeat; they're told when it's decided and when the
  child is back.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from django.db import transaction
from django.db.models import Count, Q, QuerySet
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

from apps.academics.api.views import AuditedCrudViewSet
from apps.students.models import Student, StudentGuardian
from apps.students.selectors import visible_students
from control_plane.models import Membership, User
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.permissions import load_membership
from core.rbac import STAFF_ROLES, Perm, permissions_for_roles
from core.views import TenantViewSet

from ..models import Boarder, Exeat, House, RollCall, Room

VIEW, RECORD, MANAGE = Perm.HOSTEL_VIEW, Perm.HOSTEL_RECORD, Perm.HOSTEL_MANAGE


def _perms(request: Request) -> frozenset[str]:
    load_membership(request)
    return getattr(request, "permissions", frozenset())


def _names(ids: set[Any]) -> dict[Any, str]:
    return {u.pk: u.get_full_name() or u.email for u in User.objects.filter(pk__in=ids)}


def my_houses(request: Request) -> QuerySet[House]:
    """Houses this person runs: all for leaders, their own for a warden."""
    perms = _perms(request)
    if MANAGE in perms:
        return House.objects.all()
    if RECORD in perms:
        return House.objects.filter(warden_user_id=request.user.pk)
    return House.objects.none()


def _house_of(student: Student) -> House | None:
    bed = (
        Boarder.objects.filter(student=student, left_on__isnull=True)
        .select_related("room__house")
        .first()
    )
    return bed.room.house if bed else None


def _require_house(request: Request, house: House | None) -> None:
    if house is None or not my_houses(request).filter(pk=house.pk).exists():
        raise PermissionDenied("Only this house's warden or a school leader can do this.")


class HouseSerializer(serializers.ModelSerializer[House]):
    gender_label = serializers.CharField(source="get_gender_display", read_only=True)
    warden_name = serializers.SerializerMethodField()
    beds = serializers.IntegerField(read_only=True, default=0)
    boarders = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = House
        fields: ClassVar = [
            "id",
            "name",
            "gender",
            "gender_label",
            "warden_user_id",
            "warden_name",
            "beds",
            "boarders",
        ]

    def get_warden_name(self, obj: House) -> str:
        return (
            str(self.context.get("names", {}).get(obj.warden_user_id, ""))
            if obj.warden_user_id
            else ""
        )

    def validate_warden_user_id(self, value: Any) -> Any:
        if (
            value
            and not Membership.objects.filter(
                tenant=require_tenant(), user_id=value, is_active=True, role__in=STAFF_ROLES
            ).exists()
        ):
            raise serializers.ValidationError("Choose a member of staff.")
        return value


class HouseViewSet(AuditedCrudViewSet):
    serializer_class = HouseSerializer
    audit_name = "house"
    required_permissions: ClassVar = {
        "list": (RECORD, MANAGE),
        "retrieve": (RECORD, MANAGE),
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
    }

    def get_queryset(self) -> QuerySet[House]:
        from django.db.models import Sum

        return my_houses(self.request).annotate(
            beds=Sum("rooms__beds", distinct=True),
            boarders=Count(
                "rooms__boarders", filter=Q(rooms__boarders__left_on__isnull=True), distinct=True
            ),
        )

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        context["names"] = _names(
            set(House.objects.exclude(warden_user_id=None).values_list("warden_user_id", flat=True))
        )
        return context


class HostelRoomSerializer(serializers.ModelSerializer[Room]):
    occupied = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Room
        fields: ClassVar = ["id", "house", "name", "beds", "occupied"]
        extra_kwargs: ClassVar = {"beds": {"min_value": 1, "max_value": 100}}


class HostelRoomViewSet(AuditedCrudViewSet):
    serializer_class = HostelRoomSerializer
    audit_name = "hostel_room"
    required_permissions: ClassVar = {
        "list": (RECORD, MANAGE),
        "retrieve": (RECORD, MANAGE),
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
    }

    def get_queryset(self) -> QuerySet[Room]:
        qs = Room.objects.filter(house__in=my_houses(self.request)).annotate(
            occupied=Count("boarders", filter=Q(boarders__left_on__isnull=True))
        )
        if house := self.request.query_params.get("house"):
            qs = qs.filter(house_id=house)
        return qs

    def perform_destroy(self, instance: Room) -> None:
        if instance.boarders.exists():
            raise ValidationError(
                {"detail": "Pupils have slept here. Keep the room for the records."}
            )
        super().perform_destroy(instance)


class BoarderSerializer(serializers.Serializer):  # type: ignore[type-arg]
    student = serializers.UUIDField()
    room = serializers.IntegerField()


class BoardersView(APIView):
    """GET ?house=: who sleeps where. POST {student, room}: give a bed (moving rooms
    ends the old one). DELETE ?student=: no longer boarding."""

    required_permissions: ClassVar = {
        "GET": (RECORD, MANAGE),
        "POST": (RECORD, MANAGE),
        "DELETE": (RECORD, MANAGE),
    }

    @extend_schema(
        parameters=[OpenApiParameter("house", OpenApiTypes.INT)], responses=OpenApiTypes.OBJECT
    )
    def get(self, request: Request) -> Response:
        beds = Boarder.objects.filter(
            left_on__isnull=True, room__house__in=my_houses(request)
        ).select_related("student__arm__level", "room__house")
        if house := request.query_params.get("house"):
            beds = beds.filter(room__house_id=house)
        return Response(
            [
                {
                    "student": str(b.student_id),
                    "name": b.student.full_name,
                    "class": str(b.student.arm) if b.student.arm_id else "",
                    "house": b.room.house_id,
                    "room": b.room_id,
                    "room_name": b.room.name,
                    "since": b.since,
                }
                for b in beds.order_by("room__name", "student__last_name")
            ]
        )

    @extend_schema(request=BoarderSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = BoarderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        room = get_object_or_404(
            Room.objects.select_related("house"), pk=data.validated_data["room"]
        )
        _require_house(request, room.house)
        student = get_object_or_404(
            Student, pk=data.validated_data["student"], status=Student.Status.ACTIVE
        )
        if room.boarders.filter(left_on__isnull=True).exclude(student=student).count() >= room.beds:
            raise ValidationError({"room": f"{room} is full ({room.beds} beds)."})
        with transaction.atomic(using=require_tenant().db_alias):
            Boarder.objects.filter(student=student, left_on__isnull=True).update(
                left_on=timezone.localdate()
            )
            Boarder.objects.create(student=student, room=room)
            record_event(
                action="hostel.bed",
                request=request,
                target=student,
                after={"house": room.house.name, "room": room.name},
            )
        return Response(
            {"student": str(student.pk), "room": room.pk}, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        parameters=[OpenApiParameter("student", OpenApiTypes.UUID)], responses={204: None}
    )
    def delete(self, request: Request) -> Response:
        student = get_object_or_404(Student, pk=request.query_params.get("student"))
        _require_house(request, _house_of(student))
        Boarder.objects.filter(student=student, left_on__isnull=True).update(
            left_on=timezone.localdate()
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


def _on_exeat(student_ids: list[Any], day: dt.date) -> set[Any]:
    return set(
        Exeat.objects.filter(
            student_id__in=student_ids,
            status__in=[Exeat.Status.APPROVED, Exeat.Status.OUT],
            leaves_on__lte=day,
            returns_on__gte=day,
        ).values_list("student_id", flat=True)
    )


class RollCallMarkSerializer(serializers.Serializer):  # type: ignore[type-arg]
    student = serializers.UUIDField()
    status = serializers.ChoiceField(choices=RollCall.Status.choices)


class RollCallSaveSerializer(serializers.Serializer):  # type: ignore[type-arg]
    house = serializers.IntegerField()
    date = serializers.DateField()
    session = serializers.ChoiceField(choices=RollCall.Session.choices)
    marks = RollCallMarkSerializer(many=True)


class RollCallView(APIView):
    """GET ?house=&date=&session=: the list, with anyone on an approved exeat marked
    so. POST: save it; school leaders are told who is missing."""

    required_permissions: ClassVar = {"GET": (RECORD, MANAGE), "POST": (RECORD, MANAGE)}

    @extend_schema(
        parameters=[
            OpenApiParameter("house", OpenApiTypes.INT, required=True),
            OpenApiParameter("date", OpenApiTypes.DATE),
            OpenApiParameter("session", OpenApiTypes.STR, enum=["morning", "evening"]),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request) -> Response:
        house = get_object_or_404(House, pk=request.query_params.get("house"))
        _require_house(request, house)
        try:
            day = dt.date.fromisoformat(
                request.query_params.get("date") or timezone.localdate().isoformat()
            )
        except ValueError as exc:
            raise ValidationError({"date": "Use YYYY-MM-DD."}) from exc
        session = request.query_params.get("session") or (
            "morning" if timezone.localtime().hour < 12 else "evening"
        )
        beds = list(
            Boarder.objects.filter(room__house=house, left_on__isnull=True)
            .select_related("student", "room")
            .order_by("room__name", "student__last_name")
        )
        ids = [b.student_id for b in beds]
        marks = dict(
            RollCall.objects.filter(student_id__in=ids, date=day, session=session).values_list(
                "student_id", "status"
            )
        )
        away = _on_exeat(ids, day)
        return Response(
            {
                "house": house.pk,
                "house_name": house.name,
                "date": day,
                "session": session,
                "taken": bool(marks),
                "rows": [
                    {
                        "student": str(b.student_id),
                        "name": b.student.full_name,
                        "room": b.room.name,
                        "status": marks.get(b.student_id)
                        or ("exeat" if b.student_id in away else ""),
                        "on_exeat": b.student_id in away,
                    }
                    for b in beds
                ],
            }
        )

    @extend_schema(request=RollCallSaveSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        from apps.communication.services import notify_users

        data = RollCallSaveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        house = get_object_or_404(House, pk=v["house"])
        _require_house(request, house)
        if v["date"] > timezone.localdate():
            raise ValidationError({"date": "Roll call can't be for a day that hasn't come."})
        boarders = set(
            Boarder.objects.filter(room__house=house, left_on__isnull=True).values_list(
                "student_id", flat=True
            )
        )
        missing = []
        with tenant_atomic():
            for mark in v["marks"]:
                if mark["student"] not in boarders:
                    raise ValidationError(
                        {"marks": "Someone on the list doesn't board in this house."}
                    )
                RollCall.objects.update_or_create(
                    student_id=mark["student"],
                    date=v["date"],
                    session=v["session"],
                    defaults={
                        "house": house,
                        "status": mark["status"],
                        "marked_by": request.user.pk,
                    },
                )
                if mark["status"] == RollCall.Status.ABSENT:
                    missing.append(mark["student"])
        if missing:
            names = ", ".join(
                Student.objects.filter(pk__in=missing).values_list("first_name", flat=True)
            )
            leaders = {
                m.user_id
                for m in Membership.objects.filter(tenant=require_tenant(), is_active=True)
                if MANAGE in permissions_for_roles([m.role])
            }
            notify_users(
                leaders - {request.user.pk},
                kind="hostel",
                title=f"Missing at {v['session']} roll call: {house.name}",
                body=f"Not present: {names}.",
                data={"house": house.pk, "date": v["date"].isoformat()},
            )
        return Response({"saved": len(v["marks"]), "absent": len(missing)})


class ExeatSerializer(serializers.ModelSerializer[Exeat]):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Exeat
        fields: ClassVar = [
            "id",
            "student",
            "student_name",
            "leaves_on",
            "returns_on",
            "reason",
            "collected_by",
            "status",
            "status_label",
            "decision_note",
            "left_at",
            "returned_at",
            "created_at",
        ]
        read_only_fields: ClassVar = ["status", "decision_note", "left_at", "returned_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["returns_on"] < attrs["leaves_on"]:
            raise serializers.ValidationError(
                {"returns_on": "They must come back after they leave."}
            )
        if attrs["leaves_on"] < timezone.localdate():
            raise serializers.ValidationError({"leaves_on": "Choose a day that hasn't passed."})
        return attrs


class DecisionNoteSerializer(serializers.Serializer):  # type: ignore[type-arg]
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


def _tell_family(exeat: Exeat, title: str, body: str) -> None:
    from apps.communication.services import notify_guardians

    notify_guardians(
        [exeat.student], kind="exeat", title=title, body=body, data={"exeat": str(exeat.pk)}
    )


class ExeatViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, TenantViewSet):
    serializer_class = ExeatSerializer
    required_permissions: ClassVar = {
        "list": (VIEW, RECORD, MANAGE),
        "create": (VIEW, RECORD, MANAGE),
        "approve": (RECORD, MANAGE),
        "decline": (RECORD, MANAGE),
        "depart": (RECORD, MANAGE),
        "back": (RECORD, MANAGE),
    }

    def get_queryset(self) -> QuerySet[Exeat]:
        user, roles, perms = self.actor()
        qs = Exeat.objects.select_related("student")
        if perms & {RECORD, MANAGE}:
            houses = my_houses(self.request)
            qs = qs.filter(
                student__boarding__room__house__in=houses, student__boarding__left_on__isnull=True
            ).distinct()
        else:
            qs = qs.filter(student__in=visible_students(user, roles, perms))
        if (state := self.request.query_params.get("status")) in Exeat.Status.values:
            qs = qs.filter(status=state)
        return qs

    @extend_schema(parameters=[OpenApiParameter("status", OpenApiTypes.STR)])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(ExeatSerializer(self.get_queryset()[:300], many=True).data)

    def perform_create(self, serializer: Any) -> None:
        from apps.communication.services import notify_users

        user, _, perms = self.actor()
        student = serializer.validated_data["student"]
        house = _house_of(student)
        if house is None:
            raise ValidationError({"student": "This pupil doesn't board."})
        if (
            not perms & {RECORD, MANAGE}
            and not StudentGuardian.objects.filter(
                student=student, guardian_user_id=user.pk
            ).exists()
        ):
            raise PermissionDenied("You can ask only for your own children.")
        if perms & {RECORD, MANAGE} and not my_houses(self.request).filter(pk=house.pk).exists():
            raise PermissionDenied("Only this house's warden or a school leader can do this.")
        exeat = serializer.save(requested_by=user.pk)
        if house.warden_user_id and house.warden_user_id != user.pk:
            notify_users(
                [house.warden_user_id],
                kind="exeat",
                title=f"Exeat request: {student.full_name}",
                body=f"{exeat.leaves_on:%a %d %b} to {exeat.returns_on:%a %d %b}: {exeat.reason}",
                data={"exeat": str(exeat.pk)},
            )

    def _get(self, pk: str | None) -> Exeat:
        return get_object_or_404(self.get_queryset(), pk=pk)

    def _decide(self, request: Request, pk: str | None, approve: bool) -> Response:
        exeat = self._get(pk)
        if exeat.status != Exeat.Status.REQUESTED:
            raise ValidationError({"detail": "This has already been decided."})
        if exeat.requested_by == request.user.pk:
            raise ValidationError({"detail": "Someone else must decide on your own request."})
        data = DecisionNoteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with tenant_atomic():
            exeat.status = Exeat.Status.APPROVED if approve else Exeat.Status.DECLINED
            exeat.decided_by = request.user.pk
            exeat.decision_note = data.validated_data["note"]
            exeat.save(update_fields=["status", "decided_by", "decision_note"])
            record_event(
                action=f"hostel.exeat_{exeat.status}", request=request, target=exeat.student
            )
        verdict = "approved" if approve else "declined"
        _tell_family(
            exeat,
            f"Exeat {verdict}: {exeat.student.first_name}",
            f"{exeat.leaves_on:%a %d %b} to {exeat.returns_on:%a %d %b} was {verdict}."
            + (f" {exeat.decision_note}" if exeat.decision_note else ""),
        )
        return Response(ExeatSerializer(exeat).data)

    @extend_schema(request=DecisionNoteSerializer, responses=ExeatSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response:
        return self._decide(request, pk, True)

    @extend_schema(request=DecisionNoteSerializer, responses=ExeatSerializer)
    @action(detail=True, methods=["post"])
    def decline(self, request: Request, pk: str | None = None) -> Response:
        return self._decide(request, pk, False)

    @extend_schema(request=None, responses=ExeatSerializer)
    @action(detail=True, methods=["post"])
    def depart(self, request: Request, pk: str | None = None) -> Response:
        exeat = self._get(pk)
        if exeat.status != Exeat.Status.APPROVED:
            raise ValidationError({"detail": "Only an approved exeat can start."})
        exeat.status, exeat.left_at = Exeat.Status.OUT, timezone.now()
        exeat.save(update_fields=["status", "left_at"])
        return Response(ExeatSerializer(exeat).data)

    @extend_schema(request=None, responses=ExeatSerializer)
    @action(detail=True, methods=["post"])
    def back(self, request: Request, pk: str | None = None) -> Response:
        exeat = self._get(pk)
        if exeat.status not in (Exeat.Status.OUT, Exeat.Status.APPROVED):
            raise ValidationError({"detail": "They aren't away."})
        exeat.status, exeat.returned_at = Exeat.Status.RETURNED, timezone.now()
        exeat.save(update_fields=["status", "returned_at"])
        _tell_family(
            exeat, f"{exeat.student.first_name} is back at school", "Signed back into the house."
        )
        return Response(ExeatSerializer(exeat).data)


class MyBoardingView(APIView):
    """Parents: each boarding child's house, room, the last roll calls and exeats."""

    required_permissions: ClassVar = {"GET": VIEW}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        perms = _perms(request)
        pupils = visible_students(request.user, load_membership(request), perms)
        beds = Boarder.objects.filter(student__in=pupils, left_on__isnull=True).select_related(
            "student", "room__house"
        )
        out = []
        for b in beds:
            calls = RollCall.objects.filter(student=b.student).order_by("-date", "-session")[:6]
            out.append(
                {
                    "student": str(b.student_id),
                    "name": b.student.first_name,
                    "house": b.room.house.name,
                    "room": b.room.name,
                    "roll_calls": [
                        {
                            "date": c.date,
                            "session": c.get_session_display(),
                            "status": c.get_status_display(),
                        }
                        for c in calls
                    ],
                }
            )
        return Response(out)
