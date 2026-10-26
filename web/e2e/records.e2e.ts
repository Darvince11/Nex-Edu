import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };

test("guardians are listed once, grading can be checked, and the audit log is readable", async ({ page }) => {
  await signInToSchool(page, PROPRIETOR);
  const nav = page.getByRole("navigation", { name: "School" }).first();

  await nav.getByRole("link", { name: "Guardians" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Guardians" })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "Akosua Mensah" })).toContainText("Has a login");
  await expectAccessible(page, "guardians");

  await nav.getByRole("link", { name: "Grading" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Grading" })).toBeVisible();
  await expect(page.getByText("Parts in use add up to 100.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "JHS (BECE grades)" })).toBeVisible();
  // The breadcrumb names this page, not "School settings".
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Grading");
  await expectAccessible(page, "grading");

  await nav.getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Audit log" })).toBeVisible();
  await expect(page.getByText(/Log intact/)).toBeVisible();
  await page.getByLabel("Period").selectOption({ label: "Everything" });
  await expect(page.getByRole("row").nth(1)).toBeVisible();
  await expectAccessible(page, "school audit log");
});
