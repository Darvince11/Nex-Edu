# 09 · Phased implementation backlog

Phase numbers follow the brief. They replace the phase labels in the README status table: the README's
"0. Foundation" and "1. Core school operations" are largely what the brief calls Phases 1 and 5, built on the
previous identity stack.

Each phase ends with the checklist in the brief (§10): compare against the feature register, run all tests,
verify isolation and permissions, check design consistency, verify the phase's sign-in and sign-up flows, record actual
results, update the register.

## Phase 1 · Identity and security foundation (D1: built in-house)

Status 23 Oct 2026: done except 1.7 (Sentry).

| # | Task | Status |
|---|---|---|
| 1.1 | Owner sign-up with consent record, email verification by code, honeypot, rate limits, branded emails | Done, tested |
| 1.2 | Sign-in, MFA step, forgot/set password and authenticator set-up (with recovery codes) screens in the new design | Done; API tested, screens reviewed manually only |
| 1.3 | Audit of sign-in events in the platform log | Done, tested |
| 1.4 | `PlatformStaff`, `IsPlatformStaff`, `add_platform_staff`, platform audit chain + append-only trigger | Done, tested |
| 1.5 | Generated authorization matrix (endpoint × method × role, plus cross-school) | Done, tested, mutation-checked |
| 1.6 | Tenant cache keys by UUID; pin of school-less endpoints | Done, tested |
| 1.7 | Error tracking (Sentry) and tracing | Not started: needs a Sentry project |
| 1.8 | Playwright end-to-end tests of sign-in and sign-up | Done in Phase 2 (2.6) |

## Phase 2 · Design system and application shell

Status 23 Oct 2026: done, apart from pricing figures (waiting for D3).

| # | Task | Status |
|---|---|---|
| 2.1 | Tokens, `Forbidden` state, icons | **Done.** `brand-50`, `link`/`link-hover`, `radius-control`/`radius-card`, `shadow-card`; dark-mode muted text for WCAG AA; `Forbidden` shown for any 403, set-up prompt for missing MFA; inline icons. Chart palette waits for the first charts |
| 2.2 | Grouped, collapsible sidebar and breadcrumbs | **Done, tested.** Module awareness waits for Phase 4 (`/me/workspace`) |
| 2.3 | Public site: home, features (with school types and planned modules), pricing, FAQ, contact | **Done, tested.** Pricing shows what's included and asks for contact until D3 sets prices |
| 2.4 | Super Admin console at `/platform` | **Done, tested.** Approval now sets the school up in a background job |
| 2.5 | School logo upload and display (top bar, admission page, PDFs) | **Done, tested.** Uploads decoded, size-checked, resized, re-encoded (EXIF/GPS stripped); SVG refused |
| 2.6 | Playwright + axe browser tests in CI | **Done.** Auth, MFA set-up, console, navigation, logo, public site |

Also in this phase (owner requests): authenticator-app MFA with recovery codes shown at set-up; one-step TOTP clock tolerance.

## Phase 3 · Registration and onboarding

Done: `SchoolRegistration`, one open request per owner, web-address checks, duplicate flag, review in the Super
Admin console and by command, and **school set-up in a background job** (`control_plane.provision_registration`,
safe to run twice; the console polls until done).

Done 24 Oct 2026:
- **Set-up checklist** for new schools (`apps/school/setup.py`, dashboard card): school profile, logo, terms
  accepted for the school (proprietor), academic year and term, this term's fees, **add staff**, class teachers,
  pupils, **invite parents**. Steps tick themselves off from the school's data; the console shows each school's
  progress and flags schools still unfinished after a week. Choosing modules joins the list with Phase 4.
- **Clean-up of failed set-ups**: the half-made database, its login and credentials are removed so the web
  address can be set up again; a "Try set-up again" action for super admins; set-ups stuck for 30 minutes are
  stopped and cleaned up by the 5-minute health job.
- **Faster set-up for local and test databases**: new schools are copied from a migrated template (about 0.6 s
  instead of several seconds).

Remaining: the same template for **PostgreSQL** (production). It needs `CREATE DATABASE … TEMPLATE` plus
handing every object to the school's own login, and must be proven on the staging database before use.

## Phase 4 · Module registry and dynamic navigation

**Done 25 Oct 2026.** `core/modules.py` is the catalogue: six core modules (always on), three optional modules
that existed then (online admissions, fees and payments, SMS to parents) and the Phase 6 modules (listed,
not yet switchable, and off by default once they ship). `control_plane/modules.py` holds the rules:
- An optional module priced GH₵0 is **included in every price band** (all three today, the owner's choice A);
  a price makes it a **paid add-on** that a super admin grants per school. Prices are set in the console.
- The proprietor switches modules on the school's Modules page; head teachers and administrators see it.
- Switching on needs dependencies on; switching off is refused while a dependent is on, and asks for
  confirmation when records are still open (unpaid invoices, waiting applications, queued SMS). Nothing is
  ever deleted.
- `ModuleEnabled` (a default permission) refuses every school request to a switched-off module; the public
  admission form closes; SMS stops going out; the menu, dashboard figures, quick links and set-up checklist
  follow the switches. History is kept per school and in the platform audit log.

Tested (test_modules.py): not entitled, entitled but off, on but no permission, dependency blocking both
ways, switching off with open records, and every school view belonging to a module or the core.

## Phase 5 · Core school management (complete the gaps) · built 25 Oct 2026

Already implemented before Phase 5: students, guardians, import, admissions, attendance, academics, timetable,
scores, grading, report cards, fees, payments, receipts, announcements, inbox, SMS, members, audit.

Built and tested in Phase 5:

- **Staff:** staff list and profiles (bank details only with `staff.manage`), departments, the staff register,
  and leave requests with approval (`test_staff.py`, `staff.e2e.ts`).
- **Records screens:** guardian directory with invite-to-sign-in, grading settings, the school audit log
  (`test_guardian_directory.py`, `records.e2e.ts`).
- **End of year:** promotion and graduation with per-pupil repeat or leave, run once per year unless confirmed
  (`test_promotion.py`).
- **Money:** outstanding balances (with spreadsheet), collections by day, method and class, and scholarships
  applied when invoices are made (`test_finance_reports.py`, `year-end.e2e.ts`).
- **Messages and calendar:** parent–teacher conversations about a pupil, and a school calendar with term dates
  and Ghana's public holidays worked out (Act 1142; Eid dates added by the school) (`test_messages_calendar.py`,
  `messages.e2e.ts`).
- **Reports:** class lists, attendance and results on screen, as CSV and as PDF; exports audited
  (`test_reports.py`, `reports.e2e.ts`).
- **Custom roles:** see `07-roles-permissions.md` (`test_custom_roles.py`, `custom-roles.e2e.ts`).

Not done in Phase 5: parents asking for a pupil's absence to be excused; dashboard sub-pages (CORE-02);
document templates (CORE-45).

## Phase 6 · Optional modules

One module at a time, each behind its registry entry, in this order (smallest dependency footprint and most
requested by basic schools first): library → clubs → meetings → discipline → clinic → transport → canteen →
inventory → facilities → visitors → lms → hostel → accounting → payroll → procurement → online exams →
special education → website → alumni → compliance. Each flips to `available=True` only after its tests pass.

**Built 26 Oct 2026.** All twenty are available and **off until the proprietor switches them on**
(`default_on=False`). Each has its own app, permissions (see `07-roles-permissions.md`), API tests
(`tests/test_<module>.py`), a page and a browser test (`e2e/<page>.e2e.ts`) with accessibility checks, and its
row in the feature register (OPT-01 to OPT-20, all Tested).

- **Library, clubs and sports, parent meetings, behaviour, sick bay, transport, canteen** (wallets and meal
  plans), **stores**, **facilities** (rooms, bookings, repairs), **gate and pick-up** (visitors, authorised
  collectors).
- **Homework and materials** (LMS), **online tests** (needs LMS), **boarding** (houses, roll call, exeats),
  **learning support** (confidential plans; teachers see only the adjustments; extra time carried into online
  tests).
- **Accounting** (needs Fees): spending, other income, budgets, trial balance, income and expenditure, cash book.
  **Payroll** (needs Accounting): PAYE bands (Act 1178) and SSNIT rates are settings that the school must confirm
  before the first run; the owner approves; payslips and bank schedule. **Procurement** (needs Stores and
  Accounting): two-step approval above a limit, orders, goods received into stores, suppliers paid in the books.
- **Alumni and fundraising:** contact only those who agreed (Act 843), gifts and pledges, money received goes
  into the books when Accounting is on.
- **School website:** public pages on the school's address (`/site`), plain text only, nothing public until
  published, no pupil or staff data.
- **Compliance:** starter checklist (NaSIA, GNFS, NTC, DPC, food vendors, child protection), renewals,
  evidence files, daily reminder job (`compliance.remind_all`).

New built-in roles: nurse, store keeper, gate (head teacher can grant) and canteen (proprietor only).

Before launch: confirm the payroll rates with GRA and SSNIT; update the DPIA for learning support and sick bay
(special-category data); the website on the school's own subdomain needs the production DNS and TLS set-up.

## Phase 7 · SaaS administration and subscriptions

Super Admin dashboard, tenant lifecycle (suspend, reactivate, offboard with export and crypto-shred), plans,
entitlements, overrides, platform billing via Paystack subscriptions (GHS), usage limits (students, SMS,
storage), support access grants, platform audit, migrations/cells/jobs views.

**Built 26 Oct 2026**, with the owner's decisions of that day: band prices are **per month**; an invoice unpaid
**30 days after its due date suspends the school** until it is paid; a closed school's data is kept **90 days**;
schools **buy SMS bundles** beyond a monthly allowance.

- **Invoices** (`control_plane/subscriptions.py`): made on the 1st by a daily job for every active school (band
  from its pupils, plus paid add-on modules), due after a set number of days (console setting, 14 to start).
  Reminders at 7 and 14 days overdue, suspension at 30, reactivation as soon as it is paid. The proprietor pays
  by mobile money or card through Paystack into Nex Edu's own account (references `NXS-…`, routed by the shared
  webhook and re-verified with Paystack); billing staff record bank or cash payments and cancel with a reason.
- **SMS:** a monthly allowance set in the console (2,000 to start, as before) plus bundles that Nex Edu prices in
  the console and schools buy; bought SMS don't expire and are used only after the allowance.
- **Lifecycle** (`control_plane/lifecycle.py`): suspend and reactivate with a reason; close with a full export for
  the proprietor (Nex Edu staff can't download it), then after 90 days the data key is destroyed, the database
  dropped and the files deleted. People at a suspended school are told why on sign-in; the proprietor can still
  pay (`/account/billing`).
- **Support access** (`control_plane/support_access.py`): the proprietor allows it for up to 7 days; support sees
  the set-up only, never pupils' records; a banner shows in the school; every look is recorded and shown to the
  proprietor.
- **Jobs and databases** page: scheduled jobs with last run and failures (recorded by Celery signals), cells,
  school database updates.

Tested in `test_subscriptions.py`, `test_communication.py` and `e2e/subscription.e2e.ts`.

Not done: a storage limit per band (needs the owner's limits); a helpdesk or ticket system; Paystack's own
recurring-subscription product (not needed: schools pay each monthly invoice by mobile money, which Paystack
can't charge automatically).

## Phase 8 · Integrations and intelligence

Push notifications, calendar sync, video links, accounting exports, webhooks and API keys for the developer
API module, analytics warehouse (nightly anonymised export → Athena), AI assistance (only with a DPIA update).

**Built 26 Oct 2026**, with the owner's decisions of that day: accounting export as **one standard CSV** (no
vendor sync); video as **any pasted link** (no provider integration); AI for **drafting only**; multi-campus
**stays deferred**.

- **Push** (`control_plane/push.py`): browser push (Web Push with VAPID, no outside provider), turned on per
  device from the profile; every in-app notification is pushed as a short title and line.
- **Calendar link** (`control_plane/calendar_feed.py`): a private iCalendar link per person for Google, Outlook
  and Apple calendars; term dates, holidays, events, booked parent meetings.
- **Video links** on homework, timetable lessons and parent-meeting days, shown as "Join on Zoom".
- **Accounting export**: a CSV journal (debit, credit and a signed amount) and the chart of accounts.
- **Developer API** (module, off by default; `control_plane/developer.py`): read-only API keys per school with
  scopes; signed webhooks for payments, admissions and published results, retried, with private addresses
  refused.
- **Analytics export** (`control_plane/analytics.py`): one anonymised line per school per night for Athena,
  small groups suppressed, schools identified by a keyed hash.
- **AI drafting help** (module, off by default; `apps/assist`): report-card comments and announcements drafted
  by Claude for staff to edit; pupils' names never sent; daily cap per school.

Tested in `test_integrations.py` and `e2e/integrations.e2e.ts`.

Before launch: generate the production VAPID keys; set `ANTHROPIC_API_KEY` and update the DPIA for AI drafting;
create the analytics bucket, Athena table and crawler. Not built: native mobile push (no app yet), insights
and predictions (owner chose drafting only), multi-campus (deferred), Google or Microsoft sign-in (AUTH-12),
new-device sign-in alerts (AUTH-14).

## Phase 9 · Production readiness

Full test run, sign-in, sign-up and registration flows on staging, isolation and permission matrix, module and subscription enforcement,
payment reconciliation, import/export, backup and single-school restore drill, load tests (k6: result-release
day, fee deadline), accessibility audit, deployment and rollback rehearsal, external penetration test. Output:
a release-readiness report built from the actual results.

