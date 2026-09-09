import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DriverDetailPage } from "./DriverDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, DriverDetail } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getDriver: vi.fn(),
  approveDriver: vi.fn(),
  rejectDriver: vi.fn(),
  suspendDriver: vi.fn(),
  reactivateDriver: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/drivers/driver-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/people", () => ({
  getDriver: mocks.getDriver,
  approveDriver: mocks.approveDriver,
  rejectDriver: mocks.rejectDriver,
  suspendDriver: mocks.suspendDriver,
  reactivateDriver: mocks.reactivateDriver,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const PENDING_DRIVER: DriverDetail = {
  driver_id: "driver-1",
  phone: "+919876543210",
  full_name: "Ravi Kumar",
  profile_photo_uri: null,
  verification_status: "PENDING",
  operational_status: "OFFLINE",
  strikes: 0,
  created_at: "2026-08-10T00:00:00Z",
  updated_at: "2026-08-10T00:00:00Z",
  documents: [
    {
      document_id: "doc-1",
      document_type: "DRIVING_LICENSE",
      verification_status: "PENDING",
      verification_cases: [{ case_id: "case-1", status: "PENDING" }],
    },
  ],
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("DriverDetailPage", () => {
  it("loads and shows the driver's profile and documents", async () => {
    mocks.getDriver.mockResolvedValue(PENDING_DRIVER);
    render(<DriverDetailPage driverId="driver-1" />);

    expect(await screen.findByText("Ravi Kumar")).toBeInTheDocument();
    expect(screen.getByText("DRIVING_LICENSE")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "View history →" }),
    ).toHaveAttribute("href", "/drivers/driver-1/strikes");
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getDriver.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No driver found.", 404),
    );
    render(<DriverDetailPage driverId="unknown" />);

    expect(await screen.findByText("No driver found.")).toBeInTheDocument();
  });

  it("shows Approve/Reject only while verification is PENDING, and approves", async () => {
    const user = userEvent.setup();
    mocks.getDriver.mockResolvedValue(PENDING_DRIVER);
    mocks.approveDriver.mockResolvedValue({
      ...PENDING_DRIVER,
      verification_status: "APPROVED",
    });
    render(<DriverDetailPage driverId="driver-1" />);

    const approveButton = await screen.findByRole("button", {
      name: "Approve",
    });
    await user.click(approveButton);

    expect(mocks.approveDriver).toHaveBeenCalledWith("driver-1");
    expect(await screen.findByText("Driver approved.")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve" }),
    ).not.toBeInTheDocument();
  });

  it("rejects with the entered reason", async () => {
    const user = userEvent.setup();
    mocks.getDriver.mockResolvedValue(PENDING_DRIVER);
    mocks.rejectDriver.mockResolvedValue({
      ...PENDING_DRIVER,
      verification_status: "REJECTED",
    });
    render(<DriverDetailPage driverId="driver-1" />);

    await user.click(await screen.findByRole("button", { name: "Reject" }));
    await user.type(
      screen.getByLabelText("Rejection reason"),
      "Blurry document",
    );
    await user.click(screen.getByRole("button", { name: "Confirm reject" }));

    await waitFor(() => {
      expect(mocks.rejectDriver).toHaveBeenCalledWith(
        "driver-1",
        "Blurry document",
      );
    });
  });

  it("suspends an OFFLINE driver and then offers Reactivate", async () => {
    const user = userEvent.setup();
    mocks.getDriver.mockResolvedValue(PENDING_DRIVER);
    mocks.suspendDriver.mockResolvedValue({
      driver_id: "driver-1",
      full_name: "Ravi Kumar",
      profile_photo_uri: null,
      verification_status: "PENDING",
      operational_status: "SUSPENDED",
      strikes: 0,
      created_at: "2026-08-10T00:00:00Z",
    });
    render(<DriverDetailPage driverId="driver-1" />);

    await user.click(await screen.findByRole("button", { name: "Suspend" }));
    await user.click(screen.getByRole("button", { name: "Confirm suspend" }));

    await waitFor(() => {
      expect(mocks.suspendDriver).toHaveBeenCalledWith("driver-1", "");
    });
    expect(
      await screen.findByRole("button", { name: "Reactivate" }),
    ).toBeInTheDocument();
  });
});
