"""School registration: an owner asks for a workspace and platform staff decide.

Approval has two parts. ``start_approval`` records the decision and is quick
enough for a web request. ``complete_approval`` creates the school's database,
which can take a minute, so it runs in a background job (tasks.py). The owner's
membership is created only after the database exists, in the same transaction
that marks the request approved; a failed or rejected request leaves none.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from integrations.phone import normalize_gh_phone

from .audit import record_platform_event
from .models import Membership, Role, SchoolRegistration, Tenant, User
from .provisioning.service import discard_tenant, provision_tenant, validate_slug
from .tenancy import tenant_context

logger = logging.getLogger(__name__)

Status = SchoolRegistration.Status
OPEN = (Status.PENDING, Status.PROVISIONING)
LIVE = (Status.PENDING, Status.PROVISIONING, Status.APPROVED)

# Which class levels a school runs, by the type chosen at registration.
SECTIONS_BY_TYPE = {
    SchoolRegistration.SchoolType.KG: {"kg"},
    SchoolRegistration.SchoolType.PRIMARY: {"kg", "lower_primary", "upper_primary"},
    SchoolRegistration.SchoolType.BASIC: {"kg", "lower_primary", "upper_primary", "jhs"},
    SchoolRegistration.SchoolType.JHS: {"jhs"},
}


def slug_problem(slug: str) -> str | None:
    """Why this web address can't be used, or None if it's free."""
    try:
        slug = validate_slug(slug)
    except ValidationError as exc:
        return exc.messages[0]
    taken = (
        Tenant.objects.filter(slug=slug).exists()
        or SchoolRegistration.objects.filter(slug=slug, status__in=LIVE).exists()
    )
    return "That web address is taken. Try another." if taken else None


def submit_registration(
    *, owner: User, data: dict[str, Any], request: HttpRequest | None = None
) -> SchoolRegistration:
    slug = data["slug"].strip().lower()
    problem = slug_problem(slug)
    if problem:
        raise ValidationError({"slug": problem})
    phone = normalize_gh_phone(data["phone"])
    if not phone:
        raise ValidationError({"phone": "Enter a valid Ghanaian phone number."})
    name = " ".join(data["school_name"].split())

    try:
        with transaction.atomic():
            if SchoolRegistration.objects.filter(owner=owner, status__in=OPEN).exists():
                raise ValidationError("You already have a registration under review.")
            registration = SchoolRegistration.objects.create(
                owner=owner,
                school_name=name,
                slug=slug,
                school_type=data["school_type"],
                region=data["region"],
                town=" ".join(data["town"].split()),
                phone=phone,
                expected_pupils=data["expected_pupils"],
                possible_duplicate=(
                    Tenant.objects.filter(name__iexact=name).exists()
                    or SchoolRegistration.objects.filter(
                        school_name__iexact=name, status__in=LIVE
                    ).exists()
                ),
            )
            record_platform_event(
                action="registration.submitted",
                request=request,
                actor=owner,
                target=registration,
                data={"slug": slug, "possible_duplicate": registration.possible_duplicate},
            )
    except IntegrityError as exc:  # lost a race with a parallel submission
        raise ValidationError("This registration was already submitted.") from exc
    return registration


def _check_reviewable(registration: SchoolRegistration, reviewer: User | None) -> None:
    if registration.status != SchoolRegistration.Status.PENDING:
        raise ValidationError(f"This registration is {registration.get_status_display().lower()}.")
    # Separation of duties: platform staff can't approve a school they applied for.
    if reviewer is not None and reviewer.pk == registration.owner_id:
        raise ValidationError("You can't review your own registration.")


def start_approval(
    registration: SchoolRegistration, *, reviewer: User | None = None, note: str = ""
) -> SchoolRegistration:
    """Record the decision and mark the request as being set up. Quick: safe in a request.

    The row lock means two reviewers clicking Approve together can't both start set-up.
    """
    with transaction.atomic():
        registration = (
            SchoolRegistration.objects.select_for_update()
            .select_related("owner")
            .get(pk=registration.pk)
        )
        _check_reviewable(registration, reviewer)
        registration.status = Status.PROVISIONING
        registration.reviewed_by = reviewer
        registration.reviewed_at = timezone.now()
        registration.review_note = note[:500]
        registration.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
        record_platform_event(
            action="registration.approval_started",
            actor=reviewer,
            target=registration,
            reason=note,
        )
    return registration


def complete_approval(registration_id: Any) -> Tenant | None:
    """Create the school, then make the applicant its owner. Runs in a background job.

    Safe to run twice: anything not waiting for set-up is left alone.
    """
    registration = SchoolRegistration.objects.select_related("owner", "reviewed_by").get(
        pk=registration_id
    )
    if registration.status != Status.PROVISIONING:
        logger.info(
            "Registration %s is %s; nothing to set up", registration.pk, registration.status
        )
        return None
    reviewer = registration.reviewed_by
    tenant = None
    try:
        tenant = provision_tenant(slug=registration.slug, name=registration.school_name)
        with tenant_context(tenant):
            _apply_registration_details(registration)
    except Exception as exc:
        if tenant is not None:  # the database exists but the details didn't apply
            tenant.status = Tenant.Status.FAILED
            tenant.save(update_fields=["status"])
            discard_tenant(tenant)
        registration.status = Status.FAILED
        registration.review_note = "Setup failed; platform staff have been alerted."
        registration.save(update_fields=["status", "review_note"])
        record_platform_event(
            action="registration.failed",
            actor=reviewer,
            target=registration,
            data={"error": type(exc).__name__},
        )
        raise

    with transaction.atomic():
        Membership.objects.get_or_create(user=registration.owner, tenant=tenant, role=Role.OWNER)
        registration.status = Status.APPROVED
        registration.tenant = tenant
        registration.save(update_fields=["status", "tenant"])
        record_platform_event(
            action="registration.approved",
            actor=reviewer,
            tenant=tenant,
            target=registration,
            reason=registration.review_note,
        )
    _notify(
        registration,
        f"{registration.school_name} is ready on Nex Edu",
        f"Good news: {registration.school_name} has been approved.\n\n"
        f"Sign in at {settings.FRONTEND_URL}/login with {registration.owner.email}. "
        "Your dashboard has a short checklist to get the school ready: profile, logo, "
        "term dates, fees, staff, pupils and parents.",
    )
    return tenant


def retry_setup(registration: SchoolRegistration, *, reviewer: User) -> SchoolRegistration:
    """Try a failed set-up again (super admin). The earlier attempt's database must
    be gone first; ``discard_tenant`` removed it, or the sweep will."""
    with transaction.atomic():
        registration = SchoolRegistration.objects.select_for_update().get(pk=registration.pk)
        if registration.status != Status.FAILED:
            raise ValidationError("Only a failed set-up can be tried again.")
        if reviewer.pk == registration.owner_id:
            raise ValidationError("You can't review your own registration.")
        leftover = Tenant.objects.filter(slug=registration.slug).first()
        if leftover is not None and not (
            leftover.status in (Tenant.Status.FAILED, Tenant.Status.PROVISIONING)
            and discard_tenant(leftover)
        ):
            raise ValidationError(
                "The earlier attempt's database is still being removed. Try again in a few minutes."
            )
        registration.status = Status.PROVISIONING
        registration.reviewed_by = reviewer
        registration.reviewed_at = timezone.now()
        registration.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        record_platform_event(
            action="registration.setup_retried", actor=reviewer, target=registration
        )
    return registration


STUCK_AFTER = timezone.timedelta(minutes=30)


def sweep_stuck_setups() -> int:
    """Set-ups still running after 30 minutes crashed somewhere (a worker restart, say):
    mark them failed, alert platform staff, and remove what they left behind.
    Also retries removing leftovers whose first clean-up failed. Returns schools swept."""
    cutoff = timezone.now() - STUCK_AFTER
    swept = 0
    for registration in SchoolRegistration.objects.filter(
        status=Status.PROVISIONING, reviewed_at__lt=cutoff
    ):
        registration.status = Status.FAILED
        registration.review_note = "Setup didn't finish; platform staff have been alerted."
        registration.save(update_fields=["status", "review_note"])
        record_platform_event(
            action="registration.failed",
            target=registration,
            data={"error": "set-up did not finish within 30 minutes"},
        )
        logger.error("School set-up for %s didn't finish and was stopped", registration.slug)
        swept += 1
    for tenant in Tenant.objects.filter(
        status__in=[Tenant.Status.FAILED, Tenant.Status.PROVISIONING], created_at__lt=cutoff
    ):
        if discard_tenant(tenant):
            swept += 1
    return swept


def approve_registration(
    registration: SchoolRegistration, *, reviewer: User | None = None, note: str = ""
) -> Tenant:
    """Approve and set up in one go (the review command). The web console uses
    start_approval plus the background job instead."""
    start_approval(registration, reviewer=reviewer, note=note)
    tenant = complete_approval(registration.pk)
    if tenant is None:  # pragma: no cover - start_approval just set PROVISIONING
        raise ValidationError("This registration couldn't be set up.")
    return tenant


def reject_registration(
    registration: SchoolRegistration, *, reviewer: User | None = None, note: str
) -> None:
    _check_reviewable(registration, reviewer)
    if not note.strip():
        raise ValidationError({"note": "Give a reason. The applicant will see it."})
    registration.status = SchoolRegistration.Status.REJECTED
    registration.reviewed_by = reviewer
    registration.reviewed_at = timezone.now()
    registration.review_note = note[:500]
    registration.save()
    record_platform_event(
        action="registration.rejected", actor=reviewer, target=registration, reason=note
    )
    _notify(
        registration,
        f"Your Nex Edu registration for {registration.school_name}",
        f"We couldn't approve {registration.school_name} this time.\n\n{note}\n\n"
        "Reply to this email if you have questions.",
    )


def _apply_registration_details(registration: SchoolRegistration) -> None:
    """Switch off class levels the school doesn't run and fill in its contact details."""
    from apps.academics.models import ClassLevel
    from apps.school.models import SchoolProfile

    sections = SECTIONS_BY_TYPE[registration.school_type]
    ClassLevel.objects.exclude(section__in=sections).update(is_active=False)
    profile = SchoolProfile.load()
    profile.phone = registration.phone
    profile.address = f"{registration.town}, {registration.get_region_display()} Region"
    profile.email = registration.owner.email
    profile.save(update_fields=["phone", "address", "email"])


def _notify(registration: SchoolRegistration, subject: str, body: str) -> None:
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [registration.owner.email])
    except Exception:  # the decision stands even if the email bounces
        logger.exception("Could not email the owner of registration %s", registration.pk)
