import type { AuthResponse } from "./allauth";

/** Base domain for school web addresses (greenfield.nexedu.com.gh). */
export const SCHOOL_DOMAIN = process.env.NEXT_PUBLIC_SCHOOL_DOMAIN ?? "nexedu.com.gh";

/** Only same-site relative paths; anything else falls back to the school chooser. */
export function safeReturnTo(path: string | null | undefined): string {
  if (!path?.startsWith("/") || path.startsWith("//") || path.startsWith("/\\")) return "/schools";
  return path;
}

/** Where to send someone the API refused, keeping the reason for the sign-in page. */
export function loginPath(code?: string): string {
  return code ? `/login?reason=${encodeURIComponent(code)}` : "/login";
}

export type PasswordRule = { label: string; ok: boolean };

/**
 * The rules the server enforces that can be checked while typing. The server
 * also refuses very common passwords and ones found in data breaches.
 */
export function passwordRules(
  password: string,
  context: { email?: string; names?: string[] } = {},
): PasswordRule[] {
  const lower = password.toLowerCase();
  const personal = [context.email?.split("@")[0], ...(context.names ?? [])]
    .map((part) => part?.trim().toLowerCase())
    .filter((part): part is string => Boolean(part && part.length >= 3));
  return [
    { label: "At least 12 characters", ok: password.length >= 12 },
    { label: "Not only numbers", ok: password.length > 0 && !/^\d+$/.test(password) },
    {
      label: "Doesn't contain your name or email",
      ok: password.length > 0 && !personal.some((part) => lower.includes(part)),
    },
  ];
}

export const passwordAcceptable = (rules: PasswordRule[]) => rules.every((rule) => rule.ok);

/** Email codes look like "BCDF-GHJK": consonants only, so they can't spell words. */
export function formatEmailCode(raw: string): string {
  const letters = raw
    .toUpperCase()
    .replace(/[^A-Z]/g, "")
    .slice(0, 8);
  return letters.length > 4 ? `${letters.slice(0, 4)}-${letters.slice(4)}` : letters;
}

const MESSAGES: Record<string, string> = {
  email_password_mismatch: "That email and password don't match. Check them and try again.",
  too_many_login_attempts: "Too many attempts. Wait a minute, then try again.",
  incorrect_code: "That code isn't right. Check the latest email and try again.",
  invalid_or_expired_key: "This link has expired or was already used. Ask for a new one.",
  unavailable: "We couldn't reach Nex Edu. Check your connection and try again.",
  email_taken: "Check your email to continue.",
};

/** A message for people, from allauth's error codes. */
export function authError(result: AuthResponse, fallback = "Something went wrong. Try again."): string {
  if (result.status === 429) return "Too many attempts. Wait a few minutes, then try again.";
  const error = result.errors?.[0];
  if (!error) return fallback;
  return MESSAGES[error.code] ?? (error.message || fallback);
}

/** Field-level errors keyed by the input's name, for showing beside each field. */
export function fieldErrors(result: AuthResponse): Record<string, string> {
  const byField: Record<string, string> = {};
  for (const error of result.errors ?? []) {
    if (error.param && !byField[error.param]) byField[error.param] = error.message;
  }
  return byField;
}
