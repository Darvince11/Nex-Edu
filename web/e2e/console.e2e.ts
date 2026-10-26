import { expect, type Page, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signIn, signInToSchool } from "./session";

const ADMIN = { email: "admin@nexedu.test" };

async function openConsole(page: Page, link: string) {
  await signIn(page, ADMIN);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  // Badges ("Registrations 1 waiting") are part of a link's name, so match its start.
  await page
    .getByRole("navigation", { name: "Platform" })
    .getByRole("link", { name: new RegExp(`^${link}`) })
    .click();
}

test("the console menu is grouped and has every section", async ({ page }) => {
  await signIn(page, ADMIN);
  const nav = page.getByRole("navigation", { name: "Platform" });
  for (const name of [
    "Dashboard",
    "Registrations",
    "Schools",
    "Pricing and billing",
    "Billing history",
    "General audit log",
    "My audit log",
    "Announcements",
    "System settings",
  ]) {
    await expect(nav.getByRole("link", { name: new RegExp(`^${name}`) }).first()).toBeVisible();
  }

  // Each group folds with its caret, and stays folded after a reload.
  const money = nav.getByRole("button", { name: "Money" });
  await expect(money).toHaveAttribute("aria-expanded", "true");
  await money.click();
  await expect(money).toHaveAttribute("aria-expanded", "false");
  await expect(nav.getByRole("link", { name: "Billing history" })).toBeHidden();
  await page.reload();
  await expect(nav.getByRole("button", { name: "Money" })).toHaveAttribute("aria-expanded", "false");
  await nav.getByRole("button", { name: "Money" }).click();
  await expect(nav.getByRole("link", { name: "Billing history" })).toBeVisible();
  // The group holding the current page can't be folded away.
  await expect(nav.getByRole("button", { name: "Overview" })).toBeDisabled();
  await expectAccessible(page, "console: menu");
});

test("a super admin changes a price with a reason, and it lands in the audit logs", async ({ page }) => {
  await openConsole(page, "Pricing and billing");
  await expect(page.getByRole("heading", { level: 1, name: "Pricing and billing" })).toBeVisible();
  await expectAccessible(page, "console: pricing");

  async function setPrice(amount: string, reason: string) {
    await page.getByRole("button", { name: "Change price for Up to 1,000 pupils" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("New price (GH₵)").fill(amount);
    await dialog.getByLabel("Reason").fill(reason);
    await dialog.getByRole("button", { name: "Save price" }).click();
    await expect(dialog).toBeHidden();
  }
  await setPrice("260.00", "Browser test price");
  const band1 = page.getByRole("row").filter({ hasText: "Band 1" }).first();
  await expect(band1).toContainText("GH₵260.00");
  await setPrice("250.00", "Back to the owner's price");
  await expect(band1).toContainText("GH₵250.00");

  const nav = page.getByRole("navigation", { name: "Platform" });
  await nav.getByRole("link", { name: "General audit log" }).click();
  await page.getByLabel("Activity").selectOption({ label: "Pricing and payments" });
  await expect(page.getByText("“Browser test price”")).toBeVisible();
  await expect(page.getByRole("button", { name: /Platform \(no school\)/ })).toBeVisible();
  await expectAccessible(page, "console: general audit log");

  await nav.getByRole("link", { name: "My audit log" }).click();
  await expect(page.getByText("Changed a price").first()).toBeVisible();
});

test("a payment from a school is recorded and shows in billing history", async ({ page }) => {
  await openConsole(page, "Billing history");
  await expect(page.getByRole("heading", { level: 1, name: "Billing history" })).toBeVisible();
  await page.getByRole("button", { name: "Record a payment" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("School").selectOption({ label: "Greenfield Academy" });
  await dialog.getByLabel("Amount (GH₵)").fill("250");
  await dialog.getByLabel("Paying for").fill("Browser test month");
  await dialog.getByLabel("Reference").fill("MTN-E2E-1");
  await dialog.getByRole("button", { name: "Save payment" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("row").filter({ hasText: "Browser test month" })).toContainText("GH₵250.00");
  await expectAccessible(page, "console: billing history");
  await page.getByLabel("Only payments before this month").check();
  await expect(page.getByRole("row").filter({ hasText: "Browser test month" })).toHaveCount(0);
});

test("an announcement reaches proprietors and they can dismiss it", async ({ page }) => {
  const title = `New in Nex Edu ${Date.now()}`;
  await openConsole(page, "Announcements");
  await page.getByRole("button", { name: "New announcement" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Title").fill(title);
  await dialog.getByLabel("Message").fill("Report cards can now be printed in colour.");
  await dialog.getByLabel("Also email it to them").uncheck();
  await dialog.getByRole("button", { name: "Save draft" }).click();
  await expect(dialog).toBeHidden();
  const card = page.locator("section").filter({ hasText: title });
  await card.getByRole("button", { name: "Send" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Send now" }).click();
  await expect(card.getByText(/Read by 0 of/)).toBeVisible();
  await expectAccessible(page, "console: announcements");

  await page.getByRole("banner").getByRole("button", { name: "Sign out" }).click();
  await signInToSchool(page, { email: "director@greenfield.test" });
  const banner = page.getByRole("region", { name: `From Nex Edu: ${title}` });
  await expect(banner).toContainText("printed in colour");
  await banner.getByRole("button", { name: "Dismiss" }).click();
  await expect(banner).toBeHidden();
  await page.reload();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
  await expect(page.getByRole("region", { name: `From Nex Edu: ${title}` })).toHaveCount(0);
});

test("system settings show problems, sign-in activity, health and vulnerabilities", async ({ page }) => {
  await openConsole(page, "System settings");
  await expect(page.getByRole("heading", { level: 1, name: "System settings" })).toBeVisible();

  // A screen error reported by a browser shows up as a problem to fix.
  // No long numbers: the server scrubs them (they could be phone or card numbers).
  const message = `E2E screen error ${Math.random().toString(36).slice(2, 8)}`;
  await page.evaluate(async (text) => {
    const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
    await fetch("/api/v1/problems/browser", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ message: text, page: "/platform" }),
    });
  }, message);
  await page.reload();
  const problem = page.getByRole("button", { name: new RegExp(message) });
  await expect(problem).toBeVisible();
  await expectAccessible(page, "console: problems");
  await problem.click();
  await page.getByRole("button", { name: "Mark fixed" }).click();
  await expect(page.getByRole("button", { name: new RegExp(message) })).toHaveCount(0);

  await page.getByRole("tab", { name: "Sign-in and security" }).click();
  await expect(page.getByRole("heading", { name: "Failed sign-ins by account" })).toBeVisible();
  await expectAccessible(page, "console: sign-in and security");

  await page.getByRole("tab", { name: "Updates and health" }).click();
  await page.getByRole("button", { name: "Run health checks" }).click();
  await expect(page.getByText(/health checks passed|failed:/)).toBeVisible();
  await expectAccessible(page, "console: updates and health");

  await page.getByRole("tab", { name: "Vulnerabilities" }).click();
  await expect(page.getByRole("heading", { name: /Known vulnerabilities/ })).toBeVisible();
  await expectAccessible(page, "console: vulnerabilities");
});
