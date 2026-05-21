import { describe, expect, it } from "vitest";
import { compactId, formatPercent } from "./format";

describe("format utilities", () => {
  it("formats probabilities as percentages", () => {
    expect(formatPercent(0.8234)).toBe("82.3%");
    expect(formatPercent(null)).toBe("-");
  });

  it("compacts long ids", () => {
    expect(compactId("12345678-aaaa-bbbb-cccc-123456789abc")).toBe(
      "12345678...9abc",
    );
  });
});
