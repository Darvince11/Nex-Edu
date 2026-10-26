import path from "node:path";
import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";
import { HEAD, OWNER } from "./totp";

const FIXTURE = path.join(import.meta.dirname, "fixtures", "school-logo.png");

test("the proprietor adds the school logo and it appears for staff and applicants", async ({ page }) => {
  await signInToSchool(page, OWNER);

  await page
    .getByRole("navigation", { name: "School" })
    .first()
    .getByRole("link", { name: "School settings" })
    .click();
  await expect(page.getByRole("heading", { name: "School logo" })).toBeVisible();
  await expect(page.getByText("No logo")).toBeVisible();
  await expectAccessible(page, "settings with logo card");

  await page.getByLabel("Choose a logo file").setInputFiles(FIXTURE);
  await expect(page.getByAltText("Current school logo")).toBeVisible();
  await expect(page.getByRole("button", { name: "Replace logo" })).toBeVisible();
  // Top bar: the school's logo next to its name (decorative, so found by its blob source).
  await expect(page.locator('header img[src^="blob:"]')).toBeVisible();

  await page.goto("/apply?school=greenfield");
  await expect(page.getByAltText("Greenfield Academy logo")).toBeVisible();

  await page.goto("/settings");
  await page.getByRole("button", { name: "Remove" }).click();
  await expect(page.getByText("No logo")).toBeVisible();
});

test("only the proprietor changes the logo", async ({ page }) => {
  await signInToSchool(page, HEAD);
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "School settings" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "School logo" })).toHaveCount(0);
});

test("files that aren't images are refused before upload", async ({ page }) => {
  // allauth refuses a code it has already accepted; the next step's code is valid too (tolerance 1).
  await signInToSchool(page, OWNER, Date.now() + 30_000);
  await page.goto("/settings");
  await page.getByLabel("Choose a logo file").setInputFiles({
    name: "logo.svg",
    mimeType: "image/svg+xml",
    buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'),
  });
  await expect(page.getByRole("alert").filter({ hasText: "PNG, JPG or WebP" })).toBeVisible();
});
