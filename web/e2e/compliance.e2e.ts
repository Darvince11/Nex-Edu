import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };

test("the compliance checklist is started, evidence filed and a renewal recorded", async ({ page }) => {
  await signInToSchool(page, PROPRIETOR);
  const nav = page.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const compliance = page.getByRole("switch", { name: "Accreditation and compliance" });
  await compliance.click({ force: true });
  await expect(compliance).toBeChecked();

  await nav.getByRole("link", { name: "Compliance" }).click();
  await page.getByRole("button", { name: "Add the usual checklist" }).click();
  await expect(page.getByText(/items added/)).toBeVisible();
  const fire = page.getByRole("row", { name: /Fire certificate/ });
  await expect(fire).toBeVisible();

  await fire.getByRole("button", { name: "Open Fire certificate" }).click();
  const dialog = page.getByRole("dialog");
  const nextYear = new Date().getFullYear() + 1;
  await dialog.getByLabel(/^Due on/).fill(`${nextYear}-01-15`);
  await dialog.getByRole("spinbutton", { name: /^Renews every/ }).fill("12");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog.getByText("Saved.")).toBeVisible();

  await dialog.getByLabel(/^Add a file/).setInputFiles({
    name: "fire-certificate.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 fire certificate"),
  });
  await dialog.getByRole("button", { name: "Upload" }).click();
  await expect(dialog.getByRole("button", { name: "fire-certificate.pdf", exact: true })).toBeVisible();
  await expectAccessible(page, "compliance item");

  await dialog.getByRole("button", { name: "Mark renewed" }).click();
  await expect(dialog.getByRole("button", { name: "Reopen" })).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(fire.getByText(`15 Jan ${nextYear + 1}`)).toBeVisible();
  await expectAccessible(page, "compliance checklist");

  // Leave the demo school as it was.
  await nav.getByRole("link", { name: "Modules" }).click();
  await page.getByRole("switch", { name: "Accreditation and compliance" }).click({ force: true });
  await expect(page.getByRole("switch", { name: "Accreditation and compliance" })).not.toBeChecked();
});
