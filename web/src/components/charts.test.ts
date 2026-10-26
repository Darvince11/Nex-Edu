import { describe, expect, it } from "vitest";
import { compact, niceTicks } from "./charts";

describe("niceTicks", () => {
  it("uses round steps that reach the maximum", () => {
    expect(niceTicks(100)).toEqual([0, 25, 50, 75, 100]);
    expect(niceTicks(7, 3)).toEqual([0, 2.5, 5, 7.5]);
    expect(niceTicks(1830, 4)).toEqual([0, 500, 1000, 1500, 2000]);
  });
  it("copes with no data", () => {
    expect(niceTicks(0)).toEqual([0, 1]);
  });
});

describe("compact", () => {
  it("shortens thousands and millions", () => {
    expect(compact(950)).toBe("950");
    expect(compact(1_000)).toBe("1K");
    expect(compact(12_900)).toBe("12.9K");
    expect(compact(4_200_000)).toBe("4.2M");
  });
});
