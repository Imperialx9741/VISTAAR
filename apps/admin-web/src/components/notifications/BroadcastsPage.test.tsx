import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BroadcastsPage } from "./BroadcastsPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Broadcast } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchBroadcasts: vi.fn(),
  createBroadcast: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/notifications/broadcasts",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/notifications", () => ({
  searchBroadcasts: mocks.searchBroadcasts,
  createBroadcast: mocks.createBroadcast,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const BROADCAST: Broadcast = {
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

describe("BroadcastsPage", () => {
  it("shows a loading state, then the broadcast list", async () => {
    mocks.searchBroadcasts.mockResolvedValue({
      items: [BROADCAST],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<BroadcastsPage />);

    expect(screen.getByText(/Loading Notifications/)).toBeInTheDocument();
    expect(await screen.findByText("Maintenance notice")).toBeInTheDocument();
    expect(screen.getByText("42 / 1")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchBroadcasts.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<BroadcastsPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Notifications.",
      ),
    ).toBeInTheDocument();
  });

  it("composes and sends a broadcast immediately, then refreshes the list", async () => {
    const user = userEvent.setup();
    mocks.searchBroadcasts.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    mocks.createBroadcast.mockResolvedValue(BROADCAST);

    render(<BroadcastsPage />);
    await screen.findByText("No broadcasts found.");

    await user.click(
      screen.getByRole("button", { name: "+ Compose broadcast" }),
    );
    await user.type(
      screen.getByLabelText("Message"),
      "VISTAAR will be briefly unavailable tonight.",
    );

    mocks.searchBroadcasts.mockResolvedValueOnce({
      items: [BROADCAST],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });

    await user.click(screen.getByRole("button", { name: "Send now" }));

    expect(mocks.createBroadcast).toHaveBeenCalledWith({
      channel: "IN_APP",
      subject: null,
      body: "VISTAAR will be briefly unavailable tonight.",
      audience_type: "ALL_CUSTOMERS",
      audience_user_ids: null,
      scheduled_at: null,
    });
    expect(
      await screen.findByText("Sent to 42 recipients (1 failed)."),
    ).toBeInTheDocument();
  });

  it("requires at least one recipient id for a SELECTED audience", async () => {
    const user = userEvent.setup();
    mocks.searchBroadcasts.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    render(<BroadcastsPage />);
    await screen.findByText("No broadcasts found.");

    await user.click(
      screen.getByRole("button", { name: "+ Compose broadcast" }),
    );
    await user.type(screen.getByLabelText("Message"), "Hello");
    await user.selectOptions(
      screen.getByLabelText("Audience"),
      "SELECTED",
    );

    expect(screen.getByRole("button", { name: "Send now" })).toBeDisabled();

    await user.type(
      screen.getByLabelText("Recipient user IDs"),
      "customer-1\ncustomer-2",
    );

    expect(screen.getByRole("button", { name: "Send now" })).toBeEnabled();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.searchBroadcasts.mockResolvedValue({
      items: [BROADCAST],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<BroadcastsPage />);
    await screen.findByText("Maintenance notice");

    await user.selectOptions(
      screen.getByLabelText("Filter by status"),
      "SCHEDULED",
    );

    expect(mocks.searchBroadcasts).toHaveBeenLastCalledWith(
      "SCHEDULED",
      1,
      20,
    );
  });
});
