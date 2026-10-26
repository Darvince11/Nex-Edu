"""Inviting people into a school and managing their roles.

Signup is closed, so this is the only way in. An invitee gets an email with a
one-time link to set their password; using it proves they control the inbox,
which marks the address verified (see ``signals.py``).
"""

from __future__ import annotations

from typing import Any

from allauth.account.adapter import get_adapter
from allauth.account.internal.flows.password_reset import get_reset_password_from_key_url
from allauth.account.models import EmailAddress
from allauth.account.utils import user_pk_to_url_str
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpRequest

from core.rbac import can_grant
from integrations.phone import normalize_gh_phone

from .models import Membership, Role, Tenant, User


def invite_member(
    *,
    request: HttpRequest,
    tenant: Tenant,
    granter_roles: frozenset[str],
    email: str,
    role: str,
    first_name: str = "",
    last_name: str = "",
    phone: str = "",
    send_email: bool = True,
) -> Membership:
    if role not in Role.values:
        raise ValidationError(f"Unknown role {role}")
    if not can_grant(granter_roles, role):
        raise PermissionDenied("You can't give someone more access than you have.")
    email = email.strip().lower()
    normalized_phone = normalize_gh_phone(phone) if phone else ""
    if phone and not normalized_phone:
        raise ValidationError("Enter a valid Ghanaian mobile number.")

    with transaction.atomic():
        user = User.objects.filter(email=email).first()
        if user is not None and user.pk == getattr(request.user, "pk", None):
            raise PermissionDenied("You can't give yourself a role. Ask the proprietor.")
        created = user is None
        if user is None:
            user = User.objects.create_user(
                email,
                password=None,
                first_name=first_name,
                last_name=last_name,
                phone=normalized_phone or "",
            )
            EmailAddress.objects.create(user=user, email=email, primary=True, verified=False)
        membership, _ = Membership.objects.get_or_create(user=user, tenant=tenant, role=role)
        if not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=["is_active"])

    if send_email and (created or not user.has_usable_password()):
        send_invitation(request, user, tenant, role)
    return membership


def send_invitation(request: HttpRequest, user: User, tenant: Tenant, role: str) -> None:
    key = f"{user_pk_to_url_str(user)}-{default_token_generator.make_token(user)}"
    context: dict[str, Any] = {
        "user": user,
        "school": tenant.name,
        "role": Role(role).label,
        "invite_url": get_reset_password_from_key_url(request, key),
    }
    get_adapter(request).send_mail("account/email/invite", user.email, context)


def set_membership_active(
    *, membership: Membership, active: bool, granter_roles: frozenset[str], actor: Any
) -> Membership:
    if not can_grant(granter_roles, membership.role):
        raise PermissionDenied("You can't change access for a role above your own.")
    if membership.user_id == actor.pk and not active:
        raise ValidationError("You can't remove your own access.")
    membership.is_active = active
    membership.save(update_fields=["is_active"])
    return membership
