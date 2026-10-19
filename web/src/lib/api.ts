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
  del: <T>(path: string) => apiFetch<T>(path, { method: "DELETE" }),
};

/** Raw fetch with auth headers, for registers that may be queued offline. */
export function rawPost(path: string, body: unknown, school: string): Promise<Response> {
  const headers = headersFor({ school });
  headers.set("Content-Type", "application/json");
  return fetch(path, { method: "POST", headers, body: JSON.stringify(body), credentials: "same-origin" });
}

/**
 * Download a protected file. Report cards on S3 come back as a short-lived link
 * (navigated to directly); everything else streams through the API.
 */
export async function download(path: string, filename: string): Promise<void> {
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(`${path}${separator}link=1`, {
    headers: headersFor({}),
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

export type Me = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  mfa_enrolled: boolean;
  schools: { slug: string; name: string; roles: string[] }[];
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
