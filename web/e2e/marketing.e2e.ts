import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { chooseDarkMode } from "./session";

const PAGES = [
  ["/", "Run your school from one secure place."],
  ["/features", "What Nex Edu does for your school"],
  ["/pricing", "Pricing for your school"],
  ["/faq", "Questions and answers"],
  ["/contact", "Talk to the Nex Edu team"],
] as const;

for (const scheme of ["light", "dark"] as const) {
  test.describe(`public site, ${scheme} mode`, () => {
    test.beforeEach(async ({ page }) => {
      if (scheme === "dark") await chooseDarkMode(page);
    });
    for (const [path, heading] of PAGES) {
      test(`${path} meets WCAG 2.2 AA`, async ({ page }) => {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
        await expectAccessible(page, `${path} (${scheme})`);
      });
    }
  });
}

test("the home page leads to registration and sign-in", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("main").getByRole("link", { name: "Register your school" }).first().click();
  await expect(page.getByRole("heading", { name: "Register your school" })).toBeVisible();
  await page.goto("/");
  await page.getByRole("banner").getByRole("link", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
});

test("every internal link on the public site works", async ({ page, request }) => {
  const seen = new Set<string>();
  for (const [path] of PAGES) {
    await page.goto(path);
    for (const href of await page
      .locator("a[href^='/']")
      .evaluateAll((as) => as.map((a) => a.getAttribute("href")))) {
      if (href) seen.add(href.split("#")[0] ?? href);
    }
  }
  const broken: string[] = [];
  for (const href of seen) {
    const response = await request.get(href);
    if (!response.ok()) broken.push(`${href} -> ${response.status()}`);
  }
  expect(broken).toEqual([]);
  expect(seen.size).toBeGreaterThan(8);
});

test.describe("phone width", () => {
  test.use({ viewport: { width: 360, height: 740 } });

  for (const [path, heading] of PAGES) {
    test(`${path} fits a 360 px screen and the menu opens`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, "no sideways scrolling").toBeLessThanOrEqual(0);
      await page.getByText("Menu", { exact: true }).click();
      await expect(page.getByRole("banner").getByRole("link", { name: "Pricing" })).toBeVisible();
    });
  }
});
