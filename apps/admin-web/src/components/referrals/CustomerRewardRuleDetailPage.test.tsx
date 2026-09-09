import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CustomerRewardRuleDetailPage } from "./CustomerRewardRuleDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, CustomerRewardRule } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getCustomerRewardRule: vi.fn(),
  submitCustomerRewardRuleForReview: vi.fn(),
  publishCustomerRewardRule: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/referrals/rewards/customer/rule-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/referrals", () => ({
  getCustomerRewardRule: mocks.getCustomerRewardRule,
  submitCustomerRewardRuleForReview: mocks.submitCustomerRewardRuleForReview,
  publishCustomerRewardRule: mocks.publishCustomerRewardRule,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const DRAFT_RULE: CustomerRewardRule = {
  rule_id: "rule-1",
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
});

describe("CustomerRewardRuleDetailPage", () => {
  it("loads and shows the rule's fields", async () => {
    mocks.getCustomerRewardRule.mockResolvedValue(DRAFT_RULE);
    render(<CustomerRewardRuleDetailPage ruleId="rule-1" />);

    expect(await screen.findByText("REFERRAL_REFERRED")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getCustomerRewardRule.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No rule found.", 404),
    );
    render(<CustomerRewardRuleDetailPage ruleId="unknown" />);

    expect(await screen.findByText("No rule found.")).toBeInTheDocument();
  });

  it("submits for review, then offers Publish instead", async () => {
    const user = userEvent.setup();
    mocks.getCustomerRewardRule.mockResolvedValue(DRAFT_RULE);
    mocks.submitCustomerRewardRuleForReview.mockResolvedValue({
      ...DRAFT_RULE,
      status: "IN_REVIEW",
    });
    render(<CustomerRewardRuleDetailPage ruleId="rule-1" />);

    await user.click(
      await screen.findByRole("button", { name: "Submit for review" }),
    );

    expect(mocks.submitCustomerRewardRuleForReview).toHaveBeenCalledWith(
      "rule-1",
    );
    expect(
      await screen.findByText("Submitted for review."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Submit for review" }),
    ).not.toBeInTheDocument();
  });

  it("publishes with a scheduled effective_from", async () => {
    const user = userEvent.setup();
    mocks.getCustomerRewardRule.mockResolvedValue(DRAFT_RULE);
    mocks.publishCustomerRewardRule.mockResolvedValue({
      ...DRAFT_RULE,
      status: "PUBLISHED",
    });
    render(<CustomerRewardRuleDetailPage ruleId="rule-1" />);

    await user.click(await screen.findByRole("button", { name: "Publish" }));
    // userEvent.type doesn't drive type="datetime-local" inputs
    // reliably in jsdom — fireEvent.change is the standard workaround.
    fireEvent.change(
      screen.getByLabelText("Effective from (leave blank for now)"),
      { target: { value: "2026-09-01T00:00" } },
    );
    await user.click(screen.getByRole("button", { name: "Confirm publish" }));

    // The component converts the local datetime-local value to a UTC
    // ISO string the same way — comparing against that same conversion
    // keeps this assertion correct regardless of the machine's own
    // timezone (asserting a literal UTC string would break outside
    // whatever offset it was written under).
    await waitFor(() => {
      expect(mocks.publishCustomerRewardRule).toHaveBeenCalledWith(
        "rule-1",
        new Date("2026-09-01T00:00").toISOString(),
      );
    });
  });
});
