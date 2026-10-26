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
    NURSE = "nurse", "School nurse"
    CANTEEN = "canteen", "Canteen manager"
    STORE_KEEPER = "store_keeper", "Store keeper"
    GATE = "gate", "Gate officer"
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
    # Lifecycle (control_plane.lifecycle): why a school is suspended or closed, and when.
    status_reason = models.CharField(max_length=20, blank=True)
    status_note = models.CharField(max_length=300, blank=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    purge_after = models.DateField(
        null=True, blank=True, help_text="Closed school: destroyed for good on this day"
    )
    purged_at = models.DateTimeField(null=True, blank=True)
    export_key = models.CharField(max_length=300, blank=True, help_text="The closing export")

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


class CustomRole(models.Model):
    """A role a school makes up, such as "Exams officer" or "Deputy head (academic)":
    extra permissions on top of a staff member's own role (``core.rbac.CUSTOM_ROLE_PERMISSIONS``
    lists those it may contain). Only the proprietor creates and gives them."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="custom_roles")
    name = models.CharField(max_length=60)
    description = models.CharField(max_length=200, blank=True)
    permissions = models.JSONField(default=list)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar = ["name"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_custom_role_name")
        ]

    def __str__(self) -> str:
        return self.name


class CustomRoleGrant(models.Model):
    """A staff member holds a custom role at the school."""

    role = models.ForeignKey(CustomRole, on_delete=models.CASCADE, related_name="grants")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="custom_roles")
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["role", "user"], name="uniq_custom_role_grant")
        ]


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
        PROVISIONING = "provisioning", "Being set up"
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
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
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
                condition=models.Q(status__in=["pending", "provisioning"]),
                name="one_open_registration_per_owner",
            ),
            # A subdomain is held by at most one live request.
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(status__in=["pending", "provisioning", "approved"]),
                name="uniq_live_registration_slug_v2",
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


class TenantUsage(models.Model):
    """One day's totals for a school, copied from its database by a background job.

    The Super Admin console reads only these numbers, never the school's records,
    so platform staff see how a school uses Nex Edu without seeing any pupil.
    Today's row is refreshed during the day; earlier rows are the history.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="usage")
    day = models.DateField()
    pupils = models.PositiveIntegerField(default=0)
    classes = models.PositiveIntegerField(default=0)
    applications_pending = models.PositiveIntegerField(default=0)
    registers_7d = models.PositiveIntegerField(default=0, help_text="Attendance marks, last 7 days")
    report_cards_published = models.PositiveIntegerField(default=0)
    sms_sent_month = models.PositiveIntegerField(default=0)
    sms_monthly_limit = models.PositiveIntegerField(default=0)
    payments_30d_pesewas = models.BigIntegerField(default=0)
    payments_total_pesewas = models.BigIntegerField(default=0)
    outstanding_pesewas = models.BigIntegerField(default=0, help_text="Current term, unpaid fees")
    staff = models.PositiveIntegerField(default=0)
    parents = models.PositiveIntegerField(default=0)
    active_users_7d = models.PositiveIntegerField(default=0)
    active_users_30d = models.PositiveIntegerField(default=0)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    # The school's set-up checklist (apps.school.setup): steps done, total, and what's left.
    setup_done = models.PositiveSmallIntegerField(default=0)
    setup_total = models.PositiveSmallIntegerField(default=0)
    setup_left = models.JSONField(default=list)
    collected_at = models.DateTimeField()

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["tenant", "day"], name="one_usage_row_per_school_day")
        ]
        indexes: ClassVar = [models.Index(fields=["day"])]
        ordering: ClassVar = ["-day"]

    def __str__(self) -> str:
        return f"{self.tenant_id} {self.day}"


# --- Pricing and billing (Super Admin) ---------------------------------------------------


class PriceBandSetting(models.Model):
    """A subscription price band. Edited in the console; every change is audited."""

    code = models.CharField(max_length=20, unique=True)
    label = models.CharField(max_length=80)
    max_pupils = models.PositiveIntegerField(
        null=True, blank=True, help_text="Empty: no upper limit"
    )
    price_pesewas = models.PositiveBigIntegerField()
    position = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar = ["position"]

    def __str__(self) -> str:
        return self.label


class BillingSettings(models.Model):
    """Monthly billing (owner's decision, 26 Oct 2026): band prices are per month."""

    class Period(models.TextChoices):
        UNSET = "", "Not decided"
        MONTHLY = "monthly", "Monthly"
        TERMLY = "termly", "Per term"
        YEARLY = "yearly", "Yearly"

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    period = models.CharField(
        max_length=10, choices=Period.choices, blank=True, default=Period.MONTHLY
    )
    due_days = models.PositiveSmallIntegerField(
        default=14, help_text="Days from the invoice to its due date"
    )
    sms_included_monthly = models.PositiveIntegerField(
        default=2000, help_text="SMS every school may send each month before using bundles"
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls) -> BillingSettings:
        return cls.objects.get_or_create(pk=1)[0]


class SubscriptionPayment(models.Model):
    """Money a school paid Nex Edu for its subscription, recorded by platform staff."""

    class Method(models.TextChoices):
        MOMO = "momo", "Mobile money"
        BANK = "bank", "Bank transfer"
        CARD = "card", "Card"
        CASH = "cash", "Cash"
        CHEQUE = "cheque", "Cheque"
        PAYSTACK = "paystack", "Paystack (online)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="subscription_payments"
    )
    amount_pesewas = models.PositiveBigIntegerField()
    period_label = models.CharField(
        max_length=60, help_text='What it pays for, e.g. "October 2026"'
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    reference = models.CharField(max_length=80, blank=True)
    received_on = models.DateField()
    band_code = models.CharField(max_length=20, blank=True)
    pupils = models.PositiveIntegerField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    invoice = models.ForeignKey(
        "SubscriptionInvoice",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-received_on", "-created_at"]


class SubscriptionInvoice(models.Model):
    """What a school owes Nex Edu for one month: its band plus paid add-ons."""

    class Status(models.TextChoices):
        OPEN = "open", "Unpaid"
        PAID = "paid", "Paid"
        VOID = "void", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=30, unique=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="invoices")
    month = models.DateField(help_text="First day of the month billed")
    band_code = models.CharField(max_length=20, blank=True)
    pupils = models.PositiveIntegerField(null=True, blank=True)
    lines = models.JSONField(default=list, help_text='[{"description", "amount_pesewas"}]')
    total_pesewas = models.PositiveBigIntegerField()
    issued_on = models.DateField()
    due_on = models.DateField()
    status = models.CharField(max_length=4, choices=Status.choices, default=Status.OPEN)
    paid_on = models.DateField(null=True, blank=True)
    reminders_sent = models.PositiveSmallIntegerField(
        default=0, help_text="Overdue reminders sent (at 7 and 14 days)"
    )
    void_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-month", "tenant__name"]
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["tenant", "month"],
                condition=~models.Q(status="void"),
                name="one_live_invoice_per_school_month",
            )
        ]


class SmsBundle(models.Model):
    """An SMS bundle schools can buy. Nex Edu sets these in the console."""

    code = models.SlugField(max_length=20, unique=True)
    label = models.CharField(max_length=60)
    sms = models.PositiveIntegerField()
    price_pesewas = models.PositiveBigIntegerField()
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering: ClassVar = ["position", "sms"]


class SmsCredit(models.Model):
    """SMS a school has bought and not used yet. They don't expire."""

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="sms_credit")
    balance = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class SubscriptionCharge(models.Model):
    """One online payment attempt (Paystack) by a proprietor: an invoice or an SMS bundle."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for payment"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        ABANDONED = "abandoned", "Not completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=60, unique=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="charges")
    invoice = models.ForeignKey(
        SubscriptionInvoice, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    bundle = models.ForeignKey(
        SmsBundle, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    sms = models.PositiveIntegerField(default=0, help_text="SMS added when a bundle is paid")
    amount_pesewas = models.PositiveBigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    authorization_url = models.URLField(max_length=500, blank=True)
    provider_transaction_id = models.CharField(max_length=60, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]


class SupportGrant(models.Model):
    """The proprietor lets Nex Edu support look at the school's set-up for a while.

    Support sees configuration only (classes, terms, modules, staff accounts, the
    set-up checklist), never pupils, guardians, scores or money. Every look is
    recorded and shown to the proprietor.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="support_grants")
    granted_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=300)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]


class SupportView(models.Model):
    """One look by a Nex Edu staff member under a grant."""

    grant = models.ForeignKey(SupportGrant, on_delete=models.CASCADE, related_name="views")
    staff = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-at"]


class JobRun(models.Model):
    """One run of a scheduled background job, for the console's jobs view."""

    name = models.CharField(max_length=120, db_index=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    succeeded = models.BooleanField(null=True)
    result = models.CharField(max_length=300, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["-started_at"]


# --- Announcements to proprietors --------------------------------------------------------


class PlatformAnnouncement(models.Model):
    class Audience(models.TextChoices):
        ALL = "all", "Every proprietor"
        BAND = "band", "Proprietors in one price band"
        REGION = "region", "Proprietors in one region"

    class Status(models.TextChoices):
        DRAFT = "draft"
        PUBLISHED = "published"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=140)
    body = models.TextField(max_length=5000)
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.ALL)
    band_code = models.CharField(max_length=20, blank=True)
    region = models.CharField(max_length=20, choices=GhanaRegion.choices, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    email = models.BooleanField(default=True, help_text="Also email the proprietors")
    recipient_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]


class PlatformAnnouncementRecipient(models.Model):
    """Who an announcement went to, and when they read it."""

    announcement = models.ForeignKey(
        PlatformAnnouncement, on_delete=models.CASCADE, related_name="recipients"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["announcement", "user"], name="one_receipt_per_user")
        ]


# --- System: problems and vulnerability scans --------------------------------------------


class Problem(models.Model):
    """A failure somewhere in Nex Edu, grouped by where it happens. Personal details
    are removed before anything is stored (control_plane.problems.scrub)."""

    class Kind(models.TextChoices):
        SERVER = "server", "Server error"
        JOB = "job", "Background job failed"
        BROWSER = "browser", "Error on someone's screen"
        SLOW = "slow", "Slow page"
        HEALTH = "health", "Health check failed"

    class Severity(models.TextChoices):
        CRITICAL = "critical"
        WARNING = "warning"

    class Status(models.TextChoices):
        NEW = "new", "New"
        INVESTIGATING = "investigating", "Investigating"
        FIXED = "fixed", "Fixed"
        IGNORED = "ignored", "Ignored"

    fingerprint = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    title = models.CharField(max_length=300)
    location = models.CharField(
        max_length=300, blank=True, help_text="Code or page where it happens"
    )
    detail = models.TextField(blank=True, help_text="Latest traceback or message, scrubbed")
    last_path = models.CharField(max_length=300, blank=True)
    schools = models.JSONField(default=list, help_text="Slugs of schools affected")
    count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.NEW)
    note = models.TextField(blank=True)
    updated_by_email = models.CharField(max_length=254, blank=True)

    class Meta:
        ordering: ClassVar = ["-last_seen"]

    def __str__(self) -> str:
        return self.title


class VulnerabilityScan(models.Model):
    """Known security advisories for the Python packages Nex Edu runs on (OSV)."""

    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    packages_checked = models.PositiveIntegerField(default=0)
    findings = models.JSONField(default=list)
    error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering: ClassVar = ["-started_at"]


# --- Modules (core.modules is the catalogue) ---------------------------------------------


class ModuleOffer(models.Model):
    """Price of an optional module. GH₵0: included in every price band. More than
    that: a paid add-on Nex Edu grants a school once it pays."""

    code = models.CharField(max_length=30, unique=True)
    price_pesewas = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class TenantModule(models.Model):
    """One school's switch for one optional module. No row: the default (on when
    the module is included, off for a paid add-on not granted)."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="modules")
    code = models.CharField(max_length=30)
    active = models.BooleanField(default=True)
    granted = models.BooleanField(default=False, help_text="Paid add-on granted by Nex Edu")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["tenant", "code"], name="one_switch_per_school_module")
        ]


class TenantModuleChange(models.Model):
    """History of module switches for a school, shown to the school and in the console."""

    class Action(models.TextChoices):
        ACTIVATED = "activated", "Switched on"
        DEACTIVATED = "deactivated", "Switched off"
        GRANTED = "granted", "Add-on granted"
        REVOKED = "revoked", "Add-on removed"
        CONFIRMED = "confirmed", "Choices confirmed"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="module_changes")
    code = models.CharField(max_length=30, blank=True)
    action = models.CharField(max_length=12, choices=Action.choices)
    actor_email = models.CharField(max_length=254, blank=True)
    by_platform = models.BooleanField(default=False, help_text="Done by Nex Edu staff")
    reason = models.CharField(max_length=300, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-at", "-pk"]


# --- Phase 8: calendar feeds, push, developer API ----------------------------------------


class CalendarFeed(models.Model):
    """A private calendar link (iCalendar) for one person at one school. Only a hash
    of the token is stored; the link is shown once and can be replaced."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="calendar_feeds")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="calendar_feeds")
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["user", "tenant"], name="one_calendar_feed_per_person")
        ]


class PushSubscription(models.Model):
    """One browser that agreed to show this person's notifications (Web Push)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_ok_at = models.DateTimeField(null=True, blank=True)


class ApiKey(models.Model):
    """A key for another system to read one school's data. Only a hash is stored;
    the key is shown once. Scopes limit what it can read."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=80)
    prefix = models.CharField(max_length=16, help_text="Shown to tell keys apart")
    key_hash = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]


class WebhookEndpoint(models.Model):
    """Where a school wants events sent. The signing secret is encrypted with the
    school's own key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="webhooks")
    url = models.URLField(max_length=500)
    events = models.JSONField(default=list)
    secret = models.TextField(help_text="Encrypted")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]


class WebhookDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Waiting"
        SENT = "sent", "Delivered"
        FAILED = "failed", "Gave up"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    endpoint = models.ForeignKey(
        WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries"
    )
    event = models.CharField(max_length=40)
    payload = models.JSONField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]
