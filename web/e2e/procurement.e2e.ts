import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const TEACHER = { email: "teacher@greenfield.test" };

test("a teacher asks to buy, the proprietor approves and orders, and the supplier is paid", async ({
  browser,
}) => {
  test.slow(); // two people sign in
  const stamp = Date.now().toString(36);
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  for (const name of ["Stores and inventory", "Accounting", "Procurement"]) {
    const toggle = owner.getByRole("switch", { name });
    await toggle.click({ force: true });
    await expect(toggle).toBeChecked();
  }
  await nav.getByRole("link", { name: "Stores" }).click();
  await owner.getByRole("tab", { name: "Suppliers" }).click();
  await owner.getByRole("textbox", { name: "Supplier" }).fill(`Accra Stationers ${stamp}`);
  await owner.getByRole("button", { name: "Add supplier" }).click();
  await expect(owner.getByRole("row").filter({ hasText: `Accra Stationers ${stamp}` })).toBeVisible();

  const teacherContext = await browser.newContext();
  const teacher = await teacherContext.newPage();
  await signInToSchool(teacher, TEACHER);
  await teacher.goto("/procurement");
  await teacher.getByRole("button", { name: "Ask to buy something" }).click();
  const form = teacher.getByRole("dialog");
  await form.getByRole("textbox", { name: "What it's for" }).fill(`Science lab ${stamp}`);
  await form.getByRole("textbox", { name: "Item" }).fill("Test tubes");
  await form.getByRole("textbox", { name: "How many" }).fill("20");
  await form.getByRole("textbox", { name: /^Price each/ }).fill("5");
  await expect(form.getByText("Total: GH₵100.00")).toBeVisible();
  await expectAccessible(teacher, "ask to buy");
  await form.getByRole("button", { name: "Send for approval" }).click();
  await expect(teacher.getByRole("row").filter({ hasText: `Science lab ${stamp}` })).toContainText(
    "Waiting for the head teacher",
  );
  await teacherContext.close();

  await nav.getByRole("link", { name: "Procurement" }).click();
  const row = owner.getByRole("row").filter({ hasText: `Science lab ${stamp}` });
  await row.getByRole("button", { name: /^Approve/ }).click();
  await owner.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(row).toContainText("Approved");
  await row.getByRole("button", { name: /^Order/ }).click();
  const order = owner.getByRole("dialog");
  await order
    .getByRole("combobox", { name: /^Supplier/ })
    .selectOption({ label: `Accra Stationers ${stamp}` });
  await order
    .getByRole("combobox", { name: "Spent on" })
    .selectOption({ label: "Teaching and learning materials" });
  await order.getByRole("button", { name: "Send order" }).click();
  await expect(row).toContainText("Ordered");

  await owner.getByRole("tab", { name: "Orders" }).click();
  const po = owner.getByRole("row").filter({ hasText: `Science lab ${stamp}` });
  await po.getByRole("button", { name: /^Goods in/ }).click();
  await expect(po).toContainText("Goods received");
  await po.getByRole("button", { name: /^Pay / }).click();
  await expect(po).toContainText("Paid");
  await expectAccessible(owner, "orders");

  // Leave the demo school as it was.
  await nav.getByRole("link", { name: "Modules" }).click();
  for (const name of ["Procurement", "Accounting", "Stores and inventory"]) {
    const toggle = owner.getByRole("switch", { name });
    await toggle.click({ force: true });
    await expect(toggle).not.toBeChecked();
  }
  await ownerContext.close();
});
