import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };
const TEACHER = { email: "teacher@greenfield.test" };

test("a teacher books the hall and reports a repair, which a leader closes", async ({ browser }) => {
  test.slow(); // two people sign in
  const stamp = Date.now().toString(36);
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signInToSchool(owner, PROPRIETOR);
  const nav = owner.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const facilities = owner.getByRole("switch", { name: "Facilities and repairs" });
  await facilities.click({ force: true });
  await expect(facilities).toBeChecked();
  await nav.getByRole("link", { name: "Facilities" }).click();
  await owner.getByRole("tab", { name: "Rooms" }).click();
  await owner.getByRole("button", { name: "Add a room" }).click();
  const room = owner.getByRole("dialog");
  await room.getByRole("textbox", { name: "Name" }).fill(`Hall ${stamp}`);
  await room.getByRole("combobox", { name: "Kind" }).selectOption({ label: "Hall" });
  await room.getByRole("button", { name: "Save" }).click();
  await expect(owner.getByRole("row").filter({ hasText: `Hall ${stamp}` })).toBeVisible();

  const teacherContext = await browser.newContext();
  const teacher = await teacherContext.newPage();
  await signInToSchool(teacher, TEACHER);
  await teacher.goto("/facilities");
  await teacher.getByRole("button", { name: "Book a room" }).click();
  let dialog = teacher.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Room" }).selectOption({ label: `Hall ${stamp}` });
  await dialog.getByLabel("From").fill("10:00");
  await dialog.getByLabel("Until").fill("11:00");
  await dialog.getByRole("textbox", { name: "What for" }).fill("Choir practice");
  await dialog.getByRole("button", { name: "Book" }).click();
  const card = teacher
    .locator("section")
    .filter({ has: teacher.getByRole("heading", { name: `Hall ${stamp}` }) });
  await expect(card).toContainText("Choir practice");
  await expectAccessible(teacher, "room bookings");

  await teacher.getByRole("tab", { name: "Repairs" }).click();
  await teacher.getByRole("button", { name: "Report a repair" }).click();
  dialog = teacher.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "What needs fixing" }).fill(`Broken fan ${stamp}`);
  await dialog.getByRole("combobox", { name: "Room" }).selectOption({ label: `Hall ${stamp}` });
  await dialog.getByRole("button", { name: "Report" }).click();
  await expect(teacher.getByRole("row").filter({ hasText: `Broken fan ${stamp}` })).toContainText("Reported");
  await teacherContext.close();

  await owner.getByRole("tab", { name: "Repairs" }).click();
  await owner.getByRole("button", { name: `Update Broken fan ${stamp}` }).click();
  dialog = owner.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Status" }).selectOption({ label: "Fixed" });
  await dialog.getByRole("textbox", { name: /^What was done/ }).fill("New fan fitted.");
  await dialog.getByRole("button", { name: "Save" }).click();
  await owner.getByRole("combobox", { name: "Show" }).selectOption({ label: "Fixed" });
  await expect(owner.getByRole("row").filter({ hasText: `Broken fan ${stamp}` })).toContainText(
    "New fan fitted.",
  );
  await expectAccessible(owner, "repairs");

  // Leave the demo school as it was.
  await nav.getByRole("link", { name: "Modules" }).click();
  await owner.getByRole("switch", { name: "Facilities and repairs" }).click({ force: true });
  await expect(owner.getByRole("switch", { name: "Facilities and repairs" })).not.toBeChecked();
  await ownerContext.close();
});
