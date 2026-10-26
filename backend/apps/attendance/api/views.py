from __future__ import annotations

from typing import Any, ClassVar

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import ClassArm, Term
from apps.students.selectors import visible_students
from core.permissions import load_membership
from core.rbac import Perm

from .. import services
from ..models import AttendanceRecord


class EntrySerializer(serializers.Serializer):  # type: ignore[type-arg]
    student = serializers.UUIDField()
    status = serializers.ChoiceField(choices=AttendanceRecord.Status.choices)
    note = serializers.CharField(max_length=200, required=False, default="", allow_blank=True)


class RegisterSerializer(serializers.Serializer):  # type: ignore[type-arg]
    arm = serializers.UUIDField()
    date = serializers.DateField()
    entries = EntrySerializer(many=True, allow_empty=False, max_length=200)
    batch_id = serializers.UUIDField(required=False, allow_null=True)
    recorded_at = serializers.DateTimeField(required=False, allow_null=True)


class RecordSerializer(serializers.ModelSerializer[AttendanceRecord]):
    class Meta:
        model = AttendanceRecord
        fields: ClassVar = ["id", "student", "date", "status", "note", "recorded_at"]


def _perms(request: Request) -> frozenset[str]:
    load_membership(request)
    return getattr(request, "permissions", frozenset())


class RegisterView(APIView):
    """GET ?arm=&date= returns the class list with any statuses already taken.
    POST submits the register; safe to retry with the same ``batch_id`` (offline sync)."""

    required_permissions: ClassVar = {
        "GET": (Perm.ATTENDANCE_RECORD, Perm.ATTENDANCE_MANAGE),
        "POST": (Perm.ATTENDANCE_RECORD, Perm.ATTENDANCE_MANAGE),
    }

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        arm = get_object_or_404(ClassArm, pk=request.query_params.get("arm"))
        if not services.can_take_register(request.user, _perms(request), arm):
            raise PermissionDenied("You can only take the register for classes you teach.")
        day = serializers.DateField().to_internal_value(request.query_params.get("date"))
        return Response(
            {
                "arm": str(arm.pk),
                "arm_label": str(arm),
                "date": day.isoformat(),
                "rows": services.register_sheet(arm, day),
            }
        )

    @extend_schema(request=RegisterSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = RegisterSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v: dict[str, Any] = data.validated_data
        arm = get_object_or_404(ClassArm, pk=v["arm"])
        result = services.record_register(
            request=request,
            user=request.user,
            permissions=_perms(request),
            arm=arm,
            day=v["date"],
            entries=[dict(e) for e in v["entries"]],
            batch_id=v.get("batch_id"),
            recorded_at=v.get("recorded_at"),
        )
        return Response(result)


class StudentAttendanceView(APIView):
    """A student's records and totals for a term. Parents see only their children."""

    required_permissions: ClassVar = {"GET": Perm.ATTENDANCE_VIEW}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, student_id: str) -> Response:
        student = get_object_or_404(
            visible_students(
                request.user, load_membership(request), getattr(request, "permissions", ())
            ),
            pk=student_id,
        )
        term_id = request.query_params.get("term")
        term = (
            get_object_or_404(Term, pk=term_id)
            if term_id
            else Term.objects.filter(is_current=True).first()
        )
        if term is None:
            return Response({"summary": None, "records": []})
        records = AttendanceRecord.objects.filter(student=student, term=term).order_by("-date")
        return Response(
            {
                "term": term.pk,
                "summary": services.student_summary(student, term),
                "records": RecordSerializer(records, many=True).data,
            }
        )


class ArmSummaryView(APIView):
    required_permissions: ClassVar = {"GET": (Perm.ATTENDANCE_RECORD, Perm.ATTENDANCE_MANAGE)}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        arm = get_object_or_404(ClassArm, pk=request.query_params.get("arm"))
        if not services.can_take_register(request.user, _perms(request), arm):
            raise PermissionDenied("You can only view classes you teach.")
        term = get_object_or_404(Term, pk=request.query_params.get("term"))
        return Response(
            {
                "days_open": services.days_open(arm.pk, term),
                "students": services.arm_summary(arm, term),
            }
        )
