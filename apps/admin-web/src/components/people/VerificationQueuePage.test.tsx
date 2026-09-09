import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VerificationQueuePage } from "./VerificationQueuePage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, VerificationCase } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  searchVerificationQueue: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/verification",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/people", () => ({
  searchVerificationQueue: mocks.searchVerificationQueue,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const CASE: VerificationCase = {
  case_id: "case-1",
  subject_type: "DRIVER_DOCUMENT",
  subject_id: "doc-1",
  verification_type: "DRIVER_DOCUMENT",
  status: "PENDING",
  created_at: "2026-08-10T00:00:00Z",
  completed_at: null,
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("VerificationQueuePage", () => {
  it("defaults to the PENDING filter and shows the queue", async () => {
    mocks.searchVerificationQueue.mockResolvedValue({
      items: [CASE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<VerificationQueuePage />);

    expect(mocks.searchVerificationQueue).toHaveBeenCalledWith(
      "PENDING",
      1,
      20,
    );
    // "DRIVER_DOCUMENT" appears in both the Subject and Type columns —
    // the Type cell's accessible name is the bare value, unlike Subject
    // (which also concatenates the subject_id), so this is unambiguous.
    expect(
      await screen.findByRole("cell", { name: "DRIVER_DOCUMENT" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "Filter by case status" }),
    ).toHaveValue("PENDING");
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.searchVerificationQueue.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<VerificationQueuePage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Verification.",
      ),
    ).toBeInTheDocument();
  });

  it("re-queries when the status filter changes", async () => {
    const user = userEvent.setup();
    mocks.searchVerificationQueue.mockResolvedValue({
      items: [CASE],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    render(<VerificationQueuePage />);
    await screen.findByRole("cell", { name: "DRIVER_DOCUMENT" });

    await user.selectOptions(
      screen.getByLabelText("Filter by case status"),
      "APPROVED",
    );

    expect(mocks.searchVerificationQueue).toHaveBeenLastCalledWith(
      "APPROVED",
      1,
      20,
    );
  });
});
