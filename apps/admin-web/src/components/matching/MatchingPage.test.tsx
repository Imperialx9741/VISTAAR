import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MatchingPage } from "./MatchingPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, MatchingOffer, OnlineDriversSummary } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getOnlineDrivers: vi.fn(),
  searchOffers: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/matching",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/matching", () => ({
  getOnlineDrivers: mocks.getOnlineDrivers,
  searchOffers: mocks.searchOffers,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const ONLINE_DRIVERS: OnlineDriversSummary = {
  by_category: { BIKE: 3, AUTO: 5, "CAB:ECO": 12 },
  total: 20,
};

const OFFER: MatchingOffer = {
  offer_id: "offer-1",
  ride_id: "ride-1",
  driver_id: "driver-1",
  vehicle_id: "vehicle-1",
  status: "PENDING",
  expires_at: "2026-08-29T00:00:20Z",
  responded_at: null,
  created_at: "2026-08-29T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
  mocks.getOnlineDrivers.mockResolvedValue(ONLINE_DRIVERS);
});

describe("MatchingPage", () => {
  it("shows a loading state, then the online-driver counts and offer list", async () => {
    mocks.searchOffers.mockResolvedValue({
      items: [OFFER],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<MatchingPage />);

    expect(screen.getByText(/Loading Matching \/ Offers/)).toBeInTheDocument();
    expect(await screen.findByText("Total online")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
    expect(screen.getByText("BIKE")).toBeInTheDocument();
    expect(screen.getByText("ride-1")).toBeInTheDocument();
    expect(screen.getByText("driver-1")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message for the offer list", async () => {
    mocks.searchOffers.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<MatchingPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Matching / Offers.",
      ),
    ).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message for the online-driver count", async () => {
    mocks.getOnlineDrivers.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    mocks.searchOffers.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    render(<MatchingPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Matching / Offers.",
      ),
    ).toBeInTheDocument();
  });

  it("searches with the entered ride/driver/status/date filters", async () => {
    const user = userEvent.setup();
    mocks.searchOffers.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    render(<MatchingPage />);
    await screen.findByText("No offers found.");

    await user.type(screen.getByLabelText("Filter by ride ID"), "ride-9");
    await user.type(screen.getByLabelText("Filter by driver ID"), "driver-9");
    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "ACCEPTED",
    );
    await user.type(screen.getByLabelText("From date"), "2026-08-01");
    await user.type(screen.getByLabelText("To date"), "2026-08-28");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(mocks.searchOffers).toHaveBeenLastCalledWith(
      "ACCEPTED",
      "ride-9",
      "driver-9",
      "2026-08-01T00:00:00.000Z",
      "2026-08-28T23:59:59.999Z",
      1,
      20,
    );
  });
});
