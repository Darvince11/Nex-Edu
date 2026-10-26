# Nex Edu — Architecture & Security Plan

## Context

Greenfield build (the `c:\Users\User\Desktop\SMS` folder is empty). Goal: Nex Edu, a multi-tenant school management
system that serves **100+ schools and 30,000+ students** (plus ~50k parents and ~3k staff) in
**Ghana**, for **basic schools: KG, Primary (Basic 1-6) and Junior High (JHS 1-3)**. Senior High is out of
scope. The security posture must be strong enough for children's personal data under Ghana's
**Data Protection Act, 2012 (Act 843)**, overseen by the Data Protection Commission (DPC).

> Revised after approval: the target moved from Nigerian secondary schools to Ghanaian basic schools.
> Money is in Ghana cedis (pesewas), payments favour mobile money, SMS goes through a Ghanaian gateway,
> grading follows GES / NaCCA and BECE conventions, and compliance follows Act 843.

Decisions confirmed with the user:
- **Backend:** Python (Django), **Frontend:** TypeScript (Next.js), **Mobile:** React Native (Expo)
- **Hosting:** AWS
- **Tenancy:** one database per school
- **Payments / messaging:** Paystack and Flutterwave (GHS, mobile money and card), Arkesel SMS, WhatsApp

Design target is **10× headroom**: 1,000 schools / 300k students without re-architecture.

---

## 1. Architecture overview

**Style: modular monolith + async workers, deployed in "cells".** Microservices are not justified at this
scale; a well-bounded Django monolith is faster to build, easier to secure, and scales horizontally.

```
                   Users (web / Android / iOS / SMS for parents)
                                   │
            Route 53 ── CloudFront (West African edges) ── AWS WAF + Shield
                     │                                    │
          Next.js web (ECS Fargate)              Django API (ECS Fargate, ASGI)
                     └──────────────┬─────────────────────┘
                                    │
        ┌──────────────┬────────────┼──────────────┬───────────────────┐
  Control-plane DB   Valkey      SQS queues      S3 (files)      Secrets Manager / KMS
  (tenants, users,   (cache,     → Celery        per-tenant      (per-tenant DB creds,
   memberships,      sessions,     workers        prefixes)       per-tenant data keys)
   billing)          rate limit,   (PDFs, SMS,
                     websockets)   payments, imports)
                                    │
                    PgBouncer per cell (transaction pooling)
                                    │
   ┌───────────── Cell A ─────────────┐   ┌───────────── Cell B ─────────────┐
   │ Aurora PostgreSQL Serverless v2  │   │ Aurora PostgreSQL Serverless v2  │  ...
   │  school_001 … school_025 (DBs)   │   │  school_026 … school_050 (DBs)   │
   └──────────────────────────────────┘   └──────────────────────────────────┘
                                    │
          Nightly export → S3 (Parquet) → Athena / QuickSight (cross-school analytics)
```

### 1.1 Database-per-school design

| Piece | Design |
|---|---|
| **Control-plane DB** | One Aurora cluster holding `tenants`, `users` (global identity), `memberships` (user × school × role), subscription/billing, feature flags, schema-version per tenant. A parent with children in two schools has one login. |
| **Tenant DBs** | One PostgreSQL database per school, each with its **own Postgres role and password** stored in Secrets Manager. A routing bug can't silently write to another school's DB with the wrong credentials. |
| **Cells** | ~25 school DBs per Aurora Serverless v2 cluster. Limits the blast radius of an outage, scales capacity per cell, and allows bin-packing large schools. Premium or very large schools can get a dedicated cluster. |
| **Routing** | Middleware resolves the tenant from the subdomain (`greenfield.nexedu.com.gh`) or the `X-Tenant` header for mobile. It checks the user's membership in the control plane, then sets a `contextvars` tenant. A Django DB router sends all tenant-app models to that tenant's DB alias, which is registered lazily from the tenant registry. A request with no resolved tenant fails closed. |
| **Pooling** | PgBouncer (transaction mode) per cell, with one pool per database. Django uses `CONN_MAX_AGE=0` and `DISABLE_SERVER_SIDE_CURSORS=True` behind PgBouncer. This stops 100+ DBs × N tasks from exhausting connections. |
| **Migrations** | A `migrate_tenants` management command runs migrations in parallel batches. Order: canary schools → one cell → all cells. It records the version per tenant and halts on the first failure. Use **expand/contract** migrations only, so old and new code both work during rollout. |
| **Provisioning** | A Celery workflow picks a cell (bin-packing), creates the DB and role, stores the secret, runs migrations, seeds defaults (KG 1 to JHS 3, GES subjects, NaCCA and BECE grading, 30/70 assessment weights, ledger accounts), and creates the subdomain. Target is under 5 minutes, fully automated from the super-admin console. |
| **Backups per school** | One school can be restored, exported, or deleted on its own. This is a big advantage of DB-per-school for Act 843 erasure requests and school off-boarding. |
| **Cross-school reporting** | Never query across tenant DBs live. A nightly Celery job exports anonymised or aggregated tables to S3 Parquet. Athena or QuickSight serves group or proprietor dashboards and platform analytics. |

### 1.2 Capacity estimate (design baseline)

| Metric | Estimate | 10× target |
|---|---|---|
| Registered users | ~85k | ~850k |
| Peak concurrent users (result release, fee deadline) | ~8k | ~80k |
| Peak API rate | ~800 req/s | ~8k req/s |
| Tenant DB size per school (5 yrs) | 2–10 GB | — |
| File storage (photos, assignments, PDFs) | ~3 TB | ~30 TB |

Baseline compute: 4–6 API tasks (2 vCPU / 4 GB), 2 web tasks, 4 worker tasks, autoscaling on CPU and queue
depth. Result-release spikes are handled by pre-generating report-card PDFs to S3 and serving them through
CloudFront signed URLs, not rendering on demand.

### 1.3 AWS region

- **Primary:** `af-south-1` (Cape Town), the nearest full-service AWS region to Ghana (Aurora, ECS, SQS).
  Data is processed outside Ghana, so the school contracts and DPC registration must document this and its
  safeguards. Get a Ghanaian legal review before launch.
- **DR:** `eu-west-1` (Ireland), using Aurora Global Database or cross-region snapshot copy.
- **CloudFront** serves static assets from West African edge locations.
- Before committing, measure latency from Accra and Kumasi to `af-south-1` versus `eu-west-1`. European
  regions are sometimes faster due to cable routing. If eu-west-1 wins, keep it primary with documented
  transfer safeguards.

---

## 2. Technology stack (latest stable, pinned)

Exact versions are pinned at scaffold time in `uv.lock` and `pnpm-lock.yaml`. Renovate keeps them current.

| Layer | Choice |
|---|---|
| Language | Python 3.14, TypeScript (strict), Node.js 24 LTS |
| Backend | **Django 6.x** (move to 6.2 LTS when released in April 2027), Django REST Framework, drf-spectacular (OpenAPI 3.1), django-allauth (headless, MFA), django-guardian or custom object-level permissions, Django Channels (realtime) |
| ASGI server | Granian or Uvicorn workers under Gunicorn |
| Jobs | Celery 5.x with SQS broker, django-celery-beat for schedules |
| Database | Aurora PostgreSQL (latest supported major, 17 or 18), PgBouncer |
| Cache / realtime | ElastiCache **Valkey** 8 |
| Files | S3 with SSE-KMS, GuardDuty Malware Protection for S3 |
| PDFs | ReportLab (report cards, receipts); pure Python, no system libraries needed |
| Web | **Next.js 16** (App Router, React 19), Tailwind CSS 4, shadcn/ui, TanStack Query, React Hook Form + Zod, types generated from OpenAPI via `openapi-typescript` |
| Mobile | **Expo** (React Native, latest SDK) for parents, students, and teachers. Offline-first attendance via SQLite + sync queue. Push via Expo / FCM / APNs |
| Email / SMS / chat | Amazon SES, Arkesel (Ghanaian SMS gateway; Hubtel or mNotify as alternatives), WhatsApp Business Cloud API |
| Payments | **Paystack** (primary) and **Flutterwave** (secondary) in GHS: MTN MoMo, Telecel Cash, AirtelTigo Money and cards; Hubtel is a candidate third provider |
| IaC | Terraform (or OpenTofu) with modules per cell |
| CI/CD | GitHub Actions with OIDC to AWS (no static keys), ECR, ECS blue/green via CodeDeploy |
| Observability | OpenTelemetry SDK → CloudWatch / Amazon Managed Grafana, Sentry, structured JSON logs tagged with `tenant_id` and `request_id` |
| Python tooling | uv, ruff, mypy (strict), pytest + pytest-django, factory_boy, hypothesis |
| JS tooling | pnpm, Biome or ESLint 9, Vitest, Playwright |

---

## 3. Repository layout (monorepo)

```
SMS/
├── backend/
│   ├── config/                 # settings (base/dev/prod), urls, asgi, celery
│   ├── platform/               # CONTROL PLANE: tenants, users, memberships, billing, provisioning, db router, tenant middleware
│   ├── core/                   # shared: audit log, encryption helpers, permissions, pagination, idempotency, files
│   ├── apps/                   # TENANT apps (live in each school DB)
│   │   ├── academics/          # sessions, terms, classes, arms, subjects, timetable
│   │   ├── students/           # enrolment, profiles, guardians, health, history, promotions
│   │   ├── staff/              # teachers, assignments, HR, evaluation
│   │   ├── attendance/
│   │   ├── assessments/        # CA, exams, CBT, grading, report cards, transcripts
│   │   ├── finance/            # fee structures, invoices, double-entry ledger, payments, scholarships, expenses
│   │   ├── payroll/
│   │   ├── communication/      # messaging, announcements, notifications, surveys
│   │   ├── lms/                # courses, assignments, submissions, online quizzes, virtual-class links
│   │   ├── library/  transport/  hostel/  inventory/  events/  admissions/
│   │   └── reports/            # report builder, exports
│   └── integrations/           # paystack, flutterwave, arkesel, whatsapp, ses, expo_push
├── web/                        # Next.js app (admin, teacher, student, parent portals by role)
├── mobile/                     # Expo app
├── infra/terraform/            # accounts, network, cell module, ecs, waf, monitoring
├── packages/api-client/        # generated TS client from OpenAPI
└── .github/workflows/
```

Each domain app follows the same layering: `models.py`, `services.py` (all business rules and writes),
`selectors.py` (reads), `api/` (serializers and views only), `tasks.py`, `tests/`. Views never touch the ORM
directly. This keeps authorization and auditing in one place.

---

## 4. Feature scope and delivery phases

All feature groups from the provided list are included. They are sequenced so that schools get value early.

| Phase | Scope |
|---|---|
| **0. Foundation** | AWS accounts and landing zone, Terraform cells, CI/CD, control plane, tenant provisioning, auth (MFA), RBAC, audit log, super-admin console |
| **1. Core school ops** | Academic structure (KG, Basic 1-6, JHS 1-3; 3 terms), admissions and enrolment, student and staff profiles, bulk CSV/Excel import, timetable, attendance (web + offline mobile), CA and exams, grading and GES-style terminal reports with BECE aggregates, fee billing with Paystack/Flutterwave, receipts, announcements, SMS/WhatsApp/email notifications |
| **2. Portals and engagement** | Parent and student mobile app, parent–teacher messaging, behaviour reports, LMS (assignments, quizzes, CBT practice), events and calendar, surveys |
| **3. Operations** | Payroll (GRA PAYE, SSNIT contributions), library, transport (routes, GPS optional), hostel, inventory and assets, scholarships, budgeting and expenses |
| **4. Insight** | Analytics warehouse, custom report builder, proprietor or group dashboards, public API and webhooks for third parties |

Ghana-specific requirements: a low-bandwidth UI (small bundles, aggressive caching), offline attendance, SMS
for parents without smartphones, Ghana cedi amounts as integer pesewas, +233 phone numbers, Ghana Card
numbers, and mobile money as the default payment method. Payment webhooks must handle delayed and duplicate
notifications.

---

## 5. Security plan

The baseline is **OWASP ASVS 5.0 Level 2** for the whole app. Level 3 controls apply to authentication,
finance, and health records.

### 5.1 Identity and authentication
- Mandatory **MFA** (authenticator app, TOTP) for all staff,
  admins, and finance roles. Optional but encouraged for parents. SMS OTP only as a fallback.
- Passwords: Argon2id hashing, minimum 12 characters, check against breached-password lists (HIBP
  k-anonymity), no forced periodic rotation (NIST SP 800-63B).
- Students under 13 log in with school-issued credentials or QR cards, managed by the school.
- **Web sessions:** server-side sessions in Valkey, `HttpOnly; Secure; SameSite=Lax` cookies, CSRF tokens,
  rotation on login and privilege change, idle timeout of 30 minutes for staff.
- **Mobile:** OAuth 2.1-style auth-code + PKCE. Access tokens last 10 minutes. Refresh tokens rotate with
  reuse detection, are bound to the device, and are stored in Keychain or Keystore.
- Progressive delays and lockout on failed logins, plus new-device and new-location login alerts.
- Super-admin "impersonation" requires a reason, is time-boxed, shows a banner, and is fully audited.

### 5.2 Authorization
- **RBAC per school:** Super Admin (platform), School Owner/Proprietor, Principal, Admin, Bursar,
  Teacher, Form Teacher, Librarian, Driver, Hostel Warden, Parent, Student. Custom roles are composed from
  fine-grained permissions.
- **Object-level rules (ABAC):** teachers see only their assigned classes and subjects. Parents see only
  linked children. Students see only themselves. Bursars see finance data but not health records.
- Enforced centrally in `services`/`selectors` via a policy layer. Querysets default to scoped managers, so
  an unscoped query is a code-review failure.
- An **authorization matrix test suite** is generated from the permission table. It checks every
  endpoint × role × "own vs other" combination, including cross-tenant attempts. It runs in CI and blocks
  merges.

### 5.3 Tenant isolation
- Separate database, separate DB role and credential per school, and a separate S3 prefix with
  IAM-condition-scoped access.
- The tenant context is fail-closed. Celery tasks must carry `tenant_id` explicitly, and the task base
  class sets and clears the context.
- Cache keys, websocket groups, and search indexes are all namespaced by tenant.
- Dedicated CI tests attempt cross-tenant access through every API surface.

### 5.4 Data protection and encryption
- **In transit:** TLS 1.2+ (prefer 1.3) everywhere, HSTS with preload, and TLS to Aurora and Valkey.
- **At rest:** KMS encryption on Aurora, S3, EBS, Valkey, SQS, and backups.
- **Field-level encryption** for the most sensitive data (health records, NIN, guardian ID numbers, bank
  details for payroll). Uses envelope encryption with a **per-school data key** wrapped by KMS. Deleting
  a school's key makes its leftover backups unreadable (crypto-shredding).
- Blind indexes (HMAC) where encrypted fields must be searchable.
- Data minimisation: no BVN or card data stored. Card payments stay entirely with Paystack/Flutterwave,
  which keeps the platform out of PCI DSS scope beyond SAQ A.
- Signed, short-lived S3 URLs for all files. Uploads are validated by type and size, re-encoded for images,
  and malware-scanned before they become visible.

### 5.5 Application security controls
- Strict nonce-based CSP, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, and frame
  protection.
- CORS allowlist per environment. SSRF guard on any outbound URL fetch. No raw SQL without review.
- Rate limiting by IP, user, and tenant at WAF and app level. Tighter limits on login, OTP, and payment
  endpoints.
- **Idempotency keys** on all payment and money-moving endpoints. Webhooks verify signatures (Paystack
  HMAC-SHA512, Flutterwave hash) and re-query the provider's verify API before crediting.
- The finance module uses a **double-entry ledger** with immutable entries. Corrections are reversals,
  never edits. A nightly reconciliation job matches against provider settlement reports.
- Grade changes after publication need approval and record the old and new values.

### 5.6 Audit logging
- Append-only audit log per tenant covering who, what, when, where (IP and device), before and after, and
  why. It records logins, permission changes, grade edits, fee changes, exports, and impersonation.
- Each entry is hash-chained to the previous one for tamper evidence. Entries stream to an S3 bucket with
  **Object Lock (compliance mode)** in a separate log-archive account.
- School admins can view their school's audit trail in the UI.

### 5.7 Infrastructure security (AWS)
- **Multi-account** setup via AWS Organizations / Control Tower: `management`, `security`, `log-archive`,
  `shared-services`, `staging`, `production`. Production access is through IAM Identity Center SSO with
  MFA, plus just-in-time elevation. No IAM users and no long-lived keys.
- VPC with private subnets for compute and data, and no public DB endpoints. VPC endpoints for S3, SQS,
  Secrets Manager, and KMS. Security groups follow least privilege.
- **AWS WAF** with managed rule sets (core, SQLi, known bad inputs, IP reputation), Bot Control on login
  routes, and geo-based rate rules. Shield Standard is included, with Shield Advanced optional.
- GuardDuty, Security Hub (CIS and AWS Foundational benchmarks), AWS Config, CloudTrail org trail,
  Inspector for ECR images, and IAM Access Analyzer.
- Secrets Manager with automatic rotation for DB credentials. Secrets are never stored in env files or the
  repo.
- Containers run as non-root on minimal base images (distroless or Chainguard Python), with read-only root
  filesystems and no shell in production images.

### 5.8 Software supply chain ("latest dependencies" done safely)
- **Renovate** keeps every dependency current, auto-merging patch and minor updates when tests pass.
  Majors get a weekly grouped PR. A minimum release age of 3–7 days is set before adopting new versions,
  which protects against compromised fresh releases.
- Lockfiles with hashes (`uv.lock`, `pnpm-lock.yaml`). pnpm runs with `onlyBuiltDependencies`, and
  install scripts are blocked by default.
- CI gates: `pip-audit`, `pnpm audit`, OSV-Scanner, Semgrep and CodeQL (SAST), gitleaks (secrets), Trivy
  (image and IaC scan), Checkov or tfsec (Terraform).
- An SBOM is generated with Syft for every image. Images are signed with cosign, and ECS deploys only
  signed images. GitHub Actions are pinned to commit SHAs. Branch protection requires signed commits and
  two reviewers for `infra/` and `platform/`.
- OWASP ZAP baseline DAST runs against staging on every release. An external penetration test happens
  before launch and annually.

### 5.9 Backup, DR, and resilience

| Target | Value |
|---|---|
| RPO (data loss) | ≤ 5 minutes (Aurora continuous backup, point-in-time recovery for 35 days) |
| RTO (full region) | ≤ 4 hours |
| RTO (single school restore) | ≤ 1 hour |

- **AWS Backup** to a separate account with **Vault Lock**, so ransomware or a compromised admin cannot
  delete backups. Daily cross-region copies go to the DR region.
- Monthly automated restore test of a random school DB, with checksum validation. A full DR game day runs
  twice a year.
- Multi-AZ for Aurora, Valkey, and ECS tasks spread across three AZs.

### 5.10 Compliance (Ghana Data Protection Act, 2012 (Act 843))
- Register with the Data Protection Commission (DPC) as required for data controllers, renew the
  registration on schedule, and appoint a Data Protection Supervisor.
- A **Data Protection Impact Assessment** is required before launch because the system processes children's
  data at scale.
- The platform acts as **processor**, and each school is the **controller**. A Data Processing Agreement is
  signed with every school.
- Parental consent capture for under-18s. Privacy notice and consent records are stored per student.
- Data-subject rights tooling: export a person's data (JSON/PDF), correct it, and erase or anonymise it,
  subject to the school's legal retention duties.
- Retention schedules per data type, for example alumni academic records kept permanently and health
  records kept for a limited time. Automated purge jobs enforce them.
- **Breach notification:** Act 843 requires notifying the DPC and affected people as soon as reasonably
  practicable. The internal target is 72 hours. An incident-response runbook, an on-call rota, and
  pre-drafted school and parent notifications are prepared before launch.
- Processing outside Ghana (AWS Cape Town) is disclosed to schools and documented with its safeguards.
- GDPR-aligned practices are used so that the platform can later serve schools in other countries.

---

## 6. Performance and scalability practices
- Cursor pagination everywhere, `select_related` and `prefetch_related` enforced, and N+1 query detection in
  tests (`django-zeal` or `nplusone`).
- Valkey caching for timetables, class lists, and dashboards, invalidated on write.
- Heavy work runs in Celery: report cards, bulk imports, notifications fan-out, and exports. Queues are
  separated by priority (`critical-payments`, `notifications`, `reports`, `default`), so a result-release
  PDF storm never delays payment processing.
- Notification fan-out is batched to stay within provider rate limits, with SMS cost controls per school.
- ECS autoscaling on CPU and SQS queue depth. Aurora Serverless v2 ACU limits are set per cell.
- Read replicas per cell for reports when needed.
- The web app uses Server Components, route-level code splitting, and next/image. The mobile app caches
  responses for offline viewing.

---

## 7. Environments and delivery
- Environments: `local` (Docker Compose with Postgres, Valkey, LocalStack, MailHog), `staging` (one cell
  holding a copy of the production topology with synthetic data), and `production`.
- Trunk-based workflow. Every PR runs lint, type checks, unit tests, authorization matrix, migration check,
  and security scans. Merging to main deploys to staging automatically. Production deploys are approved
  manually and roll out blue/green with automatic rollback on SLO alarms.
- Tenant migrations run as a separate pipeline stage: canary schools first, then cell by cell.
- SLOs: 99.9% monthly availability, p95 API latency under 300 ms, and payment webhook processing under
  60 seconds.

---

## 8. Verification

1. **Tenant isolation:** automated tests try to read and write across schools through every endpoint,
   Celery task, file URL, and websocket. All must fail. These also run in CI.
2. **Authorization matrix:** generated role × endpoint × ownership tests pass at 100%.
3. **Load test** with k6 or Locust against staging. Simulate result-release day (8k concurrent, then 10×)
   and fee-deadline payment bursts. Confirm p95 under 300 ms and no queue starvation.
4. **Migration rehearsal:** run `migrate_tenants` against 200 synthetic school DBs and measure duration
   and failure handling.
5. **Security:** ZAP DAST clean, external penetration test with all critical and high findings fixed,
   Security Hub score above 90%, and no critical CVEs in images.
6. **DR drill:** restore a single school to a point in time, then fail over the full region to `eu-west-1`
   and measure against RPO and RTO.
7. **Payments:** test-mode end-to-end with Paystack and Flutterwave, including duplicate, delayed, and
   forged webhooks. Reconciliation must match to the pesewa.
8. **Offline mobile:** take attendance offline on a low-end Android device, reconnect, and confirm sync
   and conflict handling.
9. **Compliance:** DPIA signed off, data-subject export and erasure tested end to end, and the breach
   runbook exercised as a tabletop drill.

## First implementation step after approval
Scaffold the monorepo (Phase 0): Terraform landing zone and one cell module, Django project with the
`platform` control plane, tenant router, middleware, and provisioning command, the auth stack with MFA and
the audit log, CI security gates, and a Next.js shell with login and a school-switcher.
