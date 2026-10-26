import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";
import { HEAD } from "./totp";

const PARENT = { email: "parent@greenfield.test" };
const TEACHER = { email: "teacher@greenfield.test" };

test("a parent writes to the class teacher, who reads it and replies", async ({ browser }) => {
  const subject = `Homework ${Date.now().toString(36)}`;

  const parentContext = await browser.newContext();
  const parent = await parentContext.newPage();
  await signInToSchool(parent, PARENT);
  await parent
    .getByRole("navigation", { name: "School" })
    .first()
    .getByRole("link", { name: /^Messages/ })
    .click();
  await expect(parent.getByRole("heading", { level: 1, name: "Messages" })).toBeVisible();
  await parent.getByRole("button", { name: "New message" }).click();
  const dialog = parent.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Which child is it about?" }).selectOption({ index: 1 });
  const to = dialog.getByRole("combobox", { name: "To" });
  await expect(to.locator("option", { hasText: "Daniel Tetteh — Class teacher" })).toBeAttached();
  await to.selectOption({ label: "Daniel Tetteh — Class teacher" });
  await dialog.getByRole("textbox", { name: "Subject" }).fill(subject);
  await dialog
    .getByRole("textbox", { name: "Message" })
    .fill("Please could you send this week's homework again?");
  await expectAccessible(parent, "new message");
  await dialog.getByRole("button", { name: "Send" }).click();
  await expect(parent.getByRole("heading", { level: 2, name: subject })).toBeVisible();
  await expect(parent.getByText("Please could you send this week's homework again?")).toBeVisible();
  await parentContext.close();

  const teacherContext = await browser.newContext();
  const teacher = await teacherContext.newPage();
  await signInToSchool(teacher, TEACHER);
  await teacher.goto("/messages");
  const row = teacher.getByRole("button", { name: new RegExp(subject) });
  await expect(row).toContainText("New");
  await row.click();
  await teacher.getByRole("textbox", { name: "Reply" }).fill("Of course, I'll send it home today.");
  await teacher.getByRole("button", { name: "Send" }).click();
  await expect(teacher.getByText("Of course, I'll send it home today.")).toBeVisible();
  await expectAccessible(teacher, "conversation");
  await teacherContext.close();
});

test("the head adds a PTA meeting that shows on the calendar", async ({ page }) => {
  await signInToSchool(page, HEAD);
  await page
    .getByRole("navigation", { name: "School" })
    .first()
    .getByRole("link", { name: "Calendar" })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: "Calendar" })).toBeVisible();
  const title = `PTA meeting ${Date.now().toString(36)}`;
  await page.getByRole("button", { name: "Add to calendar" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "What's happening" }).fill(title);
  await dialog.getByRole("combobox", { name: "Kind" }).selectOption({ label: "Meeting" });
  await dialog.getByRole("textbox", { name: /^Where/ }).fill("School hall");
  await dialog.getByRole("button", { name: "Save" }).click();
  const entry = page.getByRole("listitem").filter({ hasText: title });
  await expect(entry).toContainText("School hall");
  await expectAccessible(page, "calendar");

  await page.getByRole("button", { name: "Next month" }).click();
  await page.getByRole("button", { name: "Previous month" }).click();
  await entry.getByRole("button", { name: `Change ${title}` }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
  await expect(entry).toHaveCount(0);
});
