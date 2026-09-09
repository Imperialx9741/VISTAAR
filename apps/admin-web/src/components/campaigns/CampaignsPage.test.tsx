import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CampaignsPage } from "./CampaignsPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Campaign } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  listCampaigns: vi.fn(),
  createCampaign: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/offers-coupons",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/campaigns", () => ({
  listCampaigns: mocks.listCampaigns,
  createCampaign: mocks.createCampaign,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const CAMPAIGN: Campaign = {
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
  starts_at: "2026-08-10T00:00:00Z",
  ends_at: null,
  status: "DRAFT",
  created_by: "admin-1",
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("CampaignsPage", () => {
  it("shows a loading state, then the campaign list", async () => {
    mocks.listCampaigns.mockResolvedValue({
      items: [CAMPAIGN],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<CampaignsPage />);

    expect(screen.getByText(/Loading Offers\/Coupons/)).toBeInTheDocument();
    expect(await screen.findByText("50% off launch week")).toBeInTheDocument();
    expect(screen.getByText("SAVE50")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.listCampaigns.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<CampaignsPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Offers/Coupons.",
      ),
    ).toBeInTheDocument();
  });

  it("creates a DRAFT campaign and refreshes the list", async () => {
    const user = userEvent.setup();
    mocks.listCampaigns.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    mocks.createCampaign.mockResolvedValue(CAMPAIGN);

    render(<CampaignsPage />);
    await screen.findByText("No campaigns found.");

    await user.click(screen.getByRole("button", { name: "+ Create campaign" }));
    await user.type(screen.getByLabelText("Name"), "50% off launch week");
    await user.type(screen.getByLabelText(/Discount value/), "50");
    await user.type(screen.getByLabelText("Starts at"), "2026-08-10T00:00");

    mocks.listCampaigns.mockResolvedValueOnce({
      items: [CAMPAIGN],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });

    await user.click(screen.getByRole("button", { name: "Create draft" }));

    expect(mocks.createCampaign).toHaveBeenCalledTimes(1);
    const submitted = mocks.createCampaign.mock.calls[0][0];
    expect(submitted.name).toBe("50% off launch week");
    expect(submitted.discount_value).toBe(50);
    expect(submitted.eligible_customer_ids).toBeNull();
    expect(
      await screen.findByText(/Created a DRAFT campaign/),
    ).toBeInTheDocument();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.listCampaigns.mockResolvedValue({
      items: [CAMPAIGN],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<CampaignsPage />);
    await screen.findByText("50% off launch week");

    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "ACTIVE",
    );

    expect(mocks.listCampaigns).toHaveBeenLastCalledWith("ACTIVE", 1, 20);
  });
});
