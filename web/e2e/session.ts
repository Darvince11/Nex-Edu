import { expect, type Page } from "@playwright/test";
import { totp } from "./totp";

export const DEMO_PASSWORD = "NexEdu-demo-2026!";

type Account = { email: string; password?: string; totpSecret?: string };

/**
 * Signs in and waits for the school dashboard: nobody chooses a school, the app
 * opens theirs. `codeAt` picks a later TOTP step when the same account signs in
 * twice within 30 seconds (allauth refuses a code it has already accepted).
 */
export async function signIn(page: Page, account: Account, codeAt = Date.now()): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill(account.password ?? DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  if (account.totpSecret) {
    await expect(page.getByRole("heading", { name: "Two-step verification" })).toBeVisible();
    await page.getByLabel("Code").fill(totp(account.totpSecret, codeAt));
    await page.getByRole("button", { name: "Verify" }).click();
  }
}

export async function signInToSchool(page: Page, account: Account, codeAt?: number): Promise<void> {
  await signIn(page, account, codeAt);
  // The first sign-in on a freshly started test server opens the school's database.
  await expect(page).toHaveURL(/\/dashboard$/, { timeout: 45_000 });
}

/** Dark mode is the person's choice (stored in this browser), not the device setting. */
export async function chooseDarkMode(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      window.localStorage.setItem("nexedu.theme", "dark");
    } catch {
      // Storage blocked: the test will fail on the colour check instead.
    }
  });
}
