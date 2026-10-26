import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const TEACHER = { email: "teacher@greenfield.test" };
const PARENT = { email: "parent@greenfield.test" };

test("a teacher reports, a leader tells the parent, and the parent sees only the summary", async ({
  browser,
}) => {
  test.slow(); // three people sign in
  const staffNote = `Staff note ${Date.now().toString(36)}`;
  const summary = `Akua was late to class three times this week ${Date.now().toString(36)}.`;

  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const discipline = owner.getByRole("switch", { name: "Behaviour and discipline" });
  await discipline.click({ force: true });
  await expect(discipline).toBeChecked();

  const teacherContext = await browser.newContext();
  const teacher = await teacherContext.newPage();
  await signInToSchool(teacher, TEACHER);
  await teacher.goto("/behaviour");
  await teacher.getByRole("button", { name: "Report an incident" }).click();
  const form = teacher.getByRole("dialog");
  await form.getByRole("textbox", { name: "Find the pupil" }).fill("Akua");
  const pupil = form.getByRole("combobox", { name: "Pupil" });
  await expect(pupil.locator("option").nth(1)).toBeAttached();
  await pupil.selectOption({ index: 1 });
  await form.getByRole("combobox", { name: "Kind" }).selectOption({ label: "Lateness" });
  await form.getByRole("textbox", { name: /^What happened/ }).fill(staffNote);
  await expectAccessible(teacher, "report incident");
  await form.getByRole("button", { name: "Report" }).click();
  await expect(teacher.getByRole("row").filter({ hasText: "Akua" }).first()).toContainText("Lateness");
  await teacherContext.close();

  await nav.getByRole("link", { name: "Behaviour" }).click();
  await owner
    .getByRole("button", { name: /^Open incident for .*Akua/ })
    .first()
    .click();
  const detail = owner.getByRole("dialog");
  await expect(detail).toContainText(staffNote);
  await detail.getByRole("combobox", { name: "Action" }).selectOption({ label: "Warning" });
  await detail.getByRole("button", { name: "Record action" }).click();
  await expect(detail.getByRole("listitem").filter({ hasText: "Warning" })).toBeVisible();
  await detail.getByRole("textbox", { name: /^What parents will read/ }).fill(summary);
  await detail.getByRole("button", { name: "Send to parents" }).click();
  await expect(detail.getByText(/^Told on/)).toBeVisible();
  await expectAccessible(owner, "incident");

  const parentContext = await browser.newContext();
  const parent = await parentContext.newPage();
  await signInToSchool(parent, PARENT);
  await parent.goto("/behaviour");
  await expect(parent.getByText(summary)).toBeVisible();
  await expect(parent.getByText(staffNote)).toHaveCount(0);
  await expectAccessible(parent, "behaviour for parents");
  await parentContext.close();

  // Leave the demo school as it was.
  await owner.keyboard.press("Escape");
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "Behaviour and discipline" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "Behaviour and discipline" })).not.toBeChecked();
  await ownerContext.close();
});
