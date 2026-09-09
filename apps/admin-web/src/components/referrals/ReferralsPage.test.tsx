import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReferralsPage } from "./ReferralsPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Referral } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchReferrals: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/referrals",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/referrals", () => ({
  searchReferrals: mocks.searchReferrals,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const REFERRAL: Referral = {
  referral_id: "referral-1",
  referrer_id: "customer-1",
  referred_id: "customer-2",
  referred_type: "CUSTOMER",
  status: "ACTIVATED",
  activated_at: "2026-08-10T00:00:00Z",
  created_at: "2026-08-09T00:00:00Z",
  rewards: [
    {
      reward_id: "reward-1",
      recipient_id: "customer-1",
      reward_type: "CUSTOMER_REFERRAL_PROMOTION",
      amount: null,
      promotion_uses: 3,
      status: "ISSUED",
      created_at: "2026-08-10T00:00:00Z",
    },
  ],
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("ReferralsPage", () => {
  it("shows a loading state, then the referral list with its rewards", async () => {
    mocks.searchReferrals.mockResolvedValue({
      items: [REFERRAL],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<ReferralsPage />);

    expect(screen.getByText(/Loading Referrals/)).toBeInTheDocument();
    expect(await screen.findByText("customer-1")).toBeInTheDocument();
    expect(screen.getByText("CUSTOMER_REFERRAL_PROMOTION")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchReferrals.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<ReferralsPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Referrals.",
      ),
    ).toBeInTheDocument();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.searchReferrals.mockResolvedValue({
      items: [REFERRAL],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<ReferralsPage />);
    await screen.findByText("customer-1");

    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "ATTACHED",
    );

    expect(mocks.searchReferrals).toHaveBeenLastCalledWith("ATTACHED", 1, 20);
  });

  it("links to Reward Configuration", async () => {
    mocks.searchReferrals.mockResolvedValue({
      items: [REFERRAL],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<ReferralsPage />);
    await screen.findByText("customer-1");

    expect(
      screen.getByRole("link", { name: "Manage reward configuration →" }),
    ).toHaveAttribute("href", "/referrals/rewards");
  });
});
