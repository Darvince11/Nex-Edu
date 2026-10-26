import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { chooseDarkMode } from "./session";

const PAGES = [
  ["/login", "Welcome back"],
  ["/signup", "Register your school"],
  ["/forgot-password", "Reset your password"],
  ["/account/password/reset/not-a-real-key", "Choose a password"],
  ["/legal/privacy", "Privacy notice"],
  ["/legal/terms", "Terms of service"],
] as const;

for (const scheme of ["light", "dark"] as const) {
  test.describe(`${scheme} mode`, () => {
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

test.describe("phone width", () => {
  test.use({ viewport: { width: 360, height: 740 } });

  for (const [path, heading] of PAGES.slice(0, 3)) {
    test(`${path} fits a 360 px screen`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, "no sideways scrolling").toBeLessThanOrEqual(0);
      await expect(page.getByRole("complementary")).toBeHidden(); // brand panel
      await expect(page.getByRole("link", { name: "Nex Edu" }).first()).toBeVisible();
    });
  }
});

test("headings and forms work from the keyboard alone", async ({ page }) => {
  await page.goto("/login");
  await page.keyboard.press("Tab");
  const reachable: string[] = [];
  for (let i = 0; i < 12; i++) {
    reachable.push(
      await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        return el?.getAttribute("aria-label") || el?.getAttribute("name") || el?.textContent?.trim() || "";
      }),
    );
    await page.keyboard.press("Tab");
  }
  expect(reachable).toEqual(expect.arrayContaining(["email", "password", "Show password", "Sign in"]));
});
