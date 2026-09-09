import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DriverWalletPage } from "./DriverWalletPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, DriverWallet, WalletTransaction } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getDriverWallet: vi.fn(),
  listDriverWalletTransactions: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/finance/driver-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/finance", () => ({
  getDriverWallet: mocks.getDriverWallet,
  listDriverWalletTransactions: mocks.listDriverWalletTransactions,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const WALLET: DriverWallet = {
  balance: 500,
  currency: "INR",
  outstanding_settlement: 0,
};

const TRANSACTION: WalletTransaction = {
  transaction_id: "txn-1",
  ride_id: "ride-1",
  transaction_type: "PLATFORM_FEE",
  amount: 10,
  direction: "DEBIT",
  balance_before: 510,
  // Deliberately different from WALLET.balance (500) — both render
  // through the same CURRENCY formatter, so an equal value would make
  // "₹500.00" ambiguous between the wallet summary and this row.
  balance_after: 495,
  reference_type: null,
  reference_id: null,
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("DriverWalletPage", () => {
  it("shows a loading state, then the wallet balance and transactions", async () => {
    mocks.getDriverWallet.mockResolvedValue(WALLET);
    mocks.listDriverWalletTransactions.mockResolvedValue({
      items: [TRANSACTION],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<DriverWalletPage driverId="driver-1" />);

    expect(screen.getByText(/Loading Finance \/ Wallet/)).toBeInTheDocument();
    expect(await screen.findByText("₹500.00")).toBeInTheDocument();
    // "PLATFORM_FEE" also appears as a <select> option (the type
    // filter) — the table cell is unambiguous by role.
    expect(
      screen.getByRole("cell", { name: "PLATFORM_FEE" }),
    ).toBeInTheDocument();
    expect(screen.getByText("DEBIT")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.getDriverWallet.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    mocks.listDriverWalletTransactions.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    render(<DriverWalletPage driverId="driver-1" />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Finance / Wallet.",
      ),
    ).toBeInTheDocument();
  });

  it("re-queries transactions when the type filter changes", async () => {
    const user = userEvent.setup();
    mocks.getDriverWallet.mockResolvedValue(WALLET);
    mocks.listDriverWalletTransactions.mockResolvedValue({
      items: [TRANSACTION],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<DriverWalletPage driverId="driver-1" />);
    await screen.findByRole("cell", { name: "PLATFORM_FEE" });

    await user.selectOptions(
      screen.getByLabelText("Filter by transaction type"),
      "DRIVER_PENALTY",
    );

    expect(mocks.listDriverWalletTransactions).toHaveBeenLastCalledWith(
      "driver-1",
      "DRIVER_PENALTY",
      1,
      20,
    );
  });
});
