"""Turning browser push notifications on and off, per browser, for the signed-in person."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from control_plane import push
from control_plane.models import PushSubscription


class PushSubscriptionSerializer(serializers.Serializer[Any]):
    endpoint = serializers.URLField(max_length=1000)
    p256dh = serializers.CharField(max_length=200)
    auth = serializers.CharField(max_length=100)

    def validate_endpoint(self, value: str) -> str:
        if not value.startswith("https://"):
            raise serializers.ValidationError("A push address must use https.")
        return value


class PushView(APIView):
    """GET: whether push is available (and the key the browser needs). POST: this
    browser wants notifications. DELETE (?endpoint=): it doesn't any more."""

    permission_classes = [IsAuthenticated]
    tenant_scoped = False

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(
            {
                "enabled": push.enabled(),
                "public_key": settings.WEB_PUSH_VAPID_PUBLIC_KEY if push.enabled() else "",
                "browsers": PushSubscription.objects.filter(user=request.user).count(),
            }
        )

    @extend_schema(request=PushSubscriptionSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        if not push.enabled():
            return Response({"detail": "Notifications aren't available yet."}, status=400)
        data = PushSubscriptionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        push.subscribe(
            request.user,
            user_agent=request.headers.get("User-Agent", ""),
            **data.validated_data,
        )
        return Response({"subscribed": True}, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request: Request) -> Response:
        push.unsubscribe(request.user, request.query_params.get("endpoint", ""))
        return Response(status=status.HTTP_204_NO_CONTENT)
