/**
 * Navigation by role. This only decides what the menu shows; the API enforces
 * every permission itself, so hiding a link is never the security control.
 */

export type Role =
  | "owner"
  | "principal"
  | "admin"
  | "bursar"
  | "teacher"
  | "form_teacher"
  | "librarian"
  | "warden"
  | "driver"
  | "parent"
  | "student";

export const ROLE_LABELS: Record<Role, string> = {
  owner: "Proprietor",
  principal: "Head teacher",
  admin: "Administrator",
  bursar: "Accountant / bursar",
  teacher: "Teacher",
  form_teacher: "Class teacher",
  librarian: "Librarian",
  warden: "Hostel warden",
  driver: "Driver",
  parent: "Parent / guardian",
  student: "Student",
};

const LEADERS: Role[] = ["owner", "principal", "admin"];
const TEACHING: Role[] = ["teacher", "form_teacher"];
const FINANCE: Role[] = ["owner", "bursar"];

export type NavItem = { href: string; label: string; roles: Role[] };

export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Overview", roles: [] },
  { href: "/students", label: "Students", roles: [...LEADERS, ...TEACHING, "bursar"] },
  { href: "/children", label: "My children", roles: ["parent"] },
  { href: "/admissions", label: "Admissions", roles: LEADERS },
  { href: "/attendance", label: "Attendance", roles: [...LEADERS, ...TEACHING] },
  { href: "/scores", label: "Score entry", roles: [...LEADERS, ...TEACHING] },
  { href: "/results", label: "Results", roles: [...LEADERS, "form_teacher", "parent", "student"] },
  { href: "/fees", label: "Fees", roles: [...FINANCE, "principal", "parent"] },
  { href: "/announcements", label: "Announcements", roles: [] },
  { href: "/academics", label: "Classes & timetable", roles: [...LEADERS, ...TEACHING] },
  { href: "/people", label: "People", roles: LEADERS },
  { href: "/settings", label: "School settings", roles: [...LEADERS, "bursar"] },
];

export function navFor(roles: string[]): NavItem[] {
  return NAV.filter((item) => item.roles.length === 0 || item.roles.some((r) => roles.includes(r)));
}

export const hasAny = (roles: string[], wanted: Role[]) => wanted.some((r) => roles.includes(r));
export const isLeader = (roles: string[]) => hasAny(roles, LEADERS);
export const isFinance = (roles: string[]) => hasAny(roles, [...FINANCE, "principal"]);
export const isTeacher = (roles: string[]) => hasAny(roles, TEACHING);
export const isParentOnly = (roles: string[]) =>
  roles.length > 0 && roles.every((r) => r === "parent" || r === "student");
