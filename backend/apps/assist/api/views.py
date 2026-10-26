"""AI drafting help: a draft comes back for the person to edit; nothing is saved here."""

from __future__ import annotations

from typing import Any, ClassVar

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.selectors import is_form_teacher
from apps.assessments.models import ReportCard
from apps.students.selectors import visible_students
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.permissions import load_membership
from core.rbac import Perm

from .. import services

DRAFT = Perm.AI_DRAFT


def _unavailable(exc: services.DraftUnavailable) -> Response:
    return Response({"detail": str(exc), "code": "draft_unavailable"}, status=503)


class AssistStatusView(APIView):
    """Whether drafting can be used here, and how many drafts are left today."""

    required_permissions: ClassVar = {"GET": DRAFT}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        from django.conf import settings
        from django.utils import timezone

        from ..models import DraftLog

        start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        used = DraftLog.objects.filter(created_at__gte=start).count()
        return Response(
            {
                "configured": services.configured(),
                "left_today": max(settings.AI_DRAFTS_PER_DAY - used, 0),
            }
        )


class CommentDraftSerializer(serializers.Serializer[Any]):
    report_card = serializers.UUIDField()
    for_head = serializers.BooleanField(default=False)
    notes = serializers.CharField(max_length=500, allow_blank=True, default="")


class CommentDraftView(APIView):
    """A draft report-card comment, for whoever may write that comment."""

    required_permissions: ClassVar = {"POST": DRAFT}

    @extend_schema(request=CommentDraftSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = CommentDraftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        roles = load_membership(request)
        perms = getattr(request, "permissions", frozenset())
        card = get_object_or_404(
            ReportCard.objects.select_related("student", "term", "arm__level"),
            pk=data.validated_data["report_card"],
            student__in=visible_students(request.user, roles, perms),
        )
        for_head = data.validated_data["for_head"]
        if for_head and Perm.ASSESSMENTS_PUBLISH not in perms:
            raise PermissionDenied("Only the head teacher writes the head teacher's comment.")
        if (
            not for_head
            and Perm.ASSESSMENTS_PUBLISH not in perms
            and not is_form_teacher(request.user, card.arm_id)
        ):
            raise PermissionDenied("Only the class teacher writes this comment.")
        if not services.configured():
            return _unavailable(services.DraftUnavailable("Drafting isn't set up yet."))
        try:
            text = services.report_comment(
                card,
                for_head=for_head,
                notes=data.validated_data["notes"],
                user_id=request.user.pk,
            )
        except services.DraftUnavailable as exc:
            return _unavailable(exc)
        with tenant_atomic():
            record_event(action="assist.comment_drafted", request=request, target=card, after={})
        return Response({"draft": text})


class AnnouncementDraftSerializer(serializers.Serializer[Any]):
    notes = serializers.CharField(max_length=2000)
    audience = serializers.CharField(max_length=60, default="all parents")


class AnnouncementDraftView(APIView):
    """A draft announcement from rough notes, for people who can write announcements."""

    required_permissions: ClassVar = {"POST": DRAFT}

    @extend_schema(request=AnnouncementDraftSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        load_membership(request)
        granted = getattr(request, "permissions", frozenset())
        if not granted & {Perm.COMMUNICATION_SEND, Perm.COMMUNICATION_MANAGE}:
            raise PermissionDenied("Only people who write announcements can draft one.")
        data = AnnouncementDraftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if not services.configured():
            return _unavailable(services.DraftUnavailable("Drafting isn't set up yet."))
        try:
            draft = services.announcement(user_id=request.user.pk, **data.validated_data)
        except services.DraftUnavailable as exc:
            return _unavailable(exc)
        with tenant_atomic():
            record_event(action="assist.announcement_drafted", request=request, after={})
        return Response(draft)
