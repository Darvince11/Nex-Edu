# 09 · Phased implementation backlog

Phase numbers follow the brief. They replace the phase labels in the README status table: the README's
"0. Foundation" and "1. Core school operations" are largely what the brief calls Phases 1 and 5, built on the
previous identity stack.

Each phase ends with the checklist in the brief (§10): compare against the feature register, run all tests,
verify isolation and permissions, check design consistency, verify the phase's sign-in and sign-up flows, record actual
results, update the register.

## Phase 1 · Identity and security foundation (D1: built in-house)

Status 23 Oct 2026: done except 1.7 (Sentry) and the Playwright tests in 1.8.

| # | Task | Status |
|---|---|---|
| 1.1 | Owner sign-up with consent record, email verification by code, honeypot, rate limits, branded emails | Done, tested |
| 1.2 | Sign-in, MFA step, passkeys, forgot/set password screens in the new design | Done; API tested, screens reviewed manually only |
| 1.3 | Audit of sign-in events in the platform log | Done, tested |
| 1.4 | `PlatformStaff`, `IsPlatformStaff`, `add_platform_staff`, platform audit chain + append-only trigger | Done, tested |
| 1.5 | Generated authorization matrix (endpoint × method × role, plus cross-school) | Done, tested, mutation-checked |
| 1.6 | Tenant cache keys by UUID; pin of school-less endpoints | Done, tested |
| 1.7 | Error tracking (Sentry) and tracing | Not started: needs a Sentry project |
| 1.8 | Playwright end-to-end tests of sign-in and sign-up | Not started (moved to Phase 2 with the other browser tests) |

## Phase 2 · Design system and application shell

| # | Task | Done when |
|---|---|---|
| 2.1 | Add remaining tokens (02 §1), `Forbidden` state, icon set (one library, e.g. `lucide-react`, tree-shaken) | Components documented in a `/dev/ui` page (dev only) |
| 2.2 | `nav.ts` tree + collapsible sidebar + breadcrumbs, driven by `GET /me/workspace` | Only effective, permitted items render (tests) |
| 2.3 | Public site `(marketing)`: home, features, modules, pricing, school types, FAQ, contact, terms, privacy, DPA | Content approved by owner (D3); Lighthouse a11y ≥ 95 |
| 2.4 | Super Admin layout shell `(platform)` | Reachable only by platform staff |
| 2.5 | School logo upload and display (top bar, admission page, PDFs) | Upload validated and re-encoded; PDF shows both logos correctly |
| 2.6 | Playwright + axe smoke tests for shell, a form, a table, a modal in both themes | In CI |

## Phase 3 · Registration and onboarding

Done early (23 Oct 2026): `SchoolRegistration`, one pending request per owner, web-address checks, duplicate flag,
manual approval command that provisions the school and grants the owner role last, rejection with a reason.
Remaining: run provisioning as an idempotent background job with orphan clean-up, the onboarding checklist
(profile, terms, classes, fees, invites, modules), and the Super Admin review screen (Phase 7).

## Phase 4 · Module registry and dynamic navigation

`core/modules.py`, plan/subscription/entitlement/activation models, `ModuleEnabled` permission, task gating,
activation UI with dependencies and setup checks, history, downgrade behaviour. **Done when** tests cover:
not entitled, entitled but inactive, active but no permission, dependency blocking, deactivation with open
records, and the "every view declares a module or is core" check.

## Phase 5 · Core school management (complete the gaps)

Already implemented and tested: students, guardians, import, admissions, attendance, academics, timetable,
scores, grading, report cards, fees, payments, receipts, announcements, inbox, SMS, members, audit.
To build: staff screens, guardian directory, departments, staff attendance, leave requests, promotion and
graduation, outstanding balances and finance reports, scholarships, messages (parent–teacher), calendar,
basic reports, custom roles, audit-log screen, grading settings screen.

## Phase 6 · Optional modules

One module at a time, each behind its registry entry, in this order (smallest dependency footprint and most
requested by basic schools first): library → clubs → meetings → discipline → clinic → transport → canteen →
inventory → facilities → visitors → lms → hostel → accounting → payroll → procurement → online exams →
special education → website → alumni → compliance. Each flips to `available=True` only after its tests pass.

## Phase 7 · SaaS administration and subscriptions

Super Admin dashboard, tenant lifecycle (suspend, reactivate, offboard with export and crypto-shred), plans,
entitlements, overrides, platform billing via Paystack subscriptions (GHS), usage limits (students, SMS,
storage), support access grants, platform audit, migrations/cells/jobs views.

## Phase 8 · Integrations and intelligence

Push notifications, calendar sync, video links, accounting exports, webhooks and API keys for the developer
API module, analytics warehouse (nightly anonymised export → Athena), AI assistance (only with a DPIA update).

## Phase 9 · Production readiness

Full test run, sign-in, sign-up and registration flows on staging, isolation and permission matrix, module and subscription enforcement,
payment reconciliation, import/export, backup and single-school restore drill, load tests (k6: result-release
day, fee deadline), accessibility audit, deployment and rollback rehearsal, external penetration test. Output:
a release-readiness report built from the actual results.

