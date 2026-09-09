import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { OfferDetailPage } from "./OfferDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, MatchingOffer } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getOffer: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/matching/offer-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/matching", () => ({
  getOffer: mocks.getOffer,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
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
});

describe("OfferDetailPage", () => {
  it("loads and shows the offer's documented fields", async () => {
    mocks.getOffer.mockResolvedValue(OFFER);
    render(<OfferDetailPage offerId="offer-1" />);

    expect(await screen.findByText("ride-1")).toBeInTheDocument();
    expect(screen.getByText("driver-1")).toBeInTheDocument();
    expect(screen.getByText("vehicle-1")).toBeInTheDocument();
    expect(screen.getByText("PENDING")).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getOffer.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No offer found.", 404),
    );
    render(<OfferDetailPage offerId="unknown" />);

    expect(await screen.findByText("No offer found.")).toBeInTheDocument();
  });

  it("shows an em dash for responded_at when the offer is still pending", async () => {
    mocks.getOffer.mockResolvedValue(OFFER);
    render(<OfferDetailPage offerId="offer-1" />);

    await screen.findByText("ride-1");
    const respondedLabel = screen.getByText("Responded");
    expect(respondedLabel.nextElementSibling?.textContent).toBe("—");
  });
});
