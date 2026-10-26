import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };

test("the proprietor switches the library on, adds a book, lends it and takes it back", async ({ page }) => {
  await signInToSchool(page, PROPRIETOR);
  const nav = page.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const library = page.getByRole("switch", { name: "Library" });
  await expect(library).not.toBeChecked();
  await library.click({ force: true });
  await expect(library).toBeChecked();

  await nav.getByRole("link", { name: "Library" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Library" })).toBeVisible();
  await page.getByRole("tab", { name: "Catalogue" }).click();
  const title = `Ananse Stories ${Date.now().toString(36)}`;
  await page.getByRole("button", { name: "Add a book" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "Title" }).fill(title);
  await dialog.getByRole("button", { name: "Add book" }).click();
  await page.getByRole("button", { name: title }).click();
  const number = (await page.getByRole("dialog").locator("li .font-mono").first().innerText()).trim();
  await expectAccessible(page, "book");
  await page.keyboard.press("Escape");

  await page.getByRole("tab", { name: "Desk" }).click();
  await page.getByRole("textbox", { name: /^Borrower/ }).fill("Akua");
  await page.getByRole("list", { name: "Matching borrowers" }).getByRole("button").first().click();
  await page
    .getByRole("textbox", { name: /^Book number/ })
    .first()
    .fill(number);
  await page.getByRole("button", { name: "Lend", exact: true }).click();
  await expect(page.getByText(`Lent “${title}”`)).toBeVisible();
  await expectAccessible(page, "library desk");

  await page.getByRole("tab", { name: "On loan" }).click();
  await expect(page.getByRole("row").filter({ hasText: title })).toContainText("Akua");
  await expectAccessible(page, "library loans");

  await page.getByRole("tab", { name: "Desk" }).click();
  const back = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Take a book back" }) });
  await back.getByRole("textbox", { name: "Book number" }).fill(number);
  await back.getByRole("button", { name: "Take back" }).click();
  await expect(back.getByText(`“${title}” is back`)).toBeVisible();

  // Leave the demo school as it was.
  await nav.getByRole("link", { name: "Modules" }).click();
  await page.getByRole("switch", { name: "Library" }).click({ force: true });
  await expect(page.getByRole("switch", { name: "Library" })).not.toBeChecked();
  await expect(nav.getByRole("link", { name: "Library" })).toHaveCount(0);
});
