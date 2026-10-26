import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";
import { CLASS_TEACHER, HEAD } from "./totp";

const PARENT = { email: "parent@greenfield.test" };

test("the top bar has the profile and sign out, and nothing else to pick", async ({ page }) => {
  await signInToSchool(page, PARENT);
  const bar = page.getByRole("banner");
  await expect(bar.getByRole("link", { name: "Your profile (Akosua Mensah)" })).toBeVisible();
  await expect(bar.getByRole("button", { name: "Sign out" })).toBeVisible();
  await expect(bar.getByRole("link", { name: /Switch school|Inbox/ })).toHaveCount(0);

  await bar.getByRole("link", { name: /Your profile/ }).click();
  await expect(page).toHaveURL(/\/profile$/);
  await expect(page.getByRole("heading", { name: "Your profile" })).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveValue("parent@greenfield.test");
  await expect(page.getByLabel("Email")).toHaveAttribute("readonly", "");
  await expectAccessible(page, "profile");

  const phone = page.getByLabel("Phone");
  await phone.fill("020 555 0101");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  await expect(phone).toHaveValue("+233205550101");
  await phone.fill("024 412 3456");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(phone).toHaveValue("+233244123456");

  await bar.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test("dark mode is a switch, remembered on this device", async ({ page }) => {
  await signInToSchool(page, PARENT);
  const html = page.locator("html");
  await expect(html).not.toHaveClass(/dark/); // light is the default
  await page.getByRole("button", { name: "Switch to dark mode" }).click();
  await expect(html).toHaveClass(/dark/);
  await page.reload();
  await expect(html).toHaveClass(/dark/);
  await expect(page.getByRole("button", { name: "Switch to light mode" })).toBeVisible();
  await expectAccessible(page, "dashboard (dark)");

  // The profile's appearance setting and the top-bar switch agree.
  await page.goto("/profile");
  await page.getByText("Light", { exact: true }).click();
  await expect(html).not.toHaveClass(/dark/);
  await expect(page.getByRole("button", { name: "Switch to dark mode" })).toBeVisible();
});

test("the head teacher runs the school, enters no scores, and adds and blocks staff", async ({ page }) => {
  await signInToSchool(page, HEAD, Date.now() + 30_000);
  const nav = page.getByRole("navigation", { name: "School" }).first();
  await expect(nav.getByRole("link", { name: "Score entry" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Results and report cards" })).toBeVisible();

  // Charts: pupils per class, with a table view of the same figures.
  const enrolment = page.getByRole("region", { name: "Pupils by class" });
  await expect(enrolment.getByText("JHS 1 A")).toBeVisible();
  await enrolment.getByRole("button", { name: "Table" }).click();
  await expect(enrolment.getByRole("columnheader", { name: "Girls" })).toBeVisible();
  await expect(page.getByRole("slider", { name: "Attendance" })).toBeVisible();
  await expectAccessible(page, "head teacher dashboard with charts");

  await nav.getByRole("link", { name: "Staff and access" }).click();
  await expect(page.getByText(/You add and block teachers and support staff/)).toBeVisible();

  // Inviting: teaching and support staff (and families), never leadership or finance roles.
  await page.getByRole("button", { name: "Invite someone" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Role").locator("option")).toHaveText([
    "Teacher",
    "Class teacher",
    "Librarian",
    "Hostel warden",
    "Driver",
    "School nurse",
    "Store keeper",
    "Gate officer",
    "Parent / guardian",
    "Student",
  ]);
  const stamp = Date.now().toString(36);
  await dialog.getByLabel("First name").fill("Yaw");
  await dialog.getByLabel("Email").fill(`librarian-${stamp}@greenfield.test`);
  await dialog.getByLabel("Role").selectOption({ label: "Librarian" });
  await dialog.getByRole("button", { name: "Send invitation" }).click();
  await expect(dialog).toBeHidden();
  const invited = page.getByRole("row").filter({ hasText: `librarian-${stamp}@greenfield.test` });
  await expect(invited).toContainText("Librarian");

  // Blocking and unblocking a staff member; the proprietor's row has no Block button.
  await invited.getByRole("button", { name: /^Block / }).click();
  await expect(invited).toContainText("Blocked");
  await invited.getByRole("button", { name: /^Unblock / }).click();
  await expect(invited).not.toContainText("Blocked");
  const proprietor = page.getByRole("row").filter({ hasText: "owner@greenfield.test" });
  await expect(proprietor.getByRole("button", { name: /^Block / })).toHaveCount(0);
  await expectAccessible(page, "staff and access (head teacher)");
});

test("a class teacher adds a pupil, who joins their class straight away", async ({ page }) => {
  await signInToSchool(page, CLASS_TEACHER);
  await page
    .getByRole("navigation", { name: "School" })
    .first()
    .getByRole("link", { name: "Students" })
    .click();
  await page.getByRole("button", { name: "Add student" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Class")).toHaveValue(/.+/); // their only class, chosen for them
  await expect(dialog.getByLabel("Class").locator("option:not([disabled])")).toHaveText(["JHS 2 A"]);
  await expect(page.getByRole("button", { name: "Import CSV / Excel" })).toHaveCount(0);

  const stamp = Date.now().toString().slice(-5);
  await dialog.getByLabel("First name").fill("Kojo");
  await dialog.getByLabel("Last name").fill(`Owusu${stamp}`);
  await dialog.getByLabel("Date of birth").fill("2013-02-14");
  await dialog.getByRole("button", { name: "Save student" }).click();
  await expect(dialog).toBeHidden();

  const row = page.getByRole("row").filter({ hasText: `Owusu${stamp}` });
  await expect(row).toContainText("JHS 2 A");

  // The register for their class lists the new pupil at once.
  await page.goto("/attendance");
  await page.getByLabel("Class").selectOption({ label: "JHS 2 A" });
  await expect(page.getByText(`Owusu${stamp}`)).toBeVisible();
});
