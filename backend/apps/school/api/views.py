from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import Term
from apps.communication.models import MessagingSettings
from apps.finance.models import PaymentSettings
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.images import MAX_UPLOAD_BYTES
from core.permissions import load_membership
from core.rbac import Perm
from core.views import PublicEndpointMixin

from .. import insights, reports, services, setup
from ..models import SchoolProfile


class SchoolProfileSerializer(serializers.ModelSerializer[SchoolProfile]):
    has_logo = serializers.SerializerMethodField()

    class Meta:
        model = SchoolProfile
        # The logo's storage key is internal; it changes only through SchoolLogoView.
        exclude: ClassVar = [
            "id",
            "logo",
            "terms_accepted_at",
            "terms_accepted_by",
            "terms_version",
            "setup_hidden_at",
        ]
        read_only_fields: ClassVar = ["updated_at"]

    def get_has_logo(self, obj: SchoolProfile) -> bool:
        return bool(obj.logo)


class PaymentSettingsSerializer(serializers.ModelSerializer[PaymentSettings]):
    class Meta:
        model = PaymentSettings
        exclude: ClassVar = ["id"]


class MessagingSettingsSerializer(serializers.ModelSerializer[MessagingSettings]):
    class Meta:
        model = MessagingSettings
        exclude: ClassVar = ["id"]


class _SingletonView(APIView):
    model: type
    serializer_class: type[serializers.ModelSerializer]  # type: ignore[type-arg]
    audit_action = ""

    def get(self, request: Request) -> Response:
        return Response(self.serializer_class(self.model.load()).data)

    def patch(self, request: Request) -> Response:
        instance = self.model.load()
        serializer = self.serializer_class(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with tenant_atomic():
            serializer.save()
            record_event(
                action=self.audit_action, request=request, after=dict(serializer.validated_data)
            )
        return Response(serializer.data)


class SchoolProfileView(_SingletonView):
    model = SchoolProfile
    serializer_class = SchoolProfileSerializer
    audit_action = "school.profile_updated"
    required_permissions: ClassVar = {"GET": Perm.COMMUNICATION_VIEW, "PATCH": Perm.SCHOOL_MANAGE}


class PaymentSettingsView(_SingletonView):
    model = PaymentSettings
    serializer_class = PaymentSettingsSerializer
    audit_action = "finance.settings_updated"
    required_permissions: ClassVar = {"GET": Perm.FINANCE_VIEW, "PATCH": Perm.FINANCE_MANAGE}


class MessagingSettingsView(_SingletonView):
    model = MessagingSettings
    serializer_class = MessagingSettingsSerializer
    audit_action = "communication.settings_updated"
    required_permissions: ClassVar = {
        "GET": Perm.COMMUNICATION_MANAGE,
        "PATCH": Perm.COMMUNICATION_MANAGE,
    }


def _logo_response() -> HttpResponse:
    profile = SchoolProfile.load()
    if not profile.logo or not default_storage.exists(profile.logo):
        return HttpResponse(status=404)
    response = FileResponse(default_storage.open(profile.logo, "rb"), content_type="image/png")
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class LogoUploadSerializer(serializers.Serializer):  # type: ignore[type-arg]
    logo = serializers.FileField(max_length=200)


class SchoolLogoView(APIView):
    """The school's own logo: anyone in the school sees it; only the proprietor changes it."""

    parser_classes = [MultiPartParser]
    required_permissions: ClassVar = {
        "GET": Perm.COMMUNICATION_VIEW,
        "PUT": Perm.SCHOOL_BRANDING,
        "DELETE": Perm.SCHOOL_BRANDING,
    }

    @extend_schema(responses={(200, "image/png"): OpenApiTypes.BINARY})
    def get(self, request: Request) -> HttpResponse:
        return _logo_response()

    @extend_schema(request=LogoUploadSerializer, responses=SchoolProfileSerializer)
    def put(self, request: Request) -> Response:
        upload = LogoUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        file = upload.validated_data["logo"]
        if file.size > MAX_UPLOAD_BYTES:
            return Response({"logo": ["The logo must be 1 MB or smaller."]}, status=400)
        profile = services.set_logo(request=request, data=file.read(MAX_UPLOAD_BYTES + 1))
        return Response(SchoolProfileSerializer(profile).data)

    @extend_schema(responses=SchoolProfileSerializer)
    def delete(self, request: Request) -> Response:
        return Response(SchoolProfileSerializer(services.remove_logo(request=request)).data)


class PublicSchoolLogoView(PublicEndpointMixin, APIView):
    """The logo on the school's public admission page. Only the logo, nothing else."""

    @extend_schema(responses={(200, "image/png"): OpenApiTypes.BINARY})
    def get(self, request: Request) -> HttpResponse:
        if getattr(request, "tenant", None) is None:
            return HttpResponse(status=404)
        return _logo_response()


class InsightsView(APIView):
    """Dashboard charts. ?term= (default: current term) and, for teachers and
    leaders, ?arm= to narrow attendance and results to one class."""

    required_permissions: ClassVar = {"GET": Perm.COMMUNICATION_VIEW}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        roles = load_membership(request)
        params = request.query_params
        term = (
            Term.objects.filter(pk=params["term"]).first()
            if params.get("term", "").isdigit()
            else Term.objects.filter(is_current=True).first()
        )
        return Response(
            insights.insights(
                user=request.user,
                roles=roles,
                permissions=getattr(request, "permissions", frozenset()),
                term=term,
                arm=params.get("arm") or None,
            )
        )


class SetupChecklistView(APIView):
    """The new-school checklist. GET for leaders; POST {"action": "accept_terms"}
    (proprietor), "hide" or "show" (leaders)."""

    required_permissions: ClassVar = {"GET": Perm.SCHOOL_MANAGE, "POST": Perm.SCHOOL_MANAGE}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        load_membership(request)
        return Response(setup.checklist(request.tenant, request.permissions))  # type: ignore[attr-defined]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        load_membership(request)
        permissions = request.permissions  # type: ignore[attr-defined]
        action = request.data.get("action")
        with tenant_atomic():
            if action == "accept_terms":
                if Perm.SCHOOL_LEGAL not in permissions:
                    raise PermissionDenied("Only the proprietor accepts the terms for the school.")
                setup.accept_terms(user=request.user)
                record_event(
                    action="school.terms_accepted",
                    request=request,
                    after={"version": settings.TERMS_VERSION},
                )
            elif action in ("hide", "show"):
                setup.set_hidden(action == "hide")
            else:
                return Response({"detail": "Unknown action."}, status=400)
        return Response(setup.checklist(request.tenant, permissions))  # type: ignore[attr-defined]


class ModuleSwitchSerializer(serializers.Serializer):  # type: ignore[type-arg]
    code = serializers.CharField(max_length=30, required=False, default="")
    active = serializers.BooleanField(required=False)
    confirm = serializers.BooleanField(required=False, default=False)
    action = serializers.ChoiceField(choices=["switch", "confirm_choices"], default="switch")


class ModulesView(APIView):
    """The school's modules. Leaders see them; only the proprietor switches them or
    confirms the choices (POST {"code", "active", "confirm"} or {"action": "confirm_choices"})."""

    required_permissions: ClassVar = {"GET": Perm.SCHOOL_MANAGE, "POST": Perm.SCHOOL_MODULES}

    def _payload(self, request: Request) -> dict[str, object]:
        from control_plane import modules

        tenant = request.tenant  # type: ignore[attr-defined]
        return {
            "modules": modules.catalogue(tenant),
            "history": modules.history(tenant),
            "confirmed": modules.choices_confirmed(tenant),
        }

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(self._payload(request))

    @extend_schema(request=ModuleSwitchSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        from control_plane import modules

        data = ModuleSwitchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        tenant = request.tenant  # type: ignore[attr-defined]
        if v["action"] == "confirm_choices":
            modules.confirm_choices(tenant=tenant, request=request)
        else:
            if "active" not in v or not v["code"]:
                return Response({"detail": "Say which module and whether it's on."}, status=400)
            modules.set_active(
                tenant=tenant,
                code=v["code"],
                active=v["active"],
                request=request,
                confirm=v["confirm"],
            )
        return Response(self._payload(request))


class ReportView(APIView):
    """Class lists, attendance and results: ?arm= (default every class the person may
    see), ?term= (default the current term), ?export=csv or pdf."""

    required_permissions: ClassVar = {"GET": (Perm.REPORTS_VIEW, Perm.REPORTS_OWN_CLASS)}

    @extend_schema(
        parameters=[
            OpenApiParameter("arm", OpenApiTypes.UUID),
            OpenApiParameter("term", OpenApiTypes.INT),
            OpenApiParameter("export", OpenApiTypes.STR, enum=["csv", "pdf"]),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request, kind: str) -> HttpResponse | Response:
        from apps.academics.services import current_term

        if kind not in reports.KINDS:
            raise NotFound("No such report.")
        load_membership(request)
        arms = reports.report_arms(request.user, getattr(request, "permissions", frozenset()))
        if arm := request.query_params.get("arm"):
            arms = arms.filter(pk=arm)
        chosen = list(arms)
        if not chosen:
            raise NotFound("No class to report on.")
        term = (
            Term.objects.select_related("session").filter(pk=request.query_params["term"]).first()
            if request.query_params.get("term", "").isdigit()
            else current_term()
        )
        if term is None and kind != "class-list":
            raise NotFound("Choose a term.")
        report = (
            reports.class_list(chosen)
            if kind == "class-list"
            else reports.attendance(term, chosen)
            if kind == "attendance"
            else reports.results(term, chosen)
        )
        export = request.query_params.get("export")
        if export not in ("csv", "pdf"):
            return Response({**report, "term": term.pk if term else None})
        record_event(
            action="report.exported",
            request=request,
            after={"report": kind, "format": export, "classes": [str(a) for a in chosen]},
        )
        name = f"{kind}-{'all' if len(chosen) > 1 else str(chosen[0]).replace(' ', '-').lower()}"
        if export == "csv":
            response = HttpResponse(reports.to_csv(report), content_type="text/csv; charset=utf-8")
        else:
            response = HttpResponse(reports.to_pdf(report), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{name}.{export}"'
        return response
