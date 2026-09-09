import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SupportPage } from "./SupportPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, SupportCaseSummary } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchSupportCases: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/support",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/safety-support", () => ({
  searchSupportCases: mocks.searchSupportCases,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const CASE: SupportCaseSummary = {
  case_id: "case-1",
  user_id: "customer-1",
  ride_id: null,
  category: "BILLING",
  priority: "NORMAL",
  status: "OPEN",
  assigned_admin_id: null,
  created_at: "2026-08-10T00:00:00Z",
  updated_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("SupportPage", () => {
  it("shows a loading state, then the case list", async () => {
    mocks.searchSupportCases.mockResolvedValue({
      items: [CASE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<SupportPage />);

    expect(screen.getByText(/Loading Support \/ Disputes/)).toBeInTheDocument();
    expect(await screen.findByText("case-1")).toBeInTheDocument();
    expect(screen.getByText("NORMAL")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "GPS Disputes →" }),
    ).toHaveAttribute("href", "/support/gps-disputes");
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchSupportCases.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<SupportPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Support / Disputes.",
      ),
    ).toBeInTheDocument();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.searchSupportCases.mockResolvedValue({
      items: [CASE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<SupportPage />);
    await screen.findByText("case-1");

    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "RESOLVED",
    );

    expect(mocks.searchSupportCases).toHaveBeenLastCalledWith(
      "RESOLVED",
      1,
      20,
    );
  });
});
