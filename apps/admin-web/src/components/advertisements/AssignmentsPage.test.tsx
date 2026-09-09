import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssignmentsPage } from "./AssignmentsPage";
import { ApiError } from "@/lib/api/client";
import type { AdAssignment, AdminProfile } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchAdAssignments: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/advertisements/assignments",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/advertisements", () => ({
  searchAdAssignments: mocks.searchAdAssignments,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const ASSIGNMENT: AdAssignment = {
  assignment_id: "assignment-1",
  campaign_id: "campaign-1",
  driver_id: "driver-1",
  status: "PROOF_SUBMITTED",
  proof_uri: "https://example.com/proof.jpg",
  verification_status: "PENDING",
  assigned_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("AssignmentsPage", () => {
  it("shows a loading state, then the assignment list", async () => {
    mocks.searchAdAssignments.mockResolvedValue({
      items: [ASSIGNMENT],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<AssignmentsPage />);

    expect(screen.getByText(/Loading Advertisements/)).toBeInTheDocument();
    expect(await screen.findByText("campaign-1")).toBeInTheDocument();
    expect(screen.getByText("driver-1")).toBeInTheDocument();
    // "PENDING" appears as both the verification-status Pill and a
    // status-filter <select> option — the table cell is unambiguous by
    // role.
    expect(
      screen.getByRole("cell", { name: "PENDING" }),
    ).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchAdAssignments.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<AssignmentsPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Advertisements.",
      ),
    ).toBeInTheDocument();
  });

  it("searches with the entered campaign/driver/status filters", async () => {
    const user = userEvent.setup();
    mocks.searchAdAssignments.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    render(<AssignmentsPage />);
    await screen.findByText("No assignments found.");

    await user.type(
      screen.getByLabelText("Filter by campaign ID"),
      "campaign-9",
    );
    await user.type(screen.getByLabelText("Filter by driver ID"), "driver-9");
    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "VERIFIED",
    );
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(mocks.searchAdAssignments).toHaveBeenLastCalledWith(
      "campaign-9",
      "driver-9",
      "VERIFIED",
      1,
      20,
    );
  });
});
