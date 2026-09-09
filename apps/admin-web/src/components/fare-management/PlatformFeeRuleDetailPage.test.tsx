import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlatformFeeRuleDetailPage } from "./PlatformFeeRuleDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, PlatformFeeRule } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getPlatformFeeRule: vi.fn(),
  submitPlatformFeeRuleForReview: vi.fn(),
  publishPlatformFeeRule: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/fare-management/platform-fee/rule-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/platform-fee", () => ({
  getPlatformFeeRule: mocks.getPlatformFeeRule,
  submitPlatformFeeRuleForReview: mocks.submitPlatformFeeRuleForReview,
  publishPlatformFeeRule: mocks.publishPlatformFeeRule,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const DRAFT_RULE: PlatformFeeRule = {
  rule_id: "rule-1",
  vehicle_category: "CAB",
  fee_amount: 10,
  status: "DRAFT",
  effective_from: null,
  effective_until: null,
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("PlatformFeeRuleDetailPage", () => {
  it("loads and shows the rule's fields", async () => {
    mocks.getPlatformFeeRule.mockResolvedValue(DRAFT_RULE);
    render(<PlatformFeeRuleDetailPage ruleId="rule-1" />);

    expect(await screen.findByText("CAB")).toBeInTheDocument();
    expect(screen.getByText("DRAFT")).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getPlatformFeeRule.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No platform fee rule found.", 404),
    );
    render(<PlatformFeeRuleDetailPage ruleId="unknown" />);

    expect(
      await screen.findByText("No platform fee rule found."),
    ).toBeInTheDocument();
  });

  it("offers Submit for review and Publish on a DRAFT rule, and submits for review", async () => {
    const user = userEvent.setup();
    mocks.getPlatformFeeRule.mockResolvedValue(DRAFT_RULE);
    mocks.submitPlatformFeeRuleForReview.mockResolvedValue({
      ...DRAFT_RULE,
      status: "IN_REVIEW",
    });
    render(<PlatformFeeRuleDetailPage ruleId="rule-1" />);

    await screen.findByRole("button", { name: "Submit for review" });
    await user.click(
      screen.getByRole("button", { name: "Submit for review" }),
    );

    expect(mocks.submitPlatformFeeRuleForReview).toHaveBeenCalledWith(
      "rule-1",
    );
    expect(
      await screen.findByText("Submitted for review."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Submit for review" }),
    ).not.toBeInTheDocument();
  });

  it("publishes with no effective_from when left blank (effective now)", async () => {
    const user = userEvent.setup();
    mocks.getPlatformFeeRule.mockResolvedValue(DRAFT_RULE);
    mocks.publishPlatformFeeRule.mockResolvedValue({
      ...DRAFT_RULE,
      status: "PUBLISHED",
      effective_from: "2026-08-28T10:00:00Z",
    });
    render(<PlatformFeeRuleDetailPage ruleId="rule-1" />);

    await user.click(await screen.findByRole("button", { name: "Publish" }));
    await user.click(screen.getByRole("button", { name: "Confirm publish" }));

    await waitFor(() => {
      expect(mocks.publishPlatformFeeRule).toHaveBeenCalledWith(
        "rule-1",
        undefined,
      );
    });
    expect(
      await screen.findByText("Platform fee rule published."),
    ).toBeInTheDocument();
  });

  it("hides both actions once a rule is PUBLISHED", async () => {
    mocks.getPlatformFeeRule.mockResolvedValue({
      ...DRAFT_RULE,
      status: "PUBLISHED",
      effective_from: "2026-08-28T10:00:00Z",
    });
    render(<PlatformFeeRuleDetailPage ruleId="rule-1" />);

    await screen.findByText("PUBLISHED");
    expect(
      screen.queryByRole("button", { name: "Submit for review" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Publish" }),
    ).not.toBeInTheDocument();
  });
});
