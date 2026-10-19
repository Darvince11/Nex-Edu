# Nex Edu

Nex Edu is a multi-tenant school management system for 100+ Nigerian schools and 30,000+ students,
designed for 10× growth. Each school has its **own PostgreSQL database**. The control plane
holds global logins, schools and memberships. The full design is in
[docs/architecture-plan.md](docs/architecture-plan.md).

This repository currently contains **Phase 0: Foundation**.

| Area | Status |
|---|---|
| Database-per-school tenancy (routing, provisioning, parallel canary-first migrations) | Done, tested |
| Auth: passkeys, TOTP, recovery codes, JWT for mobile, invite-only, breached-password check | Done |
| Role-based access + record-level scoping + mandatory MFA for staff, fail-closed defaults | Done, tested |
| Field encryption with a per-school key (KMS), blind indexes, crypto-shredding | Done, tested |
| Tamper-evident, append-only audit log with S3 Object Lock export | Done, tested |
| Next.js web shell: login, MFA setup, school switcher, student list, nonce CSP | Done, builds |
| Terraform: VPC, Aurora cells, PgBouncer, Valkey, SQS, ECS, ALB, CloudFront, WAF, GuardDuty, Backup Vault Lock | Done, validates |
| CI security gates, Renovate, container images | Written, not yet run on GitHub |
| Phase 1 modules (admissions, attendance, exams, report cards, fees with Paystack/Flutterwave, notifications) | Next |

## Layout

```
backend/            Django 6.1 + DRF API (Python 3.13+, uv)
  control_plane/    Schools, cells, users, memberships, tenant router/middleware, provisioning
  core/             RBAC, permissions, encryption, audit log, security middleware, Celery base task
  apps/             School (tenant) apps: academics, students — the pattern for every new module
  tests/            Isolation, authorization, crypto, audit, provisioning, security tests
web/                Next.js 16 + React 19 + Tailwind 4
infra/terraform/    AWS modules (network, cell, ecs-service, edge, security-baseline) + production env
infra/pgbouncer/    PgBouncer config for each cell
docs/               Architecture and security plan
```

## Run it locally

Requires Python 3.13+ and Node 22+ with pnpm. No Docker needed: school databases are SQLite files.

```bash
cd backend
python -m venv .venv && .venv/Scripts/python -m pip install uv     # macOS/Linux: .venv/bin/...
UV_PROJECT_ENVIRONMENT=.venv .venv/Scripts/uv sync --locked
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py provision_tenant --slug greenfield --name "Greenfield College" --canary
.venv/Scripts/python manage.py add_member --tenant greenfield --email you@example.com --role principal --password 'choose-a-long-password'
.venv/Scripts/python manage.py runserver 127.0.0.1:8000

cd ../web
pnpm install
pnpm dev            # http://localhost:3000, proxies /api and /_allauth to Django
```

With `ACCOUNT_EMAIL_VERIFICATION = "mandatory"`, the user's email must be verified before the first login.
In development the verification email prints to the Django console.

To exercise the real PostgreSQL provisioner, run `docker compose up -d`, then use
`DJANGO_SETTINGS_MODULE=config.settings.compose` and register a cell with `manage.py add_cell`.

## Everyday commands

```bash
# backend
.venv/Scripts/python -m pytest -n auto                # full test suite
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
.venv/Scripts/python manage.py migrate_tenants         # all schools: canaries, then cell by cell
.venv/Scripts/python manage.py spectacular --file var/openapi.yaml

# web
pnpm api:types      # regenerate TypeScript types from the OpenAPI schema
pnpm lint && pnpm typecheck && pnpm build
```

## Rules for adding a feature module

1. Create the app under `backend/apps/<name>/` and add its label to `TENANT_APPS` and `TENANT_APP_LABELS`.
2. Put writes in `services.py` and record an audit event for each change. Wrap them in `tenant_atomic()`, never plain `transaction.atomic()`.
3. Build every API queryset in `selectors.py`, scoped to what the user's roles may see.
4. Every view must declare `required_permissions`. The test suite fails if one doesn't.
5. Store references to users as UUIDs, because cross-database foreign keys are impossible.
6. Use `EncryptedTextField` for health, identity and bank data, and never put those values in audit snapshots.
7. Background tasks use `TenantTask` and receive `tenant_slug` explicitly.
8. Migrations must be expand/contract, because schools upgrade in waves.
