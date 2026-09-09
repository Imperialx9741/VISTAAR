import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DriverStrikeHistoryPage } from "./DriverStrikeHistoryPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, DriverStrike } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  listDriverStrikes: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/drivers/driver-1/strikes",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/people", () => ({
  listDriverStrikes: mocks.listDriverStrikes,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const STRIKE: DriverStrike = {
  strike_id: "strike-1",
  driver_id: "driver-1",
  ride_id: "ride-1",
  reason: "UNWILLING_TO_PROCEED",
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("DriverStrikeHistoryPage", () => {
  it("shows a loading state, then the strike list", async () => {
    mocks.listDriverStrikes.mockResolvedValue({
      items: [STRIKE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<DriverStrikeHistoryPage driverId="driver-1" />);

    expect(screen.getByText(/Loading Drivers/)).toBeInTheDocument();
    expect(await screen.findByText("UNWILLING_TO_PROCEED")).toBeInTheDocument();
    expect(screen.getByText("ride-1")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.listDriverStrikes.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<DriverStrikeHistoryPage driverId="driver-1" />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Drivers.",
      ),
    ).toBeInTheDocument();
  });

  it("shows an empty state for a driver with no strikes", async () => {
    mocks.listDriverStrikes.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    render(<DriverStrikeHistoryPage driverId="driver-1" />);

    expect(
      await screen.findByText("No strikes recorded for this driver."),
    ).toBeInTheDocument();
  });

  it("paginates to the next page", async () => {
    const user = userEvent.setup();
    mocks.listDriverStrikes.mockResolvedValue({
      items: [STRIKE],
      pagination: { page: 1, page_size: 20, total: 40, total_pages: 2 },
    });
    render(<DriverStrikeHistoryPage driverId="driver-1" />);
    await screen.findByText("UNWILLING_TO_PROCEED");

    mocks.listDriverStrikes.mockResolvedValueOnce({
      items: [STRIKE],
      pagination: { page: 2, page_size: 20, total: 40, total_pages: 2 },
    });
    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(mocks.listDriverStrikes).toHaveBeenLastCalledWith("driver-1", 2, 20);
  });
});
