import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FinanceLookupPage } from "./FinanceLookupPage";
import type { AdminProfile } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/finance",
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("FinanceLookupPage", () => {
  it("shows a loading state, then the lookup form", async () => {
    render(<FinanceLookupPage />);

    expect(screen.getByText(/Loading Finance \/ Wallet/)).toBeInTheDocument();
    expect(await screen.findByLabelText("Driver ID")).toBeInTheDocument();
  });

  it("disables the button until a driver ID is entered", async () => {
    render(<FinanceLookupPage />);

    expect(
      await screen.findByRole("button", { name: "View wallet" }),
    ).toBeDisabled();
  });

  it("navigates to that driver's wallet on submit", async () => {
    const user = userEvent.setup();
    render(<FinanceLookupPage />);

    await user.type(await screen.findByLabelText("Driver ID"), "driver-1");
    await user.click(screen.getByRole("button", { name: "View wallet" }));

    expect(mocks.push).toHaveBeenCalledWith("/finance/driver-1");
  });
});
