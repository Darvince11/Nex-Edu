from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import ClassArm, ClassLevel
from apps.school.models import SchoolProfile
from core.rbac import Perm
from core.views import PublicEndpointMixin, TenantViewSet

from .. import services
from ..models import Application

APPLICANT_FIELDS = [
    "desired_level",
    "session",
    "first_name",
    "middle_name",
    "last_name",
    "date_of_birth",
    "gender",
    "previous_school",
    "guardian_name",
    "guardian_phone",
    "guardian_email",
    "guardian_relationship",
    "address",
]


class ApplicationSerializer(serializers.ModelSerializer[Application]):
    desired_level_name = serializers.CharField(source="desired_level.name", read_only=True)

    class Meta:
        model = Application
        fields: ClassVar = [
            "id",
            "reference",
            *APPLICANT_FIELDS,
            "desired_level_name",
            "status",
            "source",
            "review_notes",
            "entrance_score",
            "student_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar = [
            "reference",
            "status",
            "source",
            "student_id",
            "created_at",
            "updated_at",
        ]


class PublicApplicationSerializer(serializers.ModelSerializer[Application]):
    # Honeypot: humans never see or fill this field; bots usually do.
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Application
        fields: ClassVar = [*APPLICANT_FIELDS, "website"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["desired_level"].queryset = ClassLevel.objects.filter(is_active=True)  # type: ignore[attr-defined]


class StatusSerializer(serializers.Serializer):  # type: ignore[type-arg]
    status = serializers.ChoiceField(choices=Application.Status.choices)
    notes = serializers.CharField(required=False, default="", allow_blank=True, max_length=2000)


class EnrolSerializer(serializers.Serializer):  # type: ignore[type-arg]
    arm = serializers.PrimaryKeyRelatedField(queryset=ClassArm.objects.none())
    invite_guardian = serializers.BooleanField(default=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["arm"].queryset = ClassArm.objects.all()  # type: ignore[attr-defined]


class ApplicationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    TenantViewSet,
):
    serializer_class = ApplicationSerializer
    required_permissions: ClassVar = {
        "list": Perm.ADMISSIONS_VIEW,
        "retrieve": Perm.ADMISSIONS_VIEW,
        "create": Perm.ADMISSIONS_MANAGE,
        "update": Perm.ADMISSIONS_MANAGE,
        "partial_update": Perm.ADMISSIONS_MANAGE,
        "change_status": Perm.ADMISSIONS_MANAGE,
        "enrol": (Perm.ADMISSIONS_MANAGE,),
    }

    def get_queryset(self) -> QuerySet[Application]:
        qs = Application.objects.select_related("desired_level")
        if status_ := self.request.query_params.get("status"):
            qs = qs.filter(status=status_)
        if level := self.request.query_params.get("level"):
            qs = qs.filter(desired_level_id=level)
        return qs

    def perform_create(self, serializer: ApplicationSerializer) -> None:  # type: ignore[override]
        serializer.instance = services.submit_application(
            request=self.request,
            data=dict(serializer.validated_data),
            source=Application.Source.OFFICE,
        )

    @action(detail=True, methods=["post"])
    def change_status(self, request: Request, pk: str | None = None) -> Response:
        data = StatusSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        application = services.change_status(
            request=request,
            application=self.get_object(),
            status=data.validated_data["status"],
            notes=data.validated_data["notes"],
        )
        return Response(ApplicationSerializer(application).data)

    @action(detail=True, methods=["post"])
    def enrol(self, request: Request, pk: str | None = None) -> Response:
        data = EnrolSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _, roles, _ = self.actor()
        application = services.enrol(
            request=request,
            application=self.get_object(),
            arm=data.validated_data["arm"],
            granter_roles=roles,
            invite_guardian=data.validated_data["invite_guardian"],
        )
        return Response(ApplicationSerializer(application).data)


class PublicAdmissionView(PublicEndpointMixin, APIView):
    """The school's public online admission form (on its own subdomain).

    GET returns the form options; POST submits. Rate-limited per IP, with a
    honeypot field to drop bot submissions silently.
    """

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        if getattr(request, "tenant", None) is None:
            return Response({"detail": "School not found."}, status=404)
        profile = SchoolProfile.load()
        levels = ClassLevel.objects.filter(is_active=True).values("id", "name")
        return Response({"school": profile.name, "levels": list(levels)})

    @extend_schema(request=PublicApplicationSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        if getattr(request, "tenant", None) is None:
            return Response({"detail": "School not found."}, status=404)
        data = PublicApplicationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        fields = dict(data.validated_data)
        if fields.pop("website", ""):
            return Response({"reference": "APP-RECEIVED"}, status=status.HTTP_201_CREATED)
        application = services.submit_application(
            request=request, data=fields, source=Application.Source.ONLINE
        )
        return Response({"reference": application.reference}, status=status.HTTP_201_CREATED)
