<picture>
  <source media="(prefers-color-scheme: dark)" srcset="web/public/brand/nex-edu-logo-dark.png">
  <img src="web/public/brand/nex-edu-logo.png" alt="Nex Edu" height="96">
</picture>

# Nex Edu

Nex Edu is a multi-tenant school management system for Ghanaian basic schools: KG, Primary (Basic 1-6)
and Junior High (JHS 1-3). It is designed for 100+ schools and 30,000+ pupils, with room for 10× growth.
Each school has its **own PostgreSQL database**. The full design is in
[docs/architecture-plan.md](docs/architecture-plan.md).

## Status

| Phase | What's in it | State |
|---|---|---|
| 0. Foundation | Database-per-school tenancy, passkeys and TOTP, role permissions, per-school encryption, tamper-evident audit log, AWS Terraform, CI | Done, tested |
| 1. Core school operations | Academic year and terms, classes and GES subjects, timetable with clash checks, admissions (office and public online form), pupil records and CSV/Excel import, offline-capable attendance, score entry, BECE-graded report cards with positions and aggregates, fees in GH₵ with mobile money (Paystack, Flutterwave), receipts, double-entry ledger, announcements, inbox, SMS (Arkesel) and email | Done, tested |
| 2. Portals and engagement | Parent and student mobile app, parent–teacher messaging, LMS, events | Next |
| 3. Operations | Payroll (GRA PAYE, SSNIT), library, transport, hostel, inventory | Later |

Tests: 101 backend tests, 15 web unit tests, and a 36-step end-to-end run against the demo school.

## Preview it locally

Needs Python 3.13+ and Node 22+ with pnpm. No Docker needed: school databases are SQLite files.

**1. Backend (first time only: install and load the demo school)**

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install uv          # macOS/Linux: .venv/bin/...
UV_PROJECT_ENVIRONMENT=.venv .venv/Scripts/uv sync --locked
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py seed_demo
```

**2. Start the API** (leave it running)

```bash
cd backend
DJANGO_SETTINGS_MODULE=config.settings.dev .venv/Scripts/granian --interface asgi --host 127.0.0.1 --port 8000 config.asgi:application
```

**3. Start the web app** (second terminal)

```bash
cd web
pnpm install
pnpm build && pnpm start -p 3100
```

Open http://localhost:3100. Every demo login uses the password `NexEdu-demo-2026!`.

| Sign in as | Email | Sees |
|---|---|---|
| Parent | parent@greenfield.test | One child's report card, attendance, fees and "Pay now" |
| Head teacher | head@greenfield.test | Everything academic: results, admissions, people, settings |
| Class teacher | teacher@greenfield.test | JHS 1 A only: register, score entry, comments |
| Bursar | bursar@greenfield.test | Fees, invoices, payments, receipts |
| Proprietor | owner@greenfield.test | Everything |

Staff accounts must turn on an authenticator app (Google or Microsoft Authenticator) or a passkey at first
sign-in. The parent account doesn't need one. The public admission form is at
http://localhost:3100/apply?school=greenfield.

To try school sign-up, open http://localhost:3100/signup. Locally, emails (including the 8-letter verification
code) print in the API terminal. Approve the school as platform staff:

```bash
.venv/Scripts/python manage.py review_registration --list
.venv/Scripts/python manage.py review_registration --approve <id>   # or --reject <id> --note "reason"
```

To start over, stop the API, delete `backend/var`, and repeat step 1 from `migrate`.

## Layout

```
backend/            Django 6.1 + DRF API
  control_plane/    Schools, cells, logins, memberships, tenant routing, provisioning, invites
  core/             Roles and permissions, encryption, audit log, files, PDFs, security middleware
  apps/             Per-school modules: school, academics, students, staff, admissions,
                    attendance, assessments, finance, communication
  integrations/     Paystack, Flutterwave, Arkesel SMS, WhatsApp, Ghana phone numbers
  tests/            Isolation, authorization, every module, payments with mocked providers
web/                Next.js 16 + React 19 + Tailwind 4 (all screens for staff, parents, public form)
infra/terraform/    AWS: network, database cells, ECS, CloudFront + WAF, security baseline
infra/pgbouncer/    Connection pooling per cell
docs/               Architecture and security plan
```

## Everyday commands

```bash
# backend
.venv/Scripts/python -m pytest -n auto
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
.venv/Scripts/python manage.py migrate_tenants        # all schools: canaries first, then cell by cell
.venv/Scripts/python manage.py provision_tenant --slug newschool --name "New School"
.venv/Scripts/python manage.py spectacular --file var/openapi.yaml --validate --fail-on-warn

# web
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

## Rules for adding a feature module

1. Create the app under `backend/apps/<name>/` and add it to `TENANT_APPS` and `TENANT_APP_LABELS`.
2. Put writes in `services.py`, wrap them in `tenant_atomic()`, and record an audit event for each change.
3. Build every API queryset in a selector scoped to what the caller's roles may see.
4. Every endpoint maps each action to a permission in `required_permissions`. A test fails if one doesn't.
5. Store references to users as UUIDs, because cross-database foreign keys are impossible.
6. Use `EncryptedTextField` for health, identity and bank data, and never put those values in audit snapshots.
7. Background tasks use `TenantTask` and receive `tenant_slug` explicitly. Queue them with `transaction.on_commit`.
8. Money is integer pesewas. Migrations must be expand/contract, because schools upgrade in waves.
