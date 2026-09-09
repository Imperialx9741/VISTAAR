import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssignmentDetailPage } from "./AssignmentDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdAssignment, AdminProfile, AdPayout } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getAdAssignment: vi.fn(),
  verifyAdAssignment: vi.fn(),
  calculateAdPayout: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/advertisements/assignments/assignment-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/advertisements", () => ({
  getAdAssignment: mocks.getAdAssignment,
  verifyAdAssignment: mocks.verifyAdAssignment,
  calculateAdPayout: mocks.calculateAdPayout,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const PROOF_SUBMITTED_ASSIGNMENT: AdAssignment = {
  assignment_id: "assignment-1",
  campaign_id: "campaign-1",
  driver_id: "driver-1",
  status: "PROOF_SUBMITTED",
  proof_uri: "https://example.com/proof.jpg",
  verification_status: "PENDING",
  assigned_at: "2026-08-10T00:00:00Z",
};

const PAYOUT: AdPayout = {
  payout_id: "payout-1",
  driver_campaign_id: "assignment-1",
  gross_amount: 500,
  driver_amount: 400,
  vistaar_amount: 100,
  status: "PENDING",
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("AssignmentDetailPage", () => {
  it("loads and shows the assignment's fields, incl. the proof link", async () => {
    mocks.getAdAssignment.mockResolvedValue(PROOF_SUBMITTED_ASSIGNMENT);
    render(<AssignmentDetailPage assignmentId="assignment-1" />);

    expect(await screen.findByText("campaign-1")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "View submitted proof →" }),
    ).toHaveAttribute("href", "https://example.com/proof.jpg");
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getAdAssignment.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No assignment found.", 404),
    );
    render(<AssignmentDetailPage assignmentId="unknown" />);

    expect(
      await screen.findByText("No assignment found."),
    ).toBeInTheDocument();
  });

  it("approves proof on a PROOF_SUBMITTED assignment", async () => {
    const user = userEvent.setup();
    mocks.getAdAssignment.mockResolvedValue(PROOF_SUBMITTED_ASSIGNMENT);
    mocks.verifyAdAssignment.mockResolvedValue({
      ...PROOF_SUBMITTED_ASSIGNMENT,
      status: "VERIFIED",
      verification_status: "APPROVED",
    });
    render(<AssignmentDetailPage assignmentId="assignment-1" />);

    await user.click(
      await screen.findByRole("button", { name: "Approve proof" }),
    );

    expect(mocks.verifyAdAssignment).toHaveBeenCalledWith(
      "assignment-1",
      true,
    );
    expect(await screen.findByText("Proof approved.")).toBeInTheDocument();
  });

  it("calculates a payout on a VERIFIED assignment and shows it", async () => {
    const user = userEvent.setup();
    mocks.getAdAssignment.mockResolvedValue({
      ...PROOF_SUBMITTED_ASSIGNMENT,
      status: "VERIFIED",
      verification_status: "APPROVED",
    });
    mocks.calculateAdPayout.mockResolvedValue(PAYOUT);
    render(<AssignmentDetailPage assignmentId="assignment-1" />);

    await user.click(
      await screen.findByRole("button", { name: "Calculate payout" }),
    );

    expect(mocks.calculateAdPayout).toHaveBeenCalledWith("assignment-1");
    expect(await screen.findByText("Payout calculated.")).toBeInTheDocument();
    expect(screen.getByText("₹400.00")).toBeInTheDocument();
  });
});
