import { describe, expect, it } from "vitest";
import {
  authError,
  fieldErrors,
  formatEmailCode,
  loginPath,
  passwordAcceptable,
  passwordRules,
  safeReturnTo,
} from "./auth";
import { suggestSlug } from "./registration";

describe("safeReturnTo", () => {
  it("keeps same-site relative paths", () => {
    expect(safeReturnTo("/results?term=2")).toBe("/results?term=2");
  });

  it.each([
    "https://evil.example/",
    "//evil.example/",
    "/\\evil.example",
    "javascript:alert(1)",
    "",
    null,
    undefined,
  ])("refuses %s", (path) => {
    expect(safeReturnTo(path)).toBe("/schools");
  });
});

describe("loginPath", () => {
  it("passes the API's reason along", () => {
    expect(loginPath("not_authenticated")).toBe("/login?reason=not_authenticated");
    expect(loginPath()).toBe("/login");
  });
});

describe("passwordRules", () => {
  const ok = (password: string, context = {}) => passwordAcceptable(passwordRules(password, context));

  it("accepts a long passphrase", () => {
    expect(ok("four unrelated words here")).toBe(true);
  });

  it.each(["short", "123456789012345", ""])("refuses %j", (password) => {
    expect(ok(password)).toBe(false);
  });

  it("refuses passwords built from the person's name or email", () => {
    expect(ok("akua-boateng-2026", { names: ["Akua", "Boateng"] })).toBe(false);
    expect(ok("esi.mensah.password", { email: "esi.mensah@example.test" })).toBe(false);
    expect(ok("river-cloth-lantern", { names: ["Akua"], email: "akua@example.test" })).toBe(true);
  });
});

describe("formatEmailCode", () => {
  it("uppercases, drops stray characters and adds the dash", () => {
    expect(formatEmailCode("bcdf ghjk")).toBe("BCDF-GHJK");
    expect(formatEmailCode("BCDF-GHJK-extra")).toBe("BCDF-GHJK");
    expect(formatEmailCode("bc")).toBe("BC");
  });
});

describe("authError", () => {
  it("never echoes whether an email exists", () => {
    const message = authError({ status: 400, errors: [{ code: "email_password_mismatch", message: "x" }] });
    expect(message).toBe("That email and password don't match. Check them and try again.");
  });

  it("explains rate limits", () => {
    expect(authError({ status: 429 })).toMatch(/Too many attempts/);
  });
});

describe("fieldErrors", () => {
  it("keeps the first error for each field", () => {
    expect(
      fieldErrors({
        status: 400,
        errors: [
          { code: "a", message: "Too short", param: "password" },
          { code: "b", message: "Too common", param: "password" },
          { code: "c", message: "Enter your name.", param: "first_name" },
        ],
      }),
    ).toEqual({ password: "Too short", first_name: "Enter your name." });
  });
});

describe("suggestSlug", () => {
  it.each([
    ["St. Mary's Basic School", "st-marys-basic"],
    ["Sunrise Academy", "sunrise-academy"],
    ["  Ébène  International  ", "ebene-international"],
    ["1st Class Preparatory", "st-class-preparatory"],
  ])("%s → %s", (name, slug) => {
    expect(suggestSlug(name)).toBe(slug);
  });
});
