import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlatformFeeRulesPage } from "./PlatformFeeRulesPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, PlatformFeeRule } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  listPlatformFeeRules: vi.fn(),
  createPlatformFeeRule: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/fare-management/platform-fee",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/platform-fee", () => ({
  listPlatformFeeRules: mocks.listPlatformFeeRules,
  createPlatformFeeRule: mocks.createPlatformFeeRule,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const RULE: PlatformFeeRule = {
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

describe("PlatformFeeRulesPage", () => {
  it("shows a loading state, then the platform fee rule list", async () => {
    mocks.listPlatformFeeRules.mockResolvedValue({
      items: [RULE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<PlatformFeeRulesPage />);

    expect(
      screen.getByText(/Loading Platform Fee Management/),
    ).toBeInTheDocument();
    // "CAB" also appears as a <select> option (the category filter) —
    // the table cell is a bare <td>, unambiguous by role.
    expect(
      await screen.findByRole("cell", { name: "CAB" }),
    ).toBeInTheDocument();
    // Same reasoning — "DRAFT" is also a status-filter <select> option.
    expect(screen.getByRole("cell", { name: "DRAFT" })).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.listPlatformFeeRules.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<PlatformFeeRulesPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Platform Fee Management.",
      ),
    ).toBeInTheDocument();
  });

  it("creates a draft platform fee rule and refreshes the list", async () => {
    const user = userEvent.setup();
    mocks.listPlatformFeeRules.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    mocks.createPlatformFeeRule.mockResolvedValue(RULE);

    render(<PlatformFeeRulesPage />);
    await screen.findByText("No platform fee rules found.");

    await user.click(screen.getByRole("button", { name: "+ Create draft" }));
    await user.type(screen.getByLabelText("Fee amount (₹)"), "10");

    mocks.listPlatformFeeRules.mockResolvedValueOnce({
      items: [RULE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });

    await user.click(screen.getByRole("button", { name: "Create draft" }));

    expect(mocks.createPlatformFeeRule).toHaveBeenCalledWith({
      vehicle_category: "CAB",
      fee_amount: 10,
    });
    expect(
      await screen.findByText(/Created a DRAFT CAB rule/),
    ).toBeInTheDocument();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.listPlatformFeeRules.mockResolvedValue({
      items: [RULE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<PlatformFeeRulesPage />);
    await screen.findByRole("cell", { name: "CAB" });

    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "PUBLISHED",
    );

    expect(mocks.listPlatformFeeRules).toHaveBeenLastCalledWith(
      "",
      "PUBLISHED",
      1,
      20,
    );
  });
});
