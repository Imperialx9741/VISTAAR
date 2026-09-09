import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DriversPage } from "./DriversPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, DriverSummary } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchDrivers: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/drivers",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/people", () => ({
  searchDrivers: mocks.searchDrivers,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const DRIVER: DriverSummary = {
  driver_id: "driver-1",
  full_name: "Ravi Kumar",
  profile_photo_uri: null,
  verification_status: "PENDING",
  operational_status: "OFFLINE",
  strikes: 0,
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("DriversPage", () => {
  it("shows a loading state, then the driver list", async () => {
    mocks.searchDrivers.mockResolvedValue({
      items: [DRIVER],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<DriversPage />);

    expect(screen.getByText(/Loading Drivers/)).toBeInTheDocument();
    expect(await screen.findByText("Ravi Kumar")).toBeInTheDocument();
    // "PENDING" also appears as a <select> option (the status filter) —
    // assert the pill specifically, by role, rather than by bare text.
    expect(screen.getByRole("cell", { name: "PENDING" })).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchDrivers.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<DriversPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Drivers.",
      ),
    ).toBeInTheDocument();
  });

  it("shows a distinct Review affordance for PENDING drivers, not a plain View link", async () => {
    mocks.searchDrivers.mockResolvedValue({
      items: [DRIVER],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<DriversPage />);

    expect(await screen.findByRole("link", { name: "Review →" })).toHaveAttribute(
      "href",
      "/drivers/driver-1",
    );
    expect(screen.queryByRole("link", { name: "View" })).not.toBeInTheDocument();
  });

  it("shows a plain View link for a driver that isn't PENDING", async () => {
    mocks.searchDrivers.mockResolvedValue({
      items: [{ ...DRIVER, verification_status: "APPROVED" }],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<DriversPage />);

    expect(await screen.findByRole("link", { name: "View" })).toHaveAttribute(
      "href",
      "/drivers/driver-1",
    );
    expect(
      screen.queryByRole("link", { name: "Review →" }),
    ).not.toBeInTheDocument();
  });

  it("re-queries with the selected verification status filter", async () => {
    const user = userEvent.setup();
    mocks.searchDrivers.mockResolvedValue({
      items: [DRIVER],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<DriversPage />);
    await screen.findByText("Ravi Kumar");

    await user.selectOptions(
      screen.getByLabelText("Filter by verification status"),
      "APPROVED",
    );

    expect(mocks.searchDrivers).toHaveBeenLastCalledWith(
      "",
      "APPROVED",
      1,
      20,
    );
  });
});
