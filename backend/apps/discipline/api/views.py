"""Behaviour records. Who sees what:

- School leaders (``discipline.manage``) see every incident, record what was done,
  resolve incidents, and choose what to share with parents.
- Teachers (``discipline.record``) report incidents about pupils they teach and see
  those pupils' incidents and their own reports.
- Parents (``discipline.view``) see only incidents a leader has shared about their own
  children, and only the summary written for them, never the staff notes.
- Counselling notes are confidential (``discipline.counsel``); reading them is audited.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

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

from apps.students.models import Student
from apps.students.selectors import visible_students
from control_plane.models import User
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.permissions import load_membership
from core.rbac import Perm
from core.views import TenantViewSet

from ..models import Action, CounsellingNote, Incident

VIEW, RECORD, MANAGE, COUNSEL = (
    Perm.DISCIPLINE_VIEW,
    Perm.DISCIPLINE_RECORD,
    Perm.DISCIPLINE_MANAGE,
    Perm.DISCIPLINE_COUNSEL,
)
REPEAT_THRESHOLD = 3


def _names(ids: set[Any]) -> dict[Any, str]:
    return {u.pk: u.get_full_name() or u.email for u in User.objects.filter(pk__in=ids)}


class ActionSerializer(serializers.ModelSerializer[Action]):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Action
        fields: ClassVar = ["id", "kind", "kind_label", "date", "days", "notes", "created_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("kind") == Action.Kind.SUSPENSION and not attrs.get("days"):
            raise serializers.ValidationError({"days": "Say how many days."})
        return attrs


class IncidentSerializer(serializers.ModelSerializer[Incident]):
    """The staff view."""

    student_name = serializers.CharField(source="student.full_name", read_only=True)
    student_class = serializers.SerializerMethodField()
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    severity_label = serializers.CharField(source="get_severity_display", read_only=True)
    reported_by_name = serializers.SerializerMethodField()
    actions = ActionSerializer(many=True, read_only=True)

    class Meta:
        model = Incident
        fields: ClassVar = [
            "id",
            "student",
            "student_name",
            "student_class",
            "date",
            "category",
            "category_label",
            "severity",
            "severity_label",
            "location",
            "description",
            "reported_by",
            "reported_by_name",
            "status",
            "shared_with_parents_at",
            "shared_summary",
            "actions",
            "created_at",
        ]
        read_only_fields: ClassVar = [
            "reported_by",
            "status",
            "shared_with_parents_at",
            "shared_summary",
        ]

    def get_student_class(self, obj: Incident) -> str:
        return str(obj.student.arm) if obj.student.arm_id else ""

    def get_reported_by_name(self, obj: Incident) -> str:
        return str(self.context.get("names", {}).get(obj.reported_by, ""))

    def validate_date(self, value: dt.date) -> dt.date:
        if value > timezone.localdate():
            raise serializers.ValidationError("It can't be in the future.")
        return value


class ParentIncidentSerializer(serializers.ModelSerializer[Incident]):
    """What a parent sees: the summary written for them and what was done."""

    student_name = serializers.CharField(source="student.first_name", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    actions = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields: ClassVar = [
            "id",
            "student",
            "student_name",
            "date",
            "category_label",
            "shared_summary",
            "status",
            "actions",
        ]

    def get_actions(self, obj: Incident) -> list[dict[str, Any]]:
        return [
            {"kind_label": a.get_kind_display(), "date": a.date, "days": a.days}
            for a in obj.actions.all()
        ]


class ShareSerializer(serializers.Serializer):  # type: ignore[type-arg]
    summary = serializers.CharField(max_length=500)
    sms = serializers.BooleanField(required=False, default=False)


class IncidentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    TenantViewSet,
):
    serializer_class = IncidentSerializer
    required_permissions: ClassVar = {
        "list": (VIEW, RECORD, MANAGE),
        "retrieve": (VIEW, RECORD, MANAGE),
        "create": (RECORD, MANAGE),
        "update": (RECORD, MANAGE),
        "partial_update": (RECORD, MANAGE),
        "add_action": MANAGE,
        "resolve": MANAGE,
        "reopen": MANAGE,
        "share": MANAGE,
    }

    def _family_only(self) -> bool:
        _, _, perms = self.actor()
        return not perms & {RECORD, MANAGE}

    def get_queryset(self) -> QuerySet[Incident]:
        user, roles, perms = self.actor()
        qs = Incident.objects.select_related("student__arm__level").prefetch_related("actions")
        if MANAGE in perms:
            pass
        elif RECORD in perms:
            qs = qs.filter(
                Q(reported_by=user.pk) | Q(student__in=visible_students(user, roles, perms))
            )
        else:
            qs = qs.filter(
                student__in=visible_students(user, roles, perms),
                shared_with_parents_at__isnull=False,
            )
        params = self.request.query_params
        if student := params.get("student"):
            qs = qs.filter(student_id=student)
        if (state := params.get("status")) in Incident.Status.values:
            qs = qs.filter(status=state)
        if (category := params.get("category")) in Incident.Category.values:
            qs = qs.filter(category=category)
        return qs

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Any]]:
        if self.request.user.is_authenticated and self._family_only():
            return ParentIncidentSerializer
        return IncidentSerializer

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        if pk := self.kwargs.get("pk"):
            context["names"] = _names(
                set(Incident.objects.filter(pk=pk).values_list("reported_by", flat=True))
            )
        return context

    @extend_schema(
        parameters=[
            OpenApiParameter("student", OpenApiTypes.UUID),
            OpenApiParameter("status", OpenApiTypes.STR),
            OpenApiParameter("category", OpenApiTypes.STR),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        rows = list(self.get_queryset()[:300])
        context = {**self.get_serializer_context(), "names": _names({r.reported_by for r in rows})}
        return Response(self.get_serializer_class()(rows, many=True, context=context).data)

    def perform_create(self, serializer: Any) -> None:
        user, roles, perms = self.actor()
        student = serializer.validated_data["student"]
        if (
            MANAGE not in perms
            and not visible_students(user, roles, perms).filter(pk=student.pk).exists()
        ):
            raise PermissionDenied("You can report incidents about pupils you teach.")
        if student.status != Student.Status.ACTIVE:
            raise ValidationError({"student": "This pupil isn't on roll."})
        with tenant_atomic():
            incident = serializer.save(reported_by=user.pk)
            record_event(
                action="discipline.reported",
                request=self.request,
                target=incident,
                after={"category": incident.category, "severity": incident.severity},
            )

    def perform_update(self, serializer: Any) -> None:
        user, _, perms = self.actor()
        incident = serializer.instance
        if MANAGE not in perms and (
            incident.reported_by != user.pk or incident.status != Incident.Status.OPEN
        ):
            raise PermissionDenied("Only school leaders can change this now.")
        if (
            "student" in serializer.validated_data
            and serializer.validated_data["student"] != incident.student
        ):
            raise ValidationError({"student": "Report a new incident for a different pupil."})
        with tenant_atomic():
            serializer.save()
            record_event(action="discipline.updated", request=self.request, target=incident)

    def _get(self, pk: str | None) -> Incident:
        return get_object_or_404(self.get_queryset(), pk=pk)

    @extend_schema(request=ActionSerializer, responses=IncidentSerializer)
    @action(detail=True, methods=["post"])
    def add_action(self, request: Request, pk: str | None = None) -> Response:
        incident = self._get(pk)
        data = ActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with tenant_atomic():
            taken = data.save(incident=incident, taken_by=request.user.pk)
            record_event(
                action="discipline.action",
                request=request,
                target=incident,
                after={"kind": taken.kind, "days": taken.days},
            )
        return Response(
            IncidentSerializer(self._get(pk), context=self.get_serializer_context()).data
        )

    def _set_status(self, request: Request, pk: str | None, state: str) -> Response:
        incident = self._get(pk)
        with tenant_atomic():
            incident.status = state
            incident.save(update_fields=["status"])
            record_event(action=f"discipline.{state}", request=request, target=incident)
        return Response(IncidentSerializer(incident, context=self.get_serializer_context()).data)

    @extend_schema(request=None, responses=IncidentSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request: Request, pk: str | None = None) -> Response:
        return self._set_status(request, pk, Incident.Status.RESOLVED)

    @extend_schema(request=None, responses=IncidentSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request: Request, pk: str | None = None) -> Response:
        return self._set_status(request, pk, Incident.Status.OPEN)

    @extend_schema(request=ShareSerializer, responses=IncidentSerializer)
    @action(detail=True, methods=["post"])
    def share(self, request: Request, pk: str | None = None) -> Response:
        """Tell the pupil's parents, in words written for them."""
        from apps.communication.models import Channel
        from apps.communication.services import notify_guardians

        incident = self._get(pk)
        data = ShareSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        summary = data.validated_data["summary"].strip()
        with tenant_atomic():
            incident.shared_summary = summary
            incident.shared_with_parents_at = timezone.now()
            incident.save(update_fields=["shared_summary", "shared_with_parents_at"])
            record_event(action="discipline.shared", request=request, target=incident)
        notify_guardians(
            [incident.student],
            kind="behaviour",
            title=f"A note about {incident.student.first_name}'s behaviour",
            body=summary,
            data={"incident": str(incident.pk), "student_id": str(incident.student_id)},
            channels={Channel.SMS} if data.validated_data["sms"] else set(),
        )
        return Response(IncidentSerializer(incident, context=self.get_serializer_context()).data)


class BehaviourSummaryView(APIView):
    """Leaders: the last 90 days by kind and severity, and pupils with repeated incidents."""

    required_permissions: ClassVar = {"GET": MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        since = timezone.localdate() - dt.timedelta(days=90)
        recent = Incident.objects.filter(date__gte=since)
        labels = dict(Incident.Category.choices)
        repeat = (
            recent.values("student_id", "student__first_name", "student__last_name")
            .annotate(n=Count("pk"))
            .filter(n__gte=REPEAT_THRESHOLD)
            .order_by("-n")[:20]
        )
        return Response(
            {
                "since": since,
                "total": recent.count(),
                "open": Incident.objects.filter(status=Incident.Status.OPEN).count(),
                "by_category": [
                    {"category": r["category"], "label": labels[r["category"]], "count": r["n"]}
                    for r in recent.values("category").annotate(n=Count("pk")).order_by("-n")
                ],
                "by_severity": dict(recent.values_list("severity").annotate(n=Count("pk"))),
                "repeat": [
                    {
                        "student": str(r["student_id"]),
                        "name": f"{r['student__last_name']} {r['student__first_name']}",
                        "count": r["n"],
                    }
                    for r in repeat
                ],
            }
        )


class CounsellingNoteSerializer(serializers.ModelSerializer[CounsellingNote]):
    written_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CounsellingNote
        fields: ClassVar = [
            "id",
            "student",
            "date",
            "notes",
            "follow_up_on",
            "written_by",
            "written_by_name",
            "created_at",
        ]
        read_only_fields: ClassVar = ["written_by"]

    def get_written_by_name(self, obj: CounsellingNote) -> str:
        return str(self.context.get("names", {}).get(obj.written_by, ""))


class CounsellingNoteViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, TenantViewSet):
    """Confidential notes per pupil (``?student=`` is required). Every read is audited."""

    serializer_class = CounsellingNoteSerializer
    required_permissions: ClassVar = {"list": COUNSEL, "create": COUNSEL}

    def get_queryset(self) -> QuerySet[CounsellingNote]:
        return CounsellingNote.objects.filter(student_id=self.request.query_params.get("student"))

    @extend_schema(parameters=[OpenApiParameter("student", OpenApiTypes.UUID, required=True)])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        load_membership(request)
        student = get_object_or_404(Student, pk=request.query_params.get("student"))
        notes = list(self.get_queryset())
        with tenant_atomic():
            record_event(action="discipline.counselling_read", request=request, target=student)
        context = {"names": _names({n.written_by for n in notes})}
        return Response(CounsellingNoteSerializer(notes, many=True, context=context).data)

    def perform_create(self, serializer: Any) -> None:
        with tenant_atomic():
            note = serializer.save(written_by=self.request.user.pk)
            record_event(
                action="discipline.counselling_written", request=self.request, target=note.student
            )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        super().create(request, *args, **kwargs)
        return Response(status=status.HTTP_201_CREATED)
