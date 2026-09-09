import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GpsDisputeDetailPage } from "./GpsDisputeDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, GpsDispute } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getGpsDispute: vi.fn(),
  resolveGpsDispute: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/support/gps-disputes/dispute-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/safety-support", () => ({
  getGpsDispute: mocks.getGpsDispute,
  resolveGpsDispute: mocks.resolveGpsDispute,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const OPEN_DISPUTE: GpsDispute = {
  dispute_id: "dispute-1",
  ride_id: "ride-1",
  gps_verification_id: "verification-1",
  verification_type: "ARRIVAL",
  opened_at: "2026-08-10T00:00:00Z",
  evidence_deadline: "2026-08-11T00:00:00Z",
  status: "OPEN",
  decision: null,
  decided_by: null,
  decided_reason: null,
  decided_at: null,
  evidence: [
    {
      submitted_by: "customer-1",
      evidence_type: "TEXT",
      uri: null,
      text_explanation: "I was standing at the gate.",
      submitted_at: "2026-08-10T01:00:00Z",
    },
  ],
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("GpsDisputeDetailPage", () => {
  it("loads and shows the dispute's fields and evidence", async () => {
    mocks.getGpsDispute.mockResolvedValue(OPEN_DISPUTE);
    render(<GpsDisputeDetailPage disputeId="dispute-1" />);

    expect(await screen.findByText("ride-1")).toBeInTheDocument();
    expect(screen.getByText("TEXT")).toBeInTheDocument();
    expect(
      screen.getByText("I was standing at the gate."),
    ).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getGpsDispute.mockRejectedValue(
      new ApiError("RIDE_NOT_FOUND", "GPS dispute not found.", 404),
    );
    render(<GpsDisputeDetailPage disputeId="unknown" />);

    expect(
      await screen.findByText("GPS dispute not found."),
    ).toBeInTheDocument();
  });

  it("requires a reason before Confirm approve is enabled, then approves", async () => {
    const user = userEvent.setup();
    mocks.getGpsDispute.mockResolvedValue(OPEN_DISPUTE);
    mocks.resolveGpsDispute.mockResolvedValue({
      ...OPEN_DISPUTE,
      status: "RESOLVED",
      decision: "APPROVE",
      decided_reason: "Evidence supports the driver's location.",
    });
    render(<GpsDisputeDetailPage disputeId="dispute-1" />);

    await user.click(await screen.findByRole("button", { name: "Approve" }));
    expect(
      screen.getByRole("button", { name: "Confirm approve" }),
    ).toBeDisabled();

    await user.type(
      screen.getByLabelText("Decision reason"),
      "Evidence supports the driver's location.",
    );
    await user.click(screen.getByRole("button", { name: "Confirm approve" }));

    expect(mocks.resolveGpsDispute).toHaveBeenCalledWith(
      "dispute-1",
      "APPROVE",
      "Evidence supports the driver's location.",
    );
    expect(await screen.findByText("Dispute approved.")).toBeInTheDocument();
  });

  it("hides Approve/Reject once the dispute is no longer OPEN", async () => {
    mocks.getGpsDispute.mockResolvedValue({
      ...OPEN_DISPUTE,
      status: "RESOLVED",
      decision: "REJECT",
      decided_reason: "GPS log confirms the mismatch.",
    });
    render(<GpsDisputeDetailPage disputeId="dispute-1" />);

    await screen.findByText("ride-1");
    expect(
      screen.queryByRole("button", { name: "Approve" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Reject" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("REJECT — GPS log confirms the mismatch."),
    ).toBeInTheDocument();
  });

  it("shows an empty state when no evidence has been submitted", async () => {
    mocks.getGpsDispute.mockResolvedValue({ ...OPEN_DISPUTE, evidence: [] });
    render(<GpsDisputeDetailPage disputeId="dispute-1" />);

    expect(
      await screen.findByText("No evidence submitted yet."),
    ).toBeInTheDocument();
  });
});
