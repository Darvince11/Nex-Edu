import { describe, expect, it } from "vitest";
import { pickSchool, schoolFromHost } from "./school";

const school = (slug: string) => ({
  slug,
  name: slug,
  roles: ["teacher"],
  permissions: [],
  grantable_roles: [],
  modules: [],
  custom_roles: [],
  custom_permissions: [],
});
const me = { schools: [school("akwaaba"), school("greenfield")] };

describe("schoolFromHost", () => {
  it("reads the school from its own address", () => {
    expect(schoolFromHost("greenfield.nexedu.com.gh", "nexedu.com.gh")).toBe("greenfield");
    expect(schoolFromHost("Greenfield.NexEdu.com.gh", "nexedu.com.gh")).toBe("greenfield");
  });
  it("ignores the main site, www, deeper names and other domains", () => {
    expect(schoolFromHost("nexedu.com.gh", "nexedu.com.gh")).toBeUndefined();
    expect(schoolFromHost("www.nexedu.com.gh", "nexedu.com.gh")).toBeUndefined();
    expect(schoolFromHost("a.b.nexedu.com.gh", "nexedu.com.gh")).toBeUndefined();
    expect(schoolFromHost("greenfield.evil.test", "nexedu.com.gh")).toBeUndefined();
    expect(schoolFromHost("localhost", "nexedu.com.gh")).toBeUndefined();
  });
});

describe("pickSchool", () => {
  it("prefers the school whose address they came in on", () => {
    expect(pickSchool(me, "akwaaba", "greenfield.nexedu.com.gh")).toBe("greenfield");
  });
  it("never picks a school they don't belong to", () => {
    expect(pickSchool(me, "elsewhere", "elsewhere.nexedu.com.gh")).toBe("akwaaba");
  });
  it("falls back to the last school used, then the first", () => {
    expect(pickSchool(me, "greenfield", "localhost")).toBe("greenfield");
    expect(pickSchool(me, undefined, "localhost")).toBe("akwaaba");
    expect(pickSchool({ schools: [] }, "greenfield", "localhost")).toBeUndefined();
  });
});
