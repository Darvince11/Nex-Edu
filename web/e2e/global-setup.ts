/**
 * Warm the freshly started API before any test: the first sign-in loads the
 * auth stack and runs the first password hash, which can take longer than a
 * test's wait. Uses an unused address so no real account's rate limit moves.
 */
const BASE = "http://localhost:3200";

export default async function globalSetup(): Promise<void> {
  const session = await fetch(`${BASE}/_allauth/browser/v1/auth/session`);
  const csrf = /csrftoken=([^;]+)/.exec(session.headers.get("set-cookie") ?? "")?.[1] ?? "";
  await fetch(`${BASE}/_allauth/browser/v1/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: BASE,
      "X-CSRFToken": csrf,
      Cookie: `csrftoken=${csrf}`,
    },
    body: JSON.stringify({ email: "warm-up@example.test", password: "not-a-real-password" }),
  });
  await fetch(`${BASE}/login`);
}
