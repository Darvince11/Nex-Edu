import { describe, expect, it } from "vitest";
import { PLATFORM_NAV, platformNavFor } from "./platform";

const labels = (roles: string[]) => platformNavFor(roles).flatMap((g) => g.items.map((i) => i.label));

describe("platformNavFor", () => {
  it("gives super admins every console section", () => {
    expect(labels(["super_admin"])).toEqual(PLATFORM_NAV.flatMap((g) => g.items.map((i) => i.label)));
    expect(labels(["super_admin"])).toEqual([
      "Dashboard",
      "Registrations",
      "Schools",
      "Pricing and billing",
      "Invoices",
      "Billing history",
      "General audit log",
      "My audit log",
      "Announcements",
      "System settings",
      "Jobs and databases",
    ]);
  });

  it("keeps billing staff to money and their own log", () => {
    expect(labels(["billing"])).toEqual([
      "Dashboard",
      "Pricing and billing",
      "Invoices",
      "Billing history",
      "My audit log",
    ]);
  });

  it("keeps support away from money", () => {
    const support = labels(["support"]);
    expect(support).not.toContain("Pricing and billing");
    expect(support).not.toContain("Invoices");
    expect(support).toContain("Jobs and databases");
    expect(support).toContain("System settings");
    expect(support).toContain("General audit log");
  });
});
