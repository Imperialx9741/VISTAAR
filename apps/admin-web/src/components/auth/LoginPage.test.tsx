import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginPage } from "./LoginPage";
import { ApiError } from "@/lib/api/client";

const mocks = vi.hoisted(() => ({
  requestAdminOtp: vi.fn(),
  verifyAdminOtp: vi.fn(),
  verifyAdminMfa: vi.fn(),
  setAdminSession: vi.fn(),
}));

vi.mock("@/lib/api/auth", () => ({
  requestAdminOtp: mocks.requestAdminOtp,
  verifyAdminOtp: mocks.verifyAdminOtp,
  verifyAdminMfa: mocks.verifyAdminMfa,
}));

vi.mock("@/lib/api/session", () => ({
  setAdminSession: mocks.setAdminSession,
}));

describe("LoginPage", () => {
  it("rejects a short phone number without calling the API", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Mobile number"), "123");
    await user.click(screen.getByRole("button", { name: "Send code" }));

    expect(
      await screen.findByText("Enter a valid 10-digit mobile number."),
    ).toBeInTheDocument();
    expect(mocks.requestAdminOtp).not.toHaveBeenCalled();
  });

  it("requests a code, verifies it, and establishes a session when no MFA is required", async () => {
    const user = userEvent.setup();
    mocks.requestAdminOtp.mockResolvedValue({
      challengeId: "challenge-1",
      expiresIn: 300,
    });
    mocks.verifyAdminOtp.mockResolvedValue({
      mfaRequired: false,
      tokens: {
        accessToken: "access-1",
        refreshToken: "refresh-1",
        expiresIn: 3600,
      },
    });
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Mobile number"), "9876543210");
    await user.click(screen.getByRole("button", { name: "Send code" }));

    expect(await screen.findByText("Sent to +919876543210.")).toBeInTheDocument();
    expect(mocks.requestAdminOtp).toHaveBeenCalledWith("+919876543210");

    await user.type(screen.getByLabelText("One-time code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() => {
      expect(mocks.verifyAdminOtp).toHaveBeenCalledWith("challenge-1", "123456");
    });
    await waitFor(() => {
      expect(mocks.setAdminSession).toHaveBeenCalledWith({
        accessToken: "access-1",
        refreshToken: "refresh-1",
      });
    });
  });

  it("shows the MFA step when the backend requires a second factor", async () => {
    const user = userEvent.setup();
    mocks.requestAdminOtp.mockResolvedValue({
      challengeId: "challenge-1",
      expiresIn: 300,
    });
    mocks.verifyAdminOtp.mockResolvedValue({
      mfaRequired: true,
      mfa: { mfaToken: "mfa-token-1", expiresIn: 300 },
    });
    mocks.verifyAdminMfa.mockResolvedValue({
      accessToken: "access-2",
      refreshToken: "refresh-2",
      expiresIn: 3600,
    });
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Mobile number"), "9876543210");
    await user.click(screen.getByRole("button", { name: "Send code" }));
    await user.type(await screen.findByLabelText("One-time code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify" }));

    expect(
      await screen.findByText(
        "Enter the 6-digit code from your authenticator app.",
      ),
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText("Authenticator code"), "654321");
    await user.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() => {
      expect(mocks.verifyAdminMfa).toHaveBeenCalledWith("mfa-token-1", "654321");
    });
    await waitFor(() => {
      expect(mocks.setAdminSession).toHaveBeenCalledWith({
        accessToken: "access-2",
        refreshToken: "refresh-2",
      });
    });
  });

  it("shows the backend's own error message when requesting a code fails", async () => {
    const user = userEvent.setup();
    mocks.requestAdminOtp.mockRejectedValue(
      new ApiError("RATE_LIMITED", "Too many attempts. Try again later.", 429),
    );
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Mobile number"), "9876543210");
    await user.click(screen.getByRole("button", { name: "Send code" }));

    expect(
      await screen.findByText("Too many attempts. Try again later."),
    ).toBeInTheDocument();
  });
});
