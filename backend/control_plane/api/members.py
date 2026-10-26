"""People in a school: invite, list, deactivate. Lives in the control plane but is
scoped to the selected school and needs ``members.manage``."""

from __future__ import annotations

from typing import Any, ClassVar

from allauth.mfa.models import Authenticator
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from control_plane.members import invite_member, send_invitation, set_membership_active
from control_plane.models import Membership, Role
from control_plane.tenancy import tenant_atomic
from core.audit.services import record_event
from core.rbac import Perm, can_grant
from core.views import TenantViewSet


class MemberSerializer(serializers.ModelSerializer[Membership]):
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    has_password = serializers.SerializerMethodField()
    mfa_enrolled = serializers.SerializerMethodField()
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True)

    class Meta:
        model = Membership
        fields: ClassVar = [
            "id",
            "user",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "role_label",
            "is_active",
            "has_password",
            "mfa_enrolled",
            "last_login",
            "created_at",
        ]

    def get_has_password(self, obj: Membership) -> bool:
        return obj.user.has_usable_password()

    def get_mfa_enrolled(self, obj: Membership) -> bool:
        return obj.user_id in self.context.get("mfa_users", set())


class InviteSerializer(serializers.Serializer):  # type: ignore[type-arg]
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Role.choices)
    # Names are optional: the person can add them on their profile after signing up.
    first_name = serializers.CharField(max_length=150, required=False, default="", allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, default="", allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, default="", allow_blank=True)


GRANTERS = (
    Perm.MEMBERS_MANAGE,
    Perm.MEMBERS_MANAGE_STAFF,
    Perm.STUDENTS_MANAGE,
    Perm.ADMISSIONS_MANAGE,
)


class MemberViewSet(mixins.ListModelMixin, TenantViewSet):
    serializer_class = MemberSerializer
    queryset = Membership.objects.none()  # for schema generation; real scope in get_queryset
    # Head teacher and administrator see who has access. The proprietor
    # (members.manage) gives or removes any staff role; the head teacher
    # (members.manage_staff) adds and blocks teaching and support staff; whoever
    # manages pupils or admissions may invite parents and pupils. can_grant
    # decides per role.
    required_permissions: ClassVar = {
        "list": (Perm.MEMBERS_MANAGE, Perm.MEMBERS_VIEW),
        "create": GRANTERS,
        "deactivate": GRANTERS,
        "activate": GRANTERS,
        "resend_invite": GRANTERS,
    }

    def get_queryset(self) -> QuerySet[Membership]:
        qs = Membership.objects.filter(tenant=self.request.tenant).select_related("user")  # type: ignore[attr-defined]
        if role := self.request.query_params.get("role"):
            qs = qs.filter(role=role)
        return qs.order_by("user__last_name", "user__first_name", "role")

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        context["mfa_users"] = set(
            Authenticator.objects.filter(user__memberships__tenant=self.request.tenant)  # type: ignore[attr-defined]
            .exclude(type=Authenticator.Type.RECOVERY_CODES)
            .values_list("user_id", flat=True)
        )
        return context

    def create(self, request: Request) -> Response:
        data = InviteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _, roles, _ = self.actor()
        membership = invite_member(
            request=request,
            tenant=request.tenant,
            granter_roles=roles,  # type: ignore[attr-defined]
            **data.validated_data,
        )
        with tenant_atomic():
            record_event(
                action="members.invited",
                request=request,
                after={"email": membership.user.email, "role": membership.role},
            )
        return Response(self.get_serializer(membership).data, status=status.HTTP_201_CREATED)

    def _toggle(self, request: Request, pk: str | None, active: bool) -> Response:
        membership = get_object_or_404(self.get_queryset(), pk=pk)
        user, roles, _ = self.actor()
        set_membership_active(membership=membership, active=active, granter_roles=roles, actor=user)
        with tenant_atomic():
            record_event(
                action="members.activated" if active else "members.deactivated",
                request=request,
                after={"email": membership.user.email, "role": membership.role},
            )
        return Response(self.get_serializer(membership).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, pk: str | None = None) -> Response:
        return self._toggle(request, pk, False)

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, pk: str | None = None) -> Response:
        return self._toggle(request, pk, True)

    @action(detail=True, methods=["post"])
    def resend_invite(self, request: Request, pk: str | None = None) -> Response:
        membership = get_object_or_404(self.get_queryset(), pk=pk)
        _, roles, _ = self.actor()
        if not can_grant(roles, membership.role):
            raise PermissionDenied("You can't resend an invitation for this role.")
        if membership.user.has_usable_password():
            return Response({"detail": "This person has already set a password."}, status=400)
        send_invitation(request, membership.user, request.tenant, membership.role)  # type: ignore[attr-defined]
        return Response(status=status.HTTP_204_NO_CONTENT)
