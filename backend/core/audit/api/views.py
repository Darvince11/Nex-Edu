from __future__ import annotations

from typing import ClassVar

from django.utils import timezone
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
        """?action= (exact), ?category= (action prefix, e.g. "assessments."),
        ?actor= (email contains), ?days=, ?target_id=."""
        queryset = AuditEvent.objects.all()
        params = self.request.query_params
        if action := params.get("action"):
            queryset = queryset.filter(action=action)
        if category := params.get("category"):
            queryset = queryset.filter(action__startswith=category)
        if actor := params.get("actor", "").strip():
            queryset = queryset.filter(actor_email__icontains=actor)
        if (days := params.get("days", "")).isdigit():
            since = timezone.now() - timezone.timedelta(days=int(days))
            queryset = queryset.filter(occurred_at__gte=since)
        if target_id := params.get("target_id"):
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
