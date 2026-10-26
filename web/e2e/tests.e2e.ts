import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const TEACHER = { email: "teacher@greenfield.test" };

test("a teacher writes an online test and publishes it for the class", async ({ browser }) => {
  test.slow(); // two people sign in
  const title = `Fractions quiz ${Date.now().toString(36)}`;
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  for (const name of ["Homework and online learning", "Online tests"]) {
    const toggle = owner.getByRole("switch", { name });
    await toggle.click({ force: true });
    await expect(toggle).toBeChecked();
  }

  const teacherContext = await browser.newContext();
  const teacher = await teacherContext.newPage();
  await signInToSchool(teacher, TEACHER);
  await teacher.goto("/tests");
  await teacher.getByRole("button", { name: "New test" }).click();
  const form = teacher.getByRole("dialog");
  await form.getByRole("combobox", { name: "Class" }).selectOption({ label: "JHS 1 A" });
  const subject = form.getByRole("combobox", { name: "Subject" });
  await expect(subject.locator("option").nth(1)).toBeAttached();
  await subject.selectOption({ index: 1 });
  await form.getByRole("textbox", { name: "Title" }).fill(title);
  await form.getByRole("button", { name: "Next: add questions" }).click();

  const detail = teacher.getByRole("dialog");
  await detail.getByRole("textbox", { name: "Question" }).fill("1/2 + 1/4 = ?");
  await detail.getByRole("textbox", { name: "Choice 1" }).fill("3/4");
  await detail.getByRole("textbox", { name: "Choice 2" }).fill("2/6");
  await detail.getByRole("button", { name: "Save questions" }).click();
  await expect(detail.getByText("Questions saved.")).toBeVisible();
  await expectAccessible(teacher, "test questions");
  await detail.getByRole("button", { name: "Publish for the class" }).click();
  await expect(detail.getByRole("button", { name: /^Release results/ })).toBeVisible();
  await teacher.keyboard.press("Escape");
  await expect(teacher.getByRole("row").filter({ hasText: title })).toContainText("Published");
  await expectAccessible(teacher, "online tests");
  await teacherContext.close();

  // Leave the demo school as it was.
  await nav.getByRole("link", { name: "Modules" }).click();
  for (const name of ["Online tests", "Homework and online learning"]) {
    const toggle = owner.getByRole("switch", { name });
    await toggle.click({ force: true });
    await expect(toggle).not.toBeChecked();
  }
  await ownerContext.close();
});
