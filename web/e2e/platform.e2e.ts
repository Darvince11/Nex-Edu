import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signIn } from "./session";
import { OPS, totp } from "./totp";

test("platform staff review a registration and the school goes live", async ({ page }) => {
  // Approval returns at once; creating the school's database runs in the background
  // and the page checks until it's done, which can take a minute here.
  test.setTimeout(180_000);
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(OPS.email);
  await page.getByLabel("Password", { exact: true }).fill(OPS.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Two-step verification" })).toBeVisible();
  await page.getByLabel("Code").fill(totp(OPS.totpSecret));
  await page.getByRole("button", { name: "Verify" }).click();

  // No school of their own, so sign-in opens the console's dashboard.
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page
    .getByRole("navigation", { name: "Platform" })
    .getByRole("link", { name: /Registrations/ })
    .click();
  await expect(page.getByRole("heading", { name: "School registrations" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Under review" })).toHaveAttribute("aria-selected", "true");
  await expectAccessible(page, "platform: registrations queue");
  await page.getByRole("link", { name: "Harmattan Hills School" }).click();

  await expect(page.getByRole("heading", { name: "Harmattan Hills School" })).toBeVisible();
  await expect(page.getByText("applicant@example.test")).toBeVisible();
  await expectAccessible(page, "platform: registration detail");

  await page.getByRole("button", { name: "Approve and create school" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(/makes applicant@example\.test its owner/)).toBeVisible();
  await dialog.getByLabel(/Note/).fill("Called the school office to confirm.");
  await dialog.getByRole("button", { name: "Approve and create school" }).click();

  await expect(page.getByText("Setting up the school's database")).toBeVisible();
  await expect(
    page
      .getByRole("definition")
      .filter({ hasText: /^Approved$/ })
      .first(),
  ).toBeVisible({
    timeout: 120_000,
  });
  await expect(page.getByText("Reviewed by")).toBeVisible();
  await expect(page.getByText(OPS.email).last()).toBeVisible();
  await expect(page.getByText("harmattan-hills.nexedu.com.gh").first()).toBeVisible();

  await page.getByRole("link", { name: "Schools", exact: true }).click();
  await expect(page.getByRole("cell", { name: "Harmattan Hills School" })).toBeVisible();
  await expectAccessible(page, "platform: schools");
});

test("a super admin without an authenticator app gets in, with a reminder they can put off", async ({
  page,
}) => {
  await signIn(page, { email: "admin@nexedu.test" });
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  const reminder = page.getByRole("region", { name: "Account security" });
  await expect(reminder).toContainText("Add an authenticator app");
  await expectAccessible(page, "platform: console with reminder");

  await reminder.getByRole("button", { name: "Not now" }).click();
  await expect(reminder).toBeHidden();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Account security" })).toHaveCount(0);
});

test("the dashboard charts every school and each school opens with its size and price band", async ({
  page,
}) => {
  await signIn(page, { email: "admin@nexedu.test" });
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Pupils on Nex Edu" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Schools by price band" })).toContainText(
    "Up to 1,000 pupils",
  );
  await expectAccessible(page, "platform: dashboard");

  await page.getByRole("navigation", { name: "Platform" }).getByRole("link", { name: "Schools" }).click();
  await page.getByLabel("Search schools").fill("greenfield");
  await page.getByRole("link", { name: "Greenfield Academy" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "Greenfield Academy" })).toBeVisible();
  await expect(page.getByText("GH₵250.00")).toBeVisible();
  await expect(page.getByText("Esther Adjei")).toBeVisible(); // the proprietor
  await expect(page.getByRole("region", { name: "People by role" })).toBeVisible();
  await expectAccessible(page, "platform: school detail");
  await page.getByRole("button", { name: "Refresh figures" }).click();
  await expect(page.getByRole("button", { name: "Refresh figures" })).toBeEnabled();
  await expect(page.getByText("Figures refreshed")).toBeVisible(); // logged as a Nex Edu staff action
});

test("people who aren't platform staff are turned away", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("parent@greenfield.test");
  await page.getByLabel("Password", { exact: true }).fill("NexEdu-demo-2026!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/profile");
  await expect(page.getByRole("heading", { name: "Your profile" })).toBeVisible();
  await expect(page.getByRole("link", { name: /platform console/ })).toHaveCount(0);

  await page.goto("/platform/registrations");
  await expect(page.getByRole("heading", { name: "Platform staff only" })).toBeVisible();
  await expect(page.getByText("Harmattan Hills School")).toHaveCount(0);
});

test("a newly approved proprietor gets a set-up checklist", async ({ page }) => {
  // Harmattan Hills was approved in the first test of this file.
  await signIn(page, { email: "applicant@example.test", password: "applicant-e2e-password" });
  await expect(page).toHaveURL(/\/dashboard$/);
  const checklist = page.getByRole("region", { name: "Get your school ready" });
  await expect(checklist).toContainText("Add staff");
  await expect(checklist).toContainText("Invite parents");
  await expectAccessible(page, "dashboard with set-up checklist");

  await checklist.getByRole("button", { name: "Accept for the school" }).click();
  await expect(checklist.getByText("Done: Accept the terms for the school")).toBeAttached();

  await checklist.getByRole("button", { name: "Hide checklist" }).click();
  await expect(page.getByRole("region", { name: "Get your school ready" })).toHaveCount(0);
  await page.goto("/settings");
  await page.getByRole("button", { name: "Show the checklist on the dashboard" }).click();
  await page.goto("/dashboard");
  await expect(page.getByRole("region", { name: "Get your school ready" })).toBeVisible();
});
