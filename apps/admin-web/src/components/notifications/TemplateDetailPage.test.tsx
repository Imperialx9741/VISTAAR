import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TemplateDetailPage } from "./TemplateDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, NotificationTemplate } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getTemplate: vi.fn(),
  publishTemplate: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/notifications/templates/template-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/notifications", () => ({
  getTemplate: mocks.getTemplate,
  publishTemplate: mocks.publishTemplate,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const DRAFT_TEMPLATE: NotificationTemplate = {
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

describe("TemplateDetailPage", () => {
  it("loads and shows the template's fields and body", async () => {
    mocks.getTemplate.mockResolvedValue(DRAFT_TEMPLATE);
    render(<TemplateDetailPage templateId="template-1" />);

    expect(await screen.findByText("RIDE_ACCEPTED")).toBeInTheDocument();
    expect(
      screen.getByText("Your ride has been accepted."),
    ).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getTemplate.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No template found.", 404),
    );
    render(<TemplateDetailPage templateId="unknown" />);

    expect(
      await screen.findByText("No template found."),
    ).toBeInTheDocument();
  });

  it("publishes a DRAFT template", async () => {
    const user = userEvent.setup();
    mocks.getTemplate.mockResolvedValue(DRAFT_TEMPLATE);
    mocks.publishTemplate.mockResolvedValue({
      ...DRAFT_TEMPLATE,
      status: "PUBLISHED",
    });
    render(<TemplateDetailPage templateId="template-1" />);

    await user.click(await screen.findByRole("button", { name: "Publish" }));

    expect(mocks.publishTemplate).toHaveBeenCalledWith("template-1");
    expect(
      await screen.findByText("Template published."),
    ).toBeInTheDocument();
  });

  it("hides Publish once a template is already PUBLISHED", async () => {
    mocks.getTemplate.mockResolvedValue({
      ...DRAFT_TEMPLATE,
      status: "PUBLISHED",
    });
    render(<TemplateDetailPage templateId="template-1" />);

    await screen.findByText("RIDE_ACCEPTED");
    expect(
      screen.queryByRole("button", { name: "Publish" }),
    ).not.toBeInTheDocument();
  });
});
