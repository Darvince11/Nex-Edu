import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };

test("an API key reads the school's pupils until switched off, and the calendar link works", async ({
  page,
}) => {
  test.slow();
  await signInToSchool(page, PROPRIETOR);
  const nav = page.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  for (const name of ["Developer API and webhooks", "AI drafting help"]) {
    const toggle = page.getByRole("switch", { name });
    await toggle.click({ force: true });
    await expect(toggle).toBeChecked();
  }

  await nav.getByRole("link", { name: "Integrations" }).click();
  await page.getByRole("button", { name: "New key" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "What it's for" }).fill("Test system");
  await dialog.getByRole("checkbox", { name: /students:read/ }).check();
  await dialog.getByRole("button", { name: "Make the key" }).click();
  const key = await dialog.getByRole("textbox", { name: "API key" }).inputValue();
  expect(key).toMatch(/^nxk_/);
  await expectAccessible(page, "integrations: new key");
  await dialog.getByRole("button", { name: "Close" }).click();

  const read = await page.request.get("/api/v1/developer/students/", {
    headers: { Authorization: `Bearer ${key}` },
  });
  expect(read.status()).toBe(200);
  expect(JSON.stringify(await read.json())).toContain("Akua");

  // Webhooks only go to addresses on the public internet.
  await page.getByRole("button", { name: "Add a webhook" }).click();
  const hook = page.getByRole("dialog");
  await hook.getByRole("textbox", { name: /^Address/ }).fill("https://localhost/hook");
  await hook.getByRole("checkbox", { name: /payment.received/ }).check();
  await hook.getByRole("button", { name: "Add webhook" }).click();
  await expect(hook.getByText("That address isn't reachable on the public internet.")).toBeVisible();
  await hook.getByRole("button", { name: "Close" }).click();
  await expectAccessible(page, "integrations");

  await page.getByRole("button", { name: "Switch off Test system" }).click();
  await expect(page.getByText("Switched off")).toBeVisible();
  const refused = await page.request.get("/api/v1/developer/students/", {
    headers: { Authorization: `Bearer ${key}` },
  });
  expect(refused.status()).toBe(401);

  // A private calendar link for phone calendars.
  await page.goto("/profile");
  await page.getByRole("button", { name: "Get my calendar link" }).click();
  const link = await page.getByRole("textbox", { name: /^Your calendar link/ }).inputValue();
  const calendar = await page.request.get(new URL(link).pathname);
  expect(calendar.status()).toBe(200);
  expect(await calendar.text()).toContain("BEGIN:VCALENDAR");
  await expectAccessible(page, "profile with calendar link");
  await page.getByRole("button", { name: "Turn the link off" }).click();
  await expect(page.getByRole("button", { name: "Get my calendar link" })).toBeVisible();

  // Drafting is switched on but has no key in tests: it says so instead of failing silently.
  await page.goto("/announcements");
  await page.getByRole("button", { name: "New announcement" }).click();
  await page.getByRole("button", { name: "Draft from notes with AI" }).click();
  await page.getByRole("textbox", { name: /^Your notes/ }).fill("Sports day Friday 9am, white shirts");
  await page.getByRole("button", { name: "Write the draft" }).click();
  await expect(page.getByText("Drafting isn't set up yet.")).toBeVisible();
  await page.keyboard.press("Escape");

  // Leave the demo school as it was.
  await page.goto("/settings/modules");
  for (const name of ["Developer API and webhooks", "AI drafting help"]) {
    const toggle = page.getByRole("switch", { name });
    await toggle.click({ force: true });
    await expect(toggle).not.toBeChecked();
  }
});
