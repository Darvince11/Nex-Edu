from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from django.db.models import QuerySet
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event, snapshot
from core.permissions import has_perm, load_membership
from core.rbac import STAFF_ROLES, Perm
from core.views import TenantViewSet

from .. import services
from ..models import (
    AcademicSession,
    CalendarEvent,
    ClassArm,
    ClassLevel,
    Period,
    Subject,
    TeachingAssignment,
    Term,
)
from ..selectors import teaches_arm

READ, MANAGE = Perm.ACADEMICS_VIEW, Perm.ACADEMICS_MANAGE
CRUD_PERMS: dict[str, Any] = {
    "list": (READ, Perm.COMMUNICATION_VIEW),
    "retrieve": (READ, Perm.COMMUNICATION_VIEW),
    "create": MANAGE,
    "update": MANAGE,
    "partial_update": MANAGE,
    "destroy": MANAGE,
}


class AuditedCrudViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    TenantViewSet,
):
    """CRUD where every write is recorded in the audit log."""

    audit_name = ""
    required_permissions: ClassVar[dict[str, Any]] = CRUD_PERMS

    def perform_create(self, serializer: Any) -> None:
        with tenant_atomic():
            obj = serializer.save()
            record_event(
                action=f"{self.audit_name}.created",
                request=self.request,
                target=obj,
                after=snapshot(obj),
            )

    def perform_update(self, serializer: Any) -> None:
        with tenant_atomic():
            before = snapshot(serializer.instance)
            obj = serializer.save()
            record_event(
                action=f"{self.audit_name}.updated",
                request=self.request,
                target=obj,
                before=before,
                after=snapshot(obj),
            )

    def perform_destroy(self, instance: Any) -> None:
        with tenant_atomic():
            record_event(
                action=f"{self.audit_name}.deleted",
                request=self.request,
                target=instance,
                before=snapshot(instance),
            )
            instance.delete()


class SessionSerializer(serializers.ModelSerializer[AcademicSession]):
    class Meta:
        model = AcademicSession
        fields: ClassVar = ["id", "name", "starts_on", "ends_on", "is_current"]
        read_only_fields: ClassVar = ["is_current"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        starts = attrs.get("starts_on", getattr(self.instance, "starts_on", None))
        ends = attrs.get("ends_on", getattr(self.instance, "ends_on", None))
        if starts and ends and ends <= starts:
            raise serializers.ValidationError("The end date must be after the start date.")
        return attrs


class TermSerializer(serializers.ModelSerializer[Term]):
    label = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = Term
        fields: ClassVar = [
            "id",
            "session",
            "number",
            "label",
            "starts_on",
            "ends_on",
            "next_term_begins",
            "is_current",
        ]
        read_only_fields: ClassVar = ["is_current"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = Term(
            **{
                **(
                    {}
                    if self.instance is None
                    else {
                        f: getattr(self.instance, f)
                        for f in ("session", "number", "starts_on", "ends_on")
                    }
                ),
                **attrs,
            }
        )
        if instance.starts_on and instance.ends_on and instance.ends_on <= instance.starts_on:
            raise serializers.ValidationError("The end date must be after the start date.")
        instance.clean()
        return attrs


class LevelSerializer(serializers.ModelSerializer[ClassLevel]):
    class Meta:
        model = ClassLevel
        fields: ClassVar = ["id", "name", "section", "order", "is_active"]
        read_only_fields: ClassVar = ["name", "section", "order"]


class ArmSerializer(serializers.ModelSerializer[ClassArm]):
    label = serializers.CharField(source="__str__", read_only=True)
    level_name = serializers.CharField(source="level.name", read_only=True)

    class Meta:
        model = ClassArm
        fields: ClassVar = ["id", "level", "level_name", "name", "label"]


class SubjectSerializer(serializers.ModelSerializer[Subject]):
    class Meta:
        model = Subject
        fields: ClassVar = ["id", "name", "code", "sections", "is_active"]


class AssignmentSerializer(serializers.ModelSerializer[TeachingAssignment]):
    arm_label = serializers.CharField(source="arm.__str__", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True, default=None)

    class Meta:
        model = TeachingAssignment
        fields: ClassVar = [
            "id",
            "teacher_user_id",
            "arm",
            "arm_label",
            "subject",
            "subject_name",
            "is_form_teacher",
        ]


class PeriodSerializer(serializers.ModelSerializer[Period]):
    arm_label = serializers.CharField(source="arm.__str__", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = Period
        fields: ClassVar = [
            "id",
            "term",
            "arm",
            "arm_label",
            "subject",
            "subject_name",
            "teacher_user_id",
            "weekday",
            "starts_at",
            "ends_at",
            "room",
            "video_url",
        ]


class SessionViewSet(AuditedCrudViewSet):
    serializer_class = SessionSerializer
    audit_name = "academics.session"
    required_permissions: ClassVar = {**CRUD_PERMS, "set_current": MANAGE}

    def get_queryset(self) -> QuerySet[AcademicSession]:
        return AcademicSession.objects.all()

    @action(detail=True, methods=["post"])
    def set_current(self, request: Request, pk: str | None = None) -> Response:
        services.set_current_session(request=request, session=self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class TermViewSet(AuditedCrudViewSet):
    serializer_class = TermSerializer
    audit_name = "academics.term"
    required_permissions: ClassVar = {
        **CRUD_PERMS,
        "set_current": MANAGE,
        "current": (READ, Perm.COMMUNICATION_VIEW),
    }

    def get_queryset(self) -> QuerySet[Term]:
        qs = Term.objects.select_related("session")
        if session := self.request.query_params.get("session"):
            qs = qs.filter(session_id=session)
        return qs

    @action(detail=True, methods=["post"])
    def set_current(self, request: Request, pk: str | None = None) -> Response:
        services.set_current_term(request=request, term=self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def current(self, request: Request) -> Response:
        term = services.current_term()
        return Response(TermSerializer(term).data if term else None)


class LevelViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, TenantViewSet):
    serializer_class = LevelSerializer
    required_permissions: ClassVar = {
        "list": CRUD_PERMS["list"],
        "partial_update": MANAGE,
        "update": MANAGE,
    }

    def get_queryset(self) -> QuerySet[ClassLevel]:
        return ClassLevel.objects.all()


class ArmViewSet(AuditedCrudViewSet):
    serializer_class = ArmSerializer
    audit_name = "academics.arm"

    def get_queryset(self) -> QuerySet[ClassArm]:
        qs = ClassArm.objects.select_related("level").filter(level__is_active=True)
        mine = self.request.query_params.get("mine")
        if mine == "1":  # classes I teach
            qs = qs.filter(assignments__teacher_user_id=self.request.user.pk).distinct()
        elif mine == "form":  # classes I'm the class teacher of
            qs = qs.filter(
                assignments__teacher_user_id=self.request.user.pk,
                assignments__is_form_teacher=True,
            ).distinct()
        return qs


class SubjectViewSet(AuditedCrudViewSet):
    serializer_class = SubjectSerializer
    audit_name = "academics.subject"

    def get_queryset(self) -> QuerySet[Subject]:
        qs = Subject.objects.all()
        if arm := self.request.query_params.get("arm"):
            qs = qs.filter(assignments__arm_id=arm).distinct()
        return qs


class AssignmentViewSet(AuditedCrudViewSet):
    serializer_class = AssignmentSerializer
    audit_name = "academics.assignment"

    def get_queryset(self) -> QuerySet[TeachingAssignment]:
        qs = TeachingAssignment.objects.select_related("arm__level", "subject")
        if teacher := self.request.query_params.get("teacher"):
            qs = qs.filter(teacher_user_id=self.request.user.pk if teacher == "me" else teacher)
        if arm := self.request.query_params.get("arm"):
            qs = qs.filter(arm_id=arm)
        return qs.order_by("arm__level__order", "arm__name", "subject__name")


TIMETABLE_WRITE = (MANAGE, Perm.ACADEMICS_TIMETABLE_OWN)


class PeriodViewSet(AuditedCrudViewSet):
    """The timetable. Writes are checked for class and teacher clashes. Teachers
    without academics.manage may change only the classes they're assigned to."""

    serializer_class = PeriodSerializer
    audit_name = "timetable.period"
    required_permissions: ClassVar = {
        **CRUD_PERMS,
        "create": TIMETABLE_WRITE,
        "update": TIMETABLE_WRITE,
        "partial_update": TIMETABLE_WRITE,
        "destroy": TIMETABLE_WRITE,
    }

    def _check_classes(self, *arm_ids: Any) -> None:
        if has_perm(self.request, MANAGE):
            return
        if not all(teaches_arm(self.request.user, arm_id) for arm_id in arm_ids):
            raise PermissionDenied("You can only change the timetable of classes you teach.")

    def get_queryset(self) -> QuerySet[Period]:
        qs = Period.objects.select_related("arm__level", "subject")
        params = self.request.query_params
        if term := params.get("term"):
            qs = qs.filter(term_id=term)
        if arm := params.get("arm"):
            qs = qs.filter(arm_id=arm)
        if teacher := params.get("teacher"):
            qs = qs.filter(teacher_user_id=self.request.user.pk if teacher == "me" else teacher)
        return qs

    def perform_create(self, serializer: Any) -> None:
        self._check_classes(serializer.validated_data["arm"].pk)
        serializer.instance = services.save_period(
            request=self.request, period=Period(), data=dict(serializer.validated_data)
        )

    def perform_update(self, serializer: Any) -> None:
        moved_to = serializer.validated_data.get("arm", serializer.instance.arm)
        self._check_classes(serializer.instance.arm_id, moved_to.pk)
        serializer.instance = services.save_period(
            request=self.request, period=serializer.instance, data=dict(serializer.validated_data)
        )

    def perform_destroy(self, instance: Any) -> None:
        self._check_classes(instance.arm_id)
        super().perform_destroy(instance)


class CalendarEventSerializer(serializers.ModelSerializer[CalendarEvent]):
    notify = serializers.BooleanField(
        write_only=True, required=False, default=False, help_text="Tell everyone it's for"
    )
    ends_on = serializers.DateField(required=False)

    class Meta:
        model = CalendarEvent
        fields: ClassVar = [
            "id",
            "title",
            "kind",
            "starts_on",
            "ends_on",
            "starts_at",
            "ends_at",
            "location",
            "description",
            "audience",
            "notify",
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        starts_on = attrs.get("starts_on", getattr(instance, "starts_on", None))
        # A one-day event needs no end date.
        ends_on = attrs.get("ends_on") or getattr(instance, "ends_on", None) or starts_on
        if starts_on and ends_on and ends_on < starts_on:
            raise serializers.ValidationError({"ends_on": "It can't end before it starts."})
        if starts_on and ends_on and (ends_on - starts_on).days > MAX_EVENT_DAYS:
            raise serializers.ValidationError(
                {"ends_on": f"Keep an event to {MAX_EVENT_DAYS} days or fewer."}
            )
        starts_at = attrs.get("starts_at", getattr(instance, "starts_at", None))
        ends_at = attrs.get("ends_at", getattr(instance, "ends_at", None))
        if starts_at and ends_at and starts_on == ends_on and ends_at <= starts_at:
            raise serializers.ValidationError({"ends_at": "It must end after it starts."})
        attrs["ends_on"] = ends_on
        return attrs

    def create(self, validated_data: dict[str, Any]) -> CalendarEvent:
        validated_data.pop("notify", None)
        validated_data["created_by"] = self.context["request"].user.pk
        return super().create(validated_data)

    def update(self, instance: CalendarEvent, validated_data: dict[str, Any]) -> CalendarEvent:
        validated_data.pop("notify", None)
        return super().update(instance, validated_data)


MAX_EVENT_DAYS = 60


class CalendarEventViewSet(AuditedCrudViewSet):
    """The school's own calendar entries. Everyone reads; leaders write."""

    serializer_class = CalendarEventSerializer
    audit_name = "calendar_event"
    required_permissions: ClassVar = {
        "list": Perm.CALENDAR_VIEW,
        "retrieve": Perm.CALENDAR_VIEW,
        "create": Perm.CALENDAR_MANAGE,
        "update": Perm.CALENDAR_MANAGE,
        "partial_update": Perm.CALENDAR_MANAGE,
        "destroy": Perm.CALENDAR_MANAGE,
    }

    def get_queryset(self) -> QuerySet[CalendarEvent]:
        _, roles, _ = self.actor()
        qs = CalendarEvent.objects.all()
        if not set(roles) & STAFF_ROLES:
            qs = qs.filter(audience=CalendarEvent.Audience.EVERYONE)
        return qs

    def perform_create(self, serializer: Any) -> None:
        notify = serializer.validated_data.get("notify", False)
        super().perform_create(serializer)
        if notify:
            _announce_event(serializer.instance)


def _announce_event(event: CalendarEvent) -> None:
    from apps.communication.services import member_ids, notify_users
    from control_plane.models import Role

    roles = STAFF_ROLES if event.audience == CalendarEvent.Audience.STAFF else Role.values
    day = event.starts_on
    when = f"{day:%A} {day.day} {day:%B}"
    notify_users(
        member_ids(roles),
        kind="calendar",
        title=f"On the calendar: {event.title}",
        body=f"{event.title} — {when}." + (f" {event.location}." if event.location else ""),
        data={"event": str(event.pk), "date": event.starts_on.isoformat()},
    )


class CalendarView(APIView):
    """Everything on the calendar between ?start= and ?end=: the school's events,
    term dates and Ghana's public holidays."""

    required_permissions: ClassVar = {"GET": Perm.CALENDAR_VIEW}

    @extend_schema(
        parameters=[
            OpenApiParameter("start", OpenApiTypes.DATE),
            OpenApiParameter("end", OpenApiTypes.DATE),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request) -> Response:
        from .. import calendar

        today = timezone.localdate()
        try:
            start = dt.date.fromisoformat(
                request.query_params.get("start") or today.replace(day=1).isoformat()
            )
            end = dt.date.fromisoformat(
                request.query_params.get("end") or (start + dt.timedelta(days=41)).isoformat()
            )
        except ValueError:
            return Response({"detail": "Use YYYY-MM-DD dates."}, status=400)
        if end < start or (end - start).days > calendar.MAX_DAYS:
            return Response({"detail": "Choose up to a year, ending after it starts."}, status=400)
        roles = load_membership(request)
        return Response(calendar.entries(start, end, staff=bool(set(roles) & STAFF_ROLES)))
