import { describe, expect, it } from "vitest";
import { getNavigationForRole } from "./navigation";

describe("role navigation", () => {
  it("keeps retraining/admin controls out of doctor navigation", () => {
    const doctorKeys = getNavigationForRole("user").map((item) => item.key);

    expect(doctorKeys).toContain("reviews");
    expect(doctorKeys).not.toContain("models");
    expect(doctorKeys).not.toContain("users");
    expect(doctorKeys).not.toContain("monitoring");
  });

  it("shows MLOps/admin pages only for admin users", () => {
    const adminKeys = getNavigationForRole("admin").map((item) => item.key);

    expect(adminKeys).toContain("models");
    expect(adminKeys).toContain("users");
    expect(adminKeys).toContain("monitoring");
  });
});
