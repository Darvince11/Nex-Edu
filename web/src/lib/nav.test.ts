import { existsSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { locate, NAV_GROUPS, navFor } from "./nav";

const labels = (roles: string[]) => navFor(roles).flatMap((g) => g.items.map((i) => i.label));

describe("navFor", () => {
  it("shows parents only what concerns their children", () => {
    expect(labels(["parent"])).toEqual([
      "Overview",
      "My children",
      "Results and report cards",
      "Homework",
      "Online tests",
      "Learning support",
      "Fees and payments",
      "Library",
      "Clubs and sports",
      "Parent meetings",
      "Behaviour",
      "Sick bay",
      "Transport",
      "Canteen",
      "Gate and pick-up",
      "Boarding",
      "Announcements",
      "Messages",
      "Calendar",
      "Inbox",
    ]);
  });

  it("lists the library only while the school has it switched on", () => {
    const parent = (modules: string[]) =>
      navFor(["parent"], ["library.view"], modules).flatMap((g) => g.items.map((i) => i.label));
    expect(parent(["fees"])).not.toContain("Library");
    expect(parent(["fees", "library"])).toContain("Library");
  });

  it("shows messages only to people who may use them", () => {
    expect(labels(["student"])).toContain("Calendar");
    expect(navFor(["student"], ["calendar.view"]).flatMap((g) => g.items.map((i) => i.label))).not.toContain(
      "Messages",
    );
  });

  it("shows what a custom role adds, whatever the person's own role", () => {
    const librarian = (custom: string[]) =>
      navFor(["librarian"], ["students.view", ...custom], undefined, custom).flatMap((g) =>
        g.items.map((i) => i.label),
      );
    expect(librarian([])).not.toContain("Reports");
    expect(librarian(["reports.view", "assessments.manage"])).toEqual(
      expect.arrayContaining(["Reports", "Score entry"]),
    );
    expect(librarian(["reports.view"])).not.toContain("Custom roles");
  });

  it("keeps finance away from teachers and teaching away from bursars", () => {
    expect(labels(["teacher"])).not.toContain("Fees and payments");
    expect(labels(["bursar"])).not.toContain("Score entry");
    expect(labels(["bursar"])).toContain("Fees and payments");
  });

  it("drops groups with nothing visible", () => {
    const groups = navFor(["student"]).map((g) => g.id);
    expect(groups).not.toContain("finance");
    expect(groups).not.toContain("settings");
  });

  it("hides score entry from the head teacher, who doesn't enter scores", () => {
    const head = navFor(["principal"], ["assessments.view", "assessments.publish", "members.view"]);
    const shown = head.flatMap((g) => g.items.map((i) => i.label));
    expect(shown).not.toContain("Score entry");
    expect(shown).toContain("Results and report cards");
    expect(shown).toContain("Staff and access");
    const teacher = navFor(["teacher"], ["assessments.record"]).flatMap((g) => g.items.map((i) => i.label));
    expect(teacher).toContain("Score entry");
  });

  it("hides an optional module's pages while it's switched off", () => {
    const withFees = navFor(["owner"], undefined, ["fees", "admissions"]).flatMap((g) =>
      g.items.map((i) => i.label),
    );
    expect(withFees).toContain("Fees and payments");
    const without = navFor(["owner"], undefined, ["admissions"]).flatMap((g) => g.items.map((i) => i.label));
    expect(without).not.toContain("Fees and payments");
    expect(without).toContain("Admissions");
  });

  it("gives owners everything", () => {
    expect(labels(["owner"])).toHaveLength(NAV_GROUPS.flatMap((g) => g.items).length - 1); // not "My children"
  });
});

describe("locate", () => {
  it("finds the group and item for nested pages", () => {
    const found = locate(navFor(["owner"]), "/students/0f4c");
    expect(found?.group.label).toBe("People");
    expect(found?.item.label).toBe("Students");
  });

  it("picks the most specific link", () => {
    expect(locate(navFor(["owner"]), "/settings/modules")?.item.label).toBe("Modules");
    expect(locate(navFor(["owner"]), "/settings")?.item.label).toBe("School settings");
  });

  it("returns null off the menu", () => {
    expect(locate(navFor(["owner"]), "/payments/return")).toBeNull();
  });
});

describe("no dead links", () => {
  it.each(NAV_GROUPS.flatMap((g) => g.items.map((i) => i.href)))("%s has a page", (href) => {
    const page = path.resolve(import.meta.dirname, "../app/(school)", `.${href}`, "page.tsx");
    expect(existsSync(page)).toBe(true);
  });
});
