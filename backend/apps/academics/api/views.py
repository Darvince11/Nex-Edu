from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import QuerySet
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event, snapshot
from core.rbac import Perm
from core.views import TenantViewSet

from .. import services
from ..models import (
    AcademicSession,
    ClassArm,
    ClassLevel,
    Period,
    Subject,
    TeachingAssignment,
    Term,
)

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
        if self.request.query_params.get("mine") == "1":
            qs = qs.filter(assignments__teacher_user_id=self.request.user.pk).distinct()
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


class PeriodViewSet(AuditedCrudViewSet):
    """The timetable. Writes are checked for class and teacher clashes."""

    serializer_class = PeriodSerializer
    audit_name = "timetable.period"

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
        serializer.instance = services.save_period(
            request=self.request, period=Period(), data=dict(serializer.validated_data)
        )

    def perform_update(self, serializer: Any) -> None:
        serializer.instance = services.save_period(
            request=self.request, period=serializer.instance, data=dict(serializer.validated_data)
        )
