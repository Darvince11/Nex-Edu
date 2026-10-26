"""Back up one school and restore it, without touching any other school.

Aurora snapshots and AWS Backup protect whole database clusters. To bring back a
single school (it deleted records by mistake, its database was damaged) without
rolling back every other school on the cluster, Nex Edu keeps a logical,
per-school backup: the same zip as the closing export (every record as JSON,
every file). ``restore`` loads it either:

- **in place**: the school's database is dropped, created again, migrated and
  loaded (everyone at the school keeps their sign-in; nothing else changes), or
- **as a copy** under a new address that nobody can open (status stays
  "provisioning"), for checking, then thrown away.

Encrypted fields are decrypted into the backup and encrypted again with the
target school's key when loaded; search indexes over encrypted values (the
Ghana Card number) are worked out again; stored file paths are rewritten to the
target school's prefix. The backup zip holds personal data in clear: keep it
under the school's prefix (encrypted at rest with SSE-KMS) and nowhere else.
"""

from __future__ import annotations

import io
import json
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from control_plane import lifecycle
from control_plane.audit import record_platform_event
from control_plane.models import Tenant
from control_plane.tenancy import tenant_context

logger = logging.getLogger(__name__)


def backup(tenant: Tenant) -> str:
    """A full backup of one school (storage key of the zip)."""
    key = lifecycle.build_export(tenant)
    record_platform_event(action="tenant.backed_up", tenant=tenant, data={"key": key})
    return key


def _open(source: str) -> zipfile.ZipFile:
    path = Path(source)
    if path.is_file():
        return zipfile.ZipFile(path)
    with default_storage.open(source, "rb") as handle:
        return zipfile.ZipFile(io.BytesIO(handle.read()))


def counts(tenant: Tenant) -> dict[str, int]:
    """Rows per model in a school's database."""
    result: dict[str, int] = {}
    with tenant_context(tenant):
        for label in settings.TENANT_APP_LABELS:
            for model in apps.get_app_config(label).get_models():
                result[model._meta.label] = model.objects.using(tenant.db_alias).count()
    return result


def _load(tenant: Tenant, archive: zipfile.ZipFile, old_slug: str) -> None:
    old_prefix, new_prefix = f"tenants/{old_slug}/", f"tenants/{tenant.slug}/"
    with tempfile.TemporaryDirectory() as folder:
        fixtures = []
        for name in archive.namelist():
            if name.startswith("data/") and name.endswith(".json"):
                text = archive.read(name).decode()
                if old_prefix != new_prefix:  # file paths stored in records
                    text = text.replace(json.dumps(old_prefix)[1:-1], new_prefix)
                target = Path(folder) / Path(name).name
                target.write_text(text, encoding="utf-8")
                fixtures.append(str(target))
        with tenant_context(tenant):
            if fixtures:
                # One call, so foreign keys are checked once everything is in.
                call_command("loaddata", *fixtures, database=tenant.db_alias, verbosity=0)
            _reindex(tenant)
    for name in archive.namelist():
        if name.startswith("files/") and not name.endswith("/"):
            key = new_prefix + name[len("files/") :]
            if default_storage.exists(key):
                default_storage.delete(key)
            default_storage.save(key, ContentFile(archive.read(name)))


def _reindex(tenant: Tenant) -> None:
    """Search indexes over encrypted values depend on the school's key: redo them."""
    from apps.students.models import Student
    from apps.students.services import _set_national_id_index

    for student in Student.objects.exclude(national_id=""):
        _set_national_id_index(student)
        Student.objects.filter(pk=student.pk).update(national_id_bidx=student.national_id_bidx)


def restore_copy(source: str, *, slug: str, name: str) -> Tenant:
    """Load a backup into a new school database nobody can open (for checking)."""
    from control_plane.provisioning.service import provision_tenant

    archive = _open(source)
    manifest = json.loads(archive.read("manifest.json"))
    tenant = provision_tenant(slug=slug, name=name, seed=False)
    # Keep it unreachable: the middleware only serves active schools.
    Tenant.objects.filter(pk=tenant.pk).update(status=Tenant.Status.PROVISIONING)
    tenant.refresh_from_db()
    try:
        _load(tenant, archive, manifest["school"])
    except Exception:
        discard_copy(tenant)
        raise
    record_platform_event(
        action="tenant.restored_copy",
        tenant=tenant,
        data={"from": manifest["school"], "records": sum(manifest["records"].values())},
    )
    return tenant


def restore_in_place(tenant: Tenant, source: str) -> Tenant:
    """Replace a school's database with a backup of that same school."""
    from control_plane.db import forget_tenant_connection
    from control_plane.migration_runner import migrate_tenant_database
    from control_plane.provisioning.base import get_provisioner
    from control_plane.secrets import get_secrets_backend

    archive = _open(source)
    manifest = json.loads(archive.read("manifest.json"))
    if manifest["school"] != tenant.slug:
        raise ValueError(f"This backup is of {manifest['school']}, not {tenant.slug}.")
    was = tenant.status
    with transaction.atomic():
        Tenant.objects.filter(pk=tenant.pk).update(status=Tenant.Status.PROVISIONING)
    provisioner = get_provisioner()
    forget_tenant_connection(tenant.db_alias)
    provisioner.drop_database(tenant)
    get_secrets_backend().put(tenant.secret_ref, provisioner.create_database(tenant))
    forget_tenant_connection(tenant.db_alias)
    migrate_tenant_database(tenant)
    _load(tenant, archive, tenant.slug)
    Tenant.objects.filter(pk=tenant.pk).update(status=was)
    tenant.refresh_from_db()
    record_platform_event(
        action="tenant.restored",
        tenant=tenant,
        data={"records": sum(manifest["records"].values()), "at": timezone.now().isoformat()},
    )
    return tenant


def discard_copy(tenant: Tenant) -> None:
    from control_plane.provisioning.service import discard_tenant

    for key in lifecycle._all_keys(f"tenants/{tenant.slug}/"):
        default_storage.delete(key)
    Tenant.objects.filter(pk=tenant.pk).update(status=Tenant.Status.PROVISIONING)
    tenant.refresh_from_db()
    discard_tenant(tenant)


def drill(tenant: Tenant) -> dict[str, Any]:
    """Back up, restore as a throwaway copy, compare every table, throw the copy away."""
    started = timezone.now()
    key = backup(tenant)
    copy_slug = f"drill-{timezone.now():%m%d%H%M%S}"[:40]
    copy = restore_copy(key, slug=copy_slug, name=f"Restore drill of {tenant.name}")
    try:
        before, after = counts(tenant), counts(copy)
        mismatched = {m: (before[m], after.get(m)) for m in before if before[m] != after.get(m)}
        encrypted_ok = _same_secrets(tenant, copy)
    finally:
        discard_copy(copy)
        default_storage.delete(key)
    return {
        "school": tenant.slug,
        "tables": len(before),
        "records": sum(before.values()),
        "mismatched": mismatched,
        "encrypted_values_match": encrypted_ok,
        "seconds": round((timezone.now() - started).total_seconds(), 1),
        "passed": not mismatched and encrypted_ok,
    }


def _same_secrets(original: Tenant, copy: Tenant) -> bool:
    """Encrypted values read back the same under the copy's own key."""
    from apps.students.models import Student

    def snapshot(tenant: Tenant) -> list[tuple[str, str, str]]:
        with tenant_context(tenant):
            return sorted(
                Student.objects.values_list("admission_number", "national_id", "national_id_bidx")
            )

    a, b = snapshot(original), snapshot(copy)
    same_values = [(n, i) for n, i, _ in a] == [(n, i) for n, i, _ in b]
    # Indexes are keyed per school, so they must differ wherever there is a value.
    rekeyed = all(x[2] != y[2] for x, y in zip(a, b, strict=True) if x[1])
    return same_values and rekeyed
