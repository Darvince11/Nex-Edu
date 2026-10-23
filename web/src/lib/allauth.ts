/**
 * django-allauth headless "browser" client: sign-up with email codes,
 * email/password, TOTP, passkeys, password reset.
 * Responses use the envelope { status, data, meta }. A 401 that lists pending
 * flows (e.g. "mfa_authenticate") means another step is needed.
 */
import {
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
  startAuthentication,
  startRegistration,
} from "@simplewebauthn/browser";

const BASE = "/_allauth/browser/v1";

type Flow = { id: string; is_pending?: boolean };
export type AuthResponse = {
  status: number;
  data?: { flows?: Flow[]; [key: string]: unknown };
  meta?: { is_authenticated?: boolean; [key: string]: unknown };
  errors?: { message: string; code: string; param?: string }[];
};

function csrfToken(): string {
  return (
    document.cookie
      .split("; ")
      .find((c) => c.startsWith("csrftoken="))
      ?.split("=")[1] ?? ""
  );
}

async function call(method: "GET" | "POST" | "DELETE", path: string, body?: unknown) {
  const response = await fetch(`${BASE}${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
      "X-CSRFToken": csrfToken(),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  try {
    return (await response.json()) as AuthResponse;
  } catch {
    // Not JSON (a proxy error page, say): report it like any other failure.
    return { status: response.status, errors: [{ message: "", code: "unavailable" }] };
  }
}

export const pendingFlow = (r: AuthResponse) => r.data?.flows?.find((f) => f.is_pending)?.id;
export const firstError = (r: AuthResponse) => r.errors?.[0]?.message;

/** Also sets the CSRF cookie, so call it before the first POST. */
export const getSession = () => call("GET", "/auth/session");
export const login = (email: string, password: string) => call("POST", "/auth/login", { email, password });
export const submitMfaCode = (code: string) => call("POST", "/auth/2fa/authenticate", { code });
export const logout = () => call("DELETE", "/auth/session");
export const reauthenticate = (password: string) => call("POST", "/auth/reauthenticate", { password });
export const resetPassword = (key: string, password: string) =>
  call("POST", "/auth/password/reset", { key, password });
export const requestPasswordReset = (email: string) => call("POST", "/auth/password/request", { email });

export type SignupDetails = {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  accept_terms: boolean;
  /** Honeypot: always empty for people. */
  website: string;
};
export const signup = (details: SignupDetails) => call("POST", "/auth/signup", details);
export const verifyEmail = (code: string) => call("POST", "/auth/email/verify", { key: code });
export const resendEmailCode = () => call("POST", "/auth/email/verify/resend");

export async function loginWithPasskey(): Promise<AuthResponse> {
  const options = await call("GET", "/auth/webauthn/login");
  const requestOptions = (options.data?.request_options as { publicKey: unknown })?.publicKey;
  const credential = await startAuthentication({
    optionsJSON: requestOptions as PublicKeyCredentialRequestOptionsJSON,
  });
  return call("POST", "/auth/webauthn/login", { credential });
}

export const getTotpSetup = () => call("GET", "/account/authenticators/totp");
export const activateTotp = (code: string) => call("POST", "/account/authenticators/totp", { code });

export async function addPasskey(name: string): Promise<AuthResponse> {
  const options = await call("GET", "/account/authenticators/webauthn?passwordless");
  if (options.status !== 200) return options;
  const creationOptions = (options.data?.creation_options as { publicKey: unknown })?.publicKey;
  const credential = await startRegistration({
    optionsJSON: creationOptions as PublicKeyCredentialCreationOptionsJSON,
  });
  return call("POST", "/account/authenticators/webauthn", { name, credential });
}
