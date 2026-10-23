"""Control-plane models. These live in the shared "default" database.

School data never lives here. Each school has its own database, located through
``Tenant.secret_ref`` and registered at runtime by :mod:`control_plane.db`.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models

TENANT_SLUG_VALIDATOR = RegexValidator(
    r"^[a-z][a-z0-9-]{2,39}$",
    "Use 3-40 lowercase letters, digits or hyphens, starting with a letter.",
)


class Role(models.TextChoices):
    OWNER = "owner", "School owner / proprietor"
    PRINCIPAL = "principal", "Head teacher"
    ADMIN = "admin", "School administrator"
    BURSAR = "bursar", "Accountant / bursar"
    TEACHER = "teacher", "Teacher"
    FORM_TEACHER = "form_teacher", "Class teacher"
    LIBRARIAN = "librarian", "Librarian"
    WARDEN = "warden", "Hostel warden"
    DRIVER = "driver", "Driver"
    PARENT = "parent", "Parent / guardian"
    STUDENT = "student", "Student"


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra: Any) -> User:
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.update(is_staff=True, is_superuser=True)
        return self._create(email, password, **extra)


class User(AbstractUser):
    """A global identity. One login can belong to several schools."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None  # type: ignore[assignment]
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    # Consent to the terms and privacy notice at sign-up (Act 843): when, and which version.
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    terms_version = models.CharField(max_length=20, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects = UserManager()  # type: ignore[misc]

    def __str__(self) -> str:
        return self.email


class Cell(models.Model):
    """A group of school databases sharing one Aurora cluster and PgBouncer."""

    name = models.CharField(max_length=40, unique=True)
    region = models.CharField(max_length=30, default="af-south-1")
    db_host = models.CharField(max_length=255, help_text="Aurora writer endpoint (admin DDL)")
    db_port = models.PositiveIntegerField(default=5432)
    pooler_host = models.CharField(max_length=255, help_text="PgBouncer endpoint used by the app")
    pooler_port = models.PositiveIntegerField(default=6432)
    admin_secret_ref = models.CharField(max_length=255)
    capacity = models.PositiveIntegerField(default=25)
    is_accepting = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Tenant(models.Model):
    """A school. Owns exactly one database."""

    class Status(models.TextChoices):
        PROVISIONING = "provisioning"
        ACTIVE = "active"
        SUSPENDED = "suspended"
        FAILED = "failed"
        OFFBOARDED = "offboarded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.CharField(max_length=40, unique=True, validators=[TENANT_SLUG_VALIDATOR])
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROVISIONING)
    cell = models.ForeignKey(
        Cell, on_delete=models.PROTECT, null=True, blank=True, related_name="tenants"
    )
    db_name = models.CharField(max_length=63, unique=True)
    secret_ref = models.CharField(max_length=255, help_text="Secrets Manager id of DB credentials")
    # Per-school data key, wrapped by KMS. Never stored in plaintext.
    wrapped_data_key = models.BinaryField(null=True, blank=True, editable=False)
    is_canary = models.BooleanField(
        default=False, help_text="Receives schema migrations before other schools"
    )
    schema_version = models.CharField(max_length=64, blank=True)
    migrated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes: ClassVar = [models.Index(fields=["status"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"

    @property
    def db_alias(self) -> str:
        from django.conf import settings

        return f"{settings.TENANT_DB_ALIAS_PREFIX}{self.slug.replace('-', '_')}"


class Membership(models.Model):
    """Grants a user a role in a school. A user may hold several roles."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["user", "tenant", "role"], name="uniq_membership_role")
        ]
        indexes: ClassVar = [models.Index(fields=["tenant", "user", "is_active"])]

    def __str__(self) -> str:
        return f"{self.user} → {self.tenant.slug} as {self.role}"


class GhanaRegion(models.TextChoices):
    AHAFO = "ahafo", "Ahafo"
    ASHANTI = "ashanti", "Ashanti"
    BONO = "bono", "Bono"
    BONO_EAST = "bono_east", "Bono East"
    CENTRAL = "central", "Central"
    EASTERN = "eastern", "Eastern"
    GREATER_ACCRA = "greater_accra", "Greater Accra"
    NORTH_EAST = "north_east", "North East"
    NORTHERN = "northern", "Northern"
    OTI = "oti", "Oti"
    SAVANNAH = "savannah", "Savannah"
    UPPER_EAST = "upper_east", "Upper East"
    UPPER_WEST = "upper_west", "Upper West"
    VOLTA = "volta", "Volta"
    WESTERN = "western", "Western"
    WESTERN_NORTH = "western_north", "Western North"


class SchoolRegistration(models.Model):
    """A school owner's request for a workspace. Platform staff review every one
    (``manage.py review_registration``) before any school database is created, and
    the owner gets their membership only after provisioning succeeds."""

    class Status(models.TextChoices):
        PENDING = "pending", "Under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Not approved"
        FAILED = "failed", "Setup failed"

    class SchoolType(models.TextChoices):
        KG = "kg", "Kindergarten only"
        PRIMARY = "primary", "KG and primary (Basic 1-6)"
        BASIC = "basic", "KG, primary and JHS"
        JHS = "jhs", "Junior High only"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="school_registrations")
    school_name = models.CharField(max_length=200)
    slug = models.CharField(max_length=40, validators=[TENANT_SLUG_VALIDATOR])
    school_type = models.CharField(max_length=10, choices=SchoolType.choices)
    region = models.CharField(max_length=20, choices=GhanaRegion.choices)
    town = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    expected_pupils = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # Set for reviewers only; never shown to the applicant.
    possible_duplicate = models.BooleanField(default=False)
    review_note = models.CharField(max_length=500, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    tenant = models.OneToOneField(
        Tenant, on_delete=models.SET_NULL, null=True, blank=True, related_name="registration"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]
        constraints: ClassVar = [
            # One open request per owner: a retried submission can't create a second one.
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(status="pending"),
                name="one_pending_registration_per_owner",
            ),
            # A subdomain is held by at most one live request.
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(status__in=["pending", "approved"]),
                name="uniq_live_registration_slug",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.school_name} ({self.slug}, {self.status})"


class PlatformRole(models.TextChoices):
    SUPER_ADMIN = "super_admin", "Super admin"
    SUPPORT = "support", "Support"
    BILLING = "billing", "Billing"


class PlatformStaff(models.Model):
    """Nex Edu's own operators. Granted only by ``add_platform_staff``, never by
    registration or school invitations. ``User.is_superuser`` grants nothing here."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="platform_staff")
    role = models.CharField(max_length=20, choices=PlatformRole.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user} ({self.role})"


class PlatformAuditQuerySet(models.QuerySet["PlatformAuditEvent"]):
    def update(self, **kwargs: Any) -> int:
        raise RuntimeError("Platform audit events cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise RuntimeError("Platform audit events cannot be deleted.")


class PlatformAuditEvent(models.Model):
    """Append-only, hash-chained log of platform-level actions (see ``control_plane.audit``)."""

    seq = models.PositiveBigIntegerField(unique=True)
    occurred_at = models.DateTimeField(db_index=True)
    actor_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_email = models.CharField(max_length=254, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    ip = models.CharField(max_length=45, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    data = models.JSONField(null=True, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    objects = PlatformAuditQuerySet.as_manager()

    class Meta:
        ordering: ClassVar = ["-seq"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise RuntimeError("Platform audit events cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise RuntimeError("Platform audit events cannot be deleted.")


class PlatformAuditHead(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    last_seq = models.PositiveBigIntegerField(default=0)
    last_hash = models.CharField(max_length=64, default="0" * 64)


class TenantMigrationRun(models.Model):
    """One attempt to migrate one school database. Kept for operational history."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="migration_runs")
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    succeeded = models.BooleanField()
    schema_version = models.CharField(max_length=64, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["-started_at"]


class PaymentReference(models.Model):
    """Maps a payment provider reference to the school it belongs to.

    Paystack and Flutterwave call one platform-wide webhook URL. The webhook looks
    the reference up here, then re-verifies the transaction with the provider
    before touching that school's database. Metadata in the webhook body is
    never trusted to choose the school.
    """

    reference = models.CharField(max_length=60, unique=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="payment_references")
    provider = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
