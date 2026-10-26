"""Calendar links: a person's own private feed for the school calendar."""

from __future__ import annotations

from typing import ClassVar

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from control_plane import calendar_feed
from control_plane.audit import record_platform_event
from control_plane.models import CalendarFeed
from control_plane.tenancy import require_tenant
from core.rbac import Perm
from core.views import PublicEndpointMixin


class MyCalendarFeedView(APIView):
    """GET: whether you have a link. POST: a new link (shown once; the old one stops
    working). DELETE: turn the link off."""

    required_permissions: ClassVar = {
        "GET": Perm.CALENDAR_VIEW,
        "POST": Perm.CALENDAR_VIEW,
        "DELETE": Perm.CALENDAR_VIEW,
    }

    def _feed(self, request: Request) -> CalendarFeed | None:
        return CalendarFeed.objects.filter(user=request.user, tenant=require_tenant()).first()

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        feed = self._feed(request)
        return Response(
            {
                "active": feed is not None,
                "created_at": feed.created_at if feed else None,
                "last_used_at": feed.last_used_at if feed else None,
            }
        )

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        token = calendar_feed.issue(request.user, require_tenant())
        record_platform_event(
            action="calendar.feed_issued", request=request, tenant=require_tenant()
        )
        return Response({"url": calendar_feed.url_for(token)}, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request: Request) -> Response:
        CalendarFeed.objects.filter(user=request.user, tenant=require_tenant()).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicCalendarFeedView(PublicEndpointMixin, APIView):
    """The feed itself. Calendar apps can't sign in, so the unguessable token in the
    address is the key; it works only while the person still belongs to the school."""

    tenant_scoped = False

    @extend_schema(responses={(200, "text/calendar"): OpenApiTypes.STR})
    def get(self, request: Request, token: str) -> HttpResponse:
        feed = calendar_feed.find(token)
        if feed is None:
            return HttpResponse("Not found", status=404, content_type="text/plain")
        response = HttpResponse(
            calendar_feed.render(feed), content_type="text/calendar; charset=utf-8"
        )
        response["Content-Disposition"] = f'inline; filename="{feed.tenant.slug}.ics"'
        response["Cache-Control"] = "private, max-age=900"
        return response
