import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CampaignDetailPage } from "./CampaignDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdAssignment, AdCampaign, AdminProfile } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getAdCampaign: vi.fn(),
  pauseAdCampaign: vi.fn(),
  resumeAdCampaign: vi.fn(),
  endAdCampaign: vi.fn(),
  assignAdCampaignDriver: vi.fn(),
  searchAdAssignments: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/advertisements/campaign-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/advertisements", () => ({
  getAdCampaign: mocks.getAdCampaign,
  pauseAdCampaign: mocks.pauseAdCampaign,
  resumeAdCampaign: mocks.resumeAdCampaign,
  endAdCampaign: mocks.endAdCampaign,
  assignAdCampaignDriver: mocks.assignAdCampaignDriver,
  searchAdAssignments: mocks.searchAdAssignments,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const ACTIVE_CAMPAIGN: AdCampaign = {
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

const ASSIGNMENT: AdAssignment = {
  assignment_id: "assignment-1",
  campaign_id: "campaign-1",
  driver_id: "driver-1",
  status: "ASSIGNED",
  proof_uri: null,
  verification_status: null,
  assigned_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
  mocks.searchAdAssignments.mockResolvedValue({
    items: [],
    pagination: { page: 1, page_size: 50, total: 0, total_pages: 1 },
  });
});

describe("CampaignDetailPage", () => {
  it("loads and shows the campaign's fields", async () => {
    mocks.getAdCampaign.mockResolvedValue(ACTIVE_CAMPAIGN);
    render(<CampaignDetailPage campaignId="campaign-1" />);

    expect(await screen.findByText("Acme Ads")).toBeInTheDocument();
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getAdCampaign.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No campaign found.", 404),
    );
    render(<CampaignDetailPage campaignId="unknown" />);

    expect(
      await screen.findByText("No campaign found."),
    ).toBeInTheDocument();
  });

  it("pauses an ACTIVE campaign", async () => {
    const user = userEvent.setup();
    mocks.getAdCampaign.mockResolvedValue(ACTIVE_CAMPAIGN);
    mocks.pauseAdCampaign.mockResolvedValue({
      ...ACTIVE_CAMPAIGN,
      status: "PAUSED",
    });
    render(<CampaignDetailPage campaignId="campaign-1" />);

    await user.click(await screen.findByRole("button", { name: "Pause" }));

    expect(mocks.pauseAdCampaign).toHaveBeenCalledWith("campaign-1");
    expect(await screen.findByText("Campaign paused.")).toBeInTheDocument();
  });

  it("assigns a driver and refreshes the assignment list", async () => {
    const user = userEvent.setup();
    mocks.getAdCampaign.mockResolvedValue(ACTIVE_CAMPAIGN);
    mocks.assignAdCampaignDriver.mockResolvedValue(ASSIGNMENT);
    render(<CampaignDetailPage campaignId="campaign-1" />);

    await screen.findByText("Acme Ads");
    await user.type(screen.getByLabelText("Driver ID"), "driver-1");

    mocks.searchAdAssignments.mockResolvedValueOnce({
      items: [ASSIGNMENT],
      pagination: { page: 1, page_size: 50, total: 1, total_pages: 1 },
    });

    await user.click(screen.getByRole("button", { name: "Assign driver" }));

    await waitFor(() => {
      expect(mocks.assignAdCampaignDriver).toHaveBeenCalledWith(
        "campaign-1",
        "driver-1",
      );
    });
    expect(await screen.findByText("driver-1")).toBeInTheDocument();
  });

  it("hides Pause/Resume and shows only a disabled-assign notice once ENDED", async () => {
    mocks.getAdCampaign.mockResolvedValue({
      ...ACTIVE_CAMPAIGN,
      status: "ENDED",
    });
    render(<CampaignDetailPage campaignId="campaign-1" />);

    await screen.findByText("ENDED");
    expect(
      screen.queryByRole("button", { name: "Pause" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resume" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Only an ACTIVE campaign accepts new driver assignments.",
      ),
    ).toBeInTheDocument();
  });
});
