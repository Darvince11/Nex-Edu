import { expect, type Page, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const signInAsParent = (page: Page) => signInToSchool(page, { email: "parent@greenfield.test" });

test("the menu is grouped, role-aware, and shows where you are", async ({ page }) => {
  await signInAsParent(page);
  const nav = page.getByRole("navigation", { name: "School" }).first();

  await expect(nav.getByRole("link", { name: "My children" })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Communication" })).toBeVisible();
  for (const hidden of ["Score entry", "Admissions", "School settings", "Staff and access"]) {
    await expect(nav.getByRole("link", { name: hidden })).toHaveCount(0);
  }
  await expect(nav.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  await expectAccessible(page, "school dashboard with sidebar");

  await nav.getByRole("link", { name: "Results and report cards" }).click();
  const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
  await expect(crumbs).toContainText("Academics");
  await expect(crumbs.getByText("Results and report cards")).toHaveAttribute("aria-current", "page");
});

test("groups fold and the menu collapses to icons, remembered after reload", async ({ page }) => {
  await signInAsParent(page);
  const nav = page.getByRole("navigation", { name: "School" }).first();

  const communication = nav.getByRole("button", { name: "Communication" });
  await communication.click();
  await expect(communication).toHaveAttribute("aria-expanded", "false");
  await expect(nav.getByRole("link", { name: "Inbox" })).toHaveCount(0);
  await communication.click();
  await expect(nav.getByRole("link", { name: "Inbox" })).toBeVisible();

  await page.getByRole("button", { name: "Collapse menu" }).click();
  await expect(page.getByRole("button", { name: "Expand menu" })).toBeVisible();
  // Labels are hidden visually but links keep their accessible names.
  await expect(nav.getByRole("link", { name: "My children" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("button", { name: "Expand menu" })).toBeVisible();
  await page.getByRole("button", { name: "Expand menu" }).click();
  await expect(page.getByRole("button", { name: "Collapse menu" })).toBeVisible();
});
