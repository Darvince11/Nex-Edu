# Nex Edu SaaS blueprint (Phase 0)

Phase 0 output for the multi-tenant SaaS brief: an audit of what exists, the target design, and a phased plan.
It extends [../architecture-plan.md](../architecture-plan.md), which remains the reference for infrastructure,
security controls and Act 843 compliance. Nothing here has been implemented yet, except the logo and colour
work already in the working tree.

| # | Document | Brief deliverable |
|---|---|---|
| 01 | [Audit and technology assessment](01-audit.md) | 1, 2, 7 (inventory), 16 |
| 02 | [Design system](02-design-system.md) | 3 |
| 03 | [Multi-tenant architecture](03-tenancy.md) | 4 |
| 04 | [Identity, sign-up and school onboarding](04-identity.md) | 5, 6 |
| 05 | [Module registry and entitlements](05-modules.md) | 10 |
| 06 | [Navigation](06-navigation.md) | 8 |
| 07 | [Roles and permissions](07-roles-permissions.md) | 9 |
| 08 | [Database and API changes](08-data-and-api-changes.md) | 11 |
| 09 | [Phased backlog](09-backlog.md) | 12 |
| — | [Feature register](feature-register.csv) (160 features, opens in Excel) | 7, 13 |

Deliverables 14, 15, 17 and 18 (code, test results, deployment runbook, readiness checklist) are produced per
phase from Phase 1 on.

## Where things stand (25 Oct 2026)

Phases 1 to 5 are done (see [09](09-backlog.md)). Counts are in the
[feature register](feature-register.csv): 119 of 194 features tested. Latest runs: backend **281 passed**, web
unit **88 passed**, browser (Playwright, real API, WCAG 2.2 AA checks in light and dark mode) **70 passed**; ruff,
Biome, `tsc`, OpenAPI validation and the production build pass. No feature is marked **Accepted**; that is the
owner's call.

Phase 5 (25 Oct 2026): staff records, departments, staff register and leave; guardian directory, grading and
audit-log screens; end of year promotion and graduation; outstanding balances, collections and scholarships;
parent–teacher messages; the school calendar with Ghana's public holidays; class list, attendance and results
reports (CSV and PDF); custom roles made by the proprietor.

Latest changes (owner's request, 24 Oct 2026): light theme by default with a dark-mode switch; a profile page and
Sign out in every top bar (Inbox moved to the menu, Switch school removed); sign-in opens the person's school with
no school list; dashboard charts; proprietor-only logo, staff access and score
amendments; the head teacher enters no scores; class teachers add pupils to and prepare report cards for their own
class; teachers keep their own classes' timetables. See [07](07-roles-permissions.md).

## Decisions

| ID | Decision | Outcome |
|---|---|---|
| **D1** | Identity provider | **Built in-house on django-allauth** (owner, 23 Oct 2026). This replaces the earlier Auth0 choice and overrides the brief's Auth0 rule at the owner's direction. All Auth0 code was removed. See [04](04-identity.md). |
| **D2** | Support senior high schools? | **Basic schools only (KG–JHS) for now.** SHS deferred; hostel/boarding stays an optional module. |
| **D3** | Plans and prices | **Price bands set** (owner, 24 Oct 2026): up to 1,000 pupils GH₵250; 1,001–2,000 GH₵350; more than 2,000 GH₵450. **No free trial.** Billing (owner, 26 Oct 2026): **monthly** invoices, paid by mobile money or card through Paystack; a school is **suspended 30 days after an unpaid invoice's due date** until it pays; a closed school's data is kept **90 days**, then destroyed; schools **buy SMS bundles** beyond a monthly allowance. In code: `control_plane/pricing.py`. Optional modules are **included in every band** for now (GH₵0); any can be made a paid add-on in the console. |
| **D4** | Review new school registrations? | **Manual approval** by platform staff before a school's database is created. Built: `manage.py review_registration`. |
| **D5** | Phase 8 integrations | **Owner, 26 Oct 2026:** accounting export as one standard CSV (QuickBooks, Xero, Sage, Tally import it); video as any pasted link; AI for drafting only (report comments, announcements), off by default, no pupil names sent, Claude; multi-campus stays deferred. |

## Work report: identity, sign-in and sign-up

**Built**

| Area | What |
|---|---|
| Sign-in | New split-screen `/login`: email + password with show/hide and Caps Lock warning, authenticator-app MFA step, email-verification step for unverified accounts, enumeration-safe messages |
| Sign-up | `/signup` for school owners: account → 8-letter email code (resend with cooldown) → school details with live web-address check → "under review". Resumes where the person left off. |
| Password pages | `/forgot-password` (same answer for every email) and a restyled set-password page for invitations and resets, with live password rules |
| Registration | `SchoolRegistration` model, API (`/api/v1/registrations/`, `/slug-check/`), one pending request per owner and one live request per web address (database constraints), duplicate flag for reviewers, `review_registration` command that provisions the school, sets its class levels and contacts, and grants the owner role last |
| Security | Consent record, own honeypot, rate limits, branded emails that warn staff never ask for codes, audit of every sign-in event in the platform log |
| Platform | `PlatformStaff`, `IsPlatformStaff`, `add_platform_staff`, platform audit chain with append-only trigger, `GET /api/v1/platform/tenants/` |
| Guards | Generated authorization matrix; pin of school-less endpoints; every platform route needs platform staff |
| Legal | Draft privacy notice and terms (`/legal/*`), clearly marked as drafts |
| Removed | Auth0 SDK, settings, proxy logic, Action, setup guide, tests and `.env.local` |

**Fixed along the way:** allauth's honeypot setting silently didn't apply to the headless API; replaced with our
own. Parents no longer see the staff "set up two-step" banner.

**Not done**

- Super Admin screen for reviewing registrations (command only for now).
- Error tracking (Sentry) still needs a project from the owner.
- Legal review of the notices.
- Browser end-to-end tests (Playwright) and an accessibility audit of the new screens.

## Next step

Owner: review the new screens at `/login` and `/signup`. Then Phase 2 (design tokens, grouped navigation,
public site, Super Admin shell, school logo upload, Playwright and axe tests). See [09](09-backlog.md).
