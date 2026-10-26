import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const BURSAR = { email: "bursar@greenfield.test" };

test("the proprietor makes a role, gives it to the bursar, and the bursar gets its pages", async ({
  browser,
}) => {
  const name = `Records officer ${Date.now().toString(36)}`;
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  await owner
    .getByRole("navigation", { name: "School" })
    .first()
    .getByRole("link", { name: "Custom roles" })
    .click();
  await expect(owner.getByRole("heading", { level: 1, name: "Custom roles" })).toBeVisible();
  await owner.getByRole("button", { name: "New role" }).click();
  const dialog = owner.getByRole("dialog");
  await dialog.getByRole("textbox", { name: /^Name/ }).fill(name);
  await dialog.getByRole("checkbox", { name: "Run class lists, attendance and results reports" }).check();
  await expectAccessible(owner, "custom role form");
  await dialog.getByRole("button", { name: "Save role" }).click();

  const card = owner.locator("section").filter({ has: owner.getByRole("heading", { name }) });
  await card
    .getByRole("combobox", { name: `Give ${name} to` })
    .selectOption({ label: "Gifty Amoah (bursar@greenfield.test)" });
  await card.getByRole("button", { name: "Give role" }).click();
  await expect(card.getByText("bursar@greenfield.test")).toBeVisible();
  await expectAccessible(owner, "custom roles");

  const bursarContext = await browser.newContext();
  const bursar = await bursarContext.newPage();
  await signInToSchool(bursar, BURSAR);
  await bursar
    .getByRole("navigation", { name: "School" })
    .first()
    .getByRole("link", { name: "Reports", exact: true })
    .click();
  await expect(bursar.getByRole("heading", { name: "Class list: All classes" })).toBeVisible();
  await bursarContext.close();

  // Tidy up so other tests see the demo school as it was.
  await card.getByRole("button", { name: "Change" }).click();
  await owner.getByRole("dialog").getByRole("button", { name: "Delete role" }).click();
  await owner
    .getByRole("dialog")
    .getByRole("button", { name: /^Delete for/ })
    .click();
  await expect(owner.getByRole("heading", { name })).toHaveCount(0);
  await ownerContext.close();
});
