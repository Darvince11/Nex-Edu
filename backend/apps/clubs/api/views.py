"""Clubs and sports. School leaders set up clubs and choose patrons; a patron runs
their own club's members and activities. Parents and pupils see the clubs, their
own (or their children's) memberships and what's coming up, never other pupils'
names."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.academics.api.views import AuditedCrudViewSet
from apps.students.models import Student
from apps.students.selectors import visible_students
from control_plane.models import Membership as SchoolMembership
from control_plane.models import User
from control_plane.tenancy import require_tenant, tenant_atomic
from core.audit.services import record_event
from core.rbac import STAFF_ROLES, Perm
from core.views import TenantViewSet

from ..models import Activity, Club, Membership, Patron

VIEW, MANAGE = Perm.CLUBS_VIEW, Perm.CLUBS_MANAGE


def _names(user_ids: set[Any]) -> dict[Any, str]:
    return {u.pk: u.get_full_name() or u.email for u in User.objects.filter(pk__in=user_ids)}


def _is_staff(roles: Any) -> bool:
    return bool(set(roles) & STAFF_ROLES)


def can_run(view: TenantViewSet, club: Club) -> bool:
    user, _, perms = view.actor()
    return MANAGE in perms or Patron.objects.filter(club=club, user_id=user.pk).exists()


def _require_run(view: TenantViewSet, club: Club) -> None:
    if not can_run(view, club):
        raise PermissionDenied("Only the club's patrons and school leaders can do this.")


class ClubSerializer(serializers.ModelSerializer[Club]):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    member_count = serializers.IntegerField(read_only=True, default=0)
    patrons = serializers.SerializerMethodField()
    i_run = serializers.SerializerMethodField()
    my_children = serializers.SerializerMethodField()

    class Meta:
        model = Club
        fields: ClassVar = [
            "id",
            "name",
            "kind",
            "kind_label",
            "description",
            "meets",
            "capacity",
            "is_active",
            "member_count",
            "patrons",
            "i_run",
            "my_children",
        ]

    def get_patrons(self, obj: Club) -> list[dict[str, str]]:
        names = self.context.get("names", {})
        return [{"id": str(p.user_id), "name": names.get(p.user_id, "")} for p in obj.patrons.all()]

    def get_i_run(self, obj: Club) -> bool:
        user_id = self.context["request"].user.pk
        return any(p.user_id == user_id for p in obj.patrons.all())

    def get_my_children(self, obj: Club) -> list[str]:
        """Names of the caller's own children (or the pupil themselves) in this club."""
        return self.context.get("mine", {}).get(obj.pk, [])


class ClubMemberSerializer(serializers.Serializer):  # type: ignore[type-arg]
    student = serializers.UUIDField()
    title = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")


class ClubPatronSerializer(serializers.Serializer):  # type: ignore[type-arg]
    user = serializers.UUIDField()


class ActivitySerializer(serializers.ModelSerializer[Activity]):
    club_name = serializers.CharField(source="club.name", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Activity
        fields: ClassVar = [
            "id",
            "club",
            "club_name",
            "title",
            "kind",
            "kind_label",
            "date",
            "starts_at",
            "venue",
            "opponent",
            "result",
            "notes",
        ]
        read_only_fields: ClassVar = ["club"]


class ClubViewSet(AuditedCrudViewSet):
    serializer_class = ClubSerializer
    audit_name = "club"
    required_permissions: ClassVar = {
        "list": VIEW,
        "retrieve": VIEW,
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
        "add_member": VIEW,
        "remove_member": VIEW,
        "add_patron": MANAGE,
        "remove_patron": MANAGE,
        "add_activity": VIEW,
    }

    def get_queryset(self) -> QuerySet[Club]:
        _, _, perms = self.actor()
        qs = Club.objects.prefetch_related("patrons").annotate(
            member_count=Count("members", filter=Q(members__left_on__isnull=True))
        )
        if MANAGE not in perms or self.request.query_params.get("all") != "1":
            qs = qs.filter(is_active=True)
        return qs

    def _own_children(self) -> dict[Any, list[str]]:
        """For parents and pupils: club -> names of their own children (or themselves)."""
        user, roles, perms = self.actor()
        if _is_staff(roles):
            return {}
        mine: dict[Any, list[str]] = {}
        for m in Membership.objects.filter(
            left_on__isnull=True, student__in=visible_students(user, roles, perms)
        ).select_related("student"):
            mine.setdefault(m.club_id, []).append(m.student.first_name)
        return mine

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        ids = set(Patron.objects.values_list("user_id", flat=True))
        context["names"] = _names(ids)
        context["mine"] = self._own_children() if self.request.user.is_authenticated else {}
        return context

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        club = self.get_object()
        _, roles, _ = self.actor()
        data = dict(self.get_serializer(club).data)
        today = timezone.localdate()
        data["upcoming"] = ActivitySerializer(
            club.activities.filter(date__gte=today)[:20], many=True
        ).data
        data["past"] = ActivitySerializer(
            club.activities.filter(date__lt=today).order_by("-date")[:20], many=True
        ).data
        # Member lists are for staff; families see only their own children (my_children).
        if _is_staff(roles):
            data["members"] = [
                {
                    "student": str(m.student_id),
                    "name": m.student.full_name,
                    "class": str(m.student.arm) if m.student.arm_id else "",
                    "title": m.title,
                    "joined_on": m.joined_on,
                }
                for m in club.members.filter(left_on__isnull=True).select_related(
                    "student__arm__level"
                )
            ]
            data["can_run"] = can_run(self, club)
        return Response(data)

    @extend_schema(request=ClubMemberSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def add_member(self, request: Request, pk: str | None = None) -> Response:
        club = self.get_object()
        _require_run(self, club)
        data = ClubMemberSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        student = get_object_or_404(
            Student, pk=data.validated_data["student"], status=Student.Status.ACTIVE
        )
        current = club.members.filter(left_on__isnull=True).count()
        if club.capacity and current >= club.capacity:
            raise ValidationError({"student": f"{club.name} is full ({club.capacity} members)."})
        try:
            with transaction.atomic(using=require_tenant().db_alias):
                Membership.objects.create(
                    club=club, student=student, title=data.validated_data["title"]
                )
        except IntegrityError as exc:
            raise ValidationError({"student": "They are already a member."}) from exc
        with tenant_atomic():
            record_event(
                action="club.member_added",
                request=request,
                target=club,
                after={"student": student.full_name},
            )
        return Response({"members": current + 1}, status=status.HTTP_201_CREATED)

    @extend_schema(request=ClubMemberSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def remove_member(self, request: Request, pk: str | None = None) -> Response:
        club = self.get_object()
        _require_run(self, club)
        student_id = request.data.get("student")
        left = club.members.filter(student_id=student_id, left_on__isnull=True).update(
            left_on=timezone.localdate()
        )
        if not left:
            raise ValidationError({"student": "They aren't a member."})
        with tenant_atomic():
            record_event(
                action="club.member_left",
                request=request,
                target=club,
                after={"student": student_id},
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=ClubPatronSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def add_patron(self, request: Request, pk: str | None = None) -> Response:
        club = self.get_object()
        data = ClubPatronSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user_id = data.validated_data["user"]
        if not SchoolMembership.objects.filter(
            tenant=require_tenant(), user_id=user_id, is_active=True, role__in=STAFF_ROLES
        ).exists():
            raise ValidationError({"user": "Patrons must be active members of staff."})
        Patron.objects.get_or_create(club=club, user_id=user_id)
        with tenant_atomic():
            record_event(
                action="club.patron_added",
                request=request,
                target=club,
                after={"user": str(user_id)},
            )
        return Response(status=status.HTTP_201_CREATED)

    @extend_schema(request=ClubPatronSerializer, responses={204: None})
    @action(detail=True, methods=["post"])
    def remove_patron(self, request: Request, pk: str | None = None) -> Response:
        club = self.get_object()
        Patron.objects.filter(club=club, user_id=request.data.get("user")).delete()
        with tenant_atomic():
            record_event(
                action="club.patron_removed",
                request=request,
                target=club,
                after={"user": str(request.data.get("user"))},
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=ActivitySerializer, responses=ActivitySerializer)
    @action(detail=True, methods=["post"])
    def add_activity(self, request: Request, pk: str | None = None) -> Response:
        club = self.get_object()
        _require_run(self, club)
        data = ActivitySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        activity = data.save(club=club, created_by=request.user.pk)
        return Response(ActivitySerializer(activity).data, status=status.HTTP_201_CREATED)


class ActivityViewSet(
    mixins.ListModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, TenantViewSet
):
    """What clubs are doing. ``?mine=1``: the clubs I run, or my children belong to."""

    serializer_class = ActivitySerializer
    required_permissions: ClassVar = {
        "list": VIEW,
        "update": VIEW,
        "partial_update": VIEW,
        "destroy": VIEW,
    }

    def get_queryset(self) -> QuerySet[Activity]:
        user, roles, perms = self.actor()
        qs = Activity.objects.select_related("club").filter(club__is_active=True)
        params = self.request.query_params
        if params.get("mine") == "1":
            if _is_staff(roles):
                qs = qs.filter(club__patrons__user_id=user.pk)
            else:
                clubs = Membership.objects.filter(
                    left_on__isnull=True, student__in=visible_students(user, roles, perms)
                ).values("club_id")
                qs = qs.filter(club_id__in=clubs)
        if club := params.get("club"):
            qs = qs.filter(club_id=club)
        if params.get("upcoming") == "1":
            qs = qs.filter(date__gte=timezone.localdate())
        return qs.distinct()

    @extend_schema(
        parameters=[
            OpenApiParameter("mine", OpenApiTypes.STR),
            OpenApiParameter("club", OpenApiTypes.UUID),
            OpenApiParameter("upcoming", OpenApiTypes.STR),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(ActivitySerializer(self.get_queryset()[:200], many=True).data)

    def perform_update(self, serializer: Any) -> None:
        _require_run(self, serializer.instance.club)
        serializer.save()

    def perform_destroy(self, instance: Activity) -> None:
        _require_run(self, instance.club)
        instance.delete()
