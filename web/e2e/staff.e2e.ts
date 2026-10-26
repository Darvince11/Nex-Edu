import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";
import { CLASS_TEACHER } from "./totp";

const PROPRIETOR = { email: "director@greenfield.test" };

test("leaders keep staff records and take the staff register", async ({ page }) => {
  await signInToSchool(page, PROPRIETOR);
  const nav = page.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Staff", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Staff" })).toBeVisible();
  // Staff with a login are listed without anyone typing them in.
  await expect(page.getByText("Samuel Ofori")).toBeVisible();
  await expectAccessible(page, "staff");

  const stamp = Date.now().toString(36);
  await page.getByRole("button", { name: "Add staff member" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("First name").fill("Abena");
  await dialog.getByLabel("Last name").fill(`Cook${stamp}`);
  await dialog.getByLabel("Job title").fill("Cook");
  await dialog.getByRole("button", { name: "Add staff member" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("row").filter({ hasText: `Cook${stamp}` })).toContainText("No login");

  await nav.getByRole("link", { name: "Staff attendance" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Staff attendance" })).toBeVisible();
  await page.getByRole("button", { name: "Mark the rest present" }).click();
  await page.getByRole("button", { name: "Save register" }).click();
  await expect(page.getByText("Register saved")).toBeVisible();
  await expect(page.getByText("Everyone is marked.")).toBeVisible();
  await expectAccessible(page, "staff attendance");
});

test("a teacher asks for leave and the proprietor approves it", async ({ browser }) => {
  const teacherPage = await (await browser.newContext()).newPage();
  await signInToSchool(teacherPage, CLASS_TEACHER);
  await teacherPage
    .getByRole("navigation", { name: "School" })
    .first()
    .getByRole("link", { name: "Leave" })
    .click();
  await teacherPage.getByRole("button", { name: "Ask for leave" }).click();
  const ask = teacherPage.getByRole("dialog");
  await ask.getByLabel("Kind of leave").selectOption({ label: "Study leave" });
  // A weekday two weeks ahead: weekends aren't working days, so leave on one is refused.
  const day = new Date(Date.now() + 14 * 86_400_000);
  while (day.getUTCDay() === 0 || day.getUTCDay() === 6) day.setUTCDate(day.getUTCDate() + 1);
  const start = day.toISOString().slice(0, 10);
  await ask.getByLabel("First day").fill(start);
  await ask.getByLabel("Last day").fill(start);
  await ask.getByLabel("Reason (optional)").fill("Exam at the university");
  await ask.getByRole("button", { name: "Send request" }).click();
  await expect(ask).toBeHidden();
  await expect(teacherPage.getByText("Waiting for approval")).toBeVisible();
  await expectAccessible(teacherPage, "leave (teacher)");

  const page = await (await browser.newContext()).newPage();
  await signInToSchool(page, PROPRIETOR);
  await page.goto("/leave");
  const row = page.getByRole("row").filter({ hasText: "Exam at the university" });
  await row.getByRole("button", { name: "Decide" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(row).toHaveCount(0); // no longer waiting
  await expectAccessible(page, "leave (approver)");

  await teacherPage.reload();
  await expect(teacherPage.getByRole("row").filter({ hasText: "Exam at the university" })).toContainText(
    "Approved",
  );
});
