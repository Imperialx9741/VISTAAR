import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SafetyPage } from "./SafetyPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, SafetyIncident } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchSafetyIncidents: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/safety",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/safety-support", () => ({
  searchSafetyIncidents: mocks.searchSafetyIncidents,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const INCIDENT: SafetyIncident = {
  incident_id: "incident-1",
  ride_id: "ride-1",
  reporter_id: "customer-1",
  incident_type: "OTHER",
  status: "OPEN",
  location: { latitude: 25.5941, longitude: 85.1376 },
  created_at: "2026-08-10T00:00:00Z",
  resolved_at: null,
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("SafetyPage", () => {
  it("shows a loading state, then the incident list", async () => {
    mocks.searchSafetyIncidents.mockResolvedValue({
      items: [INCIDENT],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<SafetyPage />);

    expect(screen.getByText(/Loading Safety \/ SOS/)).toBeInTheDocument();
    expect(await screen.findByText("incident-1")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "OPEN" })).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchSafetyIncidents.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<SafetyPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Safety / SOS.",
      ),
    ).toBeInTheDocument();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.searchSafetyIncidents.mockResolvedValue({
      items: [INCIDENT],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<SafetyPage />);
    await screen.findByText("incident-1");

    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "RESOLVED",
    );

    expect(mocks.searchSafetyIncidents).toHaveBeenLastCalledWith(
      "RESOLVED",
      1,
      20,
    );
  });
});
