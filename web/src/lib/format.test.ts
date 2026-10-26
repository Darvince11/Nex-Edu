import { describe, expect, it } from "vitest";
import { cedis, timeAgo, todayInAccra, toPesewas } from "./format";

describe("cedis", () => {
  it("formats integer pesewas as Ghana cedis", () => {
    expect(cedis(125000)).toBe("GH₵1,250.00");
    expect(cedis(5)).toBe("GH₵0.05");
    expect(cedis(null)).toBe("GH₵0.00");
  });
});

describe("toPesewas", () => {
  it.each([
    ["1250", 125000],
    ["1,250.5", 125050],
    ["GH₵ 450.00", 45000],
    ["0.05", 5],
  ])("parses %s", (input, expected) => {
    expect(toPesewas(input)).toBe(expected);
  });

  it.each(["", "abc", "1.234", "-5", "1e3"])("rejects %s", (input) => {
    expect(toPesewas(input)).toBeNull();
  });
});

describe("todayInAccra", () => {
  it("uses GMT, Ghana's time zone all year", () => {
    expect(todayInAccra(new Date("2026-10-19T23:30:00Z"))).toBe("2026-10-19");
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-10-24T12:00:00Z");
  it("says how long ago in plain words", () => {
    expect(timeAgo("2026-10-24T11:59:30Z", now)).toBe("just now");
    expect(timeAgo("2026-10-24T09:00:00Z", now)).toBe("3 hours ago");
    expect(timeAgo("2026-10-23T12:00:00Z", now)).toBe("yesterday");
    expect(timeAgo("2026-10-03T12:00:00Z", now)).toBe("3 weeks ago");
    expect(timeAgo(null, now)).toBe("—");
  });
});
