import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const PARENT = { email: "parent@greenfield.test" };

test("a sick bay visit ends with the child sent home, and the parent sees it", async ({ browser }) => {
  test.slow(); // two people sign in
  const complaint = `Stomach ache ${Date.now().toString(36)}`;
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const clinic = owner.getByRole("switch", { name: "Sick bay" });
  await clinic.click({ force: true });
  await expect(clinic).toBeChecked();

  await nav.getByRole("link", { name: "Sick bay" }).click();
  await owner.getByRole("button", { name: "New visit" }).click();
  const form = owner.getByRole("dialog");
  await form.getByRole("textbox", { name: "Find the pupil" }).fill("Akua");
  const pupil = form.getByRole("combobox", { name: "Pupil" });
  await expect(pupil.locator("option").nth(1)).toBeAttached();
  await pupil.selectOption({ index: 1 });
  await expect(form.getByText(/medical notes/i)).toBeVisible();
  await form.getByRole("textbox", { name: "What's wrong" }).fill(complaint);
  await form.getByRole("textbox", { name: /^Temperature/ }).fill("37.9");
  await expectAccessible(owner, "new sick bay visit");
  await form.getByRole("button", { name: "Save visit" }).click();

  const now = owner
    .locator("section")
    .filter({ has: owner.getByRole("heading", { name: "In the sick bay now" }) });
  await expect(now).toContainText(complaint);
  await now
    .getByRole("listitem")
    .filter({ hasText: complaint })
    .getByRole("button", { name: "Finish visit" })
    .click();
  const finish = owner.getByRole("dialog");
  await finish.getByRole("combobox", { name: "How did it end?" }).selectOption({ label: "Sent home" });
  await expect(finish.getByText("The parents will be told in their inbox.")).toBeVisible();
  await finish.getByRole("button", { name: "Finish visit" }).click();
  await expect(owner.getByRole("row").filter({ hasText: complaint })).toContainText("Parents told");
  await expectAccessible(owner, "sick bay");

  const parentContext = await browser.newContext();
  const parent = await parentContext.newPage();
  await signInToSchool(parent, PARENT);
  await parent.goto("/sick-bay");
  await expect(parent.getByRole("row").filter({ hasText: complaint })).toContainText("Sent home");
  await expectAccessible(parent, "sick bay for parents");
  await parentContext.close();

  // Leave the demo school as it was.
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "Sick bay" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "Sick bay" })).not.toBeChecked();
  await ownerContext.close();
});
