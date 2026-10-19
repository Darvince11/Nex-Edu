from __future__ import annotations

import io

import pytest
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command

from control_plane.migration_runner import plan_waves, run_tenant_migrations
from control_plane.models import Cell, Tenant, TenantMigrationRun
from control_plane.provisioning.postgres import scram_sha256_verifier
from control_plane.provisioning.service import NoCellCapacity, choose_cell, validate_slug


@pytest.mark.parametrize("slug", ["ab", "1school", "Bad_Slug", "www", "api", "a" * 41])
def test_invalid_slugs_are_rejected(slug):
    with pytest.raises(ValidationError):
        validate_slug(slug)


def test_provisioned_school_is_active_with_key_and_schema(tenant):
    tenant.refresh_from_db()
    assert tenant.status == Tenant.Status.ACTIVE
    assert tenant.wrapped_data_key
    assert tenant.schema_version


@pytest.mark.django_db
def test_cell_selection_packs_by_free_capacity():
    full = Cell.objects.create(
        name="a", db_host="h", pooler_host="p", admin_secret_ref="s", capacity=1
    )
    Tenant.objects.create(slug="t-one", name="x", cell=full, db_name="d1", secret_ref="r")
    roomy = Cell.objects.create(name="b", db_host="h", pooler_host="p", admin_secret_ref="s")
    assert choose_cell() == roomy
    roomy.is_accepting = False
    roomy.save()
    with pytest.raises(NoCellCapacity):
        choose_cell()


def test_waves_put_canaries_first_then_cells(db):
    a = Cell.objects.create(name="a", db_host="h", pooler_host="p", admin_secret_ref="s")
    b = Cell.objects.create(name="b", db_host="h", pooler_host="p", admin_secret_ref="s")
    mk = lambda slug, cell, canary=False: Tenant(slug=slug, cell=cell, is_canary=canary)  # noqa: E731
    waves = plan_waves([mk("b1", b), mk("a1", a), mk("c1", b, True), mk("a2", a)])
    assert [[t.slug for t in w] for w in waves] == [["c1"], ["a1", "a2"], ["b1"]]


def test_migrate_tenants_records_runs(make_tenant):
    make_tenant("alpha", is_canary=True)
    make_tenant("bravo")
    call_command("migrate_tenants", stdout=io.StringIO())
    assert TenantMigrationRun.objects.filter(succeeded=True).count() == 2


def test_rollout_halts_after_failing_wave(make_tenant):
    canary = make_tenant("alpha", is_canary=True)
    make_tenant("bravo")

    def failing(tenant):
        if tenant.slug == "alpha":
            raise RuntimeError("boom")

    results = run_tenant_migrations(Tenant.objects.all(), migrate=failing)
    assert [r.tenant.slug for r in results] == ["alpha"]
    assert not results[0].succeeded
    run = TenantMigrationRun.objects.get(tenant=canary)
    assert "boom" in run.error


def test_migrate_tenants_command_fails_loudly(make_tenant, monkeypatch):
    make_tenant("alpha")
    from control_plane import migration_runner

    def boom(tenant):
        raise RuntimeError("bad migration")

    monkeypatch.setattr(migration_runner, "migrate_tenant_database", boom)
    with pytest.raises(CommandError, match="Rollout halted"):
        call_command("migrate_tenants", stdout=io.StringIO(), stderr=io.StringIO())


def test_scram_verifier_format():
    verifier = scram_sha256_verifier("pw", salt=b"0" * 16)
    assert verifier.startswith("SCRAM-SHA-256$4096:")
    assert "pw" not in verifier
    assert verifier == scram_sha256_verifier("pw", salt=b"0" * 16)
