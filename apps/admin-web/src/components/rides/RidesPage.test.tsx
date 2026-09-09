import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RidesPage } from "./RidesPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Ride } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchRides: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/rides",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/rides", () => ({
  searchRides: mocks.searchRides,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const RIDE: Ride = {
  ride_id: "ride-1",
  status: "COMPLETED",
  customer_id: "customer-1",
  driver_id: "driver-1",
  vehicle_id: "vehicle-1",
  requested_vehicle_category: "CAB",
  requested_cab_tier: "CAB_ECO",
  pickup: { latitude: 12.9, longitude: 77.6 },
  destination: { latitude: 12.95, longitude: 77.65 },
  fare: { base: 100, discount: 10, total: 90, currency: "INR" },
  requested_at: "2026-08-10T00:00:00Z",
  accepted_at: "2026-08-10T00:01:00Z",
  arrived_at: "2026-08-10T00:05:00Z",
  started_at: "2026-08-10T00:06:00Z",
  completed_at: "2026-08-10T00:20:00Z",
  cancelled_at: null,
  closed_at: null,
  created_at: "2026-08-10T00:00:00Z",
  updated_at: "2026-08-10T00:20:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("RidesPage", () => {
  it("shows a loading state, then the ride list", async () => {
    mocks.searchRides.mockResolvedValue({
      items: [RIDE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<RidesPage />);

    expect(screen.getByText(/Loading Rides/)).toBeInTheDocument();
    expect(await screen.findByText("customer-1")).toBeInTheDocument();
    expect(screen.getByText("CAB (CAB_ECO)")).toBeInTheDocument();
    // "COMPLETED" appears as both the status Pill and a status-filter
    // <select> option — the table cell is unambiguous by role.
    expect(
      screen.getByRole("cell", { name: "COMPLETED" }),
    ).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchRides.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<RidesPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Rides.",
      ),
    ).toBeInTheDocument();
  });

  it("searches with the entered driver/customer/status filters", async () => {
    const user = userEvent.setup();
    mocks.searchRides.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    render(<RidesPage />);
    await screen.findByText("No rides found.");

    await user.type(screen.getByLabelText("Filter by driver ID"), "driver-9");
    await user.type(
      screen.getByLabelText("Filter by customer ID"),
      "customer-9",
    );
    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "CANCELLED",
    );
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(mocks.searchRides).toHaveBeenLastCalledWith(
      "CANCELLED",
      "driver-9",
      "customer-9",
      1,
      20,
    );
  });
});
