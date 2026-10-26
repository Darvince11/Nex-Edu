import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const PARENT = { email: "parent@greenfield.test" };

test("a pupil gets a bed, roll call is taken, and the parent's exeat is approved", async ({ browser }) => {
  test.slow(); // two people sign in
  const name = `Aggrey ${Date.now().toString(36)}`;
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const boarding = owner.getByRole("switch", { name: "Boarding" });
  await boarding.click({ force: true });
  await expect(boarding).toBeChecked();

  await nav.getByRole("link", { name: "Boarding" }).click();
  await owner.getByRole("tab", { name: "Houses and rooms" }).click();
  await owner.getByRole("textbox", { name: "House name" }).fill(name);
  await owner.getByRole("button", { name: "Add house" }).click();
  await expect(owner.getByText(name).first()).toBeVisible();
  await owner.getByRole("combobox", { name: "House" }).selectOption({ label: name });
  await owner.getByRole("textbox", { name: "Room" }).fill("Room 1");
  await owner.getByRole("button", { name: "Add room" }).click();
  await expect(owner.getByText(/0 of 4 beds used/)).toBeVisible();

  await owner.getByRole("tab", { name: "Beds" }).click();
  const houseSelect = owner.getByRole("combobox", { name: "House" });
  if (await houseSelect.count()) await houseSelect.selectOption({ label: name });
  await owner.getByRole("textbox", { name: "Find the pupil" }).fill("Akua");
  const pupil = owner.getByRole("combobox", { name: "Pupil" });
  await expect(pupil.locator("option").nth(1)).toBeAttached();
  await pupil.selectOption({ index: 1 });
  await owner.getByRole("combobox", { name: "Room" }).selectOption({ index: 1 });
  await owner.getByRole("button", { name: "Give bed" }).click();
  await expect(owner.getByRole("row").filter({ hasText: "Akua" })).toContainText("Room 1");

  await owner.getByRole("tab", { name: "Roll call" }).click();
  await owner.getByRole("combobox", { name: "Session" }).selectOption("evening");
  await owner.getByRole("button", { name: /roll call$/ }).click();
  await expect(owner.getByText("Everyone accounted for.")).toBeVisible();
  await expectAccessible(owner, "roll call");

  const parentContext = await browser.newContext();
  const parent = await parentContext.newPage();
  await signInToSchool(parent, PARENT);
  await parent.goto("/boarding");
  await expect(parent.getByRole("heading", { name: new RegExp(name) })).toBeVisible();
  const soon = new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10);
  await parent.getByLabel("Leaving on").fill(soon);
  await parent.getByLabel("Back on").fill(soon);
  await parent.getByRole("textbox", { name: "Why" }).fill("Family wedding");
  await parent.getByRole("button", { name: "Ask" }).click();
  await expect(parent.getByRole("row").filter({ hasText: "Family wedding" })).toContainText(
    "Waiting for approval",
  );
  await expectAccessible(parent, "boarding for parents");
  await parentContext.close();

  await owner.getByRole("tab", { name: "Exeats" }).click();
  await owner.getByRole("button", { name: /^Approve exeat for .*Akua/ }).click();
  await owner.getByRole("combobox", { name: "Show" }).selectOption({ label: "Approved" });
  await expect(owner.getByRole("row").filter({ hasText: "Family wedding" })).toContainText("Approved");

  // Leave the demo school as it was.
  await owner.getByRole("tab", { name: "Beds" }).click();
  await owner
    .getByRole("button", { name: /no longer boards$/ })
    .first()
    .click();
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "Boarding" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "Boarding" })).not.toBeChecked();
  await ownerContext.close();
});
