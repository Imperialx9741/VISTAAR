import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VehiclesPage } from "./VehiclesPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Vehicle } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchVehicles: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/vehicles",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/people", () => ({
  searchVehicles: mocks.searchVehicles,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const VEHICLE: Vehicle = {
  vehicle_id: "vehicle-1",
  category: "CAB",
  registration_number: "KA01AB1234",
  make: "Maruti",
  model: "Dzire",
  verification_status: "PENDING",
  operational_status: "INACTIVE",
  created_at: "2026-08-10T00:00:00Z",
  updated_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("VehiclesPage", () => {
  it("shows a loading state, then the vehicle list", async () => {
    mocks.searchVehicles.mockResolvedValue({
      items: [VEHICLE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<VehiclesPage />);

    expect(screen.getByText(/Loading Vehicles/)).toBeInTheDocument();
    expect(await screen.findByText("KA01AB1234")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchVehicles.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<VehiclesPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Vehicles.",
      ),
    ).toBeInTheDocument();
  });

  it("shows a distinct Review affordance for PENDING vehicles, not a plain View link", async () => {
    mocks.searchVehicles.mockResolvedValue({
      items: [VEHICLE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<VehiclesPage />);

    expect(await screen.findByRole("link", { name: "Review →" })).toHaveAttribute(
      "href",
      "/vehicles/vehicle-1",
    );
    expect(screen.queryByRole("link", { name: "View" })).not.toBeInTheDocument();
  });

  it("shows a plain View link for a vehicle that isn't PENDING", async () => {
    mocks.searchVehicles.mockResolvedValue({
      items: [{ ...VEHICLE, verification_status: "APPROVED" }],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<VehiclesPage />);

    expect(await screen.findByRole("link", { name: "View" })).toHaveAttribute(
      "href",
      "/vehicles/vehicle-1",
    );
    expect(
      screen.queryByRole("link", { name: "Review →" }),
    ).not.toBeInTheDocument();
  });

  it("re-queries by registration number on submit", async () => {
    const user = userEvent.setup();
    mocks.searchVehicles.mockResolvedValue({
      items: [VEHICLE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<VehiclesPage />);
    await screen.findByText("KA01AB1234");

    await user.type(
      screen.getByLabelText("Search vehicles by registration number"),
      "KA01",
    );
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(mocks.searchVehicles).toHaveBeenLastCalledWith("KA01", "", 1, 20);
  });
});
