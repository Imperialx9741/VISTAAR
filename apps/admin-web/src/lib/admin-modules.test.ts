import { describe, expect, it } from "vitest";
import { GRANTABLE_MODULES } from "./admin-modules";

describe("GRANTABLE_MODULES", () => {
  it("never includes ADMIN_MANAGEMENT or SETTINGS (ADR-0040/BR-126: never grantable)", () => {
    const modules = GRANTABLE_MODULES.map((m) => m.module);
    expect(modules).not.toContain("ADMIN_MANAGEMENT");
    expect(modules).not.toContain("SETTINGS");
  });

  it("includes every other AdminModule exactly once", () => {
    const modules = GRANTABLE_MODULES.map((m) => m.module);
    expect(modules).toHaveLength(18); // 20 total modules − 2 ungrantable
    expect(new Set(modules).size).toBe(modules.length);
  });

  it("gives every entry a non-empty display label", () => {
    for (const entry of GRANTABLE_MODULES) {
      expect(entry.label.length).toBeGreaterThan(0);
    }
  });
});
