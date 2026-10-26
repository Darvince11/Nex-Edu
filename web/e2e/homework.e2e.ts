import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const TEACHER = { email: "teacher@greenfield.test" };
const PARENT = { email: "parent@greenfield.test" };

test("the class teacher sets homework and the parent sees it", async ({ browser }) => {
  test.slow(); // three people sign in
  const title = `Fractions ${Date.now().toString(36)}`;
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const lms = owner.getByRole("switch", { name: "Homework and online learning" });
  await lms.click({ force: true });
  await expect(lms).toBeChecked();

  const teacherContext = await browser.newContext();
  const teacher = await teacherContext.newPage();
  await signInToSchool(teacher, TEACHER);
  await teacher.goto("/homework");
  await teacher.getByRole("button", { name: "Set homework" }).click();
  const dialog = teacher.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Class" }).selectOption({ label: "JHS 1 A" });
  const subject = dialog.getByRole("combobox", { name: "Subject" });
  await expect(subject.locator("option").nth(1)).toBeAttached();
  await subject.selectOption({ index: 1 });
  await dialog.getByRole("textbox", { name: "Title" }).fill(title);
  await dialog.getByLabel("Due on").fill(new Date(Date.now() + 3 * 86_400_000).toISOString().slice(0, 10));
  await dialog.getByRole("spinbutton", { name: /^Marked out of/ }).fill("10");
  await expectAccessible(teacher, "set homework");
  await dialog.getByRole("button", { name: "Set homework" }).click();
  await expect(teacher.getByRole("row").filter({ hasText: title })).toContainText("JHS 1 A");
  await teacher.getByRole("button", { name: `Open ${title}` }).click();
  await expect(teacher.getByRole("dialog")).toContainText("Not handed in");
  await expectAccessible(teacher, "homework marking");
  await teacherContext.close();

  const parentContext = await browser.newContext();
  const parent = await parentContext.newPage();
  await signInToSchool(parent, PARENT);
  await parent.goto("/homework");
  await expect(parent.getByRole("heading", { name: title })).toBeVisible();
  await expect(parent.getByText("Not handed in yet.").first()).toBeVisible();
  await expectAccessible(parent, "homework for parents");
  await parentContext.close();

  // Leave the demo school as it was.
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "Homework and online learning" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "Homework and online learning" })).not.toBeChecked();
  await ownerContext.close();
});
