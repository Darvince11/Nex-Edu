# 06 · Navigation

## 1. Rules

- One config file, `web/src/lib/nav.ts` (replaces the flat list in `roles.ts`), defines groups → items with
  `href`, `module`, `permission` and `status`.
- An item renders only when **its module is effective for the school** and **the user holds its permission**,
  both read from `GET /me/workspace`. A group with no visible items is hidden.
- `status: "planned"` items are never rendered in production. There are no dead links and no "coming soon" pages
  presented as features.
- The sidebar is collapsible on desktop (icon rail, state remembered per browser) and a drawer on phones.
  The active item uses `bg-brand/10 text-brand-strong`. Breadcrumbs come from the same tree.
- Parents and students get a shorter tree (section 4). The Super Admin console has its own tree (section 5).

Legend: **E** = exists today (route built and backed by tested API) · **P** = planned · route in brackets is today's path.

## 2. School workspace (staff)

| Group | Item | Route | Module | Permission | |
|---|---|---|---|---|---|
| **Dashboard** | Overview | `/dashboard` | dashboard | — | E |
| | Key statistics | `/dashboard` (tiles) | dashboard | per tile | E (partial) |
| | Alerts and tasks | `/dashboard/tasks` | dashboard | — | P |
| | Recent activity | `/dashboard/activity` | audit | audit.view | P |
| | School performance | `/dashboard/performance` | assessments | assessments.view | P |
| **People** | Students | `/students` | students | students.view | E |
| | Parents and guardians | `/people/guardians` | students | students.view | P (guardians exist per student) |
| | Teachers and staff | `/people/staff` | staff | staff.view | P (API exists, no screen) |
| | Admissions | `/admissions` | admissions | admissions.view | E |
| | Alumni | `/alumni` | alumni | alumni.view | P |
| **Academics** | Academic years and terms | `/academics/years` [`/academics`] | academics | academics.view | E |
| | Classes and streams | `/academics/classes` [`/academics`] | academics | academics.view | E |
| | Subjects and departments | `/academics/subjects` [`/academics`] | academics | academics.view | E (subjects) / P (departments) |
| | Curriculum and lesson plans | `/academics/lesson-plans` | lms | lms.view | P |
| | Timetable | `/academics/timetable` [`/academics`] | academics | academics.view | E |
| | Assignments and homework | `/academics/homework` | lms | lms.view | P |
| | Examinations | `/academics/exams` | assessments | assessments.manage | P (components exist) |
| | Gradebook and results | `/academics/gradebook` [`/scores`, `/results`] | assessments | assessments.view | E |
| | Report cards | `/academics/report-cards` [`/results`] | assessments | assessments.view | E |
| | Promotion and graduation | `/academics/promotion` | students | students.manage | P |
| **Attendance** | Student attendance | `/attendance` | attendance | attendance.view | E |
| | Staff attendance | `/attendance/staff` | attendance | attendance.manage | P |
| | Attendance reports | `/attendance/reports` | attendance | attendance.view | P (summary API exists) |
| | Leave and absence requests | `/attendance/requests` | attendance | attendance.view | P |
| **Finance** | Fee structures | `/finance/fees` [`/fees`] | finance_core | finance.view | E |
| | Invoices and billing | `/finance/invoices` [`/fees`] | finance_core | finance.view | E |
| | Payments and receipts | `/finance/payments` [`/fees`] | finance_core | finance.view | E |
| | Outstanding balances | `/finance/balances` | finance_core | finance.view | P (summary exists) |
| | Scholarships and discounts | `/finance/discounts` | finance_core | finance.manage | P (invoice discount exists) |
| | Expenses | `/finance/expenses` | accounting | accounting.view | P |
| | Financial reports | `/finance/reports` | finance_core | finance.view | P |
| **Communication** | Announcements | `/announcements` | communication | communication.view | E |
| | Messages | `/messages` | communication | communication.send | P |
| | Notifications | `/inbox` | communication | communication.view | E |
| | Calendar and events | `/calendar` | communication | communication.view | P |
| | Parent meetings | `/meetings` | meetings | meetings.view | P |
| **Reports** | Academic, attendance, enrolment, financial, staff, custom | `/reports/*` | reports_basic / analytics | per report | P |
| **Modules** | Catalogue, enabled, settings, subscription availability, dependencies, history | `/modules/*` | — | school.manage | P |
| **Settings** | School profile | `/settings` | school | school.manage | E |
| | Academic configuration | `/settings/academic` | academics | academics.manage | P |
| | Grading and assessment | `/settings/grading` | assessments | assessments.manage | P (API exists) |
| | Users and roles | `/people` (rename `/settings/users`) | members | members.manage | E |
| | Permissions | `/settings/permissions` | members | members.manage | P (read-only matrix first) |
| | Notifications | `/settings/notifications` | communication | communication.manage | E (inside `/settings`) |
| | Integrations | `/settings/integrations` | finance_core | school.manage | E (payment settings inside `/settings`) |
| | Documents and templates | `/settings/documents` | school | school.manage | P |
| | Security and audit logs | `/settings/audit` | audit | audit.view | P (API exists) |

## 3. Optional module trees (shown only when effective)

| Module | Items |
|---|---|
| Hostel | Hostels and rooms · Allocations · Roll call · Exeat and leave · Incidents · Hostel fees |
| Transport | Routes and stops · Vehicles · Drivers · Pupil assignments · Trips and tracking · Transport fees |
| Library | Catalogue · Circulation · Members · Overdues and fines · Reports |
| Canteen | Menus · Meal plans · Wallets and top-ups · Point of sale · Reports |
| Clinic | Visits · Medical records · Medication · Immunisations · Referrals |
| Inventory | Items · Stock movements · Stores · Issues to staff · Assets |
| Procurement | Requisitions · Vendors · Purchase orders · Goods received |
| Payroll / HR | Staff contracts · Leave · Payroll runs · Payslips · PAYE and SSNIT returns |
| Accounting | Chart of accounts · Journals · Expenses · Budgets · Bank reconciliation · Statements |
| Facilities | Buildings and rooms · Maintenance requests · Work orders · Bookings |
| LMS | Courses · Lessons · Assignments · Submissions · Quizzes |
| Online exams | Question banks · Exam papers · Sittings · Marking |
| Discipline | Incidents · Sanctions · Counselling sessions · Behaviour reports |
| Clubs and sports | Clubs · Memberships · Fixtures · Achievements |
| Visitors | Visitor log · Pre-registered visits · Pupil pick-up authorisation · Gate passes |

## 4. Parent and student tree

| Item | Route | |
|---|---|---|
| Overview | `/dashboard` | E |
| My children (parent) / My profile (student) | `/children`, `/students/[id]` | E |
| Attendance | `/children` → child | E |
| Results and report cards | `/results` | E |
| Fees and payments (parent) | `/fees` | E |
| Announcements · Inbox | `/announcements`, `/inbox` | E |
| Homework, timetable, meetings | — | P |

## 5. Super Admin console (`admin.nexedu.com.gh`)

| Group | Items | |
|---|---|---|
| Overview | Platform health, signups, active schools, MRR | P |
| Schools | All schools · Registrations queue · Lifecycle (suspend, reactivate, offboard) · Support access grants | P |
| Plans and billing | Plans · Entitlements · Subscriptions · Invoices · Revenue | P |
| Modules | Registry status · Rollout flags · Usage by module | P |
| Support | Tickets (or link to external helpdesk) · Impersonation history | P |
| Operations | Cells and capacity · Tenant migrations · Incidents · Background jobs | P (data exists in Django admin) |
| Security | Platform audit log · Platform staff · Security events | P |
| Settings | Global settings · Feature flags | P |

## 6. Public site (`nexedu.com.gh`)

Home · Features · Modules · Pricing · School types · FAQ · Contact and support · Register your school · Sign in ·
Terms of service · Privacy notice (Act 843) · Data processing agreement. All **P** (today `/` redirects to `/schools`).
