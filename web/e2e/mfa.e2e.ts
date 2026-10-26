import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { totp } from "./totp";

test("a staff member can add an authenticator app from their profile and gets recovery codes", async ({
  page,
}) => {
  await page.goto("/login");
  // Its own account (seed_platform.py): the app stays on after this test.
  await page.getByLabel("Email", { exact: true }).fill("newapp@greenfield.test");
  await page.getByLabel("Password", { exact: true }).fill("NexEdu-demo-2026!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  // Optional: they're in their school without one.
  await expect(page).toHaveURL(/\/dashboard$/);

  await page
    .getByRole("banner")
    .getByRole("link", { name: /Your profile/ })
    .click();
  await expect(page.getByText("Not set up")).toBeVisible();
  await page.getByRole("link", { name: "Set up an authenticator app" }).click();
  await expect(page.getByRole("heading", { name: "Protect your account" })).toBeVisible();
  await expectAccessible(page, "security: add the app");

  const secret = (await page.locator("code").first().innerText()).trim();
  expect(secret).toMatch(/^[A-Z2-7]{16,}$/);
  await page.getByLabel("6-digit code from the app").fill(totp(secret));
  await page.getByLabel("Your password", { exact: true }).fill("NexEdu-demo-2026!");
  await page.getByRole("button", { name: "Turn on" }).click();

  await expect(page.getByRole("heading", { name: "Save your recovery codes" })).toBeVisible();
  await expect(
    page
      .getByRole("listitem")
      .filter({ hasText: /^[a-z0-9]{6,}$/i })
      .first(),
  ).toBeVisible();
  await expectAccessible(page, "security: recovery codes");
  const next = page.getByRole("button", { name: "Continue" });
  await expect(next).toBeDisabled();
  await page.getByRole("checkbox").check();
  await next.click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/profile");
  await expect(page.getByRole("link", { name: "Manage authenticator app and recovery codes" })).toBeVisible();
});
