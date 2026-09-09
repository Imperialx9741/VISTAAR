import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FareRuleDetailPage } from "./FareRuleDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, FareRule } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getFareRule: vi.fn(),
  submitFareRuleForReview: vi.fn(),
  publishFareRule: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/fare-management/rule-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/fare-management", () => ({
  getFareRule: mocks.getFareRule,
  submitFareRuleForReview: mocks.submitFareRuleForReview,
  publishFareRule: mocks.publishFareRule,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const DRAFT_RULE: FareRule = {
  rule_id: "rule-1",
  vehicle_category: "CAB_ECO",
  base_fare: 55,
  per_km: 12,
  per_minute: 0,
  waiting_per_minute: 0,
  minimum_fare: 79,
  status: "DRAFT",
  effective_from: null,
  effective_until: null,
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("FareRuleDetailPage", () => {
  it("loads and shows the rule's fields", async () => {
    mocks.getFareRule.mockResolvedValue(DRAFT_RULE);
    render(<FareRuleDetailPage ruleId="rule-1" />);

    expect(await screen.findByText("CAB_ECO")).toBeInTheDocument();
    expect(screen.getByText("DRAFT")).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getFareRule.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No fare rule found.", 404),
    );
    render(<FareRuleDetailPage ruleId="unknown" />);

    expect(
      await screen.findByText("No fare rule found."),
    ).toBeInTheDocument();
  });

  it("offers Submit for review and Publish on a DRAFT rule, and submits for review", async () => {
    const user = userEvent.setup();
    mocks.getFareRule.mockResolvedValue(DRAFT_RULE);
    mocks.submitFareRuleForReview.mockResolvedValue({
      ...DRAFT_RULE,
      status: "IN_REVIEW",
    });
    render(<FareRuleDetailPage ruleId="rule-1" />);

    await screen.findByRole("button", { name: "Submit for review" });
    await user.click(
      screen.getByRole("button", { name: "Submit for review" }),
    );

    expect(mocks.submitFareRuleForReview).toHaveBeenCalledWith("rule-1");
    expect(
      await screen.findByText("Submitted for review."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Submit for review" }),
    ).not.toBeInTheDocument();
  });

  it("publishes with no effective_from when left blank (effective now)", async () => {
    const user = userEvent.setup();
    mocks.getFareRule.mockResolvedValue(DRAFT_RULE);
    mocks.publishFareRule.mockResolvedValue({
      ...DRAFT_RULE,
      status: "PUBLISHED",
      effective_from: "2026-08-28T10:00:00Z",
    });
    render(<FareRuleDetailPage ruleId="rule-1" />);

    await user.click(await screen.findByRole("button", { name: "Publish" }));
    await user.click(screen.getByRole("button", { name: "Confirm publish" }));

    await waitFor(() => {
      expect(mocks.publishFareRule).toHaveBeenCalledWith(
        "rule-1",
        undefined,
      );
    });
    expect(
      await screen.findByText("Fare rule published."),
    ).toBeInTheDocument();
  });

  it("hides both actions once a rule is PUBLISHED", async () => {
    mocks.getFareRule.mockResolvedValue({
      ...DRAFT_RULE,
      status: "PUBLISHED",
      effective_from: "2026-08-28T10:00:00Z",
    });
    render(<FareRuleDetailPage ruleId="rule-1" />);

    await screen.findByText("PUBLISHED");
    expect(
      screen.queryByRole("button", { name: "Submit for review" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Publish" }),
    ).not.toBeInTheDocument();
  });
});
