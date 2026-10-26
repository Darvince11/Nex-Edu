# 01 · Existing-project audit and technology assessment

Audit date: 23 October 2026, on `main` at commit `4563003` plus uncommitted work (logo and colour changes,
security-page and settings edits).

## 1. Summary

Nex Edu is **already a multi-tenant SaaS**, not a single-school app: one database per school, a control
plane for identities and memberships, server-side membership checks on every request, and tests that try to
break isolation. The core day-school operations (students to fees) are built and tested. What's missing
relative to the brief is the **SaaS layer around the schools**: public website, self-serve registration,
plans and module entitlements, a Super Admin console, and (at the time) the switch from django-allauth to
**Auth0**. *Update 23 Oct 2026: the owner chose to keep and extend the in-house identity system instead (D1).*

No school name is hard-coded. The one tenant-specific string found is the default admission prefix `NXE`,
which each school overrides in its profile.

## 2. Test results (run during this audit)

| Suite | Command | Result |
|---|---|---|
| Backend | `pytest -n auto` | **104 passed** in 217 s |
| Web unit | `pnpm test` | **15 passed** (2 files) |
| Web static | `pnpm typecheck`, `pnpm lint` | Pass (41 files) |
| Web build | `pnpm build` | Pass (23 routes) |
| End-to-end | — | **None in the repo.** The README's "36-step end-to-end run" can't be reproduced from committed code. |

## 3. Stack

| Area | In use | Assessment |
|---|---|---|
| Backend | Python 3.13 (local), Django 6.1, DRF 3.18, drf-spectacular | Current and supported. Keep. |
| ASGI server | Granian 2.8 | Fine. Keep. |
| Frontend | Next.js 16.4 (App Router), React 19.3, TypeScript 6, Tailwind 4.3, TanStack Query 5 | Current. Keep. The architecture plan's shadcn/ui and React Hook Form are **not** used; components are hand-rolled in `ui.tsx`. Keep that, since it's small and consistent. |
| Validation | DRF serializers (server), Zod 4 (client) | Keep. |
| Database | PostgreSQL per school in production (Aurora), SQLite per school locally | Keep. |
| Pooling | PgBouncer per cell (Terraform + `infra/pgbouncer`) | Keep. |
| Jobs | Celery 5.6, Redis protocol (Valkey) | Keep. |
| Files | django-storages S3, per-school prefix | Keep. |
| PDFs | ReportLab 5 | Keep. |
| Authentication | django-allauth 65 headless: TOTP, recovery codes, JWT for mobile | Kept and extended (D1, 23 Oct 2026): self-service owner sign-up, email codes, new screens. See [04](04-identity.md). |
| Authorization | Custom role → permission table, selectors, fail-closed DRF permissions | Keep and extend (modules, platform roles). |
| Encryption | Per-school data keys (KMS-wrapped), field encryption, blind indexes | Keep. |
| Audit | Per-school hash-chained log, S3 export | Keep; add a platform-level log. |
| Payments | Paystack, Flutterwave (GHS, mobile money), idempotent checkout, verified webhooks | Keep. |
| Messaging | Arkesel SMS, WhatsApp, email | Keep. |
| Infra | Terraform: network, cell, ECS, edge (CloudFront + WAF), security baseline | Keep. |
| CI | GitHub Actions: ruff, migrations check, pytest, Django deploy check, pip-audit, OpenAPI, Biome, tsc, Vitest, build, pnpm audit, gitleaks, Semgrep, OSV, Trivy, terraform validate, SBOM | Strong. Add Playwright e2e and axe in Phase 2. |
| Observability | Structured JSON logs with request and tenant ID | **Gap:** no error tracking (Sentry) or tracing (OpenTelemetry) yet, though the plan names both. Add in Phase 1. |
| Mobile | Planned (Expo) | Not started. Out of scope until Phase 5+. |
| Dependency updates | Renovate | Keep. |

No migration away from the current stack is proposed.

## 4. Feature inventory: what exists

| Area | Built | Evidence |
|---|---|---|
| Tenancy | DB per school, cells, provisioning command, wave migrations, suspension status gate | `control_plane/`, `test_tenant_isolation.py`, `test_provisioning_and_migrations.py` |
| Identity | Invite-only accounts, TOTP, staff MFA gate, password reset, breached-password check | `test_authorization.py`, `test_security_baseline.py` |
| Members | Invite, roles, deactivate, resend, no escalation | `test_academics_and_members.py` |
| Academics | Sessions, terms, KG–JHS levels, arms, GES subjects, teaching assignments, timetable with clash checks | same |
| Students | Records, guardians, CSV/Excel import (all-or-nothing, dry run), encrypted sensitive fields | `test_students_and_admissions.py`, `test_crypto_and_audit.py` |
| Admissions | Office and public form (honeypot), offer → enrol | same |
| Attendance | Registers, offline batch sync with conflict rules, absence SMS | `test_attendance.py` |
| Assessments | Components (total 100), scores, grading, positions, BECE aggregate, publish/lock, audited amendments, PDFs | `test_assessments.py` |
| Finance | Fee items and schedules, invoices, part payments, discounts, void, online payments, webhooks, receipts, summary | `test_finance.py` |
| Communication | Announcements by audience, inbox, SMS limit | `test_communication.py` |
| Audit | Hash chain, tamper detection, append-only, API, S3 export | `test_crypto_and_audit.py` |
| Web | Login, MFA setup, school switcher, dashboard, students, admissions, attendance, scores, results, fees, announcements, inbox, academics, people, settings, public apply form; logo and blue theme | `web/src/app/` |

## 5. Gaps against the brief

| Brief section | Gap |
|---|---|
| §2 Branding | Tokens done; missing: very-light-blue surface token, permission-denied state, school logo upload, chart palette, Playwright/axe checks |
| §3A Public site | None exists. `/` redirects to `/schools` |
| §3B Super Admin | Only Django admin (`ADMIN_ENABLED`), no product console |
| §3 Lifecycle | No self-serve registration, export or offboarding; provisioning is a synchronous CLI |
| §3 Support access | None (safe default) |
| §4 Auth0 | Not used. Superseded by D1: identity stays in-house |
| §5 Modules | No registry, plans, subscriptions, entitlements or activation |
| §6 Navigation | Flat role-based list; no groups, sub-navigation, module awareness or breadcrumbs |
| §5 Core modules | Missing: staff screens, guardian directory, departments, staff attendance, leave, promotion, balances/reports, scholarships, messaging, calendar, custom roles, audit screen |
| §5 Optional modules | None built (hostel, transport, library, etc.) |
| §8 Observability | No Sentry or OpenTelemetry |
| §9 Testing | No end-to-end or load tests in repo |

## 6. Scope conflict to resolve (decision D2)

The brief lists **senior high and boarding schools**. The project's agreed scope (architecture plan, README) is
**Ghanaian basic schools: KG, Primary and JHS, with Senior High out of scope**. Academics seed only KG–JHS, and
grading implements BECE. Supporting SHS means programmes, electives, WASSCE grading and houses: a real model
change. Boarding as an optional module fits either scope. Until D2 is decided, the blueprint treats SHS as
deferred and designs `Section` and grading so they can be extended.

## 7. Risks found

| Risk | Severity | Action |
|---|---|---|
| Auth0 cost at the expected MAU, and an extra cross-border processor under Act 843 | High (business) | Resolved: D1 keeps identity in-house |
| Provisioning failure leaves a `failed` tenant and possibly an orphaned DB; no idempotency key | Medium | Phase 3 |
| Unknown vs suspended school gives 404 vs 403, revealing which slugs exist | Low | Return the same response for both on unauthenticated requests (moved to Phase 7, with tenant lifecycle) |
| Report-card footer text isn't wrapped and can overlap the footer logo | Low | Wrap or truncate in `core/pdf.py` (Phase 2) |
| README test counts and e2e claim are out of date | Low | Update the README when Phase 1 lands |
