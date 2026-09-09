import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RewardConfigPage } from "./RewardConfigPage";
import type {
  AdminProfile,
  CustomerRewardRule,
  DriverBonusRule,
} from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  listDriverBonusRules: vi.fn(),
  createDriverBonusRule: vi.fn(),
  listCustomerRewardRules: vi.fn(),
  createCustomerRewardRule: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/referrals/rewards",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/referrals", () => ({
  listDriverBonusRules: mocks.listDriverBonusRules,
  createDriverBonusRule: mocks.createDriverBonusRule,
  listCustomerRewardRules: mocks.listCustomerRewardRules,
  createCustomerRewardRule: mocks.createCustomerRewardRule,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const DRIVER_BONUS_RULE: DriverBonusRule = {
  rule_id: "driver-rule-1",
  referred_amount: 100,
  referrer_amount: 100,
  status: "DRAFT",
  effective_from: null,
  effective_until: null,
  created_at: "2026-08-10T00:00:00Z",
};

const CUSTOMER_REWARD_RULE: CustomerRewardRule = {
  rule_id: "customer-rule-1",
  reward_type: "REFERRAL_REFERRED",
  discount_percent: 50,
  total_uses: 3,
  status: "DRAFT",
  effective_from: null,
  effective_until: null,
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
  mocks.listDriverBonusRules.mockResolvedValue({
    items: [DRIVER_BONUS_RULE],
    pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
  });
  mocks.listCustomerRewardRules.mockResolvedValue({
    items: [CUSTOMER_REWARD_RULE],
    pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
  });
});

describe("RewardConfigPage", () => {
  it("shows both the driver-bonus and customer-reward sections", async () => {
    render(<RewardConfigPage />);

    expect(
      await screen.findByText("Driver Referral Bonus"),
    ).toBeInTheDocument();
    expect(screen.getByText("Customer Referral Rewards")).toBeInTheDocument();
    // referred_amount and referrer_amount are both 100 in the fixture —
    // two cells legitimately render "100" (the list table shows bare
    // amounts, unlike the detail page's own "₹"-prefixed summary).
    expect(await screen.findAllByText("100")).toHaveLength(2);
    // "REFERRAL_REFERRED" also appears as a <select> option (the
    // reward-type filter) — the table cell is unambiguous by role.
    expect(
      screen.getByRole("cell", { name: "REFERRAL_REFERRED" }),
    ).toBeInTheDocument();
  });

  it("creates a driver-bonus draft with the entered amounts", async () => {
    const user = userEvent.setup();
    mocks.createDriverBonusRule.mockResolvedValue(DRIVER_BONUS_RULE);
    render(<RewardConfigPage />);
    await screen.findByText("Driver Referral Bonus");

    const buttons = screen.getAllByRole("button", { name: "+ Create draft" });
    await user.click(buttons[0]);
    await user.type(
      screen.getByLabelText("Referred driver amount (₹)"),
      "100",
    );
    await user.type(
      screen.getByLabelText("Referrer driver amount (₹)"),
      "100",
    );
    await user.click(screen.getByRole("button", { name: "Create draft" }));

    expect(mocks.createDriverBonusRule).toHaveBeenCalledWith(100, 100);
    expect(
      await screen.findByText(/Created a DRAFT driver-bonus rule/),
    ).toBeInTheDocument();
  });

  it("creates a customer-reward draft with the entered fields", async () => {
    const user = userEvent.setup();
    mocks.createCustomerRewardRule.mockResolvedValue(CUSTOMER_REWARD_RULE);
    render(<RewardConfigPage />);
    await screen.findByText("Customer Referral Rewards");

    const buttons = screen.getAllByRole("button", { name: "+ Create draft" });
    await user.click(buttons[1]);
    await user.type(screen.getByLabelText("Discount (%)"), "50");
    await user.type(screen.getByLabelText("Total uses"), "3");
    await user.click(screen.getByRole("button", { name: "Create draft" }));

    expect(mocks.createCustomerRewardRule).toHaveBeenCalledWith(
      "REFERRAL_REFERRED",
      50,
      3,
    );
    expect(
      await screen.findByText(/Created a DRAFT REFERRAL_REFERRED rule/),
    ).toBeInTheDocument();
  });
});
