import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };

test("the bursar records spending, sets a budget, and the books balance", async ({ page }) => {
  const payee = `ECG ${Date.now().toString(36)}`;
  await signInToSchool(page, PROPRIETOR);
  const nav = page.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const accounting = page.getByRole("switch", { name: "Accounting" });
  await accounting.click({ force: true });
  await expect(accounting).toBeChecked();

  await nav.getByRole("link", { name: "Accounting" }).click();
  await page.getByRole("button", { name: "Record spending" }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("combobox", { name: "Spent on" })
    .selectOption({ label: "Utilities (electricity, water, internet)" });
  await dialog.getByRole("textbox", { name: /^Amount/ }).fill("450");
  await dialog.getByRole("textbox", { name: "Paid to" }).fill(payee);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("row").filter({ hasText: payee })).toContainText("GH₵450.00");
  await expectAccessible(page, "accounting");

  await page.getByRole("tab", { name: "Budgets" }).click();
  await page
    .getByRole("combobox", { name: "Account" })
    .selectOption({ label: "Utilities (electricity, water, internet)" });
  await page.getByRole("textbox", { name: /^Budget/ }).fill("1000");
  await page.getByRole("button", { name: "Set budget" }).click();
  await expect(page.getByRole("row").filter({ hasText: "Utilities" })).toContainText("GH₵1,000.00");

  await page.getByRole("tab", { name: "Reports" }).click();
  await page.getByRole("combobox", { name: "Report" }).selectOption({ label: "Trial balance" });
  await expect(page.getByText("The books balance.")).toBeVisible();
  await expectAccessible(page, "trial balance");

  // Leave the demo school as it was: void the entry, then switch off.
  await page.getByRole("tab", { name: "Money in and out" }).click();
  await page.getByRole("row").filter({ hasText: payee }).getByRole("button", { name: /^Void/ }).click();
  await page.getByRole("dialog").getByRole("textbox", { name: "Why" }).fill("End of test");
  await page.getByRole("dialog").getByRole("button", { name: "Void" }).click();
  await expect(page.getByRole("row").filter({ hasText: payee })).toContainText("Voided");
  await nav.getByRole("link", { name: "Modules" }).click();
  await page.getByRole("switch", { name: "Accounting" }).click({ force: true });
  await expect(page.getByRole("switch", { name: "Accounting" })).not.toBeChecked();
});
