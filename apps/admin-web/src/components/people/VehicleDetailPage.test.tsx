import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VehicleDetailPage } from "./VehicleDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Vehicle, VehicleDocument } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getVehicle: vi.fn(),
  listVehicleDocuments: vi.fn(),
  approveVehicle: vi.fn(),
  rejectVehicle: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/vehicles/vehicle-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/people", () => ({
  getVehicle: mocks.getVehicle,
  listVehicleDocuments: mocks.listVehicleDocuments,
  approveVehicle: mocks.approveVehicle,
  rejectVehicle: mocks.rejectVehicle,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const PENDING_VEHICLE: Vehicle = {
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

const DOCUMENT: VehicleDocument = {
  document_id: "vdoc-1",
  vehicle_id: "vehicle-1",
  document_type: "REGISTRATION_CERTIFICATE",
  document_number: "RC12345",
  evidence_uri: "https://example.test/rc.pdf",
  verification_status: "PENDING",
  expires_at: null,
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
  mocks.listVehicleDocuments.mockResolvedValue([DOCUMENT]);
});

describe("VehicleDetailPage", () => {
  it("loads and shows the vehicle and its documents", async () => {
    mocks.getVehicle.mockResolvedValue(PENDING_VEHICLE);
    render(<VehicleDetailPage vehicleId="vehicle-1" />);

    expect(await screen.findByText("KA01AB1234")).toBeInTheDocument();
    expect(await screen.findByText("REGISTRATION_CERTIFICATE")).toBeInTheDocument();
  });

  it("shows a real error banner when the vehicle load fails", async () => {
    mocks.getVehicle.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No vehicle found.", 404),
    );
    render(<VehicleDetailPage vehicleId="unknown" />);

    expect(await screen.findByText("No vehicle found.")).toBeInTheDocument();
  });

  it("shows a scoped error for documents without blanking the vehicle summary", async () => {
    mocks.getVehicle.mockResolvedValue(PENDING_VEHICLE);
    mocks.listVehicleDocuments.mockRejectedValue(
      new ApiError("FORBIDDEN", "no verification access", 403),
    );
    render(<VehicleDetailPage vehicleId="vehicle-1" />);

    expect(await screen.findByText("KA01AB1234")).toBeInTheDocument();
    expect(await screen.findByText("no verification access")).toBeInTheDocument();
  });

  it("approves a pending vehicle", async () => {
    const user = userEvent.setup();
    mocks.getVehicle.mockResolvedValue(PENDING_VEHICLE);
    mocks.approveVehicle.mockResolvedValue({
      ...PENDING_VEHICLE,
      verification_status: "APPROVED",
    });
    render(<VehicleDetailPage vehicleId="vehicle-1" />);

    await user.click(await screen.findByRole("button", { name: "Approve" }));

    expect(mocks.approveVehicle).toHaveBeenCalledWith("vehicle-1");
    expect(await screen.findByText("Vehicle approved.")).toBeInTheDocument();
  });
});
