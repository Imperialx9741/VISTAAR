import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TemplatesPage } from "./TemplatesPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, NotificationTemplate } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  listTemplates: vi.fn(),
  createTemplate: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/notifications/templates",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/notifications", () => ({
  listTemplates: mocks.listTemplates,
  createTemplate: mocks.createTemplate,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const TEMPLATE: NotificationTemplate = {
  template_id: "template-1",
  template_key: "RIDE_ACCEPTED",
  channel: "SMS",
  event_key: "ride.accepted",
  title: null,
  body: "Your ride has been accepted.",
  version: 1,
  status: "DRAFT",
  created_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("TemplatesPage", () => {
  it("shows a loading state, then the template list", async () => {
    mocks.listTemplates.mockResolvedValue({
      items: [TEMPLATE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<TemplatesPage />);

    expect(screen.getByText(/Loading Notifications/)).toBeInTheDocument();
    expect(await screen.findByText("RIDE_ACCEPTED")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.listTemplates.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<TemplatesPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Notifications.",
      ),
    ).toBeInTheDocument();
  });

  it("creates a DRAFT template and refreshes the list", async () => {
    const user = userEvent.setup();
    mocks.listTemplates.mockResolvedValue({
      items: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    });
    mocks.createTemplate.mockResolvedValue(TEMPLATE);

    render(<TemplatesPage />);
    await screen.findByText("No templates found.");

    await user.click(
      screen.getByRole("button", { name: "+ Create template" }),
    );
    await user.type(screen.getByLabelText("Template key"), "RIDE_ACCEPTED");
    await user.type(
      screen.getByLabelText("Body"),
      "Your ride has been accepted.",
    );

    mocks.listTemplates.mockResolvedValueOnce({
      items: [TEMPLATE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });

    await user.click(screen.getByRole("button", { name: "Create draft" }));

    expect(mocks.createTemplate).toHaveBeenCalledWith({
      template_key: "RIDE_ACCEPTED",
      channel: "SMS",
      event_key: null,
      title: null,
      body: "Your ride has been accepted.",
    });
    expect(
      await screen.findByText(/Created RIDE_ACCEPTED \(SMS\) v1, DRAFT\./),
    ).toBeInTheDocument();
  });
});
