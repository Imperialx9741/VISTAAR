import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { CustomerDetailPage } from "./CustomerDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, CustomerDetail } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getCustomer: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/customers/cust-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/people", () => ({
  getCustomer: mocks.getCustomer,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const CUSTOMER: CustomerDetail = {
  customer_id: "cust-1",
  full_name: "Asha Rao",
  profile_photo_uri: null,
  status: "ACTIVE",
  language: "en",
  created_at: "2026-08-10T00:00:00Z",
  updated_at: "2026-08-10T00:00:00Z",
  phone: "+919876543210",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("CustomerDetailPage", () => {
  it("loads and shows the customer's name, phone, and status", async () => {
    mocks.getCustomer.mockResolvedValue(CUSTOMER);
    render(<CustomerDetailPage customerId="cust-1" />);

    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
    expect(screen.getByText("+919876543210")).toBeInTheDocument();
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getCustomer.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No customer found.", 404),
    );
    render(<CustomerDetailPage customerId="unknown" />);

    expect(await screen.findByText("No customer found.")).toBeInTheDocument();
  });
});
