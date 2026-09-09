import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CampaignsPage } from "./CampaignsPage";
import { ApiError } from "@/lib/api/client";
import type { AdCampaign, AdminProfile } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  listAdCampaigns: vi.fn(),
  createAdCampaign: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/advertisements",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/advertisements", () => ({
  listAdCampaigns: mocks.listAdCampaigns,
  createAdCampaign: mocks.createAdCampaign,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const CAMPAIGN: AdCampaign = {
  campaign_id: "campaign-1",
  partner_name: "Acme Ads",
  status: "ACTIVE",
  payout_amount: 500,
  driver_share_percent: 80,
  vistaar_share_percent: 20,
  starts_at: null,
  ends_at: null,
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("CampaignsPage", () => {
  it("shows a loading state, then the campaign list", async () => {
    mocks.listAdCampaigns.mockResolvedValue({
      items: [CAMPAIGN],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<CampaignsPage />);

    expect(screen.getByText(/Loading Advertisements/)).toBeInTheDocument();
    expect(await screen.findByText("Acme Ads")).toBeInTheDocument();
    expect(screen.getByText("80% / 20%")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.listAdCampaigns.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<CampaignsPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Advertisements.",
      ),
    ).toBeInTheDocument();
  });

  it("creates a campaign and refreshes the list", async () => {
    const user = userEvent.setup();
    mocks.listAdCampaigns.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    mocks.createAdCampaign.mockResolvedValue(CAMPAIGN);

    render(<CampaignsPage />);
    await screen.findByText("No campaigns found.");

    await user.click(
      screen.getByRole("button", { name: "+ Create campaign" }),
    );
    await user.type(screen.getByLabelText("Partner name"), "Acme Ads");
    await user.type(screen.getByLabelText("Payout amount (₹)"), "500");

    mocks.listAdCampaigns.mockResolvedValueOnce({
      items: [CAMPAIGN],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });

    await user.click(screen.getByRole("button", { name: "Create campaign" }));

    expect(mocks.createAdCampaign).toHaveBeenCalledWith({
      partner_name: "Acme Ads",
      payout_amount: 500,
      driver_share_percent: 80,
      vistaar_share_percent: 20,
      starts_at: undefined,
      ends_at: undefined,
    });
    expect(
      await screen.findByText(/Created campaign "Acme Ads"/),
    ).toBeInTheDocument();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.listAdCampaigns.mockResolvedValue({
      items: [CAMPAIGN],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<CampaignsPage />);
    await screen.findByText("Acme Ads");

    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "PAUSED",
    );

    expect(mocks.listAdCampaigns).toHaveBeenLastCalledWith("PAUSED", 1, 20);
  });
});
