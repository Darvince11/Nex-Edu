import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const TEACHER = { email: "teacher@greenfield.test" };

test("leaders see every class, drill into one, and download reports", async ({ page }) => {
  await signInToSchool(page, PROPRIETOR);
  await page
    .getByRole("navigation", { name: "School" })
    .first()
    .getByRole("link", { name: "Reports", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: "Reports" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Class list: All classes" })).toBeVisible();
  await expectAccessible(page, "class lists");

  await page.getByRole("tab", { name: "Attendance" }).click();
  await expect(page.getByRole("heading", { name: "Attendance: all classes" })).toBeVisible();
  await page.getByRole("button", { name: "JHS 1 A" }).first().click();
  await expect(page.getByRole("heading", { name: "Attendance: JHS 1 A" })).toBeVisible();
  await expectAccessible(page, "attendance report");

  const csv = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download spreadsheet" }).click();
  expect((await csv).suggestedFilename()).toBe("attendance.csv");

  await page.getByRole("tab", { name: "Results" }).click();
  await expect(page.getByRole("heading", { name: "Results: JHS 1 A" })).toBeVisible();
  const pdf = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF" }).click();
  expect((await pdf).suggestedFilename()).toBe("results.pdf");
});

test("a class teacher's reports cover only their own class", async ({ page }) => {
  await signInToSchool(page, TEACHER);
  await page.goto("/reports");
  await expect(page.getByRole("heading", { name: "Class list: JHS 1 A" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Class" }).locator("option")).toHaveText(["JHS 1 A"]);
});
