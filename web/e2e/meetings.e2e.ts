import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const PARENT = { email: "parent@greenfield.test" };

test("a meeting day is set up, opened, and a parent books a time", async ({ browser }) => {
  test.slow(); // two people sign in
  const title = `Parent meetings ${Date.now().toString(36)}`;
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const meetings = owner.getByRole("switch", { name: "Parent meetings" });
  await meetings.click({ force: true });
  await expect(meetings).toBeChecked();

  await nav.getByRole("link", { name: "Parent meetings" }).click();
  await owner.getByRole("button", { name: "New meeting day" }).click();
  const dialog = owner.getByRole("dialog");
  await dialog.getByRole("textbox", { name: /^Name/ }).fill(title);
  await dialog.getByLabel("Date").fill(new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10));
  await dialog.getByRole("combobox", { name: "Each meeting lasts" }).selectOption({ label: "30 minutes" });
  await dialog.getByLabel("From").fill("09:00");
  await dialog.getByLabel("Until").fill("10:00");
  await dialog.getByRole("button", { name: "Create meeting day" }).click();
  await expect(owner.getByRole("heading", { level: 1, name: title })).toBeVisible();

  const teacher = owner.getByRole("combobox", { name: "Teacher taking part" });
  const value = await teacher.locator("option", { hasText: "Daniel Tetteh" }).getAttribute("value");
  await teacher.selectOption(value ?? "");
  await owner.getByRole("button", { name: "Add teacher" }).click();
  await expect(owner.getByRole("heading", { name: /^Daniel Tetteh/ })).toBeVisible();
  await owner.getByRole("button", { name: "Open bookings and tell parents" }).click();
  await expect(owner.getByText("Bookings are open.")).toBeVisible();
  await expectAccessible(owner, "meeting day set-up");

  const parentContext = await browser.newContext();
  const parent = await parentContext.newPage();
  await signInToSchool(parent, PARENT);
  await parent.goto("/meetings");
  await parent.getByRole("link", { name: new RegExp(`^${title}`) }).click();
  await parent.getByRole("button", { name: /^Book 09:00 with Daniel Tetteh/ }).click();
  await expect(parent.getByText("Booked 09:00")).toBeVisible();
  await expectAccessible(parent, "booking");
  await parentContext.close();

  await owner.reload();
  const row = owner.getByRole("row").filter({ hasText: "09:00" });
  await expect(row).toContainText("Akua");
  // Leave the demo school as it was.
  await row.getByRole("button", { name: "Cancel 09:00" }).click();
  await expect(row).toContainText("Free");
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "Parent meetings" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "Parent meetings" })).not.toBeChecked();
  await ownerContext.close();
});
