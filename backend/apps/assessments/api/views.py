from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from django.db.models import QuerySet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.api.views import AuditedCrudViewSet
from apps.academics.models import ClassArm, Subject, Term
from apps.academics.selectors import is_form_teacher
from apps.students.models import Student
from apps.students.selectors import visible_students
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.files import tenant_file_response
from core.permissions import load_membership
from core.rbac import STAFF_ROLES, Perm
from core.views import TenantViewSet

from .. import services
from ..models import AssessmentComponent, GradeBand, ReportCard

MANAGE = Perm.ASSESSMENTS_MANAGE
CONFIG_PERMS: dict[str, Any] = {
    "list": Perm.ASSESSMENTS_VIEW,
    "retrieve": Perm.ASSESSMENTS_VIEW,
    "create": MANAGE,
    "update": MANAGE,
    "partial_update": MANAGE,
    "destroy": MANAGE,
}


def _perms(request: Request) -> frozenset[str]:
    load_membership(request)
    return getattr(request, "permissions", frozenset())


class ComponentSerializer(serializers.ModelSerializer[AssessmentComponent]):
    class Meta:
        model = AssessmentComponent
        fields: ClassVar = ["id", "name", "code", "max_score", "order", "is_active"]


class GradeBandSerializer(serializers.ModelSerializer[GradeBand]):
    class Meta:
        model = GradeBand
        fields: ClassVar = ["id", "section", "grade", "min_score", "max_score", "remark", "points"]


class ComponentViewSet(AuditedCrudViewSet):
    serializer_class = ComponentSerializer
    audit_name = "assessments.component"
    required_permissions: ClassVar = CONFIG_PERMS

    def get_queryset(self) -> QuerySet[AssessmentComponent]:
        return AssessmentComponent.objects.all()


class GradeBandViewSet(AuditedCrudViewSet):
    serializer_class = GradeBandSerializer
    audit_name = "assessments.grade_band"
    required_permissions: ClassVar = CONFIG_PERMS

    def get_queryset(self) -> QuerySet[GradeBand]:
        return GradeBand.objects.all()


class ScoreEntrySerializer(serializers.Serializer):  # type: ignore[type-arg]
    student = serializers.UUIDField()
    component = serializers.IntegerField()
    score = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)


class ScoreSheetSerializer(serializers.Serializer):  # type: ignore[type-arg]
    arm = serializers.UUIDField()
    subject = serializers.IntegerField()
    term = serializers.IntegerField()
    entries = ScoreEntrySerializer(many=True, max_length=2000)


class ScoreSheetView(APIView):
    """GET ?arm=&subject=&term= returns the grid; POST saves changed cells."""

    required_permissions: ClassVar = {
        "GET": (Perm.ASSESSMENTS_RECORD, MANAGE),
        "POST": (Perm.ASSESSMENTS_RECORD, MANAGE),
    }

    def _targets(self, params: Any) -> tuple[ClassArm, Subject, Term]:
        return (
            get_object_or_404(ClassArm.objects.select_related("level"), pk=params.get("arm")),
            get_object_or_404(Subject, pk=params.get("subject")),
            get_object_or_404(Term, pk=params.get("term")),
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        arm, subject, term = self._targets(request.query_params)
        if not services.can_record(request.user, _perms(request), arm, subject):
            raise PermissionDenied(
                "You can only enter scores for subjects you teach in this class."
            )
        return Response(services.score_sheet(arm, subject, term))

    @extend_schema(request=ScoreSheetSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = ScoreSheetSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        arm, subject, term = self._targets(data.validated_data)
        result = services.record_scores(
            request=request,
            user=request.user,
            permissions=_perms(request),
            arm=arm,
            subject=subject,
            term=term,
            entries=[dict(e) for e in data.validated_data["entries"]],
        )
        return Response(result)


class ArmTermSerializer(serializers.Serializer):  # type: ignore[type-arg]
    arm = serializers.UUIDField()
    term = serializers.IntegerField()


class ComputeResultsView(APIView):
    required_permissions: ClassVar = {"POST": Perm.ASSESSMENTS_PUBLISH}

    @extend_schema(request=ArmTermSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = ArmTermSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        arm = get_object_or_404(
            ClassArm.objects.select_related("level"), pk=data.validated_data["arm"]
        )
        term = get_object_or_404(Term, pk=data.validated_data["term"])
        return Response(services.compute_results(request=request, arm=arm, term=term))


class PublishResultsView(APIView):
    required_permissions: ClassVar = {"POST": Perm.ASSESSMENTS_PUBLISH}

    @extend_schema(request=ArmTermSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = ArmTermSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        arm = get_object_or_404(ClassArm, pk=data.validated_data["arm"])
        term = get_object_or_404(Term, pk=data.validated_data["term"])
        return Response(
            {"published": services.publish_results(request=request, arm=arm, term=term)}
        )


class AmendSerializer(serializers.Serializer):  # type: ignore[type-arg]
    student = serializers.UUIDField()
    subject = serializers.IntegerField()
    term = serializers.IntegerField()
    component = serializers.IntegerField()
    score = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal(0))
    reason = serializers.CharField(max_length=500)


class AmendScoreView(APIView):
    required_permissions: ClassVar = {"POST": Perm.ASSESSMENTS_AMEND}

    @extend_schema(request=AmendSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = AmendSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        score = services.amend_score(
            request=request,
            user=request.user,
            permissions=_perms(request),
            student=get_object_or_404(
                Student.objects.select_related("arm__level"), pk=v["student"]
            ),
            subject=get_object_or_404(Subject, pk=v["subject"]),
            term=get_object_or_404(Term, pk=v["term"]),
            component=get_object_or_404(AssessmentComponent, pk=v["component"]),
            score=v["score"],
            reason=v["reason"],
        )
        return Response({"score": str(score.score)})


class ReportCardSerializer(serializers.ModelSerializer[ReportCard]):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    arm_label = serializers.CharField(source="arm.__str__", read_only=True)
    term_label = serializers.CharField(source="term.__str__", read_only=True)
    position_label = serializers.SerializerMethodField()
    has_pdf = serializers.SerializerMethodField()

    class Meta:
        model = ReportCard
        fields: ClassVar = [
            "id",
            "student",
            "student_name",
            "admission_number",
            "term",
            "term_label",
            "arm",
            "arm_label",
            "lines",
            "total_score",
            "average",
            "position",
            "position_label",
            "class_size",
            "aggregate",
            "days_present",
            "days_open",
            "form_teacher_comment",
            "principal_comment",
            "status",
            "computed_at",
            "published_at",
            "has_pdf",
        ]
        read_only_fields: ClassVar = [
            f for f in fields if f not in ("form_teacher_comment", "principal_comment")
        ]

    def get_position_label(self, obj: ReportCard) -> str:
        return f"{services.ordinal(obj.position)} of {obj.class_size}" if obj.position else ""

    def get_has_pdf(self, obj: ReportCard) -> bool:
        return bool(obj.pdf_path) and not obj.needs_regeneration


class ReportCardViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, TenantViewSet
):
    """Staff see drafts for students in their scope; parents and students see only
    published cards for themselves / their children."""

    serializer_class = ReportCardSerializer
    required_permissions: ClassVar = {
        "list": Perm.ASSESSMENTS_VIEW,
        "retrieve": Perm.ASSESSMENTS_VIEW,
        "pdf": Perm.ASSESSMENTS_VIEW,
        "partial_update": (Perm.ASSESSMENTS_RECORD, Perm.ASSESSMENTS_PUBLISH),
        "update": (Perm.ASSESSMENTS_RECORD, Perm.ASSESSMENTS_PUBLISH),
    }

    def get_queryset(self) -> QuerySet[ReportCard]:
        user, roles, _ = self.actor()
        students = visible_students(user, roles)
        qs = ReportCard.objects.filter(student__in=students).select_related(
            "student", "term__session", "arm__level"
        )
        if not roles & STAFF_ROLES:
            qs = qs.filter(status=ReportCard.Status.PUBLISHED)
        params = self.request.query_params
        if term := params.get("term"):
            qs = qs.filter(term_id=term)
        if arm := params.get("arm"):
            qs = qs.filter(arm_id=arm)
        if student := params.get("student"):
            qs = qs.filter(student_id=student)
        return qs.order_by("position", "student__last_name")

    def perform_update(self, serializer: ReportCardSerializer) -> None:  # type: ignore[override]
        card = serializer.instance
        if card is None:
            raise PermissionDenied("Report card not found.")
        user, _, perms = self.actor()
        changes = dict(serializer.validated_data)
        if "principal_comment" in changes and Perm.ASSESSMENTS_PUBLISH not in perms:
            raise PermissionDenied("Only the head teacher can write the head teacher's comment.")
        if (
            "form_teacher_comment" in changes
            and Perm.ASSESSMENTS_PUBLISH not in perms
            and not is_form_teacher(user, card.arm_id)
        ):
            raise PermissionDenied("Only the class teacher can write this comment.")
        with tenant_atomic():
            card = serializer.save(
                needs_regeneration=card.status == ReportCard.Status.PUBLISHED
                or card.needs_regeneration
            )
            record_event(
                action="assessments.comment_updated",
                request=self.request,
                target=card,
                after=changes,
            )
        if card.status == ReportCard.Status.PUBLISHED:
            services._schedule_pdfs(card.arm, card.term)

    @action(detail=True, methods=["get"])
    def pdf(self, request: Request, pk: str | None = None) -> HttpResponse:
        card = self.get_object()
        if not card.pdf_path or card.needs_regeneration:
            return Response(
                {"detail": "The PDF is still being prepared. Try again shortly."}, status=409
            )  # type: ignore[return-value]
        filename = f"report-{card.student.admission_number.replace('/', '-')}-{card.term_id}.pdf"
        return tenant_file_response(
            card.pdf_path,
            filename=filename,
            content_type="application/pdf",
            as_link=request.query_params.get("link") == "1",
        )
