import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminManagementPage } from "./AdminManagementPage";
import { ApiError } from "@/lib/api/client";
import type { AdminAccount, AdminProfile } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  listAdmins: vi.fn(),
  createAdmin: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin-management",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/admin-management", () => ({
  listAdmins: mocks.listAdmins,
  createAdmin: mocks.createAdmin,
}));

const SUPER_ADMIN_PROFILE: AdminProfile = {
  admin_id: "admin-super",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const SAMPLE_ADMIN: AdminAccount = {
  admin_id: "admin-employee-1",
  role: "ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-10T00:00:00Z",
  permissions: [],
};

function mockSuccessfulLoad(admins: AdminAccount[] = [SAMPLE_ADMIN]) {
  mocks.getAdminProfile.mockResolvedValue(SUPER_ADMIN_PROFILE);
  mocks.listAdmins.mockResolvedValue({
    items: admins,
    pagination: { page: 1, page_size: 20, total: admins.length, total_pages: 1 },
  });
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("AdminManagementPage", () => {
  it("shows a loading state, then the employee admin list", async () => {
    mockSuccessfulLoad();
    render(<AdminManagementPage />);

    expect(screen.getByText(/Loading Admin Management/)).toBeInTheDocument();

    expect(await screen.findByText("admin-employee-1")).toBeInTheDocument();
    expect(screen.getByText("ADMIN")).toBeInTheDocument();
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message, not a crash", async () => {
    mocks.getAdminProfile.mockResolvedValue(SUPER_ADMIN_PROFILE);
    mocks.listAdmins.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<AdminManagementPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Admin Management.",
      ),
    ).toBeInTheDocument();
  });

  it("creates an employee admin and refreshes the list", async () => {
    const user = userEvent.setup();
    mockSuccessfulLoad([]);
    mocks.createAdmin.mockResolvedValue({
      admin_id: "admin-employee-2",
      role: "ADMIN",
      status: "ACTIVE",
      created_at: "2026-08-28T00:00:00Z",
      permissions: [],
    });

    render(<AdminManagementPage />);
    await screen.findByText("No employee admins yet.");

    await user.click(screen.getByRole("button", { name: "+ Create admin" }));
    await user.type(screen.getByLabelText("Phone number"), "+919876543210");

    mocks.listAdmins.mockResolvedValueOnce({
      items: [
        {
          admin_id: "admin-employee-2",
          role: "ADMIN",
          status: "ACTIVE",
          created_at: "2026-08-28T00:00:00Z",
          permissions: [],
        },
      ],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });

    await user.click(screen.getByRole("button", { name: "Create admin" }));

    expect(mocks.createAdmin).toHaveBeenCalledWith("+919876543210", []);
    expect(
      await screen.findByText(/Created admin for \+919876543210/),
    ).toBeInTheDocument();
    expect(await screen.findByText("admin-employee-2")).toBeInTheDocument();
  });

  it("disables Previous on the first page and enables Next when more pages exist", async () => {
    mocks.getAdminProfile.mockResolvedValue(SUPER_ADMIN_PROFILE);
    mocks.listAdmins.mockResolvedValue({
      items: [SAMPLE_ADMIN],
      pagination: { page: 1, page_size: 20, total: 40, total_pages: 2 },
    });
    render(<AdminManagementPage />);

    await screen.findByText("admin-employee-1");
    const pagination = screen.getByText(/Page 1 of 2/).parentElement!;
    expect(within(pagination).getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(within(pagination).getByRole("button", { name: "Next" })).toBeEnabled();
  });

  it("advances to the next page on click", async () => {
    const user = userEvent.setup();
    mocks.getAdminProfile.mockResolvedValue(SUPER_ADMIN_PROFILE);
    mocks.listAdmins.mockResolvedValue({
      items: [SAMPLE_ADMIN],
      pagination: { page: 1, page_size: 20, total: 40, total_pages: 2 },
    });
    render(<AdminManagementPage />);
    await screen.findByText("admin-employee-1");

    await user.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(mocks.listAdmins).toHaveBeenCalledWith(2, 20);
    });
  });
});
