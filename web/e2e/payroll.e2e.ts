import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const TEACHER = { email: "teacher@greenfield.test" };

test("pay is set, the month worked out and approved, and the teacher sees their payslip", async ({
  browser,
}) => {
  test.slow(); // two people sign in
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  for (const name of ["Accounting", "Payroll"]) {
    const toggle = owner.getByRole("switch", { name });
    await toggle.click({ force: true });
    await expect(toggle).toBeChecked();
  }

  await nav.getByRole("link", { name: "Payroll" }).click();
  await owner.getByRole("tab", { name: "Tax and SSNIT rules" }).click();
  await expect(owner.getByText("Above GH₵50,000.00")).toBeVisible();
  await owner.getByRole("button", { name: "I've checked: use these rates" }).click();
  await expect(owner.getByText(/^Confirmed on/)).toBeVisible();
  await expectAccessible(owner, "payroll rules");

  await owner.getByRole("tab", { name: "Salaries" }).click();
  await owner.getByRole("button", { name: /^Set pay for .*Daniel Tetteh/ }).click();
  const form = owner.getByRole("dialog");
  await form.getByRole("textbox", { name: /^Basic salary/ }).fill("3000");
  await form.getByRole("button", { name: "Save pay" }).click();
  // GH₵3,000 basic: SSNIT 165.00, PAYE on 2,835.00 is 375.73, net 2,459.27.
  await expect(owner.getByRole("row").filter({ hasText: "Daniel Tetteh" })).toContainText("GH₵2,459.27");

  await owner.getByRole("tab", { name: "Monthly pay" }).click();
  await owner.getByRole("button", { name: "Work out this month's pay" }).click();
  const run = owner.getByRole("dialog");
  await expect(run.getByRole("row").filter({ hasText: "Daniel Tetteh" })).toContainText("GH₵375.73");
  await run.getByRole("button", { name: "Approve this month's pay" }).click();
  await run.getByRole("button", { name: "Mark as paid" }).click();
  await expect(run.getByRole("button", { name: "Mark as paid" })).toHaveCount(0);
  await expectAccessible(owner, "pay run");
  await owner.keyboard.press("Escape");

  const teacherContext = await browser.newContext();
  const teacher = await teacherContext.newPage();
  await signInToSchool(teacher, TEACHER);
  await teacher.goto("/payroll");
  await expect(teacher.getByRole("heading", { level: 1, name: "My payslips" })).toBeVisible();
  await expect(teacher.getByRole("row").nth(1)).toContainText("GH₵2,459.27");
  await expectAccessible(teacher, "my payslips");
  await teacherContext.close();

  // Leave the demo school as it was (the books keep the run).
  await nav.getByRole("link", { name: "Modules" }).click();
  for (const name of ["Payroll", "Accounting"]) {
    const toggle = owner.getByRole("switch", { name });
    await toggle.click({ force: true });
    await expect(toggle).not.toBeChecked();
  }
  await ownerContext.close();
});
