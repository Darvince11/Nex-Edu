from __future__ import annotations

from typing import ClassVar

from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit.models import AuditEvent
from core.audit.services import verify_chain
from core.rbac import Perm


class AuditEventSerializer(serializers.ModelSerializer[AuditEvent]):
    class Meta:
        model = AuditEvent
        fields: ClassVar = [
            "seq",
            "occurred_at",
            "actor_id",
            "actor_email",
            "action",
            "target_type",
            "target_id",
            "ip",
            "request_id",
            "before",
            "after",
            "reason",
            "hash",
        ]


class AuditPagination(CursorPagination):
    ordering = "-seq"
    page_size = 100


class AuditEventListView(generics.ListAPIView[AuditEvent]):
    serializer_class = AuditEventSerializer
    pagination_class = AuditPagination
    required_permissions: ClassVar = {"GET": Perm.AUDIT_VIEW}

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = AuditEvent.objects.all()
        if action := self.request.query_params.get("action"):
            queryset = queryset.filter(action=action)
        if target_id := self.request.query_params.get("target_id"):
            queryset = queryset.filter(target_id=target_id)
        return queryset


class ChainReportSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    checked = serializers.IntegerField()
    first_bad_seq = serializers.IntegerField(allow_null=True)
    reason = serializers.CharField(allow_blank=True)


class AuditVerifyView(APIView):
    required_permissions: ClassVar = {"GET": Perm.AUDIT_VIEW}

    @extend_schema(responses=ChainReportSerializer)
    def get(self, request: Request) -> Response:
        report = verify_chain()
        return Response(
            {
                "valid": report.valid,
                "checked": report.checked,
                "first_bad_seq": report.first_bad_seq,
                "reason": report.reason,
            }
        )
