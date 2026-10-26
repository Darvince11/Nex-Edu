"""The sick bay. Who sees what:

- The school nurse and school leaders (``clinic.record``) log visits and see them all,
  with the pupil's medical notes alongside.
- Class teachers (``clinic.view``) see when their own pupils were in the sick bay and
  how it ended, not what was wrong or what was given.
- Parents (``clinic.view``) see their own children's visits in full, and are told
  whenever a child is sent home, collected or referred.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from django.db.models import Count, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.students.models import Student
from apps.students.selectors import visible_students
from control_plane.models import Role, User
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm
from core.views import TenantViewSet

from ..models import Visit

VIEW, RECORD = Perm.CLINIC_VIEW, Perm.CLINIC_RECORD
FREQUENT = 4  # visits in 30 days worth a closer look


class VisitSerializer(serializers.ModelSerializer[Visit]):
    """The nurse's view (and the parents', for their own children)."""

    student_name = serializers.CharField(source="student.full_name", read_only=True)
    student_class = serializers.SerializerMethodField()
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)
    seen_by_name = serializers.SerializerMethodField()
    tell_parents = serializers.BooleanField(write_only=True, required=False, default=False)
    sms = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Visit
        fields: ClassVar = [
            "id",
            "student",
            "student_name",
            "student_class",
            "arrived_at",
            "left_at",
            "complaint",
            "temperature",
            "treatment",
            "medication",
            "outcome",
            "outcome_label",
            "seen_by_name",
            "parents_told_at",
            "tell_parents",
            "sms",
        ]
        read_only_fields: ClassVar = ["left_at", "parents_told_at"]
        extra_kwargs: ClassVar = {"arrived_at": {"required": False}}

    def get_student_class(self, obj: Visit) -> str:
        return str(obj.student.arm) if obj.student.arm_id else ""

    def get_seen_by_name(self, obj: Visit) -> str:
        return str(self.context.get("names", {}).get(obj.seen_by, ""))

    def validate_temperature(self, value: Any) -> Any:
        if value is not None and not 30 <= value <= 45:
            raise serializers.ValidationError("Enter the temperature in °C, for example 37.2.")
        return value


class TeacherVisitSerializer(serializers.ModelSerializer[Visit]):
    """What a class teacher sees: when, and how it ended."""

    student_name = serializers.CharField(source="student.full_name", read_only=True)
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)

    class Meta:
        model = Visit
        fields: ClassVar = [
            "id",
            "student",
            "student_name",
            "arrived_at",
            "left_at",
            "outcome_label",
        ]


def _tell_parents(visit: Visit, *, sms: bool) -> None:
    from apps.communication.models import Channel
    from apps.communication.services import notify_guardians

    pupil = visit.student
    what = visit.get_outcome_display().lower() if visit.outcome else "being looked after"
    notify_guardians(
        [pupil],
        kind="clinic",
        title=f"{pupil.first_name} visited the sick bay",
        body=(
            f"{pupil.first_name} came to the sick bay at "
            f"{timezone.localtime(visit.arrived_at):%H:%M} and is {what}. "
            "Open Nex Edu for details, or call the school."
        ),
        data={"visit": str(visit.pk), "student_id": str(pupil.pk)},
        channels={Channel.SMS} if sms else set(),
    )
    visit.parents_told_at = timezone.now()
    visit.save(update_fields=["parents_told_at"])


class VisitViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    TenantViewSet,
):
    required_permissions: ClassVar = {
        "list": (VIEW, RECORD),
        "retrieve": (VIEW, RECORD),
        "create": RECORD,
        "update": RECORD,
        "partial_update": RECORD,
    }

    def _nurse(self) -> bool:
        return RECORD in self.actor()[2]

    def _parent(self) -> bool:
        return Role.PARENT in self.actor()[1] and not self._nurse()

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Any]]:
        if self._nurse() or self._parent():
            return VisitSerializer
        return TeacherVisitSerializer

    def get_queryset(self) -> QuerySet[Visit]:
        user, roles, perms = self.actor()
        qs = Visit.objects.select_related("student__arm__level")
        if not self._nurse():
            qs = qs.filter(student__in=visible_students(user, roles, perms))
        params = self.request.query_params
        if student := params.get("student"):
            qs = qs.filter(student_id=student)
        if params.get("now") == "1":
            qs = qs.filter(outcome="")
        if (day := params.get("date")) and self._nurse():
            try:
                qs = qs.filter(arrived_at__date=dt.date.fromisoformat(day))
            except ValueError as exc:
                raise ValidationError({"date": "Use YYYY-MM-DD."}) from exc
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("student", OpenApiTypes.UUID),
            OpenApiParameter("now", OpenApiTypes.STR),
            OpenApiParameter("date", OpenApiTypes.DATE),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        rows = list(self.get_queryset()[:300])
        names = {
            u.pk: u.get_full_name() or u.email
            for u in User.objects.filter(pk__in={r.seen_by for r in rows})
        }
        return Response(self.get_serializer_class()(rows, many=True, context={"names": names}).data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        visit = self.get_object()
        data = dict(self.get_serializer(visit).data)
        if self._nurse():
            # The pupil's standing medical notes, for whoever is treating them.
            data["medical_notes"] = visit.student.medical_notes
            with tenant_atomic():
                record_event(action="clinic.viewed", request=request, target=visit.student)
        return Response(data)

    def perform_create(self, serializer: Any) -> None:
        user, _, _ = self.actor()
        v = serializer.validated_data
        if v["student"].status != Student.Status.ACTIVE:
            raise ValidationError({"student": "This pupil isn't on roll."})
        tell, sms = v.pop("tell_parents", False), v.pop("sms", False)
        outcome = v.get("outcome", "")
        with tenant_atomic():
            visit = serializer.save(
                seen_by=user.pk,
                arrived_at=v.get("arrived_at") or timezone.now(),
                left_at=timezone.now() if outcome else None,
            )
            record_event(action="clinic.visit", request=self.request, target=visit.student)
        if tell or outcome in Visit.TELL_PARENTS:
            _tell_parents(visit, sms=sms)

    def perform_update(self, serializer: Any) -> None:
        v = serializer.validated_data
        tell, sms = v.pop("tell_parents", False), v.pop("sms", False)
        if "student" in v and v["student"] != serializer.instance.student:
            raise ValidationError({"student": "Log a new visit for a different pupil."})
        before = serializer.instance.outcome
        with tenant_atomic():
            visit = serializer.save()
            if visit.outcome and not visit.left_at:
                visit.left_at = timezone.now()
                visit.save(update_fields=["left_at"])
            record_event(action="clinic.updated", request=self.request, target=visit.student)
        ended_badly = visit.outcome in Visit.TELL_PARENTS and before != visit.outcome
        if tell or ended_badly:
            _tell_parents(visit, sms=sms)


class ClinicSummaryView(APIView):
    """The nurse's overview: today, who is in now, the last 30 days, frequent visitors."""

    required_permissions: ClassVar = {"GET": RECORD}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        today = timezone.localdate()
        since = today - dt.timedelta(days=30)
        recent = Visit.objects.filter(arrived_at__date__gte=since)
        labels = dict(Visit.Outcome.choices)
        frequent = (
            recent.values("student_id", "student__first_name", "student__last_name")
            .annotate(n=Count("pk"))
            .filter(n__gte=FREQUENT)
            .order_by("-n")[:20]
        )
        return Response(
            {
                "today": Visit.objects.filter(arrived_at__date=today).count(),
                "in_now": Visit.objects.filter(outcome="").count(),
                "last_30_days": recent.count(),
                "by_outcome": [
                    {
                        "outcome": r["outcome"],
                        "label": labels.get(r["outcome"], "Still in"),
                        "count": r["n"],
                    }
                    for r in recent.values("outcome").annotate(n=Count("pk")).order_by("-n")
                ],
                "sent_home": recent.filter(
                    Q(
                        outcome__in=[
                            Visit.Outcome.SENT_HOME,
                            Visit.Outcome.COLLECTED,
                            Visit.Outcome.REFERRED,
                        ]
                    )
                ).count(),
                "frequent": [
                    {
                        "student": str(r["student_id"]),
                        "name": f"{r['student__last_name']} {r['student__first_name']}",
                        "count": r["n"],
                    }
                    for r in frequent
                ],
            }
        )


class PupilHealthView(APIView):
    """The nurse looking up a pupil: their medical notes and recent visits."""

    required_permissions: ClassVar = {"GET": RECORD}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, student_id: str) -> Response:
        pupil = get_object_or_404(Student.objects.select_related("arm__level"), pk=student_id)
        if pupil.status != Student.Status.ACTIVE:
            raise PermissionDenied("This pupil isn't on roll.")
        with tenant_atomic():
            record_event(action="clinic.viewed", request=request, target=pupil)
        visits = Visit.objects.filter(student=pupil)[:20]
        return Response(
            {
                "student": str(pupil.pk),
                "name": pupil.full_name,
                "class": str(pupil.arm) if pupil.arm_id else "",
                "medical_notes": pupil.medical_notes,
                "visits": VisitSerializer(visits, many=True).data,
            }
        )
