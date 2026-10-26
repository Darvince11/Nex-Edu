import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { latestCode } from "./mail";

const DEMO_PASSWORD = "NexEdu-demo-2026!";

test("a school owner signs up, verifies their email and registers a school", async ({ page }) => {
  const stamp = Date.now();
  const email = `owner-${stamp}@example.test`;

  await page.goto("/signup");
  await expect(page.getByRole("heading", { name: "Register your school" })).toBeVisible();
  await expectAccessible(page, "sign-up: account step");

  await page.getByLabel("First name").fill("Esi");
  await page.getByLabel("Last name").fill("Mensah");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill("lantern river cloth market");
  await expect(page.getByText("At least 12 characters")).toBeVisible();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();
  await expectAccessible(page, "sign-up: verify step");
  await page.getByLabel("Verification code").fill(await latestCode(email));
  await page.getByRole("button", { name: "Verify email" }).click();

  await expect(page.getByRole("heading", { name: "Tell us about your school" })).toBeVisible();
  await page.getByLabel("School name").fill(`Esi Academy ${stamp}`);
  await expect(page.getByLabel("Web address")).toHaveValue(`esi-academy-${stamp}`);
  await expect(page.getByText("Available", { exact: true })).toBeVisible();
  await expectAccessible(page, "sign-up: school step");
  await page.getByLabel("Pupils (about)").fill("180");
  await page.getByLabel("Region").selectOption("ashanti");
  await page.getByLabel("Town or city").fill("Kumasi");
  await page.getByLabel("School phone").fill("024 412 3456");
  await page.getByRole("button", { name: "Send for review" }).click();

  await expect(page.getByRole("heading", { name: "Thanks, we're reviewing your school" })).toBeVisible();
  await expectAccessible(page, "sign-up: under review");

  // A new owner has no school yet; their account page shows the request.
  await page.goto("/schools");
  await expect(page.getByText("Under review")).toBeVisible();
  await expect(page.getByText(`Esi Academy ${stamp}`)).toBeVisible();
});

test("the account step refuses to send an incomplete form", async ({ page }) => {
  await page.goto("/signup");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Enter your first name.")).toBeVisible();
  await expect(page.getByText("Agree to the terms and privacy notice to continue.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Register your school" })).toBeVisible();
});

test("sign-in gives no hint about accounts, then lets the right password in", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();

  await page.getByLabel("Email", { exact: true }).fill("parent@greenfield.test");
  await page.getByLabel("Password", { exact: true }).fill("not-the-right-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  // Next.js keeps its own empty role="alert" route announcer, so match by text.
  await expect(page.getByRole("alert").filter({ hasText: "don't match" })).toHaveText(
    "That email and password don't match. Check them and try again.",
  );

  await page.getByLabel("Password", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  // Nobody picks a school: the app opens theirs.
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("banner").getByText("Greenfield Academy")).toBeVisible();
  await expect(page.getByRole("button", { name: /Greenfield Academy/ })).toHaveCount(0);
});

test("the password field can be shown and hidden", async ({ page }) => {
  await page.goto("/login");
  const password = page.getByLabel("Password", { exact: true });
  await password.fill("secret-value");
  await expect(password).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(page.getByRole("button", { name: "Hide password" })).toHaveAttribute("aria-pressed", "true");
});

test("forgot password gives the same answer for any email", async ({ page }) => {
  for (const email of ["parent@greenfield.test", `nobody-${Date.now()}@example.test`]) {
    await page.goto("/forgot-password");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByRole("button", { name: "Send reset link" }).click();
    await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
    await expect(page.getByText(`If ${email} has a Nex Edu account`)).toBeVisible();
  }
});
