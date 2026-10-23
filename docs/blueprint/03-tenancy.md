# 03 · Multi-tenant architecture

**Decision: keep the existing database-per-school design.** It already meets the brief's isolation rules and
is covered by tests (`tests/test_tenant_isolation.py`, `tests/test_authorization.py`). This document records
how it works, where it falls short of the brief, and what each later phase adds.

## 1. Layers

| Layer | Where it lives | Holds |
|---|---|---|
| Public SaaS site | `web/` routes under `(marketing)` (Phase 2), apex domain `nexedu.com.gh` | Marketing pages, pricing, registration entry, sign-in |
| Control plane | `default` database, `backend/control_plane/` | Users, tenants, memberships, cells, plans, subscriptions, module entitlements, platform staff, support grants, payment-reference routing |
| School workspace | One database per school, `backend/apps/*` | All school-owned records: students, staff, academics, attendance, results, fees, messages, the school's audit chain |
| Super Admin | `web/` routes under `(platform)` at `admin.nexedu.com.gh` (Phase 7), `control_plane` APIs | Operates the control plane only. Reads school data only through an audited support grant. |

## 2. Tenant identity and resolution

- **Stable identifier:** `Tenant.id` (UUID) is the permanent identifier. `Tenant.slug` is the human-facing
  handle used in subdomains; it is unique and validated (`TENANT_SLUG_VALIDATOR`, reserved words blocked).
  Renaming a slug is a platform-admin operation that keeps the UUID.
- **Resolution** (`control_plane/middleware.py`): `X-Tenant` header, else subdomain of `TENANT_BASE_DOMAIN`.
  This only *selects* a school.
- **Authorization** (`core/permissions.py`): `IsTenantMember` then loads the caller's active memberships for
  that tenant from the control plane. A browser-supplied slug therefore grants nothing by itself: without a
  server-side membership row the request is refused (`test_api_rejects_users_from_another_school`,
  `test_member_of_two_schools_sees_only_selected_school`).
- **Fail closed:** tenant models raise `TenantContextMissing` without a selected school
  (`test_tenant_models_fail_closed_without_a_school`); objects from one school can't be saved into another
  (`CrossTenantAccess`).
- **Status gate:** only `active` tenants resolve. `suspended`, `provisioning`, `failed` and `offboarded` return 403.

## 3. Isolation by surface

| Surface | Mechanism today | Gap → phase |
|---|---|---|
| Database | Separate DB and DB role per school; router sends tenant apps to the tenant alias | — |
| API querysets | Selectors scope by role and ownership; every view declares permissions (`test_every_tenant_api_view_declares_permissions`) | Add module gate (Phase 4) |
| Files | Keys forced to `tenants/<slug>/…`, path traversal refused (`core/files.py`); S3 IAM scoped to prefix in Terraform | Uploaded logos and documents: same helper (Phase 2/5) |
| Background jobs | `TenantTask` requires explicit `tenant_slug` (`test_tenant_task_requires_explicit_school`) | Module-disabled jobs skip safely (Phase 4) |
| HTTP caching | `Vary: X-Tenant, Authorization, Cookie` and `private, no-store` on tenant responses | — |
| App cache (Valkey) | `core.misc.tenant_cache_key` prefixes keys with `t:<tenant_uuid>:` (tested) | Use it for every tenant cache entry |
| Search | No search index yet | Same prefix rule if one is added |
| Exports and reports | Generated inside tenant context | Cross-school analytics only via the nightly anonymised export (architecture plan §1.1) |
| Payments webhooks | `PaymentReference` maps provider reference → tenant; body metadata is never trusted | — |
| Audit | Per-school hash-chained log; exported to S3. Platform-level hash-chained log in the control plane (Phase 1, done) | Stream platform log to S3 Object Lock too (Phase 7) |

## 4. Tenant lifecycle

```
registered ──► provisioning ──► active ◄──► suspended
                    │              │
                    ▼              ▼
                 failed      offboarding ──► offboarded (DB dropped after export + retention period)
```

| Transition | Who | Today | To build |
|---|---|---|---|
| registered → provisioning | Owner registration (auto) or platform admin | CLI `provision_tenant` only | Self-serve registration workflow, Celery job (Phase 3) |
| provisioning → active | System | Synchronous, in-process | Idempotent job keyed by registration ID; cleanup of orphaned DB on failure (Phase 3) |
| active ↔ suspended | Platform admin (non-payment, abuse) | Status field and gate exist | Admin UI, reason, audit, owner notice (Phase 7) |
| → offboarding/offboarded | Owner request or contract end | Not built | Full export (JSON + CSV + PDFs), retention timer, crypto-shred data key, drop DB (Phase 7) |

## 5. Support access

Platform staff never hold school memberships by default
(`test_platform_superuser_gets_no_implicit_school_access`). When support genuinely needs to see a school:

1. Support staff open a **SupportAccessGrant** (tenant, reason, scope: read-only or read-write, max 4 hours).
2. The school owner approves it in-app, or a second platform admin approves it for emergencies.
3. During the grant the request carries a synthetic, time-boxed role; a banner shows in the UI.
4. Every request is written to both the control-plane audit log and the school's own audit chain.

Built in Phase 7. Until then there is no support access path. That is the safe default.

## 6. Scale assumptions (to be measured, not promised)

The architecture plan estimates ~85k registered users and ~8k peak concurrent users at 100 schools. These are
design inputs only. Phase 9 load tests (result-release day, fee-deadline bursts) against staging decide capacity.
Nothing in this blueprint promises a user count.
