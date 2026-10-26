/**
 * School roles and role helpers. The menu itself lives in nav.ts. The API
 * enforces every permission, so these only shape what the UI shows.
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
  | "nurse"
  | "canteen"
  | "store_keeper"
  | "gate"
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
  nurse: "School nurse",
  canteen: "Canteen manager",
  store_keeper: "Store keeper",
  gate: "Gate officer",
  parent: "Parent / guardian",
  student: "Student",
};

/** Nex Edu's own staff (the platform console), not school roles. */
export const PLATFORM_ROLE_LABELS: Record<string, string> = {
  super_admin: "Super admin",
  support: "Support",
  billing: "Billing",
};

const LEADERS: Role[] = ["owner", "principal", "admin"];
const TEACHING: Role[] = ["teacher", "form_teacher"];
const FINANCE: Role[] = ["owner", "bursar"];

export const hasAny = (roles: string[], wanted: Role[]) => wanted.some((r) => roles.includes(r));
export const isLeader = (roles: string[]) => hasAny(roles, LEADERS);
export const isFinance = (roles: string[]) => hasAny(roles, [...FINANCE, "principal"]);
export const isTeacher = (roles: string[]) => hasAny(roles, TEACHING);
export const isParentOnly = (roles: string[]) =>
  roles.length > 0 && roles.every((r) => r === "parent" || r === "student");
