"""Accreditation and compliance (proprietor and head teacher): the checklist and
its evidence. Evidence files sit under the school's own storage prefix and only
people who manage compliance can download them."""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.files.storage import default_storage
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.academics.api.views import AuditedCrudViewSet
from apps.lms.api.views import _download, _store
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm

from .. import services
from ..models import Evidence, Requirement

MANAGE = Perm.COMPLIANCE_MANAGE


class EvidenceSerializer(serializers.ModelSerializer[Evidence]):
    class Meta:
        model = Evidence
        fields: ClassVar = ["id", "name", "size", "uploaded_at"]


class RequirementSerializer(serializers.ModelSerializer[Requirement]):
    state = serializers.SerializerMethodField()
    area_label = serializers.CharField(source="get_area_display", read_only=True)
    evidence = EvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = Requirement
        fields: ClassVar = [
            "id",
            "area",
            "area_label",
            "title",
            "authority",
            "notes",
            "due_on",
            "renew_every_months",
            "status",
            "completed_on",
            "state",
            "evidence",
        ]
        read_only_fields: ClassVar = ["status", "completed_on"]
        extra_kwargs: ClassVar = {"renew_every_months": {"min_value": 1, "max_value": 120}}

    def get_state(self, obj: Requirement) -> str:
        return obj.state(timezone.localdate())


class EvidenceUploadSerializer(serializers.Serializer[Any]):
    file = serializers.FileField()


class RequirementViewSet(AuditedCrudViewSet):
    serializer_class = RequirementSerializer
    audit_name = "compliance.requirement"
    required_permissions: ClassVar = dict.fromkeys(
        (
            "list",
            "retrieve",
            "create",
            "update",
            "partial_update",
            "destroy",
            "starter",
            "complete",
            "reopen",
            "upload",
            "evidence_file",
            "remove_evidence",
        ),
        MANAGE,
    )

    def get_queryset(self) -> Any:
        return Requirement.objects.prefetch_related("evidence")

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def starter(self, request: Request) -> Response:
        """Add the usual items for a Ghanaian basic school."""
        with tenant_atomic():
            added = services.add_starter()
            record_event(action="compliance.starter_added", request=request, after={"added": added})
        return Response({"added": added}, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=RequirementSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: str | None = None) -> Response:
        item = self.get_object()
        with tenant_atomic():
            services.complete(item, on=timezone.localdate())
            record_event(
                action="compliance.completed",
                request=request,
                target=item,
                after={"title": item.title, "next_due": str(item.due_on or "")},
            )
        return Response(RequirementSerializer(self.get_queryset().get(pk=item.pk)).data)

    @extend_schema(request=None, responses=RequirementSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request: Request, pk: str | None = None) -> Response:
        item = self.get_object()
        with tenant_atomic():
            item.status, item.completed_on = Requirement.Status.OPEN, None
            item.save(update_fields=["status", "completed_on"])
            record_event(action="compliance.reopened", request=request, target=item)
        return Response(RequirementSerializer(self.get_queryset().get(pk=item.pk)).data)

    @extend_schema(
        request={"multipart/form-data": EvidenceUploadSerializer}, responses=EvidenceSerializer
    )
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def upload(self, request: Request, pk: str | None = None) -> Response:
        item = self.get_object()
        data = EvidenceUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["file"]
        with tenant_atomic():
            key, name = _store(upload, f"compliance/{item.pk}")
            evidence = Evidence.objects.create(
                requirement=item,
                name=name,
                file_key=key,
                size=upload.size,
                uploaded_by=request.user.pk,
            )
            record_event(
                action="compliance.evidence_added",
                request=request,
                target=item,
                after={"file": name},
            )
        return Response(EvidenceSerializer(evidence).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[OpenApiParameter("evidence_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"], url_path=r"evidence/(?P<evidence_id>[0-9a-f-]{36})")
    def evidence_file(self, request: Request, pk: str | None = None, evidence_id: str = "") -> Any:
        item = self.get_object()
        evidence = item.evidence.filter(pk=evidence_id).first()
        if evidence is None:
            return Response({"detail": "Not found."}, status=404)
        return _download(request, evidence.file_key, evidence.name)

    @extend_schema(
        request=None,
        parameters=[OpenApiParameter("evidence_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        responses={204: None},
    )
    @action(
        detail=True, methods=["delete"], url_path=r"evidence/(?P<evidence_id>[0-9a-f-]{36})/remove"
    )
    def remove_evidence(
        self, request: Request, pk: str | None = None, evidence_id: str = ""
    ) -> Response:
        item = self.get_object()
        evidence = item.evidence.filter(pk=evidence_id).first()
        if evidence is None:
            return Response({"detail": "Not found."}, status=404)
        with tenant_atomic():
            record_event(
                action="compliance.evidence_removed",
                request=request,
                target=item,
                before={"file": evidence.name},
            )
            evidence.delete()
            default_storage.delete(evidence.file_key)
        return Response(status=status.HTTP_204_NO_CONTENT)
