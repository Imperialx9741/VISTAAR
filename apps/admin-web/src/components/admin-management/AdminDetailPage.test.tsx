import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminDetailPage } from "./AdminDetailPage";
import { ApiError } from "@/lib/api/client";
import { GRANTABLE_MODULES } from "@/lib/admin-modules";
import type { AdminAccount, AdminProfile } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getAdmin: vi.fn(),
  updatePermissions: vi.fn(),
  disableAdmin: vi.fn(),
  enableAdmin: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin-management/admin-employee-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/admin-management", () => ({
  getAdmin: mocks.getAdmin,
  updatePermissions: mocks.updatePermissions,
  disableAdmin: mocks.disableAdmin,
  enableAdmin: mocks.enableAdmin,
}));

const SUPER_ADMIN_PROFILE: AdminProfile = {
  admin_id: "admin-super",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const EMPLOYEE_ADMIN: AdminAccount = {
  admin_id: "admin-employee-1",
  role: "ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-10T00:00:00Z",
  permissions: [],
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(SUPER_ADMIN_PROFILE);
});

describe("AdminDetailPage", () => {
  it("loads and shows the target admin's role, status, and ID", async () => {
    mocks.getAdmin.mockResolvedValue(EMPLOYEE_ADMIN);
    render(<AdminDetailPage adminId="admin-employee-1" />);

    expect(await screen.findByText("ADMIN")).toBeInTheDocument();
    // The ID appears twice by design (TopBar subtitle + summary card) —
    // assert both are actually present rather than picking one.
    expect(screen.getAllByText("admin-employee-1")).toHaveLength(2);
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
  });

  it("shows a real error banner, not a crash, when the load fails", async () => {
    mocks.getAdmin.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No admin found.", 404),
    );
    render(<AdminDetailPage adminId="unknown" />);

    expect(await screen.findByText("No admin found.")).toBeInTheDocument();
  });

  it("never renders the permission editor for a Super Admin target, and explains why", async () => {
    mocks.getAdmin.mockResolvedValue({
      ...EMPLOYEE_ADMIN,
      admin_id: "admin-super-2",
      role: "SUPER_ADMIN",
    });
    render(<AdminDetailPage adminId="admin-super-2" />);

    await screen.findByText("SUPER_ADMIN");
    expect(screen.queryByText("Module access")).not.toBeInTheDocument();
    expect(
      screen.getByText(/not managed through this screen/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Disable admin|Enable admin/ }),
    ).not.toBeInTheDocument();
  });

  it("keeps Save disabled until a permission is actually changed, then saves the whole set", async () => {
    const user = userEvent.setup();
    mocks.getAdmin.mockResolvedValue(EMPLOYEE_ADMIN);
    const target = GRANTABLE_MODULES[0];
    mocks.updatePermissions.mockResolvedValue({
      permissions: [{ module: target.module, access_level: "VIEW" }],
    });

    render(<AdminDetailPage adminId="admin-employee-1" />);
    await screen.findByText("Module access");

    const saveButton = screen.getByRole("button", { name: "Save permissions" });
    expect(saveButton).toBeDisabled();

    await user.click(
      screen.getByRole("radio", { name: `${target.label} — VIEW` }),
    );
    expect(saveButton).toBeEnabled();

    await user.click(saveButton);

    await waitFor(() => {
      expect(mocks.updatePermissions).toHaveBeenCalledWith(
        "admin-employee-1",
        [{ module: target.module, access_level: "VIEW" }],
      );
    });
    expect(await screen.findByText("Permissions saved.")).toBeInTheDocument();
    expect(saveButton).toBeDisabled();
  });

  it("disables an active admin and flips the action to Enable", async () => {
    const user = userEvent.setup();
    mocks.getAdmin.mockResolvedValue(EMPLOYEE_ADMIN);
    mocks.disableAdmin.mockResolvedValue({
      ...EMPLOYEE_ADMIN,
      status: "DISABLED",
    });

    render(<AdminDetailPage adminId="admin-employee-1" />);
    await screen.findByRole("button", { name: "Disable admin" });

    await user.click(screen.getByRole("button", { name: "Disable admin" }));

    expect(mocks.disableAdmin).toHaveBeenCalledWith("admin-employee-1");
    expect(await screen.findByText("DISABLED")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Enable admin" }),
    ).toBeInTheDocument();
  });

  it("surfaces a real error if disable/enable fails, without losing the current state", async () => {
    const user = userEvent.setup();
    mocks.getAdmin.mockResolvedValue(EMPLOYEE_ADMIN);
    mocks.disableAdmin.mockRejectedValue(
      new ApiError("FORBIDDEN", "Cannot modify this account.", 403),
    );

    render(<AdminDetailPage adminId="admin-employee-1" />);
    await screen.findByRole("button", { name: "Disable admin" });

    await user.click(screen.getByRole("button", { name: "Disable admin" }));

    expect(
      await screen.findByText("Cannot modify this account."),
    ).toBeInTheDocument();
    // Status is unchanged since the call failed.
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
  });
});
