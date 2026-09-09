import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DeliveryHistoryPage } from "./DeliveryHistoryPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Delivery } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchDeliveries: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/notifications",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/notifications", () => ({
  searchDeliveries: mocks.searchDeliveries,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const DELIVERY: Delivery = {
  delivery_id: "delivery-1",
  user_id: "customer-1",
  channel: "SMS",
  template_key: "RIDE_ACCEPTED",
  event_id: null,
  status: "SENT",
  provider_reference: null,
  created_at: "2026-08-10T00:00:00Z",
  delivered_at: "2026-08-10T00:00:01Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("DeliveryHistoryPage", () => {
  it("shows a loading state, then the delivery list", async () => {
    mocks.searchDeliveries.mockResolvedValue({
      items: [DELIVERY],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<DeliveryHistoryPage />);

    expect(screen.getByText(/Loading Notifications/)).toBeInTheDocument();
    expect(await screen.findByText("customer-1")).toBeInTheDocument();
    expect(screen.getByText("RIDE_ACCEPTED")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchDeliveries.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<DeliveryHistoryPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Notifications.",
      ),
    ).toBeInTheDocument();
  });

  it("re-queries when the channel filter changes", async () => {
    const user = userEvent.setup();
    mocks.searchDeliveries.mockResolvedValue({
      items: [DELIVERY],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<DeliveryHistoryPage />);
    await screen.findByText("customer-1");

    await user.selectOptions(
      screen.getByLabelText("Filter by channel"),
      "PUSH",
    );

    expect(mocks.searchDeliveries).toHaveBeenLastCalledWith("PUSH", "", 1, 20);
  });

  it("links to the Templates and Broadcasts screens", async () => {
    mocks.searchDeliveries.mockResolvedValue({
      items: [DELIVERY],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<DeliveryHistoryPage />);
    await screen.findByText("customer-1");

    expect(
      screen.getByRole("link", { name: "Manage templates →" }),
    ).toHaveAttribute("href", "/notifications/templates");
    expect(
      screen.getByRole("link", { name: "Broadcasts →" }),
    ).toHaveAttribute("href", "/notifications/broadcasts");
  });
});
