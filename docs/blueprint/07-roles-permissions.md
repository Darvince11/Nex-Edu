# 07 · Roles and permissions

Source of truth: [backend/core/rbac.py](../../backend/core/rbac.py). This page mirrors it. If they differ,
the code wins and this page is wrong. Permissions say *what kind* of action; selectors decide *which records*
(own classes, own children, self).

## 1. Platform roles (control plane)

| Role | Can | Cannot |
|---|---|---|
| `super_admin` | Everything in the Super Admin console; create platform staff; approve emergency support grants | Read school data without a support grant |
| `support` | View tenant metadata, registrations, subscriptions; request support grants | Change plans or billing; approve own grant |
| `billing` | Plans, subscriptions, invoices, revenue | Tenant lifecycle; support grants |

What each sees in the Super Admin console (built 24 Oct 2026):

| Console section | Super admin | Support | Billing |
|---|---|---|---|
| Dashboard | ● | ● | ● |
| Registrations, Schools (and school detail) | ● (decides) | ● (reads) | |
| Pricing and billing | ● (changes prices, period) | | ● (reads) |
| Billing history | ● | | ● (records payments) |
| General audit log | ● | ● | |
| My audit log | ● | ● | ● |
| Announcements | ● (writes, sends) | ● (reads) | |
| System settings (problems, security, updates, vulnerabilities) | ● (also starts scans) | ● (triages problems) | |

Platform roles live in a `PlatformStaff` table, are reminded to add an authenticator app (required only when
`PLATFORM_MFA_REQUIRED` is on), and are never assignable through
public registration or school invitations.

## 2. School roles: current matrix

Key: ● granted · ○ granted but scoped by selectors (own classes / own children / self) · blank = denied.

| Permission | Owner | Head | Admin | Bursar | Teacher | Class teacher | Librarian | Warden | Driver | Parent | Student |
|---|---|---|---|---|---|---|---|---|---|---|---|
| school.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| school.branding | ● |  |  |  |  |  |  |  |  |  |  |
| school.legal | ● |  |  |  |  |  |  |  |  |  |  |
| school.modules | ● |  |  |  |  |  |  |  |  |  |  |
| students.view | ● | ● | ● | ● | ○ | ○ | ● | ● |  | ○ | ○ |
| students.view_all | ● | ● | ● | ● |  |  | ● | ● |  |  |  |
| students.view_sensitive | ● | ● | ● |  |  | ○ |  | ● |  | ○ |  |
| students.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| students.add_to_own_class | ● |  |  |  |  | ○ |  |  |  |  |  |
| staff.view | ● | ● | ● | ● |  |  |  |  |  |  |  |
| staff.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| leave.request | ● | ● | ● | ● | ● | ● | ● | ● | ● |  |  |
| academics.view | ● | ● | ● |  | ● | ● |  |  |  |  |  |
| academics.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| academics.timetable_own | ● |  |  |  | ○ | ○ |  |  |  |  |  |
| admissions.view | ● | ● | ● |  |  |  |  |  |  |  |  |
| admissions.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| attendance.view | ● | ● | ● |  | ○ | ○ |  | ● |  | ○ | ○ |
| attendance.record | ● | ● | ● |  | ○ | ○ |  |  |  |  |  |
| attendance.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| assessments.view | ● | ● | ● |  | ○ | ○ |  |  |  | ○ | ○ |
| assessments.record | ● |  | ● |  | ○ | ○ |  |  |  |  |  |
| assessments.manage | ● |  | ● |  |  |  |  |  |  |  |  |
| assessments.configure | ● | ● | ● |  |  |  |  |  |  |  |  |
| assessments.publish | ● | ● | ● |  |  |  |  |  |  |  |  |
| assessments.publish_own_class | ● |  |  |  |  | ○ |  |  |  |  |  |
| assessments.amend | ● |  |  |  |  |  |  |  |  |  |  |
| finance.view | ● | ● |  | ● |  |  |  |  |  | ○ |  |
| finance.manage | ● |  |  | ● |  |  |  |  |  |  |  |
| finance.pay | ● |  |  |  |  |  |  |  |  | ○ |  |
| communication.view | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| communication.send | ● | ● | ● |  | ○ | ○ |  |  |  |  |  |
| communication.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| messages.use | ● | ● | ● | ● | ○ | ○ |  |  |  | ○ |  |
| messages.oversee | ● | ● |  |  |  |  |  |  |  |  |  |
| calendar.view | ● | ● | ● | ● | ● | ● | ● | ● | ● | ○ | ○ |
| calendar.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| members.manage | ● |  |  |  |  |  |  |  |  |  |  |
| members.manage_staff | ● | ● |  |  |  |  |  |  |  |  |  |
| members.view | ● | ● | ● |  |  |  |  |  |  |  |  |
| audit.view | ● | ● | ● |  |  |  |  |  |  |  |  |
| reports.view | ● | ● | ● |  |  |  |  |  |  |  |  |
| reports.own_class | ● |  |  |  |  | ○ |  |  |  |  |  |
| library.view | ● | ● | ● |  | ● | ● | ● |  |  | ○ | ○ |
| library.manage | ● | ● | ● |  |  |  | ● |  |  |  |  |
| clubs.view | ● | ● | ● | ● | ● | ● | ● | ● | ● | ○ | ○ |
| clubs.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| meetings.view | ● | ● | ● |  | ○ | ○ |  |  |  | ○ |  |
| meetings.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| discipline.view | ● |  |  |  |  |  |  |  |  | ○ |  |
| discipline.record | ● | ● | ● |  | ○ | ○ |  | ○ |  |  |  |
| discipline.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| discipline.counsel | ● | ● |  |  |  |  |  |  |  |  |  |
| clinic.view | ● | ● | ● |  |  | ○ |  |  |  | ○ |  |
| clinic.record | ● | ● | ● |  |  |  |  |  |  |  |  |
| transport.view | ● |  |  |  |  |  |  |  |  | ○ | ○ |
| transport.record | ● |  |  |  |  |  |  |  | ○ |  |  |
| transport.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| canteen.view | ● |  |  |  |  |  |  |  |  | ○ | ○ |
| canteen.sell | ● | ● | ● | ● |  |  |  |  |  |  |  |
| canteen.manage | ● | ● | ● | ● |  |  |  |  |  |  |  |
| inventory.request | ● | ● | ● | ● | ● | ● | ● | ● | ● |  |  |
| inventory.manage | ● | ● | ● | ● |  |  |  |  |  |  |  |
| facilities.use | ● | ● | ● | ● | ● | ● | ● | ● | ● |  |  |
| facilities.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| gate.record | ● | ● | ● |  |  |  |  |  |  |  |  |
| gate.family | ● |  |  |  |  |  |  |  |  | ○ |  |
| lms.teach | ● |  |  |  | ○ | ○ |  |  |  |  |  |
| lms.learn | ● |  |  |  |  |  |  |  |  |  | ○ |
| lms.view | ● |  |  |  |  |  |  |  |  | ○ |  |
| lms.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| hostel.view | ● |  |  |  |  |  |  |  |  | ○ |  |
| hostel.record | ● | ● | ● |  |  |  |  | ○ |  |  |  |
| hostel.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| accounting.view | ● | ● |  | ● |  |  |  |  |  |  |  |
| accounting.manage | ● |  |  | ● |  |  |  |  |  |  |  |
| payroll.self | ● | ● | ● | ● | ● | ● | ● | ● | ● |  |  |
| payroll.manage | ● |  |  | ● |  |  |  |  |  |  |  |
| payroll.approve | ● |  |  |  |  |  |  |  |  |  |  |
| procurement.request | ● | ● | ● | ● | ● | ● | ● | ● | ● |  |  |
| procurement.approve | ● | ● |  |  |  |  |  |  |  |  |  |
| procurement.final | ● |  |  |  |  |  |  |  |  |  |  |
| procurement.manage | ● |  |  | ● |  |  |  |  |  |  |  |
| support.view | ● |  | ● |  | ○ | ○ |  |  |  | ○ |  |
| support.manage | ● | ● |  |  |  |  |  |  |  |  |  |
| alumni.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| website.manage | ● | ● | ● |  |  |  |  |  |  |  |  |
| compliance.manage | ● | ● |  |  |  |  |  |  |  |  |  |
| integrations.manage | ● |  |  |  |  |  |  |  |  |  |  |
| assist.draft | ● | ● | ● |  | ● | ● |  |  |  |  |  |

How the leadership roles differ (owner's direction, 24 Oct 2026):

- **Proprietor (owner)** can do everything. Only the proprietor changes the school logo (`school.branding`), adds
  or blocks **head teachers, administrators, bursars and proprietors** (`members.manage`) and amends published scores
  (`assessments.amend`).
- **Head teacher** runs the school day to day: pupils, classes, admissions, registers, grading set-up, computing and
  publishing report cards, and messages. They **do not enter or amend scores**. They **add and block teaching and
  support staff** (teachers, class teachers, librarians, wardens, drivers: `members.manage_staff`, owner's
  decision 24 Oct 2026) but not leadership or finance roles. Nobody can give themselves a role, so the head teacher
  can't add themselves as a teacher to enter scores. They, and the administrator, invite parents and pupils.
- **Class teacher** adds pupils to **their own class only** (`students.add_to_own_class`), and computes and publishes
  that class's report cards (`assessments.publish_own_class`).
- **Every teacher** keeps the timetable of the classes they teach (`academics.timetable_own`), enters scores for
  their subjects and takes registers. **Subject teachers can't add pupils.**
- The "own class" checks are made per request against teaching assignments (`tests/test_teacher_rights.py`).

Added in Phase 5 (25 Oct 2026):

- **Messages:** parents write to their child's teachers, the head teacher and the bursar; teachers write to
  the parents of pupils in classes they teach; leaders and the bursar to any parent. The proprietor and head
  teacher can read every conversation (`messages.oversee`, safeguarding) but only the two people in it write.
- **Calendar:** everyone reads; staff-only events are hidden from parents and pupils; leaders write.
- **Reports:** leaders report on any class; class teachers on their own class (`reports.own_class`).
- **Seeing every pupil** is now a permission (`students.view_all`) held by the roles that always had it, so a
  custom role can give it.
- **Custom roles** (`control_plane/custom_roles.py`): the proprietor makes named roles from a fixed list of
  permissions (`core.rbac.CUSTOM_ROLE_PERMISSIONS`) and gives them to active staff. They add to the person's own
  role and never contain the proprietor's own powers (logo, terms, modules), giving or blocking access, or
  amending published scores. Parents and pupils can't hold one, nobody gives one to themselves, and one stops
  working as soon as the person is blocked (`tests/test_custom_roles.py`).

Added in Phase 6 (25 Oct 2026):

- **School nurse** (`nurse`) is a new built-in role: every pupil's record including medical notes, and the sick
  bay (`clinic.record`). The head teacher can add and block nurses. (Not shown as a column above; it holds only
  `students.view`, `students.view_all`, `students.view_sensitive`, `communication.view`, `clinic.*`,
  `calendar.view`, `clubs.view` and `leave.request`.)
- **Canteen manager** (`canteen`) is a new built-in role: the canteen till (`canteen.sell`) and every pupil's name.
  It handles cash, so only the proprietor gives it (like the bursar).
- **Store keeper** (`store_keeper`) is a new built-in role: the stores (`inventory.manage`). The head teacher can add
  and block store keepers.
- **Gate officer** (`gate`) is a new built-in role: visitors and pick-ups (`gate.record`). The head teacher can add
  and block gate officers.
- Each optional module adds its own permissions (library, clubs, meetings, discipline, clinic); they only work
  while the school has the module switched on (`ModuleEnabled`).

Additional rules already enforced and tested:

- **No privilege escalation:** staff roles need `members.manage` and may not add a permission the granter lacks;
  parent and student roles can be granted by whoever manages pupils, admissions or members
  (`can_grant`, `test_cannot_grant_more_access_than_you_have`, `test_only_the_proprietor_gives_staff_access`).
- **Authenticator app optional** for school accounts and Nex Edu platform staff (owner's decision, 24 Oct 2026).
  The platform console shows a reminder ("Not now" snoozes it for a week). A deployment can make it a gate with
  `MFA_REQUIRED_ROLES` (school roles) and `PLATFORM_MFA_REQUIRED=true`
  (`test_staff_work_without_an_authenticator_app_unless_the_school_requires_one`,
  `test_platform_staff_get_in_without_an_app_unless_it_is_required`).
- **Fail closed:** a view without declared permissions is denied (`test_every_tenant_api_view_declares_permissions`).

## 3. Planned additions

| Change | Phase | Notes |
|---|---|---|
| Module permissions (`<module>.view`, `<module>.manage`, plus operation-specific ones such as `canteen.sell`, `clinic.view_records`) | 4–6 | Defined in the module registry, added to the role table when the module ships |
| New school roles: `hr_officer`, `nurse`, `store_keeper`, `canteen_manager`, `counsellor`, `gate_officer`, `transport_officer` | 6 | Each created with its module; none get students.view_sensitive by default except `nurse` (clinic records only) |
| Existing `librarian`, `warden`, `driver` gain their module permissions | 6 | Today they only have read access to students/comms |
| `accountant` vs `bursar` | 6 | Keep `bursar` for fees; add `accounting.*` to bursar when the accounting module is active, rather than a second role |
| Read-only permission matrix screen | 2 | Generated from the API so it can never drift from the code |
| Authorization matrix test generated from this table | 1 | Every endpoint × role × own/other, including cross-tenant (architecture plan §5.2) |
