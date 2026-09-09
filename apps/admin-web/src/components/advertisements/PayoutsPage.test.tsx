import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PayoutsPage } from "./PayoutsPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, AdPayout } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  listAdPayouts: vi.fn(),
  settleAdPayout: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/advertisements/payouts",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/advertisements", () => ({
  listAdPayouts: mocks.listAdPayouts,
  settleAdPayout: mocks.settleAdPayout,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const PENDING_PAYOUT: AdPayout = {
  payout_id: "payout-1",
  driver_campaign_id: "assignment-1",
  gross_amount: 500,
  driver_amount: 400,
  vistaar_amount: 100,
  status: "PENDING",
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("PayoutsPage", () => {
  it("shows a loading state, then the payout list", async () => {
    mocks.listAdPayouts.mockResolvedValue({
      items: [PENDING_PAYOUT],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<PayoutsPage />);

    expect(screen.getByText(/Loading Advertisements/)).toBeInTheDocument();
    expect(await screen.findByText("₹500.00")).toBeInTheDocument();
    expect(screen.getByText("₹400.00")).toBeInTheDocument();
    expect(screen.getByText("₹100.00")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.listAdPayouts.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<PayoutsPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Advertisements.",
      ),
    ).toBeInTheDocument();
  });

  it("settles a PENDING payout and refreshes the list", async () => {
    const user = userEvent.setup();
    mocks.listAdPayouts.mockResolvedValue({
      items: [PENDING_PAYOUT],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    mocks.settleAdPayout.mockResolvedValue({
      ...PENDING_PAYOUT,
      status: "PAID",
    });
    render(<PayoutsPage />);

    await user.click(await screen.findByRole("button", { name: "Settle" }));

    expect(mocks.settleAdPayout).toHaveBeenCalledWith("payout-1");
    expect(
      await screen.findByText("Payout payout-1 settled."),
    ).toBeInTheDocument();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.listAdPayouts.mockResolvedValue({
      items: [PENDING_PAYOUT],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<PayoutsPage />);
    await screen.findByText("₹500.00");

    await user.selectOptions(screen.getByLabelText("Filter by status"), "PAID");

    expect(mocks.listAdPayouts).toHaveBeenLastCalledWith("PAID", 1, 20);
  });
});
