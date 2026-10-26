import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const PARENT = { email: "parent@greenfield.test" };

test("a bus route is set up, a pupil gets on, and the parent sees it", async ({ browser }) => {
  test.slow(); // two people sign in
  const stamp = Date.now().toString(36);
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const transport = owner.getByRole("switch", { name: "School transport" });
  await transport.click({ force: true });
  await expect(transport).toBeChecked();

  await nav.getByRole("link", { name: "Transport" }).click();
  await owner.getByRole("tab", { name: "Buses", exact: true }).click();
  await owner.getByRole("button", { name: "Add a bus" }).click();
  let dialog = owner.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "Name" }).fill(`Bus ${stamp}`);
  await dialog.getByRole("button", { name: "Save bus" }).click();
  await expect(owner.getByRole("row").filter({ hasText: `Bus ${stamp}` })).toBeVisible();

  await owner.getByRole("tab", { name: "Routes" }).click();
  await owner.getByRole("button", { name: "New route" }).click();
  dialog = owner.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "Route name" }).fill(`Kasoa ${stamp}`);
  await dialog.getByRole("combobox", { name: "Bus" }).selectOption({ label: `Bus ${stamp} (30 seats)` });
  await dialog.getByRole("textbox", { name: "Stop 1" }).fill("Old Barrier");
  await dialog.getByLabel("Pick-up").fill("06:45");
  await dialog.getByRole("button", { name: "Save route" }).click();
  const card = owner
    .locator("section")
    .filter({ has: owner.getByRole("heading", { name: new RegExp(`^Kasoa ${stamp}`) }) });
  await expect(card).toContainText("Old Barrier");

  await card.getByRole("button", { name: "Add a pupil" }).click();
  dialog = owner.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "Find the pupil" }).fill("Akua");
  const pupil = dialog.getByRole("combobox", { name: "Pupil" });
  await expect(pupil.locator("option").nth(1)).toBeAttached();
  await pupil.selectOption({ index: 1 });
  await dialog.getByRole("button", { name: "Add pupil" }).click();
  await expect(card.getByRole("heading")).toContainText("1 of 30 pupils");
  await expectAccessible(owner, "transport routes");

  await card.getByRole("button", { name: "Pick-up list" }).click();
  dialog = owner.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Trip" }).selectOption("morning");
  await dialog.getByRole("button", { name: /^Got on: .*Akua/ }).click();
  await expect(dialog.getByText("Got on", { exact: true }).first()).toBeVisible();
  await expectAccessible(owner, "pick-up list");

  const parentContext = await browser.newContext();
  const parent = await parentContext.newPage();
  await signInToSchool(parent, PARENT);
  await parent.goto("/transport");
  await expect(parent.getByText(`Kasoa ${stamp}`)).toBeVisible();
  await expect(parent.getByText("Today: morning Got on")).toBeVisible();
  await expectAccessible(parent, "school bus for parents");
  await parentContext.close();

  // Leave the demo school as it was.
  await owner.keyboard.press("Escape");
  await owner.getByRole("tab", { name: "Pupils on the buses" }).click();
  await owner
    .getByRole("button", { name: /^Take .*Akua.* off the bus/ })
    .first()
    .click();
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "School transport" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "School transport" })).not.toBeChecked();
  await ownerContext.close();
});
