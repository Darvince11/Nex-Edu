# 05 · Module registry, entitlements and activation

## 1. Three gates

A user can use a module operation only when **all three** hold:

```
effective = plan_entitles(tenant, module)        # Layer A: Super Admin, via plan or override
          ∧ school_activated(tenant, module)     # Layer B: School admin switched it on
          ∧ role_permits(user, tenant, perm)     # Layer C: core/rbac.py
```

Core modules are always entitled and always active, so only Layer C applies to them. The API enforces all
three. The sidebar only reflects them; hiding a link is never the control.

## 2. Registry

The registry is **code**, not database rows: `backend/core/modules.py` defines each module once, versioned
with the code that implements it. The database stores only plan entitlements, per-school activation state and
history. A module that exists in the registry but has no implementation is marked `available=False` and can't
be entitled or activated, so it never shows up as a dead link.

```python
Module(
    key="hostel",
    name="Hostel and boarding",
    kind=OPTIONAL,               # CORE | OPTIONAL
    depends_on=("students",),
    setup_checks=("at least one hostel and room defined",),
    permissions=("hostel.view", "hostel.manage"),
    nav="hostel",                # key into web/src/lib/nav.ts
    background_tasks=("hostel.tasks.nightly_roll_call_report",),
    available=False,             # flips to True when the module ships and passes its tests
)
```

### API enforcement

- Views declare `module = "hostel"`. A DRF permission `ModuleEnabled` (added to the default permission chain
  after `IsTenantMember`) returns `403 {"code": "module_disabled"}` when the module is unavailable, not
  entitled or not active.
- `TenantTask` checks the same gate before running a module's job and exits cleanly (logged, not failed).
- A test asserts that every tenant view either belongs to a core module or declares `module`, in the same
  style as `test_every_tenant_api_view_declares_permissions`.

## 3. Catalogue

`Available` means code exists and is tested today. Everything else is planned and stays hidden until it ships.

### Core (always on)

| Key | Module | Depends on | Available |
|---|---|---|---|
| `dashboard` | Dashboard | — | Yes (basic) |
| `school` | School profile and settings | — | Yes |
| `academics` | Years, terms, levels, arms, subjects, teaching assignments, timetable | school | Yes |
| `students` | Students, enrolment, guardians, import | academics | Yes |
| `staff` | Teachers and staff records | school | Yes |
| `admissions` | Office and public online admissions | students | Yes |
| `attendance` | Student attendance (offline-capable) | students | Yes. Staff attendance: No |
| `assessments` | Components, scores, grading, report cards | academics, students | Yes |
| `finance_core` | Fee items, schedules, invoices, payments, receipts, mobile money | students | Yes |
| `communication` | Announcements, inbox, SMS, email | — | Yes |
| `portals` | Parent / student / teacher views | students | Yes (web). Mobile app: No |
| `reports_basic` | Standard reports and exports | — | Partial (finance summary, attendance summary) |
| `members` | Users, roles, invitations | — | Yes |
| `audit` | Audit log and verification | — | Yes |

### Optional

| Key | Module | Depends on | Plan tier (proposed) |
|---|---|---|---|
| `hostel` | Hostel and boarding | students | Standard |
| `transport` | Transport and fleet | students, staff | Standard |
| `canteen` | Canteen and meals | students, finance_core | Standard |
| `library` | Library | students, staff | Standard |
| `clinic` | Clinic and health | students | Standard |
| `inventory` | Store and inventory | staff | Standard |
| `procurement` | Procurement and vendors | inventory, accounting | Premium |
| `payroll` | Advanced HR and payroll (GRA PAYE, SSNIT) | staff, accounting | Premium |
| `accounting` | Full accounting (GL, budgets, expenses) | finance_core | Premium |
| `facilities` | Facilities and maintenance | staff | Standard |
| `lms` | LMS and e-learning | academics | Standard |
| `online_exams` | Online examinations | lms, assessments | Premium |
| `discipline` | Discipline and counselling | students | Standard |
| `special_ed` | Special education and learning support | students | Standard |
| `clubs` | Clubs and sports | students | Basic |
| `visitors` | Visitor and gate management | staff | Standard |
| `meetings` | Parent meetings and appointments | communication | Basic |
| `website` | Public school website and advanced admissions | admissions | Premium |
| `alumni` | Alumni and fundraising | students, finance_core | Premium |
| `compliance` | Accreditation and compliance | — | Premium |
| `analytics` | Advanced analytics and AI | — | Premium |
| `multi_campus` | Multi-campus management | — | Enterprise |
| `developer_api` | Premium integrations and developer APIs | — | Enterprise |

Plan tiers are a proposal for the owner (decision D3). Prices are not set in this blueprint.

## 4. Data model (control plane)

| Model | Fields | Notes |
|---|---|---|
| `Plan` | key, name, is_public, price_pesewas_monthly, price_pesewas_termly, limits (JSON: max_students, sms_per_month, storage_gb) | Edited by Super Admin |
| `PlanModule` | plan, module_key | Which optional modules a plan entitles |
| `Subscription` | tenant, plan, status (trialing, active, past_due, cancelled), current_period_start/end, provider, provider_ref | One active per tenant (partial unique constraint) |
| `EntitlementOverride` | tenant, module_key, granted (bool), reason, expires_at, granted_by | Super Admin exceptions; audited |
| `TenantModule` | tenant, module_key, is_active, activated_at, activated_by, deactivated_at, settings (JSON) | School-level switch |
| `ModuleActivationEvent` | tenant, module_key, action, actor, reason, at | Append-only history, shown on the module page |

## 5. Activation rules

1. **Activate:** entitled ✓ → dependencies active ✓ → setup checks shown → school admin confirms → `TenantModule`
   active → event + school audit entry. Dependencies are never auto-activated silently.
2. **Deactivate:** blocked when an active module depends on it, or when the module has open transactions
   (unsettled canteen balances, books on loan, payroll run in progress). The UI lists the blockers.
3. **Data is never deleted** by deactivation. Records stay in the school DB, read-only; reactivation restores
   access. Deletion only happens through tenant offboarding or an Act 843 erasure request.
4. **Downgrade:** if a plan change removes an entitlement, the module becomes read-only for 30 days with a
   notice, then hidden. Data is kept.
5. Every change is written to `ModuleActivationEvent` and the school's audit chain.

## 6. Exposure to the web app

`GET /api/v1/me/workspace` (selected school) returns:

```json
{ "school": {"slug": "...", "name": "...", "logo_url": "..."},
  "roles": ["principal"],
  "permissions": ["students.view", "..."],
  "modules": {"hostel": {"active": true}, "library": {"active": false, "entitled": true}},
  "onboarding": {"complete": false, "next_step": "terms"} }
```

The sidebar is built from this (see [06-navigation.md](06-navigation.md)).
