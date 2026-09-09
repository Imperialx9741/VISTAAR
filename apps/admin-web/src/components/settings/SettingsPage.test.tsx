import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingsPage } from "./SettingsPage";
import { ApiError } from "@/lib/api/client";
import type { AdminProfile, Setting } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  listSettings: vi.fn(),
  updateSetting: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/settings", () => ({
  listSettings: mocks.listSettings,
  updateSetting: mocks.updateSetting,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const SETTING: Setting = {
  key: "welcome_discount_percent",
  value: 50,
  category: "PROMOTION_DEFAULT",
  description: "Discount percent applied to the welcome promotion.",
  updated_by: "admin-1",
  updated_at: "2026-08-10T00:00:00Z",
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("SettingsPage", () => {
  it("shows a loading state, then the settings list and dedicated-screen links", async () => {
    mocks.listSettings.mockResolvedValue([SETTING]);
    render(<SettingsPage />);

    expect(screen.getByText(/Loading Settings/)).toBeInTheDocument();
    expect(
      await screen.findByRole("cell", { name: "welcome_discount_percent" }),
    ).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Fare settings.*Fare Management/ }),
    ).toHaveAttribute("href", "/fare-management");
    expect(
      screen.getByRole("link", {
        name: /Notification settings.*Notification Templates/,
      }),
    ).toHaveAttribute("href", "/notifications/templates");
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.listSettings.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<SettingsPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Settings.",
      ),
    ).toBeInTheDocument();
  });

  it("edits a setting's value and saves it", async () => {
    const user = userEvent.setup();
    mocks.listSettings.mockResolvedValue([SETTING]);
    mocks.updateSetting.mockResolvedValue({ ...SETTING, value: 60 });
    render(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const textarea = screen.getByLabelText("Value for welcome_discount_percent");
    await user.clear(textarea);
    await user.type(textarea, "60");

    mocks.listSettings.mockResolvedValueOnce([{ ...SETTING, value: 60 }]);
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(mocks.updateSetting).toHaveBeenCalledWith(
      "welcome_discount_percent",
      60,
    );
    expect(
      await screen.findByText("welcome_discount_percent updated."),
    ).toBeInTheDocument();
  });

  it("shows a validation error instead of saving on invalid JSON", async () => {
    const user = userEvent.setup();
    mocks.listSettings.mockResolvedValue([SETTING]);
    render(<SettingsPage />);

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const textarea = screen.getByLabelText("Value for welcome_discount_percent");
    await user.clear(textarea);
    await user.type(textarea, "not valid json at all");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(
        "That's not valid JSON — check the value and try again.",
      ),
    ).toBeInTheDocument();
    expect(mocks.updateSetting).not.toHaveBeenCalled();
  });

  it("re-queries when the category filter changes", async () => {
    const user = userEvent.setup();
    mocks.listSettings.mockResolvedValue([SETTING]);
    render(<SettingsPage />);
    await screen.findByRole("cell", { name: "welcome_discount_percent" });

    await user.selectOptions(
      screen.getByLabelText("Filter by category"),
      "FEATURE_FLAG",
    );

    expect(mocks.listSettings).toHaveBeenLastCalledWith("FEATURE_FLAG");
  });
});
