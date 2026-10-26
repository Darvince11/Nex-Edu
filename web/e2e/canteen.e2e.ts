import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const PARENT = { email: "parent@greenfield.test" };

test("a wallet is topped up, a meal is sold, and the parent sees the balance", async ({ browser }) => {
  test.slow(); // two people sign in
  const dish = `Waakye ${Date.now().toString(36)}`;
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const canteen = owner.getByRole("switch", { name: "Canteen" });
  await canteen.click({ force: true });
  await expect(canteen).toBeChecked();

  await nav.getByRole("link", { name: "Canteen" }).click();
  await owner.getByRole("tab", { name: "Menu" }).click();
  await owner.getByRole("button", { name: "Add to the menu" }).click();
  const form = owner.getByRole("dialog");
  await form.getByRole("textbox", { name: "Name" }).fill(dish);
  await form.getByRole("textbox", { name: /^Price/ }).fill("7.50");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(owner.getByRole("row").filter({ hasText: dish })).toContainText("GH₵7.50");

  await owner.getByRole("tab", { name: "Till" }).click();
  await owner.getByRole("textbox", { name: /^Find the pupil/ }).fill("Akua");
  await owner.getByRole("list", { name: "Matching pupils" }).getByRole("button").first().click();
  await owner.getByRole("textbox", { name: /^Cash top-up/ }).fill("20");
  await owner.getByRole("button", { name: "Add money" }).click();
  // The pupil's balance on the till (the day's totals above can show the same amount).
  const till = owner.getByRole("tabpanel");
  await expect(till.getByText("GH₵20.00", { exact: true })).toBeVisible();
  await owner.getByRole("button", { name: `Add ${dish}` }).click();
  await owner.getByRole("button", { name: "Charge GH₵7.50" }).click();
  await expect(till.getByText("GH₵12.50", { exact: true })).toBeVisible();
  await expectAccessible(owner, "canteen till");

  const parentContext = await browser.newContext();
  const parent = await parentContext.newPage();
  await signInToSchool(parent, PARENT);
  await parent.goto("/canteen");
  await expect(parent.getByText("GH₵12.50").first()).toBeVisible();
  await expect(parent.getByText(`1 × ${dish}`)).toBeVisible();
  await expectAccessible(parent, "canteen for parents");
  await parentContext.close();

  // Leave the demo school as it was: give the money back, then switch off.
  await owner.getByRole("button", { name: "Refund" }).click();
  const refund = owner.getByRole("dialog");
  await refund.getByRole("textbox", { name: /^Amount/ }).fill("12.50");
  await refund.getByRole("textbox", { name: "Why" }).fill("End of test");
  await refund.getByRole("button", { name: "Give money back" }).click();
  await expect(owner.getByText("GH₵0.00", { exact: true })).toBeVisible();
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "Canteen" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "Canteen" })).not.toBeChecked();
  await ownerContext.close();
});
