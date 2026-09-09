import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FareRulesPage } from "./FareRulesPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, FareRule } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  listFareRules: vi.fn(),
  createFareRule: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/fare-management",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/fare-management", () => ({
  listFareRules: mocks.listFareRules,
  createFareRule: mocks.createFareRule,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const RULE: FareRule = {
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

describe("FareRulesPage", () => {
  it("shows a loading state, then the fare rule list", async () => {
    mocks.listFareRules.mockResolvedValue({
      items: [RULE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<FareRulesPage />);

    expect(screen.getByText(/Loading Fare Management/)).toBeInTheDocument();
    // "CAB_ECO" also appears as a <select> option (the category filter)
    // — the table cell is a bare <td>, unambiguous by role.
    expect(
      await screen.findByRole("cell", { name: "CAB_ECO" }),
    ).toBeInTheDocument();
    // Same reasoning — "DRAFT" is also a status-filter <select> option.
    expect(screen.getByRole("cell", { name: "DRAFT" })).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.listFareRules.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<FareRulesPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Fare Management.",
      ),
    ).toBeInTheDocument();
  });

  it("creates a draft fare rule and refreshes the list", async () => {
    const user = userEvent.setup();
    mocks.listFareRules.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    mocks.createFareRule.mockResolvedValue(RULE);

    render(<FareRulesPage />);
    await screen.findByText("No fare rules found.");

    await user.click(screen.getByRole("button", { name: "+ Create draft" }));
    await user.type(screen.getByLabelText("Base fare (₹)"), "55");
    await user.type(screen.getByLabelText("Per km (₹)"), "12");
    await user.type(screen.getByLabelText("Minimum fare (₹)"), "79");

    mocks.listFareRules.mockResolvedValueOnce({
      items: [RULE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });

    await user.click(screen.getByRole("button", { name: "Create draft" }));

    expect(mocks.createFareRule).toHaveBeenCalledWith({
      vehicle_category: "CAB_ECO",
      base_fare: 55,
      per_km: 12,
      per_minute: 0,
      waiting_per_minute: 0,
      minimum_fare: 79,
    });
    expect(
      await screen.findByText(/Created a DRAFT CAB_ECO rule/),
    ).toBeInTheDocument();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.listFareRules.mockResolvedValue({
      items: [RULE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<FareRulesPage />);
    await screen.findByRole("cell", { name: "CAB_ECO" });

    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "PUBLISHED",
    );

    expect(mocks.listFareRules).toHaveBeenLastCalledWith(
      "",
      "PUBLISHED",
      1,
      20,
    );
  });
});
