import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const TEACHER = { email: "teacher@greenfield.test" };

test("a learning support plan is written and the class teacher sees only the adjustments", async ({
  browser,
}) => {
  test.slow(); // two people sign in
  const secret = `Confidential report ${Date.now().toString(36)}`;
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const support = owner.getByRole("switch", { name: "Learning support" });
  await support.click({ force: true });
  await expect(support).toBeChecked();

  await nav.getByRole("link", { name: "Learning support" }).click();
  await owner.getByRole("button", { name: "New plan" }).click();
  const form = owner.getByRole("dialog");
  await form.getByRole("textbox", { name: "Find the pupil" }).fill("Akua");
  const pupil = form.getByRole("combobox", { name: "Pupil" });
  await expect(pupil.locator("option").nth(1)).toBeAttached();
  await pupil.selectOption({ index: 1 });
  await form.getByRole("checkbox", { name: "Sight" }).check();
  await form.getByRole("textbox", { name: /^Confidential summary/ }).fill(secret);
  await form
    .getByRole("textbox", { name: /^What every teacher should do/ })
    .fill("Front seat and large print.");
  await expectAccessible(owner, "support plan");
  await form.getByRole("button", { name: "Save plan" }).click();
  await expect(owner.getByText("Front seat and large print.")).toBeVisible();

  const teacherContext = await browser.newContext();
  const teacher = await teacherContext.newPage();
  await signInToSchool(teacher, TEACHER);
  await teacher.goto("/support");
  await expect(teacher.getByText("Front seat and large print.")).toBeVisible();
  await expect(teacher.getByText(secret)).toHaveCount(0);
  await expectAccessible(teacher, "support for teachers");
  await teacherContext.close();

  // Leave the demo school as it was: close the plan, then switch off.
  await owner.getByRole("button", { name: /^Open plan for .*Akua/ }).click();
  await owner.getByRole("dialog").getByRole("combobox", { name: "Plan" }).selectOption("closed");
  await owner.getByRole("dialog").getByRole("button", { name: "Save plan" }).click();
  await expect(owner.getByText("No learning support plans.")).toBeVisible();
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "Learning support" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "Learning support" })).not.toBeChecked();
  await ownerContext.close();
});
