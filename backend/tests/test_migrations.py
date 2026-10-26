"""Rollback safety: every migration can be undone, and a school database really goes
back past the latest changes and forward again (the rollback rehearsal)."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import migrations
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

OURS = ("control_plane", "core", "audit", *settings.TENANT_APP_LABELS)
# Added in Phases 6 to 8: an emergency rollback could take any of these back out.
RECENT = ("assist", "compliance", "website", "alumni", "support", "exams", "procurement")


def test_every_migration_can_be_reversed():
    loader = MigrationLoader(None, ignore_no_migrations=True)
    irreversible = [
        f"{app}.{name}"
        for (app, name), migration in loader.disk_migrations.items()
        if app in OURS
        for op in migration.operations
        if (isinstance(op, migrations.RunPython) and op.reverse_code is None)
        or (isinstance(op, migrations.RunSQL) and op.reverse_sql is None)
    ]
    assert irreversible == []


def test_a_school_database_goes_back_and_forward_again(tenant):
    alias = tenant.db_alias
    with tenant_context(tenant):
        for app in RECENT:
            call_command("migrate", app, "zero", database=alias, verbosity=0)
        applied = {a for a, _ in MigrationRecorder(_connection(alias)).applied_migrations()}
        assert not applied & set(RECENT)
        call_command("migrate", database=alias, verbosity=0)
        applied = {a for a, _ in MigrationRecorder(_connection(alias)).applied_migrations()}
        assert set(RECENT) <= applied


def _connection(alias):
    from django.db import connections

    return connections[alias]
