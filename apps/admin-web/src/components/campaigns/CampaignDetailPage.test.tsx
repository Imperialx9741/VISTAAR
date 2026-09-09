import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CampaignDetailPage } from "./CampaignDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Campaign } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getCampaign: vi.fn(),
  updateCampaign: vi.fn(),
  activateCampaign: vi.fn(),
  pauseCampaign: vi.fn(),
  endCampaign: vi.fn(),
  bulkAddEligibleCustomers: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/offers-coupons/campaign-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/campaigns", () => ({
  getCampaign: mocks.getCampaign,
  updateCampaign: mocks.updateCampaign,
  activateCampaign: mocks.activateCampaign,
  pauseCampaign: mocks.pauseCampaign,
  endCampaign: mocks.endCampaign,
  bulkAddEligibleCustomers: mocks.bulkAddEligibleCustomers,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const DRAFT_CAMPAIGN: Campaign = {
  campaign_id: "campaign-1",
  code: "SAVE50",
  name: "50% off launch week",
  vehicle_category: "CAB",
  discount_type: "PERCENT",
  discount_value: 50,
  max_discount_amount: 100,
  minimum_fare: null,
  eligible_scope: "ALL",
  per_customer_use_limit: 1,
  total_usage_limit: null,
  ride_count_limit: null,
  starts_at: "2026-08-10T09:00:00.000Z",
  ends_at: null,
  status: "DRAFT",
  created_by: "admin-1",
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("CampaignDetailPage", () => {
  it("loads and shows the campaign's fields", async () => {
    mocks.getCampaign.mockResolvedValue(DRAFT_CAMPAIGN);
    render(<CampaignDetailPage campaignId="campaign-1" />);

    expect(await screen.findByText("50% off launch week")).toBeInTheDocument();
    expect(screen.getByText("SAVE50")).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getCampaign.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No campaign found.", 404),
    );
    render(<CampaignDetailPage campaignId="unknown" />);

    expect(
      await screen.findByText("No campaign found."),
    ).toBeInTheDocument();
  });

  it("offers Edit and Activate on a DRAFT campaign, and activates", async () => {
    const user = userEvent.setup();
    mocks.getCampaign.mockResolvedValue(DRAFT_CAMPAIGN);
    mocks.activateCampaign.mockResolvedValue({
      ...DRAFT_CAMPAIGN,
      status: "ACTIVE",
    });
    render(<CampaignDetailPage campaignId="campaign-1" />);

    await screen.findByRole("button", { name: "Edit" });
    await user.click(screen.getByRole("button", { name: "Activate" }));

    expect(mocks.activateCampaign).toHaveBeenCalledWith("campaign-1");
    expect(await screen.findByText("Campaign activated.")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Pause" }),
    ).toBeInTheDocument();
  });

  it("edits a DRAFT campaign and returns to the summary view", async () => {
    const user = userEvent.setup();
    mocks.getCampaign.mockResolvedValue(DRAFT_CAMPAIGN);
    mocks.updateCampaign.mockResolvedValue({
      ...DRAFT_CAMPAIGN,
      name: "Updated name",
    });
    render(<CampaignDetailPage campaignId="campaign-1" />);

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const nameField = screen.getByLabelText("Name");
    await user.clear(nameField);
    await user.type(nameField, "Updated name");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(mocks.updateCampaign).toHaveBeenCalledWith(
      "campaign-1",
      expect.objectContaining({ name: "Updated name" }),
    );
    expect(await screen.findByText("Updated name")).toBeInTheDocument();
    expect(await screen.findByText("Campaign updated.")).toBeInTheDocument();
  });

  it("hides every action (Edit, Activate, Pause, End) once a campaign is ENDED — terminal", async () => {
    mocks.getCampaign.mockResolvedValue({
      ...DRAFT_CAMPAIGN,
      status: "ENDED",
    });
    render(<CampaignDetailPage campaignId="campaign-1" />);

    await screen.findByText("50% off launch week");
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Activate" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "End" })).not.toBeInTheDocument();
  });

  it("does not show the CSV bulk-upload panel for an ALL-scope campaign", async () => {
    mocks.getCampaign.mockResolvedValue(DRAFT_CAMPAIGN); // eligible_scope: "ALL"
    render(<CampaignDetailPage campaignId="campaign-1" />);

    await screen.findByText("50% off launch week");
    expect(
      screen.queryByText("Bulk-add eligible customers (CSV)"),
    ).not.toBeInTheDocument();
  });

  it("shows the CSV bulk-upload panel for a DRAFT, SELECTED-scope campaign", async () => {
    mocks.getCampaign.mockResolvedValue({
      ...DRAFT_CAMPAIGN,
      eligible_scope: "SELECTED",
    });
    render(<CampaignDetailPage campaignId="campaign-1" />);

    expect(
      await screen.findByText("Bulk-add eligible customers (CSV)"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
  });

  it("uploads a CSV and shows the added/already_eligible/unmatched result", async () => {
    const user = userEvent.setup();
    mocks.getCampaign.mockResolvedValue({
      ...DRAFT_CAMPAIGN,
      eligible_scope: "SELECTED",
    });
    mocks.bulkAddEligibleCustomers.mockResolvedValue({
      added: 2,
      already_eligible: 1,
      unmatched: [{ row: 4, phone: "not-a-phone", reason: "invalid phone number" }],
    });
    render(<CampaignDetailPage campaignId="campaign-1" />);
    await screen.findByText("Bulk-add eligible customers (CSV)");

    const file = new File(["phone\n+919999999999\n"], "customers.csv", {
      type: "text/csv",
    });
    await user.upload(screen.getByLabelText("CSV file"), file);
    await user.click(screen.getByRole("button", { name: "Upload" }));

    expect(mocks.bulkAddEligibleCustomers).toHaveBeenCalledWith(
      "campaign-1",
      file,
    );
    expect(
      await screen.findByText("Added 2, already eligible 1, 1 unmatched."),
    ).toBeInTheDocument();
    expect(screen.getByText("not-a-phone")).toBeInTheDocument();
    expect(screen.getByText("invalid phone number")).toBeInTheDocument();
  });

  it("shows a real error banner when the upload fails", async () => {
    const user = userEvent.setup();
    mocks.getCampaign.mockResolvedValue({
      ...DRAFT_CAMPAIGN,
      eligible_scope: "SELECTED",
    });
    mocks.bulkAddEligibleCustomers.mockRejectedValue(
      new ApiError(
        "VALIDATION_FAILED",
        "CSV must have a header row with a 'phone' column.",
        422,
      ),
    );
    render(<CampaignDetailPage campaignId="campaign-1" />);
    await screen.findByText("Bulk-add eligible customers (CSV)");

    const file = new File(["oops"], "customers.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText("CSV file"), file);
    await user.click(screen.getByRole("button", { name: "Upload" }));

    expect(
      await screen.findByText("CSV must have a header row with a 'phone' column."),
    ).toBeInTheDocument();
  });
});
