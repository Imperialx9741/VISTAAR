import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DriverBonusRuleDetailPage } from "./DriverBonusRuleDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, DriverBonusRule } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getDriverBonusRule: vi.fn(),
  submitDriverBonusRuleForReview: vi.fn(),
  publishDriverBonusRule: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/referrals/rewards/driver-bonus/rule-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/referrals", () => ({
  getDriverBonusRule: mocks.getDriverBonusRule,
  submitDriverBonusRuleForReview: mocks.submitDriverBonusRuleForReview,
  publishDriverBonusRule: mocks.publishDriverBonusRule,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const DRAFT_RULE: DriverBonusRule = {
  rule_id: "rule-1",
  referred_amount: 100,
  referrer_amount: 100,
  status: "DRAFT",
  effective_from: null,
  effective_until: null,
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("DriverBonusRuleDetailPage", () => {
  it("loads and shows the rule's amounts", async () => {
    mocks.getDriverBonusRule.mockResolvedValue(DRAFT_RULE);
    render(<DriverBonusRuleDetailPage ruleId="rule-1" />);

    // Both referred_amount and referrer_amount are 100 in the fixture —
    // two summary cells legitimately show "₹100".
    expect(await screen.findAllByText("₹100")).toHaveLength(2);
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getDriverBonusRule.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No rule found.", 404),
    );
    render(<DriverBonusRuleDetailPage ruleId="unknown" />);

    expect(await screen.findByText("No rule found.")).toBeInTheDocument();
  });

  it("submits for review", async () => {
    const user = userEvent.setup();
    mocks.getDriverBonusRule.mockResolvedValue(DRAFT_RULE);
    mocks.submitDriverBonusRuleForReview.mockResolvedValue({
      ...DRAFT_RULE,
      status: "IN_REVIEW",
    });
    render(<DriverBonusRuleDetailPage ruleId="rule-1" />);

    await user.click(
      await screen.findByRole("button", { name: "Submit for review" }),
    );

    expect(mocks.submitDriverBonusRuleForReview).toHaveBeenCalledWith(
      "rule-1",
    );
    expect(
      await screen.findByText("Submitted for review."),
    ).toBeInTheDocument();
  });

  it("publishes with no effective_from when left blank", async () => {
    const user = userEvent.setup();
    mocks.getDriverBonusRule.mockResolvedValue(DRAFT_RULE);
    mocks.publishDriverBonusRule.mockResolvedValue({
      ...DRAFT_RULE,
      status: "PUBLISHED",
    });
    render(<DriverBonusRuleDetailPage ruleId="rule-1" />);

    await user.click(await screen.findByRole("button", { name: "Publish" }));
    await user.click(screen.getByRole("button", { name: "Confirm publish" }));

    await waitFor(() => {
      expect(mocks.publishDriverBonusRule).toHaveBeenCalledWith(
        "rule-1",
        undefined,
      );
    });
    expect(await screen.findByText("Rule published.")).toBeInTheDocument();
  });
});
