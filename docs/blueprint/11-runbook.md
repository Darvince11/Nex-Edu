# Deployment and rollback runbook

For whoever ships Nex Edu to production and whoever is on call when it goes wrong. Commands
run from `backend/` unless stated.

## 1. Before a release

A release is a commit on `main` that passed every CI job (`.github/workflows/ci.yml`):

- lint and format, migrations committed, backend tests (isolation, permissions, crypto, audit);
- production settings pass `check --deploy --fail-level WARNING`;
- web unit tests, the browser suite with accessibility checks, and the OpenAPI schema;
- secret scanning, Semgrep, OSV dependency scan, Trivy on the Terraform;
- image built, scanned and given an SBOM.

**Migrations must work with the release before them (expand only).** Add tables, add columns
that are nullable or have a default, add indexes. Never drop or rename a column, table or
choice value in the release that stops using it; do that one release later. This is what makes
an application rollback safe without touching any database (section 4).

## 2. Deploying

1. **Control plane first:** `python manage.py migrate` (the shared database: schools,
   people, billing).
2. **New image:** the ECS service rolls to the new image tag (immutable git SHA); the load
   balancer drains old tasks. Watch the target group's 5xx rate and the console's
   **System › Jobs and databases** page.
3. **School databases, in waves:** `python manage.py migrate_tenants`. Canary schools
   (`Tenant.is_canary`) go first, then one wave per cell. The run **stops at the first wave
   with a failure**; every attempt is kept (`TenantMigrationRun`) and shown on the Jobs and
   databases page. A school whose database is behind keeps working on the old schema, which the
   new code still reads (expand only).
4. **Check:** console dashboard (no new problems), Jobs and databases (no failed or late
   jobs), one sign-in to a canary school.

## 3. Scheduled jobs that must be running

Celery beat runs every job in `CELERY_BEAT_SCHEDULE`. The ones that, if stopped, hurt schools
or money:

| Job | Every | If it stops |
|---|---|---|
| `integrations.payments.reconcile_all` | 15 min | Fee payments whose webhook was lost stay pending |
| `control_plane.billing_daily` | day | No invoices, reminders or suspensions; paid charges not confirmed |
| `control_plane.purge_closed_schools` | day | Closed schools kept past 90 days |
| `compliance.remind_all` | day | No renewal reminders |
| `control_plane.health_checks` | 5 min | Stuck school set-ups and broken databases go unnoticed |

Each run is recorded; the Jobs and databases page marks a job **Late** after twice its interval
and **Failed** on an error.

## 4. Rolling back

Pick the smallest step that fixes it.

1. **Application rollback (most incidents):** redeploy the previous image tag on the ECS
   service. No database change is needed because migrations are expand only.
2. **One school's schema:** if a school migration failed half way or must be undone,
   `python manage.py migrate <app> <previous_migration> --database <alias>` inside that school's
   context. Every migration can be reversed (`tests/test_migrations.py` fails otherwise), and a
   school database is taken back past the Phase 6 to 8 apps and forward again in the same test.
3. **One school's data** (records deleted by mistake, a damaged database):
   - `python manage.py backup_school --slug <school>` makes a logical backup (every record and
     file) under the school's own prefix. Take one before any manual repair.
   - `python manage.py restore_school --from <zip> --copy-as <new-slug>` loads it as a copy no
     one can open, to check what it holds.
   - `python manage.py restore_school --from <zip> --in-place <school> --yes-replace` drops the
     school's database, creates it again, migrates and loads the backup. Sign-ins, billing and
     every other school are untouched. Encrypted fields are encrypted again with the school's
     key; the Ghana Card search index is rebuilt.
4. **A whole cluster** (lost or corrupted): restore the Aurora cluster to a point in time
   (automated backups, 35 days) into a new cluster; repoint the cell's endpoints. For one school
   from that restored cluster, dump its database there and load it into the live cell.

## 5. Backups

- **Aurora automated backups:** 35 days, point-in-time; deletion protection on.
- **AWS Backup** (vault with a compliance lock: 35 to 400 days, unchangeable after 3 days): daily
  at 01:00 UTC kept 35 days and copied to the disaster-recovery vault for 90 days; monthly on the
  1st at 02:00 UTC, moved to cold storage after 30 days, kept 395.
- **Per school:** on demand with `backup_school`; the closing export when a school leaves.
  These zips hold personal data in clear: they stay under the school's prefix (SSE-KMS) and are
  deleted after use.

**Restore drill:** `python manage.py restore_drill --slug <school>` backs up a school, restores it
as a copy, compares every table and the encrypted values, and removes the copy. Run it monthly
on a canary school and after any change to models or encryption; record the result.

## 6. Suspending, reactivating, closing

From the console (school page › Account status), super admins only, always with a reason. An
unpaid invoice suspends a school automatically 30 days after its due date and paying reactivates
it. Closing exports the school for its proprietor and destroys it after 90 days (data key,
database, files). See `control_plane/lifecycle.py`.

## 7. Not yet in this repository

- The deploy workflow (`deploy.yml`, referred to at the end of `ci.yml`) that pushes to ECR,
  signs with cosign and updates the ECS service. Until it exists, deploys are manual.
- A staging environment matching production, where sections 2 to 5 are rehearsed for real.
