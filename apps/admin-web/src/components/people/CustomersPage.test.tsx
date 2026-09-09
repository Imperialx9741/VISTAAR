import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CustomersPage } from "./CustomersPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, CustomerSummary } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchCustomers: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/customers",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/people", () => ({
  searchCustomers: mocks.searchCustomers,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const CUSTOMER: CustomerSummary = {
  customer_id: "cust-1",
  full_name: "Asha Rao",
  profile_photo_uri: null,
  status: "ACTIVE",
  language: "en",
  created_at: "2026-08-10T00:00:00Z",
  updated_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("CustomersPage", () => {
  it("shows a loading state, then the customer list", async () => {
    mocks.searchCustomers.mockResolvedValue({
      items: [CUSTOMER],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<CustomersPage />);

    expect(screen.getByText(/Loading Customers/)).toBeInTheDocument();
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchCustomers.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<CustomersPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Customers.",
      ),
    ).toBeInTheDocument();
  });

  it("searches by name on submit", async () => {
    const user = userEvent.setup();
    mocks.searchCustomers.mockResolvedValue({
      items: [CUSTOMER],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<CustomersPage />);
    await screen.findByText("Asha Rao");

    await user.type(
      screen.getByLabelText("Search customers by name"),
      "Asha",
    );
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(mocks.searchCustomers).toHaveBeenLastCalledWith("Asha", 1, 20);
  });
});
