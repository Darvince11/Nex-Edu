"""A signed-in owner asks for a school workspace. No school is selected here."""

from __future__ import annotations

from typing import Any, ClassVar

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from control_plane.models import SchoolRegistration
from control_plane.registrations import slug_problem, submit_registration
from core.permissions import HasVerifiedEmail


class RegistrationSerializer(serializers.ModelSerializer[SchoolRegistration]):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    decision_note = serializers.SerializerMethodField()
    school_slug = serializers.SlugRelatedField(source="tenant", slug_field="slug", read_only=True)
    expected_pupils = serializers.IntegerField(min_value=1, max_value=10_000)

    class Meta:
        model = SchoolRegistration
        fields: ClassVar = [
            "id",
            "school_name",
            "slug",
            "school_type",
            "region",
            "town",
            "phone",
            "expected_pupils",
            "status",
            "status_label",
            "decision_note",
            "school_slug",
            "created_at",
        ]
        read_only_fields: ClassVar = ["id", "status", "created_at"]
        extra_kwargs: ClassVar = {"slug": {"validators": []}}  # checked in the service

    def get_decision_note(self, obj: SchoolRegistration) -> str:
        # Only a rejection's note is written for the applicant.
        return obj.review_note if obj.status == SchoolRegistration.Status.REJECTED else ""


class RegistrationListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasVerifiedEmail]
    tenant_scoped = False
    throttle_scope = "registration"

    def get_throttles(self) -> list[BaseThrottle]:
        throttles = super().get_throttles()
        return [*throttles, ScopedRateThrottle()] if self.request.method == "POST" else throttles

    @extend_schema(responses=RegistrationSerializer(many=True))
    def get(self, request: Request) -> Response:
        mine = SchoolRegistration.objects.filter(owner=request.user).select_related("tenant")
        return Response(RegistrationSerializer(mine, many=True).data)

    @extend_schema(request=RegistrationSerializer, responses={201: RegistrationSerializer})
    def post(self, request: Request) -> Response:
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        registration = submit_registration(
            owner=request.user, data=serializer.validated_data, request=request
        )
        return Response(RegistrationSerializer(registration).data, status=status.HTTP_201_CREATED)


class SlugAvailabilitySerializer(serializers.Serializer[Any]):
    available = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True)


class SlugAvailabilityView(APIView):
    permission_classes = [IsAuthenticated, HasVerifiedEmail]
    tenant_scoped = False

    @extend_schema(responses=SlugAvailabilitySerializer)
    def get(self, request: Request) -> Response:
        problem = slug_problem(request.query_params.get("slug", ""))
        return Response({"available": problem is None, "reason": problem or ""})
