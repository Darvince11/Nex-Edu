import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const PARENT = { email: "parent@greenfield.test" };

test("a club is set up, a pupil joins, and their parent sees it", async ({ browser }) => {
  test.slow(); // two people sign in
  const name = `Football ${Date.now().toString(36)}`;
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const clubs = owner.getByRole("switch", { name: "Clubs and sports" });
  await clubs.click({ force: true });
  await expect(clubs).toBeChecked();

  await nav.getByRole("link", { name: "Clubs and sports" }).click();
  await owner.getByRole("button", { name: "New club" }).click();
  const dialog = owner.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "Name" }).fill(name);
  await dialog.getByRole("combobox", { name: "Kind" }).selectOption({ label: "Sports team" });
  await dialog.getByRole("button", { name: "Add club" }).click();
  await owner.getByRole("link", { name: new RegExp(`^${name}`) }).click();
  await expect(owner.getByRole("heading", { level: 1, name })).toBeVisible();

  await owner.getByRole("combobox", { name: "Add a patron" }).selectOption({ label: "Daniel Tetteh" });
  await owner
    .locator("section")
    .filter({ hasText: "Patrons" })
    .getByRole("button", { name: "Add", exact: true })
    .click();
  await expect(owner.getByRole("button", { name: "Remove Daniel Tetteh as patron" })).toBeVisible();

  await owner.getByRole("textbox", { name: "Find a pupil" }).fill("Akua");
  const pupil = owner.getByRole("combobox", { name: "Pupil" });
  await expect(pupil.locator("option").nth(1)).toBeAttached();
  await pupil.selectOption({ index: 1 });
  await owner.getByRole("textbox", { name: /^Role/ }).fill("Captain");
  await owner.getByRole("button", { name: "Add member" }).click();
  await expect(owner.getByRole("row").filter({ hasText: "Captain" })).toContainText("Akua");

  const soon = new Date(Date.now() + 3 * 86_400_000).toISOString().slice(0, 10);
  await owner
    .locator("section")
    .filter({ hasText: "Coming up" })
    .getByRole("button", { name: "Add", exact: true })
    .click();
  const add = owner.getByRole("dialog");
  await add.getByRole("textbox", { name: "What" }).fill("Inter-schools match");
  await add.getByRole("combobox", { name: "Kind" }).selectOption({ label: "Match or competition" });
  await add.getByLabel("Date").fill(soon);
  await add.getByRole("textbox", { name: /^Against/ }).fill("Royal Heights");
  await add.getByRole("button", { name: "Add", exact: true }).click();
  await expect(owner.getByText("Inter-schools match").first()).toBeVisible();
  await expectAccessible(owner, "club");

  const parentContext = await browser.newContext();
  const parent = await parentContext.newPage();
  await signInToSchool(parent, PARENT);
  await parent.goto("/clubs");
  await expect(parent.getByRole("link", { name: new RegExp(`^${name}`) })).toContainText("Akua is a member");
  await expect(parent.getByRole("heading", { name: "Coming up for your family" })).toBeVisible();
  await expectAccessible(parent, "clubs for parents");
  await parentContext.close();

  // Leave the demo school as it was.
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "Clubs and sports" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "Clubs and sports" })).not.toBeChecked();
  await ownerContext.close();
});
