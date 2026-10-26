import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const BURSAR = { email: "bursar@greenfield.test" };

test("the end-of-year plan lists every class with a move for each pupil", async ({ page }) => {
  await signInToSchool(page, PROPRIETOR);
  await page
    .getByRole("navigation", { name: "School" })
    .first()
    .getByRole("link", { name: "End of year" })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: "End of year" })).toBeVisible();
  // The demo school has a JHS 3 level but no JHS 3 class yet; moving up creates it.
  await expect(page.getByRole("heading", { name: "JHS 2 A → JHS 3 A" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Basic 6 A → JHS 1 A" })).toBeVisible();
  await expect(page.getByRole("combobox").first()).toBeVisible();
  // Applying would reshuffle the demo classes for other tests; only check the plan.
  await expectAccessible(page, "end of year");
});

test("the bursar sees who owes, what came in, and can record a scholarship", async ({ page }) => {
  await signInToSchool(page, BURSAR);
  await page
    .getByRole("navigation", { name: "School" })
    .first()
    .getByRole("link", { name: "Finance reports" })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: "Finance reports" })).toBeVisible();
  await expect(page.getByText("Still owed")).toBeVisible();
  const owing = page.getByRole("table").getByRole("row").nth(1).getByRole("link");
  const pupilName = (await owing.innerText()).trim();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download spreadsheet" }).click();
  expect((await download).suggestedFilename()).toBe("outstanding-fees.csv");
  await expectAccessible(page, "finance balances");

  await page.getByRole("tab", { name: "Collections" }).click();
  await expect(page.getByRole("heading", { name: "Collected each day" })).toBeVisible();
  await expectAccessible(page, "finance collections");

  await page.getByRole("tab", { name: "Scholarships" }).click();
  await page.getByRole("button", { name: "Add scholarship" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Find the pupil").fill(pupilName.split(" ")[0] ?? "");
  const pupil = dialog.getByRole("combobox", { name: "Pupil", exact: true });
  await expect(pupil.locator("option").nth(1)).toBeAttached();
  await pupil.selectOption({ index: 1 });
  const name = `Bursary ${Date.now().toString(36)}`;
  await dialog.getByRole("textbox", { name: /^Name/ }).fill(name);
  await dialog.getByLabel("Percentage off").fill("10");
  // Leave this term's demo invoices untouched for the other tests.
  await dialog.getByLabel(/this term's bill/).uncheck();
  await dialog.getByRole("button", { name: "Save scholarship" }).click();
  await expect(page.getByRole("row").filter({ hasText: name })).toContainText("10%");
  await expectAccessible(page, "scholarships");
});
