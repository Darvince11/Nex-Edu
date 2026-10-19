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
