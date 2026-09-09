import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { RideDetailPage } from "./RideDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Ride } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getRide: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/rides/ride-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/rides", () => ({
  getRide: mocks.getRide,
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

describe("RideDetailPage", () => {
  it("loads and shows the ride's fields, fare, and timeline", async () => {
    mocks.getRide.mockResolvedValue(RIDE);
    render(<RideDetailPage rideId="ride-1" />);

    expect(await screen.findByText("customer-1")).toBeInTheDocument();
    expect(screen.getByText("₹90.00")).toBeInTheDocument();
    expect(screen.getByText("Started")).toBeInTheDocument();
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
    // cancelled_at is null — the timeline shows an em dash, not a date.
    const cancelledRow = screen.getByText("Cancelled").closest("div");
    expect(cancelledRow?.textContent).toContain("—");
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getRide.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No ride found.", 404),
    );
    render(<RideDetailPage rideId="unknown" />);

    expect(await screen.findByText("No ride found.")).toBeInTheDocument();
  });

  it("shows no fare quote message when the ride has none yet", async () => {
    mocks.getRide.mockResolvedValue({ ...RIDE, fare: null });
    render(<RideDetailPage rideId="ride-1" />);

    expect(await screen.findByText("No fare quote yet.")).toBeInTheDocument();
  });
});
