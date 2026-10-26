import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };

test("a past pupil who agreed to contact is added and their gift recorded", async ({ page }) => {
  const surname = `Old${Date.now().toString(36)}`;
  await signInToSchool(page, PROPRIETOR);
  const nav = page.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const alumni = page.getByRole("switch", { name: "Alumni and fundraising" });
  await alumni.click({ force: true });
  await expect(alumni).toBeChecked();

  await nav.getByRole("link", { name: "Alumni" }).click();
  await page.getByRole("button", { name: "Add a past pupil" }).click();
  const form = page.getByRole("dialog");
  await form.getByRole("textbox", { name: "First name" }).fill("Kofi");
  await form.getByRole("textbox", { name: "Last name" }).fill(surname);
  await form.getByRole("spinbutton", { name: /^Class of/ }).fill("2012");
  await form.getByRole("textbox", { name: "Phone" }).fill("0244111222");
  await form.getByRole("checkbox", { name: /agreed to hear from the school/ }).check();
  await expectAccessible(page, "alumni form");
  await form.getByRole("button", { name: "Save" }).click();
  const row = page.getByRole("row", { name: new RegExp(surname) });
  await expect(row.getByText("Agreed")).toBeVisible();

  await page.getByRole("tab", { name: "Gifts and pledges" }).click();
  await page.getByRole("button", { name: "Record a gift" }).click();
  const gift = page.getByRole("dialog");
  await gift.getByRole("combobox", { name: /^Past pupil/ }).selectOption({ label: `Kofi ${surname} (2012)` });
  await gift.getByRole("textbox", { name: "Amount (GH₵)" }).fill("250");
  await gift.getByRole("combobox", { name: "Status" }).selectOption("pledge");
  await gift.getByRole("textbox", { name: "For" }).fill("Library roof");
  await gift.getByRole("button", { name: "Save gift" }).click();
  await page.getByRole("button", { name: `Mark the pledge from Kofi ${surname} as paid` }).click();
  await expect(page.getByRole("row", { name: /Library roof/ }).getByText("Received")).toBeVisible();
  await expectAccessible(page, "alumni gifts");

  await page.getByRole("tab", { name: "Past pupils" }).click();
  await expect(row.getByText("GH₵250.00")).toBeVisible();

  // Leave the demo school as it was.
  await row.getByRole("button", { name: `Edit Kofi ${surname}` }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove from the list" }).click();
  await expect(row).toHaveCount(0);
  await nav.getByRole("link", { name: "Modules" }).click();
  await page.getByRole("switch", { name: "Alumni and fundraising" }).click({ force: true });
  await expect(page.getByRole("switch", { name: "Alumni and fundraising" })).not.toBeChecked();
});
