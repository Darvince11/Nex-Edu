from __future__ import annotations

from typing import ClassVar

from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.communication.models import MessagingSettings
from apps.finance.models import PaymentSettings
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm

from ..models import SchoolProfile


class SchoolProfileSerializer(serializers.ModelSerializer[SchoolProfile]):
    class Meta:
        model = SchoolProfile
        exclude: ClassVar = ["id"]
        read_only_fields: ClassVar = ["updated_at"]


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
