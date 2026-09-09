import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DashboardPage } from "./DashboardPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, AuditLogEntry, DashboardSummary } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getDashboardSummary: vi.fn(),
  getAdminProfile: vi.fn(),
  getRecentAuditLog: vi.fn(),
}));

vi.mock("@/lib/api/dashboard", () => ({
  getDashboardSummary: mocks.getDashboardSummary,
  getAdminProfile: mocks.getAdminProfile,
  getRecentAuditLog: mocks.getRecentAuditLog,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

// Real, non-zero backend numbers — deliberately NOT the hardcoded
// SAMPLE_DASHBOARD_SUMMARY set that used to live in mock-data.ts
// (7 / 4 / 1 / 12 / 2 / 18 / 18650) — a test that used those exact
// numbers wouldn't be able to tell "real API response" apart from
// "the fallback fired again by accident."
const REAL_SUMMARY: DashboardSummary = {
  pending_driver_approvals: 3,
  pending_vehicle_approvals: 9,
  open_gps_disputes: 5,
  open_sos_incidents: 6,
  open_support_cases: 27,
  outstanding_penalties: 41,
  platform_fee_collected_today: 9412,
  rides_today_by_status: { COMPLETED: 3 },
  online_drivers: 8,
};

const EMPTY_SUMMARY: DashboardSummary = {
  pending_driver_approvals: 0,
  pending_vehicle_approvals: 0,
  open_gps_disputes: 0,
  open_sos_incidents: 0,
  open_support_cases: 0,
  outstanding_penalties: 0,
  platform_fee_collected_today: 0,
  rides_today_by_status: {},
  online_drivers: 0,
};

const AUDIT_LOG: AuditLogEntry[] = [];

describe("DashboardPage", () => {
  it("shows real backend numbers, not the old hardcoded sample set", async () => {
    mocks.getDashboardSummary.mockResolvedValue(REAL_SUMMARY);
    mocks.getAdminProfile.mockResolvedValue(PROFILE);
    mocks.getRecentAuditLog.mockResolvedValue(AUDIT_LOG);

    render(<DashboardPage />);

    expect(await screen.findByText("9")).toBeInTheDocument(); // pending vehicle approvals
    expect(screen.getByText("27")).toBeInTheDocument(); // open support cases
    expect(screen.getByText("41")).toBeInTheDocument(); // outstanding penalties
    // None of the old sample-only figures (7, 12, 18650) appear.
    expect(screen.queryByText("7")).not.toBeInTheDocument();
    expect(screen.queryByText("12")).not.toBeInTheDocument();
  });

  it("shows a real zero/empty state, not fake nonzero fallback numbers", async () => {
    mocks.getDashboardSummary.mockResolvedValue(EMPTY_SUMMARY);
    mocks.getAdminProfile.mockResolvedValue(PROFILE);
    mocks.getRecentAuditLog.mockResolvedValue(AUDIT_LOG);

    render(<DashboardPage />);

    // Every stat card genuinely reads 0 — appears 7 times (one per
    // zero-valued numeric stat card; platform fee is currency-formatted
    // separately).
    expect((await screen.findAllByText("0")).length).toBeGreaterThanOrEqual(7);
  });

  it("shows a real error state when the API fails — never fake business data", async () => {
    mocks.getDashboardSummary.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No admin profile exists for this account.", 404),
    );
    mocks.getAdminProfile.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No admin profile exists for this account.", 404),
    );
    mocks.getRecentAuditLog.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No admin profile exists for this account.", 404),
    );

    render(<DashboardPage />);

    expect(
      await screen.findByText(
        "Something went wrong loading the dashboard. Try reloading.",
      ),
    ).toBeInTheDocument();
    // None of the old hardcoded sample numbers ever render.
    expect(screen.queryByText("18,650")).not.toBeInTheDocument();
    expect(screen.queryByText("7")).not.toBeInTheDocument();
  });
});
