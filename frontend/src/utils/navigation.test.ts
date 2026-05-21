import { describe, expect, it } from "vitest";
import { getNavigationForRole } from "./navigation";

describe("role navigation", () => {
  it("hides admin model management from doctor users", () => {
    const keys = getNavigationForRole("user").map((item) => item.key);

    expect(keys).toContain("dashboard");
    expect(keys).toContain("analyze");
    expect(keys).toContain("cases");
    expect(keys).toContain("reviews");
    expect(keys).not.toContain("models");
    expect(keys).not.toContain("users");
    expect(keys).not.toContain("monitoring");
  });

  it("shows admin management areas to admins", () => {
    const keys = getNavigationForRole("admin").map((item) => item.key);

    expect(keys).toContain("dashboard");
    expect(keys).toContain("models");
    expect(keys).toContain("cases");
    expect(keys).toContain("reviews");
    expect(keys).toContain("users");
    expect(keys).toContain("monitoring");
    expect(keys).not.toContain("analyze");
  });
});
