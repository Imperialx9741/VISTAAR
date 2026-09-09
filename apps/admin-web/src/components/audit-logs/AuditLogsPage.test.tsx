import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuditLogsPage } from "./AuditLogsPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, AuditLogEntry } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchAuditLogs: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/audit-logs",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/audit-logs", () => ({
  searchAuditLogs: mocks.searchAuditLogs,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const ENTRY: AuditLogEntry = {
  id: 5001,
  admin_id: "admin-1",
  action: "APPROVE_DRIVER",
  target_type: "DRIVER",
  target_id: "driver-1",
  reason: null,
  before_state: { verification_status: "PENDING" },
  after_state: { verification_status: "APPROVED" },
  request_id: "req-1",
  created_at: "2026-08-28T10:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("AuditLogsPage", () => {
  it("loads with no filters applied and shows the entries", async () => {
    mocks.searchAuditLogs.mockResolvedValue({
      items: [ENTRY],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<AuditLogsPage />);

    expect(screen.getByText(/Loading Audit Logs/)).toBeInTheDocument();
    expect(await screen.findByText("APPROVE_DRIVER")).toBeInTheDocument();
    expect(mocks.searchAuditLogs).toHaveBeenCalledWith(
      {
        adminId: "",
        targetType: "",
        targetId: "",
        action: "",
        createdAfter: "",
        createdBefore: "",
      },
      1,
      20,
    );
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchAuditLogs.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<AuditLogsPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Audit Logs.",
      ),
    ).toBeInTheDocument();
  });

  it("searches with the entered filters, widening dates to a day boundary", async () => {
    const user = userEvent.setup();
    mocks.searchAuditLogs.mockResolvedValue({
      items: [ENTRY],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<AuditLogsPage />);
    await screen.findByText("APPROVE_DRIVER");

    await user.type(screen.getByLabelText("Filter by admin ID"), "admin-1");
    await user.type(
      screen.getByLabelText("Filter by action"),
      "APPROVE_DRIVER",
    );
    await user.type(screen.getByLabelText("From date"), "2026-08-01");
    await user.type(screen.getByLabelText("To date"), "2026-08-28");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(mocks.searchAuditLogs).toHaveBeenLastCalledWith(
      {
        adminId: "admin-1",
        targetType: "",
        targetId: "",
        action: "APPROVE_DRIVER",
        createdAfter: "2026-08-01T00:00:00.000Z",
        createdBefore: "2026-08-28T23:59:59.999Z",
      },
      1,
      20,
    );
  });

  it("clears filters and re-searches", async () => {
    const user = userEvent.setup();
    mocks.searchAuditLogs.mockResolvedValue({
      items: [ENTRY],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<AuditLogsPage />);
    await screen.findByText("APPROVE_DRIVER");

    await user.type(screen.getByLabelText("Filter by admin ID"), "admin-1");
    await user.click(screen.getByRole("button", { name: "Clear" }));

    expect(screen.getByLabelText("Filter by admin ID")).toHaveValue("");
    expect(mocks.searchAuditLogs).toHaveBeenLastCalledWith(
      {
        adminId: "",
        targetType: "",
        targetId: "",
        action: "",
        createdAfter: "",
        createdBefore: "",
      },
      1,
      20,
    );
  });
});
