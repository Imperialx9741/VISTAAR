import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IncidentDetailPage } from "./IncidentDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, SafetyIncident } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getSafetyIncident: vi.fn(),
  acknowledgeSafetyIncident: vi.fn(),
  escalateSafetyIncident: vi.fn(),
  resolveSafetyIncident: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/safety/incident-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/safety-support", () => ({
  getSafetyIncident: mocks.getSafetyIncident,
  acknowledgeSafetyIncident: mocks.acknowledgeSafetyIncident,
  escalateSafetyIncident: mocks.escalateSafetyIncident,
  resolveSafetyIncident: mocks.resolveSafetyIncident,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const OPEN_INCIDENT: SafetyIncident = {
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

describe("IncidentDetailPage", () => {
  it("loads and shows the incident's fields", async () => {
    mocks.getSafetyIncident.mockResolvedValue(OPEN_INCIDENT);
    render(<IncidentDetailPage incidentId="incident-1" />);

    expect(await screen.findByText("OTHER")).toBeInTheDocument();
    expect(screen.getByText("25.5941, 85.1376")).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getSafetyIncident.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No incident found.", 404),
    );
    render(<IncidentDetailPage incidentId="unknown" />);

    expect(
      await screen.findByText("No incident found."),
    ).toBeInTheDocument();
  });

  it("offers only Acknowledge on an OPEN incident, and transitions on click", async () => {
    const user = userEvent.setup();
    mocks.getSafetyIncident.mockResolvedValue(OPEN_INCIDENT);
    mocks.acknowledgeSafetyIncident.mockResolvedValue({
      ...OPEN_INCIDENT,
      status: "ACKNOWLEDGED",
    });
    render(<IncidentDetailPage incidentId="incident-1" />);

    await screen.findByRole("button", { name: "Acknowledge" });
    expect(
      screen.queryByRole("button", { name: "Escalate" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resolve" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Acknowledge" }));

    expect(mocks.acknowledgeSafetyIncident).toHaveBeenCalledWith("incident-1");
    expect(
      await screen.findByText("Incident acknowledged."),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Escalate" }),
    ).toBeInTheDocument();
  });

  it("resolves an IN_PROGRESS incident", async () => {
    const user = userEvent.setup();
    mocks.getSafetyIncident.mockResolvedValue({
      ...OPEN_INCIDENT,
      status: "IN_PROGRESS",
    });
    mocks.resolveSafetyIncident.mockResolvedValue({
      ...OPEN_INCIDENT,
      status: "RESOLVED",
    });
    render(<IncidentDetailPage incidentId="incident-1" />);

    await user.click(await screen.findByRole("button", { name: "Resolve" }));

    expect(mocks.resolveSafetyIncident).toHaveBeenCalledWith("incident-1");
    expect(await screen.findByText("Incident resolved.")).toBeInTheDocument();
  });
});
