/**
 * School workspace navigation, grouped as in docs/blueprint/06-navigation.md.
 * Items of an optional module (admissions, fees) are listed only while the
 * school has that module switched on.
 * This only decides what the menu shows; the API enforces every permission
 * itself, so hiding a link is never the security control. Only pages that
 * exist are listed (nav.test.ts fails on a dead link).
 */
import { PERM, type Permission } from "./permissions";
import type { Role } from "./roles";

export type NavIcon =
  | "home"
  | "pupils"
  | "children"
  | "admissions"
  | "people"
  | "classes"
  | "scores"
  | "results"
  | "attendance"
  | "fees"
  | "announcements"
  | "inbox"
  | "settings"
  | "modules"
  | "staff"
  | "leave"
  | "audit"
  | "messages"
  | "calendar"
  | "reports"
  | "library"
  | "clubs"
  | "meetings"
  | "behaviour"
  | "clinic"
  | "transport"
  | "canteen"
  | "stores"
  | "facilities"
  | "gate"
  | "homework"
  | "boarding"
  | "accounting"
  | "payroll"
  | "procurement"
  | "tests"
  | "support"
  | "alumni"
  | "website"
  | "compliance"
  | "integrations";

export type NavItem = {
  href: string;
  label: string;
  icon: NavIcon;
  roles: Role[];
  /** Also needs one of these, where a role alone doesn't settle it (the head teacher enters no scores). */
  perms?: Permission[];
  /** Only while this optional module is switched on for the school. */
  module?: string;
  /**
   * Also shown, whatever the person's role, when one of the school's custom roles
   * gives them one of these. Defaults to `perms`. Only staff hold custom roles.
   */
  custom?: Permission[];
};
export type NavGroup = { id: string; label: string; items: NavItem[] };

const EVERYONE: Role[] = [];
const LEADERS: Role[] = ["owner", "principal", "admin"];
const TEACHING: Role[] = ["teacher", "form_teacher"];
const FINANCE: Role[] = ["owner", "bursar"];
const STAFF: Role[] = [
  ...LEADERS,
  "bursar",
  ...TEACHING,
  "librarian",
  "warden",
  "driver",
  "nurse",
  "canteen",
  "store_keeper",
  "gate",
];

export const NAV_GROUPS: NavGroup[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    items: [{ href: "/dashboard", label: "Overview", icon: "home", roles: EVERYONE }],
  },
  {
    id: "people",
    label: "People",
    items: [
      {
        href: "/students",
        label: "Students",
        icon: "pupils",
        roles: [...LEADERS, ...TEACHING, "bursar"],
        custom: [PERM.STUDENTS_VIEW, PERM.STUDENTS_VIEW_ALL, PERM.STUDENTS_MANAGE],
      },
      { href: "/children", label: "My children", icon: "children", roles: ["parent"] },
      {
        href: "/guardians",
        label: "Guardians",
        icon: "children",
        roles: [...LEADERS, ...TEACHING, "bursar"],
        perms: [PERM.STUDENTS_VIEW],
      },
      {
        href: "/admissions",
        label: "Admissions",
        icon: "admissions",
        roles: LEADERS,
        module: "admissions",
        custom: [PERM.ADMISSIONS_VIEW, PERM.ADMISSIONS_MANAGE],
      },
      {
        href: "/promotion",
        label: "End of year",
        icon: "results",
        roles: LEADERS,
        perms: [PERM.STUDENTS_MANAGE],
      },
      {
        href: "/staff",
        label: "Staff",
        icon: "staff",
        roles: [...LEADERS, "bursar"],
        perms: [PERM.STAFF_VIEW],
      },
      {
        href: "/staff-attendance",
        label: "Staff attendance",
        icon: "attendance",
        roles: LEADERS,
        perms: [PERM.STAFF_MANAGE],
      },
      {
        href: "/alumni",
        label: "Alumni",
        icon: "alumni",
        roles: LEADERS,
        perms: [PERM.ALUMNI_MANAGE],
        module: "alumni",
      },
      { href: "/leave", label: "Leave", icon: "leave", roles: STAFF, perms: [PERM.LEAVE_REQUEST] },
      {
        href: "/people",
        label: "Staff and access",
        icon: "people",
        roles: LEADERS,
        perms: [PERM.MEMBERS_VIEW, PERM.MEMBERS_MANAGE],
      },
    ],
  },
  {
    id: "academics",
    label: "Academics",
    items: [
      {
        href: "/academics",
        label: "Classes and timetable",
        icon: "classes",
        roles: [...LEADERS, ...TEACHING],
        custom: [PERM.ACADEMICS_MANAGE],
      },
      {
        href: "/scores",
        label: "Score entry",
        icon: "scores",
        roles: [...LEADERS, ...TEACHING],
        perms: [PERM.ASSESSMENTS_RECORD, PERM.ASSESSMENTS_MANAGE],
      },
      {
        href: "/results",
        label: "Results and report cards",
        icon: "results",
        roles: [...LEADERS, "form_teacher", "parent", "student"],
        custom: [PERM.ASSESSMENTS_PUBLISH],
      },
      {
        href: "/reports",
        label: "Reports",
        icon: "reports",
        roles: [...LEADERS, "form_teacher"],
        perms: [PERM.REPORTS_VIEW, PERM.REPORTS_OWN_CLASS],
      },
      {
        href: "/homework",
        label: "Homework",
        icon: "homework",
        roles: [...LEADERS, ...TEACHING, "parent", "student"],
        perms: [PERM.LMS_TEACH, PERM.LMS_LEARN, PERM.LMS_VIEW, PERM.LMS_MANAGE],
        module: "lms",
      },
      {
        href: "/tests",
        label: "Online tests",
        icon: "tests",
        roles: [...LEADERS, ...TEACHING, "parent", "student"],
        perms: [PERM.LMS_TEACH, PERM.LMS_LEARN, PERM.LMS_VIEW, PERM.LMS_MANAGE],
        module: "online_exams",
      },
      {
        href: "/support",
        label: "Learning support",
        icon: "support",
        roles: [...LEADERS, ...TEACHING, "parent"],
        perms: [PERM.SUPPORT_VIEW, PERM.SUPPORT_MANAGE],
        module: "special_ed",
      },
    ],
  },
  {
    id: "attendance",
    label: "Attendance",
    items: [
      {
        href: "/attendance",
        label: "Registers",
        icon: "attendance",
        roles: [...LEADERS, ...TEACHING],
        custom: [PERM.ATTENDANCE_MANAGE],
      },
    ],
  },
  {
    id: "finance",
    label: "Finance",
    items: [
      {
        href: "/fees",
        label: "Fees and payments",
        icon: "fees",
        roles: [...FINANCE, "principal", "parent"],
        module: "fees",
        custom: [PERM.FINANCE_VIEW, PERM.FINANCE_MANAGE],
      },
      {
        href: "/finance-reports",
        label: "Finance reports",
        icon: "results",
        roles: [...FINANCE, "principal"],
        perms: [PERM.FINANCE_VIEW],
        module: "fees",
      },
      {
        href: "/accounting",
        label: "Accounting",
        icon: "accounting",
        roles: [...FINANCE, "principal"],
        perms: [PERM.ACCOUNTING_VIEW, PERM.ACCOUNTING_MANAGE],
        module: "accounting",
      },
      {
        href: "/payroll",
        label: "Payroll",
        icon: "payroll",
        roles: STAFF,
        perms: [PERM.PAYROLL_SELF, PERM.PAYROLL_MANAGE, PERM.PAYROLL_APPROVE],
        module: "payroll",
      },
      {
        href: "/procurement",
        label: "Procurement",
        icon: "procurement",
        roles: STAFF,
        perms: [PERM.PROCUREMENT_REQUEST, PERM.PROCUREMENT_APPROVE, PERM.PROCUREMENT_MANAGE],
        module: "procurement",
      },
    ],
  },
  {
    id: "activities",
    label: "School life",
    items: [
      {
        href: "/library",
        label: "Library",
        icon: "library",
        roles: [...LEADERS, ...TEACHING, "librarian", "parent", "student"],
        perms: [PERM.LIBRARY_VIEW, PERM.LIBRARY_MANAGE],
        module: "library",
      },
      {
        href: "/clubs",
        label: "Clubs and sports",
        icon: "clubs",
        roles: EVERYONE,
        perms: [PERM.CLUBS_VIEW],
        module: "clubs",
        custom: [PERM.CLUBS_MANAGE],
      },
      {
        href: "/meetings",
        label: "Parent meetings",
        icon: "meetings",
        roles: [...LEADERS, ...TEACHING, "parent"],
        perms: [PERM.MEETINGS_VIEW, PERM.MEETINGS_MANAGE],
        module: "meetings",
      },
      {
        href: "/behaviour",
        label: "Behaviour",
        icon: "behaviour",
        roles: [...LEADERS, ...TEACHING, "warden", "parent"],
        perms: [PERM.DISCIPLINE_VIEW, PERM.DISCIPLINE_RECORD, PERM.DISCIPLINE_MANAGE],
        module: "discipline",
        custom: [PERM.DISCIPLINE_RECORD, PERM.DISCIPLINE_MANAGE, PERM.DISCIPLINE_COUNSEL],
      },
      {
        href: "/sick-bay",
        label: "Sick bay",
        icon: "clinic",
        roles: [...LEADERS, "form_teacher", "nurse", "parent"],
        perms: [PERM.CLINIC_VIEW, PERM.CLINIC_RECORD],
        module: "clinic",
        custom: [PERM.CLINIC_RECORD],
      },
      {
        href: "/transport",
        label: "Transport",
        icon: "transport",
        roles: [...LEADERS, "driver", "parent", "student"],
        perms: [PERM.TRANSPORT_VIEW, PERM.TRANSPORT_RECORD, PERM.TRANSPORT_MANAGE],
        module: "transport",
        custom: [PERM.TRANSPORT_MANAGE],
      },
      {
        href: "/canteen",
        label: "Canteen",
        icon: "canteen",
        roles: [...LEADERS, "bursar", "canteen", "parent", "student"],
        perms: [PERM.CANTEEN_VIEW, PERM.CANTEEN_SELL, PERM.CANTEEN_MANAGE],
        module: "canteen",
        custom: [PERM.CANTEEN_SELL, PERM.CANTEEN_MANAGE],
      },
      {
        href: "/stores",
        label: "Stores",
        icon: "stores",
        roles: STAFF,
        perms: [PERM.INVENTORY_REQUEST, PERM.INVENTORY_MANAGE],
        module: "inventory",
      },
      {
        href: "/facilities",
        label: "Facilities",
        icon: "facilities",
        roles: STAFF,
        perms: [PERM.FACILITIES_USE, PERM.FACILITIES_MANAGE],
        module: "facilities",
      },
      {
        href: "/gate",
        label: "Gate and pick-up",
        icon: "gate",
        roles: [...LEADERS, "gate", "parent"],
        perms: [PERM.GATE_RECORD, PERM.GATE_FAMILY],
        module: "visitors",
      },
      {
        href: "/boarding",
        label: "Boarding",
        icon: "boarding",
        roles: [...LEADERS, "warden", "parent"],
        perms: [PERM.HOSTEL_VIEW, PERM.HOSTEL_RECORD, PERM.HOSTEL_MANAGE],
        module: "hostel",
      },
    ],
  },
  {
    id: "communication",
    label: "Communication",
    items: [
      { href: "/announcements", label: "Announcements", icon: "announcements", roles: EVERYONE },
      {
        href: "/messages",
        label: "Messages",
        icon: "messages",
        roles: EVERYONE,
        perms: [PERM.MESSAGES_USE, PERM.MESSAGES_OVERSEE],
      },
      { href: "/calendar", label: "Calendar", icon: "calendar", roles: EVERYONE },
      {
        href: "/website",
        label: "School website",
        icon: "website",
        roles: LEADERS,
        perms: [PERM.WEBSITE_MANAGE],
        module: "website",
      },
      { href: "/inbox", label: "Inbox", icon: "inbox", roles: EVERYONE },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    items: [
      {
        href: "/settings",
        label: "School settings",
        icon: "settings",
        roles: [...LEADERS, "bursar"],
        custom: [PERM.SCHOOL_MANAGE],
      },
      {
        href: "/settings/grading",
        label: "Grading",
        icon: "results",
        roles: LEADERS,
        perms: [PERM.ASSESSMENTS_VIEW],
        custom: [PERM.ASSESSMENTS_CONFIGURE],
      },
      {
        href: "/settings/audit",
        label: "Audit log",
        icon: "audit",
        roles: LEADERS,
        perms: [PERM.AUDIT_VIEW],
      },
      {
        href: "/compliance",
        label: "Compliance",
        icon: "compliance",
        roles: ["owner", "principal"],
        perms: [PERM.COMPLIANCE_MANAGE],
        module: "compliance",
      },
      {
        href: "/settings/modules",
        label: "Modules",
        icon: "modules",
        roles: LEADERS,
        perms: [PERM.SCHOOL_MANAGE],
      },
      {
        href: "/integrations",
        label: "Integrations",
        icon: "integrations",
        roles: ["owner"],
        perms: [PERM.INTEGRATIONS_MANAGE],
        module: "developer_api",
        custom: [],
      },
      {
        href: "/subscription",
        label: "Subscription and billing",
        icon: "fees",
        roles: ["owner"],
        custom: [],
      },
      {
        href: "/settings/roles",
        label: "Custom roles",
        icon: "people",
        roles: ["owner"],
        perms: [PERM.MEMBERS_MANAGE],
        custom: [],
      },
    ],
  },
];

const byRole = (item: NavItem, roles: string[], permissions?: string[]) =>
  (item.roles.length === 0 || item.roles.some((role) => roles.includes(role))) &&
  (!item.perms || !permissions || item.perms.some((p) => permissions.includes(p)));

const byCustomRole = (item: NavItem, custom: string[]) =>
  (item.custom ?? item.perms ?? []).some((p) => custom.includes(p));

const allowed = (
  item: NavItem,
  roles: string[],
  permissions?: string[],
  modules?: string[],
  custom: string[] = [],
) =>
  (byRole(item, roles, permissions) || byCustomRole(item, custom)) &&
  (!item.module || !modules || modules.includes(item.module));

/**
 * The groups and items this person may see; empty groups are dropped. Pass the
 * school's permissions from /me; without them only roles are checked. `custom` is
 * what the school's custom roles add (/me custom_permissions).
 */
export function navFor(
  roles: string[],
  permissions?: string[],
  modules?: string[],
  custom: string[] = [],
): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => allowed(item, roles, permissions, modules, custom)),
  })).filter((group) => group.items.length > 0);
}

const matches = (item: NavItem, pathname: string) =>
  pathname === item.href || pathname.startsWith(`${item.href}/`);

/**
 * Group and item for the current page (for highlighting and breadcrumbs). The
 * longest matching link wins, so /settings/modules is "Modules", not "School settings".
 */
export function locate(groups: NavGroup[], pathname: string): { group: NavGroup; item: NavItem } | null {
  let best: { group: NavGroup; item: NavItem } | null = null;
  for (const group of groups) {
    for (const item of group.items) {
      if (matches(item, pathname) && (!best || item.href.length > best.item.href.length))
        best = { group, item };
    }
  }
  return best;
}
