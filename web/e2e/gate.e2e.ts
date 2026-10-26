import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const PARENT = { email: "parent@greenfield.test" };

test("a parent lists who may collect, and the gate records the pick-up", async ({ browser }) => {
  test.slow(); // two people sign in
  const aunt = `Auntie ${Date.now().toString(36)}`;
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const gate = owner.getByRole("switch", { name: "Visitors and the gate" });
  await gate.click({ force: true });
  await expect(gate).toBeChecked();

  const parentContext = await browser.newContext();
  const parent = await parentContext.newPage();
  await signInToSchool(parent, PARENT);
  await parent.goto("/gate");
  await parent.getByRole("textbox", { name: "Name" }).first().fill(aunt);
  await parent.getByRole("textbox", { name: "Relationship" }).first().fill("Aunt");
  await parent.getByRole("button", { name: "Add person" }).first().click();
  await expect(parent.getByText(aunt)).toBeVisible();
  await expectAccessible(parent, "pick-up list");

  await nav.getByRole("link", { name: "Gate and pick-up" }).click();
  await owner.getByRole("textbox", { name: /^Visitor's name/ }).fill("Mr Boateng");
  await owner.getByRole("textbox", { name: "Here to" }).fill("Deliver textbooks");
  await owner.getByRole("button", { name: "Sign in" }).click();
  await expect(owner.getByText("Mr Boateng")).toBeVisible();

  await owner.getByRole("textbox", { name: /^Pupil/ }).fill("Akua");
  await owner.getByRole("list", { name: "Matching pupils" }).getByRole("button").first().click();
  await owner.getByRole("combobox", { name: "Who is collecting?" }).selectOption({ label: `${aunt} (Aunt)` });
  await owner.getByRole("button", { name: "Record pick-up" }).click();
  await expect(owner.getByText(`left with ${aunt}`)).toBeVisible();
  await owner.getByRole("button", { name: "Sign out Mr Boateng" }).click();
  await expect(owner.getByText("No visitors on site.")).toBeVisible();
  await expectAccessible(owner, "gate");

  await parent.reload();
  await expect(parent.getByRole("row").filter({ hasText: aunt })).toBeVisible();
  await parent.getByRole("button", { name: `Remove ${aunt}` }).click();
  await parentContext.close();

  // Leave the demo school as it was.
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "Visitors and the gate" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "Visitors and the gate" })).not.toBeChecked();
  await ownerContext.close();
});
