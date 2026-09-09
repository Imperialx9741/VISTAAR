import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PenaltiesPage } from "./PenaltiesPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Penalty } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchPenalties: vi.fn(),
  resolvePenalty: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/penalties",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/penalties", () => ({
  searchPenalties: mocks.searchPenalties,
  resolvePenalty: mocks.resolvePenalty,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const OUTSTANDING_PENALTY: Penalty = {
  penalty_id: "penalty-1",
  user_id: "user-1",
  ride_id: "ride-1",
  penalty_type: "CUSTOMER_CANCELLATION",
  amount: 50,
  status: "OUTSTANDING",
  issued_at: "2026-08-10T00:00:00Z",
  settled_at: null,
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("PenaltiesPage", () => {
  it("shows a loading state, then the penalty list", async () => {
    mocks.searchPenalties.mockResolvedValue({
      items: [OUTSTANDING_PENALTY],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<PenaltiesPage />);

    expect(screen.getByText(/Loading Penalties/)).toBeInTheDocument();
    expect(await screen.findByText("user-1")).toBeInTheDocument();
    expect(screen.getByText("₹50.00")).toBeInTheDocument();
    // "OUTSTANDING" also appears as a <select> option (the status
    // filter) — the table cell is unambiguous by role.
    expect(
      screen.getByRole("cell", { name: "OUTSTANDING" }),
    ).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchPenalties.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<PenaltiesPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Penalties / Strikes.",
      ),
    ).toBeInTheDocument();
  });

  it("waives an outstanding penalty with the entered reason", async () => {
    const user = userEvent.setup();
    mocks.searchPenalties.mockResolvedValue({
      items: [OUTSTANDING_PENALTY],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    mocks.resolvePenalty.mockResolvedValue({
      ...OUTSTANDING_PENALTY,
      status: "WAIVED",
    });
    render(<PenaltiesPage />);

    await user.click(await screen.findByRole("button", { name: "Waive" }));
    await user.type(
      screen.getByLabelText("Waive reason"),
      "Goodwill gesture",
    );

    mocks.searchPenalties.mockResolvedValueOnce({
      items: [{ ...OUTSTANDING_PENALTY, status: "WAIVED" }],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });

    await user.click(screen.getByRole("button", { name: "Confirm waive" }));

    expect(mocks.resolvePenalty).toHaveBeenCalledWith(
      "penalty-1",
      "Goodwill gesture",
    );
    expect(
      await screen.findByText("Penalty penalty-1 waived."),
    ).toBeInTheDocument();
  });

  it("shows no Waive action once a penalty is no longer OUTSTANDING", async () => {
    mocks.searchPenalties.mockResolvedValue({
      items: [{ ...OUTSTANDING_PENALTY, status: "SETTLED" }],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<PenaltiesPage />);

    await screen.findByText("user-1");
    expect(
      screen.queryByRole("button", { name: "Waive" }),
    ).not.toBeInTheDocument();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.searchPenalties.mockResolvedValue({
      items: [OUTSTANDING_PENALTY],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<PenaltiesPage />);
    await screen.findByText("user-1");

    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "WAIVED",
    );

    expect(mocks.searchPenalties).toHaveBeenLastCalledWith(
      "WAIVED",
      "",
      1,
      20,
    );
  });
});
