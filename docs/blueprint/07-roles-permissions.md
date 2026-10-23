# 07 · Roles and permissions

Source of truth: [backend/core/rbac.py](../../backend/core/rbac.py). This page mirrors it. If they differ,
the code wins and this page is wrong. Permissions say *what kind* of action; selectors decide *which records*
(own classes, own children, self).

## 1. Platform roles (control plane, Phase 1 / 7, not built)

| Role | Can | Cannot |
|---|---|---|
| `super_admin` | Everything in the Super Admin console; create platform staff; approve emergency support grants | Read school data without a support grant |
| `support` | View tenant metadata, registrations, subscriptions; request support grants | Change plans or billing; approve own grant |
| `billing` | Plans, subscriptions, invoices, revenue | Tenant lifecycle; support grants |

Platform roles live in a `PlatformStaff` table, need MFA on every session, and are never assignable through
public registration or school invitations.

## 2. School roles: current matrix

Key: ● granted · ○ granted but scoped by selectors (own classes / own children / self) · blank = denied.

| Permission | Owner | Head | Admin | Bursar | Teacher | Class teacher | Librarian | Warden | Driver | Parent | Student |
|---|---|---|---|---|---|---|---|---|---|---|---|
| school.manage | ● | ● | ● | | | | | | | | |
| members.manage | ● | ● | ● | | | | | | | | |
| audit.view | ● | ● | ● | | | | | | | | |
| students.view | ● | ● | ● | ● | ○ | ○ | ● | ● | | ○ | ○ |
| students.view_sensitive | ● | ● | ● | | | ○ | | ● | | ○ | |
| students.manage | ● | ● | ● | | | | | | | | |
| staff.view | ● | ● | ● | ● | | | | | | | |
| staff.manage | ● | ● | ● | | | | | | | | |
| academics.view | ● | ● | ● | | ● | ● | | | | | |
| academics.manage | ● | ● | ● | | | | | | | | |
| admissions.view / .manage | ● | ● | ● | | | | | | | | |
| attendance.view | ● | ● | ● | | ○ | ○ | | ● | | ○ | ○ |
| attendance.record | ● | ● | ● | | ○ | ○ | | | | | |
| attendance.manage | ● | ● | ● | | | | | | | | |
| assessments.view | ● | ● | ● | | ○ | ○ | | | | ○ (published) | ○ (published) |
| assessments.record | ● | ● | ● | | ○ | ○ | | | | | |
| assessments.manage | ● | ● | ● | | | | | | | | |
| assessments.publish | ● | ● | ● | | | | | | | | |
| assessments.amend | ● | ● | | | | | | | | | |
| finance.view | ● | ● | | ● | | | | | | ○ | |
| finance.manage | ● | | | ● | | | | | | | |
| finance.pay | ● | | | | | | | | | ○ | |
| communication.view | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| communication.send | ● | ● | ● | | ○ | ○ | | | | | |
| communication.manage | ● | ● | ● | | | | | | | | |

Additional rules already enforced and tested:

- **No privilege escalation:** a user can grant a role only if it adds no permission they lack
  (`can_grant`, `test_cannot_grant_more_access_than_you_have`).
- **MFA required** for every role except parent and student (`MFA_REQUIRED_ROLES`, `test_staff_without_mfa_are_blocked`).
- **Fail closed:** a view without declared permissions is denied (`test_every_tenant_api_view_declares_permissions`).

## 3. Planned additions

| Change | Phase | Notes |
|---|---|---|
| Module permissions (`<module>.view`, `<module>.manage`, plus operation-specific ones such as `canteen.sell`, `clinic.view_records`) | 4–6 | Defined in the module registry, added to the role table when the module ships |
| New school roles: `hr_officer`, `nurse`, `store_keeper`, `canteen_manager`, `counsellor`, `gate_officer`, `transport_officer` | 6 | Each created with its module; none get students.view_sensitive by default except `nurse` (clinic records only) |
| Existing `librarian`, `warden`, `driver` gain their module permissions | 6 | Today they only have read access to students/comms |
| `accountant` vs `bursar` | 6 | Keep `bursar` for fees; add `accounting.*` to bursar when the accounting module is active, rather than a second role |
| Custom roles (school-defined bundles of permissions) | 5 | Stored per school; still bounded by `can_grant`; built-in roles stay read-only |
| Read-only permission matrix screen | 2 | Generated from the API so it can never drift from the code |
| Authorization matrix test generated from this table | 1 | Every endpoint × role × own/other, including cross-tenant (architecture plan §5.2) |
