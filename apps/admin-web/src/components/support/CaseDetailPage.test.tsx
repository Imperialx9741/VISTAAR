import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CaseDetailPage } from "./CaseDetailPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, SupportCaseDetail } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getSupportCase: vi.fn(),
  resolveSupportCase: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/support/case-1",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/safety-support", () => ({
  getSupportCase: mocks.getSupportCase,
  resolveSupportCase: mocks.resolveSupportCase,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const OPEN_CASE: SupportCaseDetail = {
  case_id: "case-1",
  user_id: "customer-1",
  ride_id: null,
  category: "BILLING",
  priority: "NORMAL",
  status: "OPEN",
  assigned_admin_id: null,
  created_at: "2026-08-10T00:00:00Z",
  updated_at: "2026-08-10T00:00:00Z",
  messages: [
    {
      message_id: "msg-1",
      sender_type: "CUSTOMER",
      sender_id: "customer-1",
      message: "My ride overcharged me.",
      created_at: "2026-08-10T00:05:00Z",
    },
  ],
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("CaseDetailPage", () => {
  it("loads and shows the case's fields and conversation", async () => {
    mocks.getSupportCase.mockResolvedValue(OPEN_CASE);
    render(<CaseDetailPage caseId="case-1" />);

    expect(await screen.findByText("BILLING")).toBeInTheDocument();
    expect(
      screen.getByText("My ride overcharged me."),
    ).toBeInTheDocument();
    expect(screen.getByText("CUSTOMER")).toBeInTheDocument();
  });

  it("shows a real error banner when the load fails", async () => {
    mocks.getSupportCase.mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "No case found.", 404),
    );
    render(<CaseDetailPage caseId="unknown" />);

    expect(await screen.findByText("No case found.")).toBeInTheDocument();
  });

  it("resolves an open case", async () => {
    const user = userEvent.setup();
    mocks.getSupportCase.mockResolvedValue(OPEN_CASE);
    mocks.resolveSupportCase.mockResolvedValue({
      ...OPEN_CASE,
      status: "RESOLVED",
    });
    render(<CaseDetailPage caseId="case-1" />);

    await user.click(
      await screen.findByRole("button", { name: "Resolve case" }),
    );

    expect(mocks.resolveSupportCase).toHaveBeenCalledWith("case-1");
    expect(await screen.findByText("Case resolved.")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resolve case" }),
    ).not.toBeInTheDocument();
  });

  it("hides Resolve on an already-CLOSED case", async () => {
    mocks.getSupportCase.mockResolvedValue({
      ...OPEN_CASE,
      status: "CLOSED",
    });
    render(<CaseDetailPage caseId="case-1" />);

    await screen.findByText("BILLING");
    expect(
      screen.queryByRole("button", { name: "Resolve case" }),
    ).not.toBeInTheDocument();
  });

  it("shows an empty-conversation message when there are no messages", async () => {
    mocks.getSupportCase.mockResolvedValue({ ...OPEN_CASE, messages: [] });
    render(<CaseDetailPage caseId="case-1" />);

    expect(await screen.findByText("No messages yet.")).toBeInTheDocument();
  });
});
