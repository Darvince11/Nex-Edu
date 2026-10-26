"""Learning support. Who sees what:

- Whoever runs support (``support.manage``: the head teacher, or a coordinator given
  it through a custom role) writes plans and notes and reads everything; reading a
  plan in full is audited.
- Teachers (``support.view``) see, for pupils they teach, the needs, goals and
  adjustments, never the confidential summary or notes.
- Parents (``support.view``) see their own child's plan once it's shared with them:
  needs, goals and adjustments.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.students.models import Student
from apps.students.selectors import visible_students
from control_plane.models import User
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.rbac import STAFF_ROLES, Perm
from core.views import TenantViewSet

from ..models import NEEDS, Note, Plan

VIEW, MANAGE = Perm.SUPPORT_VIEW, Perm.SUPPORT_MANAGE
NEED_LABELS = dict(NEEDS)


class GoalSerializer(serializers.Serializer):  # type: ignore[type-arg]
    goal = serializers.CharField(max_length=200)
    measure = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=[("working", "Working on it"), ("met", "Met"), ("not_met", "Not met yet")],
        default="working",
    )


class PlanSerializer(serializers.ModelSerializer[Plan]):
    """The full plan, for whoever runs support."""

    student_name = serializers.CharField(source="student.full_name", read_only=True)
    student_class = serializers.SerializerMethodField()
    goals = GoalSerializer(many=True, required=False)
    need_labels = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields: ClassVar = [
            "id",
            "student",
            "student_name",
            "student_class",
            "needs",
            "need_labels",
            "summary",
            "goals",
            "adjustments",
            "extra_time_percent",
            "review_on",
            "shared_with_parents",
            "status",
            "updated_at",
        ]
        extra_kwargs: ClassVar = {"extra_time_percent": {"min_value": 0, "max_value": 100}}

    def get_student_class(self, obj: Plan) -> str:
        return str(obj.student.arm) if obj.student.arm_id else ""

    def get_need_labels(self, obj: Plan) -> list[str]:
        return [NEED_LABELS.get(n, n) for n in obj.needs]

    def validate_needs(self, value: Any) -> list[str]:
        if not isinstance(value, list) or not value or any(n not in NEED_LABELS for n in value):
            raise serializers.ValidationError("Choose at least one area of need.")
        return value


class SharedPlanSerializer(PlanSerializer):
    """For teachers and parents: no confidential summary."""

    class Meta(PlanSerializer.Meta):
        fields: ClassVar = [f for f in PlanSerializer.Meta.fields if f != "summary"]


class NoteSerializer(serializers.ModelSerializer[Note]):
    written_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Note
        fields: ClassVar = ["id", "date", "text", "written_by_name", "created_at"]
        extra_kwargs: ClassVar = {"date": {"required": False}}

    def get_written_by_name(self, obj: Note) -> str:
        return str(self.context.get("names", {}).get(obj.written_by, ""))


class PlanViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    TenantViewSet,
):
    required_permissions: ClassVar = {
        "list": (VIEW, MANAGE),
        "retrieve": (VIEW, MANAGE),
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "notes": MANAGE,
        "add_note": MANAGE,
    }

    def _manage(self) -> bool:
        return MANAGE in self.actor()[2]

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Any]]:
        return PlanSerializer if self._manage() else SharedPlanSerializer

    def get_queryset(self) -> QuerySet[Plan]:
        user, roles, perms = self.actor()
        qs = Plan.objects.select_related("student__arm__level")
        if MANAGE in perms:
            if self.request.query_params.get("status") == "closed":
                return qs.filter(status=Plan.Status.CLOSED)
            return qs.filter(status=Plan.Status.ACTIVE) if self.action == "list" else qs
        qs = qs.filter(status=Plan.Status.ACTIVE, student__in=visible_students(user, roles, perms))
        if not set(roles) & STAFF_ROLES:
            qs = qs.filter(shared_with_parents=True)
        return qs

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        plan = self.get_object()
        if self._manage():
            with tenant_atomic():
                record_event(action="support.viewed", request=request, target=plan.student)
        return Response(self.get_serializer(plan).data)

    def perform_create(self, serializer: Any) -> None:
        student: Student = serializer.validated_data["student"]
        if Plan.objects.filter(student=student, status=Plan.Status.ACTIVE).exists():
            raise ValidationError(
                {"student": "This pupil already has an active plan. Change that one."}
            )
        with tenant_atomic():
            plan = serializer.save(created_by=self.request.user.pk)
            record_event(action="support.plan_created", request=self.request, target=plan.student)

    def perform_update(self, serializer: Any) -> None:
        if (
            "student" in serializer.validated_data
            and serializer.validated_data["student"] != serializer.instance.student
        ):
            raise ValidationError({"student": "Start a new plan for a different pupil."})
        with tenant_atomic():
            plan = serializer.save()
            record_event(action="support.plan_changed", request=self.request, target=plan.student)

    @extend_schema(responses=NoteSerializer(many=True))
    @action(detail=True, methods=["get"])
    def notes(self, request: Request, pk: str | None = None) -> Response:
        plan = get_object_or_404(Plan, pk=pk)
        notes = list(plan.notes.all())
        names = {
            u.pk: u.get_full_name() or u.email
            for u in User.objects.filter(pk__in={n.written_by for n in notes})
        }
        with tenant_atomic():
            record_event(action="support.notes_read", request=request, target=plan.student)
        return Response(NoteSerializer(notes, many=True, context={"names": names}).data)

    @extend_schema(request=NoteSerializer, responses=NoteSerializer)
    @action(detail=True, methods=["post"])
    def add_note(self, request: Request, pk: str | None = None) -> Response:
        plan = get_object_or_404(Plan, pk=pk)
        data = NoteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with tenant_atomic():
            note = Note.objects.create(
                plan=plan,
                date=data.validated_data.get("date") or timezone.localdate(),
                text=data.validated_data["text"],
                written_by=request.user.pk,
            )
            record_event(action="support.note_written", request=request, target=plan.student)
        return Response(NoteSerializer(note).data, status=status.HTTP_201_CREATED)
