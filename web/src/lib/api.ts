/**
 * Browser-side API client. Requests go to this origin and Next.js proxies them
 * to Django, so the session cookie and CSRF token are first-party.
 */

const SCHOOL_COOKIE = "nexedu_school";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string | undefined,
    public body: unknown,
  ) {
    super(describe(body) ?? `Request failed (${status})`);
  }
}

/** A readable message from a DRF error body. */
function describe(body: unknown): string | undefined {
  if (!body || typeof body !== "object") return undefined;
  const b = body as Record<string, unknown>;
  if (typeof b.detail === "string") return b.detail;
  if (Array.isArray(b.detail)) return b.detail.join(" ");
  const first = Object.entries(b).find(([k]) => k !== "code");
  if (!first) return undefined;
  const [field, value] = first;
  const text = Array.isArray(value) ? value.join(" ") : typeof value === "string" ? value : "";
  return field === "non_field_errors" ? text : `${field.replace(/_/g, " ")}: ${text}`;
}

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`))
    ?.split("=")[1];
}

export function getSelectedSchool(): string | undefined {
  const value = readCookie(SCHOOL_COOKIE);
  return value ? decodeURIComponent(value) : undefined;
}

export function selectSchool(slug: string): void {
  // Not a secret: it only says which school the UI is showing. The server
  // re-checks membership on every request.
  // biome-ignore lint/suspicious/noDocumentCookie: the Cookie Store API is missing in some browsers our users have.
  document.cookie = `${SCHOOL_COOKIE}=${encodeURIComponent(slug)}; Path=/; SameSite=Lax; Secure`;
}

type Init = Omit<RequestInit, "body"> & { school?: string | false; body?: unknown };

function headersFor(init: Init): Headers {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const csrf = readCookie("csrftoken");
  if (csrf) headers.set("X-CSRFToken", csrf);
  const tenant = init.school === false ? undefined : (init.school ?? getSelectedSchool());
  if (tenant) headers.set("X-Tenant", tenant);
  return headers;
}

export async function apiFetch<T>(path: string, init: Init = {}): Promise<T> {
  const headers = headersFor(init);
  let body: BodyInit | undefined;
  if (init.body instanceof FormData) {
    body = init.body;
  } else if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.body);
  }
  const { school: _school, body: _body, ...rest } = init;
  const response = await fetch(path, { ...rest, body, headers, credentials: "same-origin" });
  const text = await response.text();
  let parsed: unknown;
  try {
    parsed = text ? JSON.parse(text) : undefined;
  } catch {
    parsed = text;
  }
  if (!response.ok) {
    const code = (parsed as { code?: string } | undefined)?.code;
    throw new ApiError(response.status, code, parsed);
  }
  return parsed as T;
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown, headers?: HeadersInit) =>
    apiFetch<T>(path, { method: "POST", body: body ?? {}, headers }),
  patch: <T>(path: string, body: unknown) => apiFetch<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body: unknown) => apiFetch<T>(path, { method: "PUT", body }),
  del: <T>(path: string) => apiFetch<T>(path, { method: "DELETE" }),
};

/** Raw fetch with auth headers, for registers that may be queued offline. */
export function rawPost(path: string, body: unknown, school: string): Promise<Response> {
  const headers = headersFor({ school });
  headers.set("Content-Type", "application/json");
  return fetch(path, { method: "POST", headers, body: JSON.stringify(body), credentials: "same-origin" });
}

/** An image from the API (sent with the school header), or null if there isn't one. */
export async function fetchImage(path: string, school?: string): Promise<Blob | null> {
  const response = await fetch(path, { headers: headersFor({ school }), credentials: "same-origin" });
  if (response.status === 404) return null;
  if (!response.ok) throw new ApiError(response.status, undefined, undefined);
  if (!response.headers.get("Content-Type")?.startsWith("image/")) return null;
  return response.blob();
}

/**
 * Download a protected file. Report cards on S3 come back as a short-lived link
 * (navigated to directly); everything else streams through the API. Pass
 * `school: false` for files that belong to no school request (a closed school's export).
 */
export async function download(path: string, filename: string, school?: string | false): Promise<void> {
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(`${path}${separator}link=1`, {
    headers: headersFor({ school }),
    credentials: "same-origin",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => undefined);
    throw new ApiError(response.status, body?.code, body);
  }
  if (response.headers.get("Content-Type")?.includes("application/json")) {
    const { url } = (await response.json()) as { url: string };
    window.location.assign(url);
    return;
  }
  const blobUrl = URL.createObjectURL(await response.blob());
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 10_000);
}

export type Paged<T> = { next: string | null; previous: string | null; results: T[] };

export type MySchool = {
  slug: string;
  name: string;
  roles: string[];
  /** What these roles allow (core/rbac.py). Only shapes the UI; the API checks every request. */
  permissions: string[];
  /** Roles this person may give or block here (core.rbac.can_grant). */
  grantable_roles: string[];
  /** Modules switched on at this school (core/modules.py); the menu hides the rest. */
  modules: string[];
  /** The school's own roles this person holds, and the permissions they add. */
  custom_roles: string[];
  custom_permissions: string[];
  /** Until when Nex Edu support may see the school's set-up (the proprietor allowed it). */
  support_access_until?: string | null;
};

export type Me = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  last_login: string | null;
  mfa_enrolled: boolean;
  platform_roles: string[];
  schools: MySchool[];
  /** Schools the person belongs to that are suspended or closed. */
  unavailable_schools?: {
    slug: string;
    name: string;
    status: "suspended" | "offboarded";
    unpaid: boolean;
    purge_after: string | null;
    is_owner: boolean;
  }[];
};

export type Registration = {
  id: string;
  school_name: string;
  slug: string;
  school_type: string;
  region: string;
  town: string;
  phone: string;
  expected_pupils: number;
  status: "pending" | "provisioning" | "approved" | "rejected" | "failed";
  status_label: string;
  decision_note: string;
  school_slug: string | null;
  created_at: string;
};

/** A registration as platform staff see it (includes the duplicate flag). */
export type PlatformRegistration = Omit<Registration, "decision_note"> & {
  school_type_label: string;
  region_label: string;
  possible_duplicate: boolean;
  owner_name: string;
  owner_email: string;
  owner_joined: string;
  review_note: string;
  reviewed_by_email: string;
  reviewed_at: string | null;
};

export type PriceBand = { code: string; label: string; max_pupils: number | null; price_pesewas: number };

/** A school in the console list: identity and totals only, never its records. */
export type PlatformTenant = {
  id: string;
  slug: string;
  name: string;
  status: "provisioning" | "active" | "suspended" | "failed" | "offboarded";
  is_canary: boolean;
  created_at: string;
  region: string;
  town: string;
  pupils: number | null;
  staff: number | null;
  active_users_7d: number | null;
  last_activity_at: string | null;
  band: PriceBand | null;
  attention: string[];
};

export type TenantUsage = {
  day: string;
  pupils: number;
  classes: number;
  applications_pending: number;
  registers_7d: number;
  report_cards_published: number;
  sms_sent_month: number;
  sms_monthly_limit: number;
  payments_30d_pesewas: number;
  payments_total_pesewas: number;
  outstanding_pesewas: number;
  staff: number;
  parents: number;
  active_users_7d: number;
  active_users_30d: number;
  last_activity_at: string | null;
  setup_done: number;
  setup_total: number;
  setup_left: string[];
  collected_at: string;
};

export type PlatformSchool = Omit<
  PlatformTenant,
  "region" | "town" | "pupils" | "staff" | "active_users_7d" | "last_activity_at"
> & {
  schema_version: string;
  migrated_at: string | null;
  cell: string;
  registration: {
    school_type: string;
    region: string;
    town: string;
    phone: string;
    expected_pupils: number;
    submitted_at: string;
    approved_by: string;
    approved_at: string | null;
  } | null;
  owner: { name: string; email: string; phone: string; last_login: string | null } | null;
  people: {
    by_role: { role: string; label: string; count: number }[];
    staff: number;
    staff_with_app: number;
    not_joined: number;
    last_sign_in: string | null;
  };
  lifecycle: {
    status_reason: string;
    status_note: string;
    status_changed_at: string | null;
    purge_after: string | null;
    purged_at: string | null;
  };
  billing: {
    unpaid_pesewas: number;
    unpaid_invoices: number;
    oldest_due_on: string | null;
    sms: { monthly: number; bought: number };
    support_open_until: string | null;
  };
  usage: TenantUsage | null;
  history: { day: string; pupils: number; active_users_7d: number; registers_7d: number }[];
  platform_events: { occurred_at: string; actor_email: string; action: string; reason: string }[];
};

export type PlatformOverview = {
  generated_at: string;
  schools: {
    active: number;
    setting_up: number;
    suspended: number;
    failed: number;
    closed: number;
    active_7d: number;
  };
  registrations_pending: number;
  people: {
    pupils: number;
    staff: number;
    parents: number;
    active_users_7d: number;
    active_users_30d: number;
  };
  money: {
    expected_subscriptions_pesewas: number;
    fees_processed_30d_pesewas: number;
    fees_processed_total_pesewas: number;
    fees_outstanding_pesewas: number;
  };
  messages: { sms_sent_month: number };
  bands: (Omit<PriceBand, "max_pupils"> & { schools: number })[];
  history: { day: string; pupils: number; active_users: number; schools: number }[];
  schools_by_month: { month: string; count: number }[];
  registrations_by_month: { month: string; count: number }[];
  by_region: { region: string; schools: number }[];
  top_schools: { slug: string; name: string; pupils: number; staff: number }[];
  attention: { slug: string; name: string; reasons: string[] }[];
};

export type Term = {
  id: number;
  session: number;
  number: number;
  label: string;
  starts_on: string;
  ends_on: string;
  next_term_begins: string | null;
  is_current: boolean;
};

export type Session = { id: number; name: string; starts_on: string; ends_on: string; is_current: boolean };
export type Arm = { id: string; level: number; level_name: string; name: string; label: string };
export type Level = { id: number; name: string; section: string; order: number; is_active: boolean };
export type Subject = { id: number; name: string; code: string; sections: string[]; is_active: boolean };
export type Assignment = {
  id: number;
  teacher_user_id: string;
  arm: string;
  arm_label: string;
  subject: number | null;
  subject_name: string | null;
  is_form_teacher: boolean;
};
export type Period = {
  id: number;
  term: number;
  arm: string;
  arm_label: string;
  subject: number;
  subject_name: string;
  teacher_user_id: string | null;
  weekday: number;
  starts_at: string;
  ends_at: string;
  room: string;
  video_url: string;
};

export type Student = {
  id: string;
  admission_number: string;
  first_name: string;
  middle_name: string;
  last_name: string;
  date_of_birth: string;
  gender: string;
  arm: string | null;
  arm_name: string | null;
  status: string;
  admitted_on: string | null;
  address: string;
  hometown: string;
  region: string;
  medical_notes?: string;
  national_id?: string;
};

export type Guardian = {
  id: number;
  full_name: string;
  phone: string;
  email: string;
  relationship: string;
  is_primary: boolean;
  receives_sms: boolean;
  guardian_user_id: string | null;
};

export type Application = {
  id: string;
  reference: string;
  desired_level: number;
  desired_level_name: string;
  first_name: string;
  middle_name: string;
  last_name: string;
  date_of_birth: string;
  gender: string;
  previous_school: string;
  guardian_name: string;
  guardian_phone: string;
  guardian_email: string;
  status: string;
  source: string;
  review_notes: string;
  student_id: string | null;
  created_at: string;
};

export type ReportLine = {
  subject: string;
  code: string;
  components: Record<string, string | null>;
  total: string;
  grade: string;
  remark: string;
  position: string;
  class_highest: string;
  class_lowest: string;
  class_average: string;
};

export type ReportCard = {
  id: string;
  student: string;
  student_name: string;
  admission_number: string;
  term: number;
  term_label: string;
  arm_label: string;
  lines: ReportLine[];
  total_score: string;
  average: string;
  position: number | null;
  position_label: string;
  class_size: number;
  aggregate: number | null;
  days_present: number;
  days_open: number;
  form_teacher_comment: string;
  principal_comment: string;
  status: string;
  has_pdf: boolean;
};

export type Payment = {
  id: string;
  invoice: string;
  invoice_number: string;
  student_name: string;
  method: string;
  status: string;
  amount_pesewas: number;
  amount_received_pesewas: number;
  reference: string;
  receipt_number: string | null;
  authorization_url: string;
  paid_at: string | null;
  created_at: string;
};

export type Invoice = {
  id: string;
  number: string;
  student: string;
  student_name: string;
  admission_number: string;
  term: number;
  term_label: string;
  status: string;
  total_pesewas: number;
  paid_pesewas: number;
  balance_pesewas: number;
  due_date: string | null;
  issued_at: string;
  lines: { id: number; description: string; amount_pesewas: number }[];
  payments: Payment[];
};

export type Announcement = {
  id: string;
  title: string;
  body: string;
  audience: string;
  level: number | null;
  arm: string | null;
  channels: string[];
  status: string;
  created_at: string;
  published_at: string | null;
  recipient_count: number;
};

export type Notification = {
  id: string;
  kind: string;
  title: string;
  body: string;
  data: Record<string, string>;
  read_at: string | null;
  created_at: string;
};

export type Member = {
  id: number;
  user: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  role: string;
  role_label: string;
  is_active: boolean;
  has_password: boolean;
  mfa_enrolled: boolean;
  last_login: string | null;
};

// --- Super Admin console: billing, audit, announcements, system ---------------------------

export type Pricing = {
  period: "" | "monthly" | "termly" | "yearly";
  period_label: string;
  free_trial_days: number;
  bands: (PriceBand & { schools: number })[];
  schools: {
    slug: string;
    name: string;
    pupils: number | null;
    band_code: string | null;
    amount_pesewas: number | null;
  }[];
  expected_pesewas: number;
};

export type SubscriptionPayment = {
  id: string;
  school: string;
  slug: string;
  amount_pesewas: number;
  period_label: string;
  method: string;
  method_label: string;
  reference: string;
  received_on: string;
  band_code: string;
  pupils: number | null;
  note: string;
  recorded_by: string;
};

export type BillingHistory = {
  total_pesewas: number;
  payments_count: number;
  this_month_pesewas: number;
  before_this_month_pesewas: number;
  by_month: { month: string; total_pesewas: number; payments: number }[];
  payments: SubscriptionPayment[];
};

export type AuditEntry = {
  seq: number;
  occurred_at: string;
  action: string;
  actor_email: string;
  ip: string;
  reason: string;
  data: Record<string, unknown>;
  target_type: string;
  schools: { slug: string; name: string }[];
};

export type AuditPage = { events: AuditEntry[]; next_before: number | null };

export type PlatformAnnouncement = {
  id: string;
  title: string;
  body: string;
  audience: "all" | "band" | "region";
  band_code: string;
  region: string;
  email: boolean;
  status: "draft" | "published";
  recipient_count: number;
  read_count: number;
  created_by_email: string;
  created_at: string;
  published_at: string | null;
};

export type Problem = {
  id: number;
  kind: "server" | "job" | "browser" | "slow" | "health";
  kind_label: string;
  severity: "critical" | "warning";
  title: string;
  location: string;
  detail: string;
  last_path: string;
  schools: string[];
  count: number;
  first_seen: string;
  last_seen: string;
  status: "new" | "investigating" | "fixed" | "ignored";
  note: string;
  updated_by_email: string;
};

type SchoolRef = { slug: string; name: string };

export type SecurityActivity = {
  hours: number;
  failed_sign_ins: number;
  successful_sign_ins: number;
  accounts: {
    email: string;
    attempts: number;
    addresses: number;
    last_attempt: string;
    known_account: boolean;
    schools: SchoolRef[];
    suspicious: boolean;
  }[];
  suspicious_addresses: { ip: string; accounts: number; attempts: number; last: string }[];
  password_resets: { action: string; email: string; occurred_at: string; ip: string; schools: SchoolRef[] }[];
  authenticator_changes: {
    action: string;
    email: string;
    occurred_at: string;
    ip: string;
    schools: SchoolRef[];
  }[];
};

export type SystemStatus = {
  app_version: string;
  release: string;
  python: string;
  django: string;
  debug: boolean;
  schema_version: string;
  schools: number;
  schools_behind: { slug: string; name: string; migrated_at: string | null }[];
  platform_mfa_required: boolean;
  school_mfa_roles: string[];
  breached_password_check: boolean;
  security_checks: { id: string; level: "error" | "warning"; message: string; hint: string }[];
  scan: {
    started_at: string;
    finished_at: string | null;
    packages_checked: number;
    findings: {
      package: string;
      version: string;
      id: string;
      aliases: string[];
      summary: string;
      fixed_in: string[];
      url: string;
    }[];
    error: string;
  } | null;
  health?: { check: string; ok: boolean; title: string; school: string }[];
};

export type StaffMember = {
  id: string;
  user_id: string | null;
  staff_number: string;
  first_name: string;
  last_name: string;
  gender: string;
  phone: string;
  email: string;
  job_title: string;
  department: number | null;
  department_name: string;
  qualification: string;
  employment_date: string | null;
  is_active: boolean;
  bank_name?: string;
  bank_account_name?: string;
  bank_account_number?: string;
};

export type Department = {
  id: number;
  name: string;
  head: string | null;
  head_name: string;
  staff_count: number;
};

export type StaffRegisterRow = {
  staff: string;
  name: string;
  staff_number: string;
  job_title: string;
  department: string;
  status: "present" | "late" | "absent" | "on_leave" | "excused" | null;
  time_in: string;
  note: string;
  on_leave: boolean;
};

export type LeaveRequest = {
  id: string;
  staff: string;
  staff_name: string;
  kind: string;
  kind_label: string;
  start: string;
  end: string;
  days: number;
  reason: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  status_label: string;
  decision_note: string;
  decided_at: string | null;
  created_at: string;
  mine: boolean;
};

export type NexEduAnnouncement = { id: string; title: string; body: string; published_at: string };

export type Person = { id: string; name: string };
export type Conversation = {
  id: string;
  student: string;
  student_name: string;
  student_class: string;
  subject: string;
  staff: Person;
  parent: Person;
  created_at: string;
  last_message_at: string;
  unread: boolean;
  /** The caller is one of the two people in it (and so may reply). */
  mine: boolean;
};
export type ConversationMessage = {
  id: string;
  sender_user_id: string;
  sender_name: string;
  body: string;
  created_at: string;
  mine: boolean;
};
export type Contact = { user: string; name: string; role: string };

export type CalendarKind = "holiday" | "exam" | "meeting" | "event" | "other" | "term" | "public_holiday";
export type CalendarEntry = {
  id: string | null;
  source: "school" | "term" | "public_holiday";
  title: string;
  kind: CalendarKind;
  starts_on: string;
  ends_on: string;
  starts_at: string | null;
  ends_at: string | null;
  location: string;
  description: string;
  audience: "everyone" | "staff";
  editable: boolean;
};
