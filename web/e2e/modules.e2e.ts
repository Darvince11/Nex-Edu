import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signIn, signInToSchool } from "./session";

// A proprietor without an authenticator app (seed_platform.py), so no one-time codes to juggle.
const PROPRIETOR = { email: "director@greenfield.test" };

test("the proprietor switches a module off and on, and the menu follows", async ({ page }) => {
  await signInToSchool(page, PROPRIETOR);
  const nav = page.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Modules" })).toBeVisible();
  await expectAccessible(page, "modules");

  const admissions = page.getByRole("switch", { name: "Online admissions" });
  await expect(admissions).toBeChecked();
  await expect(nav.getByRole("link", { name: "Admissions" })).toBeVisible();
  // Switches change once the server agrees, so click and then wait for the new state.
  await admissions.click({ force: true });
  await expect(admissions).not.toBeChecked();
  await expect(nav.getByRole("link", { name: "Admissions" })).toHaveCount(0);

  await admissions.click({ force: true });
  await expect(admissions).toBeChecked();
  await expect(nav.getByRole("link", { name: "Admissions" })).toBeVisible();

  // The demo school has unpaid invoices, so switching fees off asks first.
  await page.getByRole("switch", { name: "Fees and payments" }).click({ force: true });
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("unpaid invoice");
  await dialog.getByRole("button", { name: "Keep it on" }).click();
  await expect(page.getByRole("switch", { name: "Fees and payments" })).toBeChecked();

  await page.getByRole("button", { name: "Save my choices" }).click();
  await expect(page.getByRole("button", { name: "Choices saved" })).toBeVisible();
  await expect(page.getByText("Switched off · Online admissions")).toBeVisible();
});

test("Nex Edu staff see a school's modules on its page", async ({ page }) => {
  await signIn(page, { email: "admin@nexedu.test" });
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.goto("/platform/schools/greenfield");
  const card = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Modules", exact: true }) });
  await expect(card).toContainText("Fees and payments");
  await expect(card.getByRole("button", { name: "Switch off" }).first()).toBeVisible();
  await expectAccessible(page, "console school page with modules");
});
