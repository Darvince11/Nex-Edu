from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Cell,
    Membership,
    PlatformAuditEvent,
    PlatformStaff,
    Tenant,
    TenantMigrationRun,
    User,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_active", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "phone")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)


@admin.register(Cell)
class CellAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "capacity", "is_accepting")


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "status", "cell", "is_canary", "schema_version", "migrated_at")
    list_filter = ("status", "cell", "is_canary")
    search_fields = ("slug", "name")
    readonly_fields = ("db_name", "secret_ref", "schema_version", "migrated_at", "created_at")
    exclude = ("wrapped_data_key",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "tenant__slug")
    raw_id_fields = ("user",)


@admin.register(TenantMigrationRun)
class TenantMigrationRunAdmin(admin.ModelAdmin):
    list_display = ("tenant", "started_at", "succeeded", "schema_version")
    list_filter = ("succeeded",)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


@admin.register(PlatformStaff)
class PlatformStaffAdmin(ReadOnlyAdmin):
    """Read-only: platform roles are granted with ``manage.py add_platform_staff``."""

    list_display = ("user", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")


@admin.register(PlatformAuditEvent)
class PlatformAuditEventAdmin(ReadOnlyAdmin):
    list_display = ("seq", "occurred_at", "actor_email", "action", "tenant_id", "target_id")
    list_filter = ("action",)
