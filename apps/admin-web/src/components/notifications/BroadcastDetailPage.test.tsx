import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { BroadcastDetailPage } from "./BroadcastDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Broadcast } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getBroadcast: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/notifications/broadcasts/broadcast-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/notifications", () => ({
  getBroadcast: mocks.getBroadcast,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const SENT_BROADCAST: Broadcast = {
  broadcast_id: "broadcast-1",
  channel: "IN_APP",
  subject: "Maintenance notice",
  body: "VISTAAR will be briefly unavailable tonight.",
  audience_type: "ALL_CUSTOMERS",
  audience_user_ids: null,
  status: "SENT",
  scheduled_at: null,
  sent_count: 42,
  failed_count: 1,
  created_by: "admin-1",
  created_at: "2026-08-29T00:00:00Z",
  sent_at: "2026-08-29T00:01:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("BroadcastDetailPage", () => {
  it("loads and shows the broadcast's fields", async () => {
    mocks.getBroadcast.mockResolvedValue(SENT_BROADCAST);
    render(<BroadcastDetailPage broadcastId="broadcast-1" />);

    expect(await screen.findByText("Maintenance notice")).toBeInTheDocument();
    expect(
      screen.getByText("VISTAAR will be briefly unavailable tonight."),
    ).toBeInTheDocument();
    expect(screen.getByText("42 / 1")).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getBroadcast.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "Broadcast not found.", 404),
    );
    render(<BroadcastDetailPage broadcastId="unknown" />);

    expect(
      await screen.findByText("Broadcast not found."),
    ).toBeInTheDocument();
  });

  it("shows the scheduled time for a still-SCHEDULED broadcast", async () => {
    mocks.getBroadcast.mockResolvedValue({
      ...SENT_BROADCAST,
      status: "SCHEDULED",
      sent_count: 0,
      failed_count: 0,
      sent_at: null,
      scheduled_at: "2026-09-01T10:00:00Z",
    });
    render(<BroadcastDetailPage broadcastId="broadcast-1" />);

    await screen.findByText("Maintenance notice");
    expect(screen.getByText("Scheduled for")).toBeInTheDocument();
  });
});
