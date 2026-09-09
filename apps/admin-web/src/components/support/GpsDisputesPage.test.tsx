import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GpsDisputesPage } from "./GpsDisputesPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, GpsDispute } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchGpsDisputes: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/support/gps-disputes",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/safety-support", () => ({
  searchGpsDisputes: mocks.searchGpsDisputes,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const DISPUTE: GpsDispute = {
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
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("GpsDisputesPage", () => {
  it("shows a loading state, then the dispute list", async () => {
    mocks.searchGpsDisputes.mockResolvedValue({
      items: [DISPUTE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<GpsDisputesPage />);

    expect(screen.getByText(/Loading Support/)).toBeInTheDocument();
    expect(await screen.findByText("ride-1")).toBeInTheDocument();
    expect(screen.getByText("ARRIVAL")).toBeInTheDocument();
    // "OPEN" also appears as a <select> option (the status filter) —
    // the table cell is unambiguous by role.
    expect(screen.getByRole("cell", { name: "OPEN" })).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchGpsDisputes.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<GpsDisputesPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Support / Disputes.",
      ),
    ).toBeInTheDocument();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.searchGpsDisputes.mockResolvedValue({
      items: [DISPUTE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<GpsDisputesPage />);
    await screen.findByText("ride-1");

    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "RESOLVED",
    );

    expect(mocks.searchGpsDisputes).toHaveBeenLastCalledWith("RESOLVED", 1, 20);
  });
});
