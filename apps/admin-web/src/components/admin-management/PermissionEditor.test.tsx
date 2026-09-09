import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PermissionEditor } from "./PermissionEditor";
import { GRANTABLE_MODULES } from "@/lib/admin-modules";
import type { AdminPermission } from "@/lib/api/types";

describe("PermissionEditor", () => {
  it("renders one row per grantable module, and never a row for ADMIN_MANAGEMENT or SETTINGS", () => {
    render(<PermissionEditor value={[]} onChange={() => {}} />);
    expect(screen.getAllByRole("row")).toHaveLength(GRANTABLE_MODULES.length + 1); // +1 header row
    expect(screen.queryByText("Admin Management")).not.toBeInTheDocument();
    expect(screen.queryByText("Settings")).not.toBeInTheDocument();
  });

  it("defaults every module to None when no grant exists", () => {
    render(<PermissionEditor value={[]} onChange={() => {}} />);
    const noneRadio = screen.getByRole("radio", {
      name: `${GRANTABLE_MODULES[0].label} — no access`,
    });
    expect(noneRadio).toBeChecked();
  });

  it("reflects an existing grant's access level", () => {
    const value: AdminPermission[] = [
      { module: GRANTABLE_MODULES[0].module, access_level: "MANAGE" },
    ];
    render(<PermissionEditor value={value} onChange={() => {}} />);
    const manageRadio = screen.getByRole("radio", {
      name: `${GRANTABLE_MODULES[0].label} — MANAGE`,
    });
    expect(manageRadio).toBeChecked();
  });

  it("calls onChange with the module added when moving from None to VIEW", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const target = GRANTABLE_MODULES[0];
    render(<PermissionEditor value={[]} onChange={onChange} />);

    await user.click(
      screen.getByRole("radio", { name: `${target.label} — VIEW` }),
    );

    expect(onChange).toHaveBeenCalledWith([
      { module: target.module, access_level: "VIEW" },
    ]);
  });

  it("calls onChange with the module removed when moving to None", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const target = GRANTABLE_MODULES[0];
    const value: AdminPermission[] = [
      { module: target.module, access_level: "VIEW" },
    ];
    render(<PermissionEditor value={value} onChange={onChange} />);

    await user.click(
      screen.getByRole("radio", { name: `${target.label} — no access` }),
    );

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("does not change other modules' grants when editing one", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const [first, second] = GRANTABLE_MODULES;
    const value: AdminPermission[] = [
      { module: second.module, access_level: "VIEW" },
    ];
    render(<PermissionEditor value={value} onChange={onChange} />);

    await user.click(
      screen.getByRole("radio", { name: `${first.label} — MANAGE` }),
    );

    expect(onChange).toHaveBeenCalledWith([
      { module: second.module, access_level: "VIEW" },
      { module: first.module, access_level: "MANAGE" },
    ]);
  });

  it("disables every radio when disabled is set", () => {
    render(<PermissionEditor value={[]} onChange={() => {}} disabled />);
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).toBeDisabled();
    }
  });
});
