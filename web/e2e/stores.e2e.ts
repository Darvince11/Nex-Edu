import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const TEACHER = { email: "teacher@greenfield.test" };

test("the stores take stock in, a teacher asks for some, and the stores issue it", async ({ browser }) => {
  test.slow(); // two people sign in
  const item = `Chalk ${Date.now().toString(36)}`;
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const stores = owner.getByRole("switch", { name: "Stores and inventory" });
  await stores.click({ force: true });
  await expect(stores).toBeChecked();

  await nav.getByRole("link", { name: "Stores" }).click();
  await owner.getByRole("button", { name: "Add an item" }).click();
  let dialog = owner.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "Name" }).fill(item);
  await dialog.getByRole("textbox", { name: /^Counted in/ }).fill("boxes");
  await dialog.getByRole("button", { name: "Add item" }).click();
  await owner.getByRole("button", { name: `Receive ${item}` }).click();
  dialog = owner.getByRole("dialog");
  await dialog.getByRole("spinbutton", { name: /^How many/ }).fill("10");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(owner.getByRole("row").filter({ hasText: item })).toContainText("10 boxes");
  await expectAccessible(owner, "stores stock");

  const teacherContext = await browser.newContext();
  const teacher = await teacherContext.newPage();
  await signInToSchool(teacher, TEACHER);
  await teacher.goto("/stores");
  await teacher
    .getByRole("combobox", { name: "What do you need?" })
    .selectOption({ label: `${item} (boxes)` });
  await teacher.getByRole("spinbutton", { name: "How many" }).fill("3");
  await teacher.getByRole("button", { name: "Ask the stores" }).click();
  await expect(teacher.getByRole("row").filter({ hasText: item })).toContainText("Waiting");
  await expectAccessible(teacher, "ask the stores");
  await teacherContext.close();

  await owner.getByRole("tab", { name: "Requests" }).click();
  await owner.getByRole("button", { name: new RegExp(`^Issue ${item} to`) }).click();
  await owner.getByRole("combobox", { name: "Show" }).selectOption({ label: "Issued" });
  await expect(owner.getByRole("row").filter({ hasText: item })).toContainText("Issued");
  await owner.getByRole("tab", { name: "Stock" }).click();
  await expect(owner.getByRole("row").filter({ hasText: item })).toContainText("7 boxes");

  // Leave the demo school as it was.
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "Stores and inventory" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "Stores and inventory" })).not.toBeChecked();
  await ownerContext.close();
});
