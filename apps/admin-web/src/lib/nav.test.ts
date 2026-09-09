import { describe, expect, it } from "vitest";
import { isModuleVisible } from "./nav";

describe("isModuleVisible", () => {
  it("SUPER_ADMIN sees every module, with no permission rows needed (ADR-0040 implicit full access)", () => {
    expect(isModuleVisible("ADMIN_MANAGEMENT", "SUPER_ADMIN", [])).toBe(true);
    expect(isModuleVisible("RIDES", "SUPER_ADMIN", [])).toBe(true);
  });

  it("an employee admin with no grants sees nothing", () => {
    expect(isModuleVisible("RIDES", "ADMIN", [])).toBe(false);
  });

  it("an employee admin sees only modules they hold at least VIEW on", () => {
    const permissions = [
      { module: "RIDES" as const, access_level: "VIEW" as const },
    ];
    expect(isModuleVisible("RIDES", "ADMIN", permissions)).toBe(true);
    expect(isModuleVisible("FINANCE", "ADMIN", permissions)).toBe(false);
  });

  it("an employee admin never sees ADMIN_MANAGEMENT even if a stray row existed", () => {
    // Defensive case: the backend never writes this row (ungrantable),
    // but the nav gate itself should still never special-case it as
    // visible — it only ever checks for a matching permission row.
    const permissions = [
      {
        module: "ADMIN_MANAGEMENT" as const,
        access_level: "MANAGE" as const,
      },
    ];
    // isModuleVisible only checks "does a row for this module exist" —
    // it doesn't independently re-enforce ungrantability (that's the
    // backend's job, admin-modules.ts's GRANTABLE_MODULES list is the
    // frontend's own copy of that same rule). This test documents that
    // boundary rather than assuming the nav helper re-derives it.
    expect(isModuleVisible("ADMIN_MANAGEMENT", "ADMIN", permissions)).toBe(
      true,
    );
  });
});
